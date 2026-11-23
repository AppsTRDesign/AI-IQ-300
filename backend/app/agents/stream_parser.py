"""Splits a model's streamed text into visible text, hidden thinking and tool calls, so tool payloads never leak
into the chat. Besides our own tag protocol it recognizes the textual tool-call formats local models emit when the
server does not convert them into native tool calls:

  <tool name="write_file" path="a.py">...</tool>                                   (AI IQ 300 tag protocol)
  <function=write_file><parameter=path>a.py</parameter>...</function>             (Qwen3-Coder XML)
  <tool_call>{"name": "write_file", "arguments": {...}}</tool_call>               (Hermes / Qwen JSON)
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

# opener -> closer; longer/more specific openers first
DSML = "｜DSML｜"  # DeepSeek's markup: <｜DSML｜invoke name="x"><｜DSML｜parameter name="k" string="true">v</｜DSML｜parameter>
TAGS = [(f"<{DSML}invoke ", f"</{DSML}invoke>"),
        ("<tool_call>", "</tool_call>"), ("<function=", "</function>"), ("<tools ", "</tools>"), ("<tools=", "</tools>"),
        ("<tool=", "</tool>"), ("<tool ", "</tool>"), ("<tool>", "</tool>"),
        ("<think>", "</think>"), ("<thinking>", "</thinking>"), ("<reasoning>", "</reasoning>"),
        ("<|channel|>analysis<|message|>", "<|end|>"),  # gpt-oss (harmony) reasoning channel
        ("<|channel|>commentary to=", "<|call|>"),  # gpt-oss (harmony) tool call written as text
        ("<|tool_call_begin|>", "<|tool_call_end|>"),  # Kimi K2: functions.NAME:0<|tool_call_argument_begin|>{json}
        ('<invoke name="', "</invoke>")]  # MiniMax M2: <invoke name="x"><parameter name="k">v</parameter></invoke>
HARMONY_RUN = re.compile(r"(?:<\|\w+\|>[\w .=]*)*(?:<\|?\w*\|?)?")  # complete or partial control-token run
THINK_OPENERS = {"<think>", "<thinking>", "<reasoning>", "<|channel|>analysis<|message|>"}
# Closing tags without an opener, and harmony control tokens around the final answer: never shown.
# Also the pieces of other call formats that a model leaves around its text (seen in notes: "...doğruluyorum.
# </parameter>", a note that was only "</tool>", DeepSeek's <｜DSML｜function_calls> wrapper).
STRAY = re.compile(r"<system>[^<\n]{0,60}</system>|</?system>|</?tool_call>|</function>|<\|start\|>assistant|<\|channel\|>\w+(?: to=[\w.]+)?"
                   r"(?:\s*<\|constrain\|>\w+)?<\|message\|>|<\|(?:end|return|start|call)\|>"
                   r"|</parameter>|<parameter=[\w.-]+>|</tools?>|</?arg_(?:key|value)>|</?invoke\b[^>\n]{0,80}>"
                   r"|</?｜DSML｜[\w]*[^>\n]{0,80}>|<｜[\w▁ ]{1,40}｜>"
                   # Kimi K2 section markers, MiniMax's wrapper, Llama 3's python tag / end-of-message tokens
                   r"|<\|tool_calls_section_(?:begin|end)\|>|</?[\w-]+:tool_calls?>|<\|python_tag\|>|<\|e[om]t?_id\|>"
                   # Chat-template tokens of other families left in the text (Nemotron: "<|close|>think<|sep|>
                   # <|close|>message<|sep|>" at the end of a note), with the role word the token names
                   r"|<\|(?:close|sep|open|im_start|im_end|im_sep|eot|eos|bos|endoftext|end_of_turn|start_of_turn)\|>"
                   r"(?:think|message|assistant|user|system|model)?")
# A reasoning closer with no opener: the template opened the block in the prompt (DeepSeek-R1 / QwQ style), so
# everything shown before it was reasoning.
LONE_CLOSE = re.compile(r"</(?:think|thinking|reasoning)>")
# key="value" or key='value' (models copy the args='[...]' style of the examples; single-quoted values were
# dropped, so a call like mcp arguments='{...}' reached the tool with no arguments at all)
# A JSON list written without quotes (argv=["git","log","-3"], seen live) is taken as well: dropped, run got no
# command at all.
# A JSON object the same way (arguments={"owner": "x"}): runs to the last brace on the line.
ATTR = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\[[^\]\n<>]*\])|(\{[^\n<>]*\}))')


def attrs(text: str) -> dict:
    return {k: html.unescape(a or b or c or d) for k, a, b, c, d in ATTR.findall(text or "")}


# Arguments that hold a whole file, an edit or a command. Weak models put them into the opening tag as an attribute
# (<tool name="write_file" path="a.js" content="...">) instead of between the tags. Such a value holds quotes and
# '>' of its own (SVG, HTML, arrow functions): read like a short attribute it ended at the first quote, the rest
# became the body, and every write of app.js stopped at  cart: '<svg viewBox=  (seen live, a dozen times in a row).
BIG_ATTRS = ("content", "edits", "command", "code", "old", "new", "items", "text", "body", "patch", "diff",
             "old_string", "new_string", "search", "replace", "script", "html", "markdown", "query")
_BIG_OPEN = re.compile(r'^<([\w.-]+)((?:\s+[\w.-]+\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'))*)\s+(' + "|".join(BIG_ATTRS)
                       + r')\s*=\s*(["\'])', re.S)
_TAIL_ATTR = re.compile(r'\s+([\w.-]+)\s*=\s*(?:"([^"\n]{0,300})"|\'([^\'\n]{0,300})\')\s*$')
_PAIR_SPLIT = re.compile(r'(["\'])\s+(new|new_string|replace|replacement|updated|after)\s*=\s*(["\'])', re.S)


def _unescape_big(value: str, quote: str) -> str:
    """A value written with JSON-style escapes (one long line with \\n in it) becomes real text again."""
    if "\n" not in value and ("\\n" in value or "\\t" in value):
        value = (value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
                 .replace("\\" + quote, quote).replace("\\\\", "\\"))
    elif quote == '"' and '"' not in value and "&quot;" in value:
        value = value.replace("&quot;", '"')
    return value


# An opening tag whose short attributes all closed on one line, followed (only whitespace between) by the next call:
# the model never wrote </tool> for the first one. Read as one block, the first call's last attribute ran to the end of
# the second (research query="Kozan hava durumu\">\n<tool name=\"todo" was searched on the web, seen live).
# A value may also be a bare JSON list or object on the same line: <tool name="run" argv=["git", "init"]> followed by
# the next call swallowed every later call of the reply into the first one's body, unrun (nemotron-3-ultra on NVIDIA:
# no .gitignore, no commit, 20 turns spent finding out why).
_OPEN_LINE = re.compile(r'<tools?\s+name\s*=\s*"[\w.-]+"'
                        r'(?:\s+[\w.-]+\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'|\[[^\]\n]*\]|\{[^\n]*?\}(?=[\s/>])))*\s*/?>')
_NEXT_CALL = re.compile(r'\s*<tools?\s+name\s*=\s*"[\w.-]+"')
_SHORT_BIG = ("query", "code", "command", "script", "search", "items")


def split_unclosed(block: str) -> tuple[str, str] | None:
    """(first call closed, the rest) when `block` is two calls, the first one left without its closing tag."""
    m = _OPEN_LINE.match(block)
    if not m or not _NEXT_CALL.match(block, m.end()):
        return None
    opening = block[:m.end()]
    return (opening if opening.endswith("/>") else opening + "</tool>"), block[m.end():].lstrip()


def big_attr_call(raw: str) -> tuple[str, dict, str] | None:
    """(tag, args, body) of a tag whose big argument (content=, command=, old=/new= ...) was written as an attribute.
    The value runs to the last quote before the tag's end; short attributes after it (append="true") are kept."""
    m = _BIG_OPEN.match(raw.strip())
    if not m:
        return None
    tag, before, key, quote = m.group(1), m.group(2), m.group(3), m.group(4)
    rest = raw.strip()[m.end():]
    if rest.startswith(quote):
        return None  # content="" and the text between the tags: the ordinary parse is right
    body = ""
    rest = re.sub(r"\s*</(?:%s|tool|tools)>\s*$" % re.escape(tag), "", rest)
    # A real body after the opening tag (content="..." and then the file between the tags as well): the body wins
    # unless it is empty; the attribute value ends at the quote right before that '>'.
    tail: dict = {}
    if rest.rstrip().endswith("/>"):
        rest = rest.rstrip()[:-2]
    elif rest.rstrip().endswith(">"):
        rest = rest.rstrip()[:-1]
    else:
        close = rest.rfind(quote + ">")
        if close < 0:
            return None
        rest, body = rest[:close + 1], rest[close + 2:]
    while (t := _TAIL_ATTR.search(rest)) and t.start() > 0:
        # peel short attributes written after the big one (append="true"); a value of the big one itself that looks
        # like one (fill="none" at the very end of an SVG) cannot be told apart and stays only if nothing else fits
        if not rest[:t.start()].rstrip().endswith(quote):
            break
        tail[t.group(1)] = t.group(2) if t.group(2) is not None else t.group(3)
        rest = rest[:t.start()]
    rest = rest.rstrip()
    if not rest.endswith(quote):
        return None
    value = rest[:-1]
    args = attrs(before)
    args.update({k: html.unescape(v) for k, v in tail.items()})
    if key in ("old", "old_string", "search") and (p := list(_PAIR_SPLIT.finditer(value))):
        # old="..." new="...": both are big; the last  " new="  splits them
        cut = p[-1]
        args[key] = _unescape_big(value[:cut.start()], quote)
        args[cut.group(2)] = _unescape_big(value[cut.end():], cut.group(3))
    else:
        if key in _SHORT_BIG and (nxt := re.search(r'["\']?\s*/?>?\s*<tools?\s+name\s*=\s*"', value)):
            # a search / script value that ran into the next call's tag: only what came before it is the value
            value = value[:nxt.start()].rstrip()
        args[key] = _unescape_big(value, quote)
    return tag, args, body
MAX_OPEN = max(len(o) for o, _ in TAGS)
CLOSERS = ("</tool_call>", "</function>", "</think>", "</thinking>", "</reasoning>")
STRAY_HEADS = ("</parameter>", "<parameter=", "</tool>", "</tools>", f"<{DSML}", f"</{DSML}", "</arg_", "<arg_",
               "</invoke", "<invoke", "<｜", "</minimax", "<minimax")
# Any short tag-shaped tail ("</minimax:", "<|tool_ca"): a vendor's call wrapper split between two chunks went to
# the chat in halves, STRAY never saw it whole (a note that was only "</minimax:tool_call>", nemotron on NVIDIA).
TAG_TAIL = re.compile(r"</?[A-Za-z_][\w:.|-]{0,40}$|<\|[\w|]{0,24}$|<\|\w{1,24}\|>\w{0,10}$")


@dataclass
class ToolCall:
    name: str
    args: dict
    body: str
    arguments: dict | None = None  # set for JSON/XML formats: full argument dict (split by the registry)


def _xml_function(raw: str) -> ToolCall | None:
    m = re.search(r"<function=([\w.-]+)>(.*?)(?:</function>|$)", raw, re.S)
    if not m:
        return None
    params = {k: v[1:] if v.startswith("\n") else v for k, v in
              re.findall(r"<parameter=([\w.-]+)>(.*?)</parameter>", m.group(2), re.S)}
    params = {k: v[:-1] if v.endswith("\n") else v for k, v in params.items()}
    return ToolCall(m.group(1), {}, "", params)


def _normalize(raw: str) -> str:
    """Variants weak models write for our tag: <tools ="x">, <tool="x">, <tools name="x">...</tools>."""
    raw = re.sub(r'^<tools?\s*=\s*["\']?([\w.-]+)["\']?(?=[\s>/])', r'<tool name="\1"', raw)
    raw = re.sub(r"^<tools\b", "<tool", raw)
    return re.sub(r"</tools>\s*$", "</tool>", raw)


def _dsml(raw: str) -> ToolCall | None:
    m = re.match(r'<｜DSML｜invoke\s+name\s*=\s*"([\w.-]+)"\s*>(.*?)(?:</｜DSML｜invoke>)?\s*$', raw, re.S)
    if not m:
        return None
    params = {}
    for k, s, v in re.findall(r'<｜DSML｜parameter\s+name\s*=\s*"([\w.-]+)"([^>]*)>(.*?)</｜DSML｜parameter>',
                              m.group(2), re.S):
        if 'string="false"' in s:
            try:
                params[k] = json.loads(v)
                continue
            except json.JSONDecodeError:
                pass
        params[k] = v
    return ToolCall(m.group(1), {}, "", params)


def parse_tool(raw: str, names: set[str] | frozenset[str] = frozenset()) -> ToolCall | None:
    raw = _normalize(raw.strip())
    if raw.startswith(f"<{DSML}invoke"):
        return _dsml(raw)
    if raw.startswith("<|tool_call_begin|>"):  # Kimi K2
        m = re.match(r"<\|tool_call_begin\|>\s*(?:functions\.)?([\w.-]+?)(?::\d+)?\s*<\|tool_call_argument_begin\|>"
                     r"(.*?)(?:<\|tool_call_end\|>)?\s*$", raw, re.S)
        try:
            args = json.loads(m.group(2)) if m else None
        except json.JSONDecodeError:
            args = None
        return ToolCall(m.group(1), {}, "", args) if m and isinstance(args, dict) else None
    if raw.startswith('<invoke name="'):  # MiniMax M2: the DSML shape without its prefix
        return _dsml(raw.replace("<invoke", f"<{DSML}invoke").replace("</invoke>", f"</{DSML}invoke>")
                     .replace("<parameter", f"<{DSML}parameter").replace("</parameter>", f"</{DSML}parameter>"))
    if names and (call := parse_named(raw, names)):
        return call
    if raw.startswith("<|channel|>commentary to="):  # harmony: to=functions.NAME ... <|message|>{json}<|call|>
        m = re.match(r"<\|channel\|>commentary to=(?:functions\.)?([\w.-]+).*?<\|message\|>(.*?)(?:<\|call\|>)?$", raw, re.S)
        try:
            args = json.loads(m.group(2)) if m else None
        except json.JSONDecodeError:
            args = None
        return ToolCall(m.group(1), {}, "", args) if m and isinstance(args, dict) else None
    if "<function=" in raw:
        return _xml_function(raw)
    if raw.startswith("<tool_call>") and "<arg_key>" in raw or re.fullmatch(r"<tool_call>\s*[\w.-]+\s*</tool_call>", raw):
        # GLM: <tool_call>NAME<arg_key>k</arg_key><arg_value>v</arg_value>...</tool_call>
        inner = raw[len("<tool_call>"):].removesuffix("</tool_call>")
        name = re.match(r"\s*([\w.-]+)", inner)
        args = {}
        for k, v in re.findall(r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>(.*?)</arg_value>", inner, re.S):
            try:
                args[k] = json.loads(v) if v.strip()[:1] in "[{" else v
            except json.JSONDecodeError:
                args[k] = v
        return ToolCall(name.group(1), {}, "", args) if name else None
    if raw.startswith("<tool_call>"):
        inner = raw[len("<tool_call>"):].removesuffix("</tool_call>").strip()
        try:
            d = json.loads(inner)
        except json.JSONDecodeError:
            return None
        args = d.get("arguments") or d.get("parameters") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        return ToolCall(d.get("name", ""), {}, "", args) if d.get("name") else None
    if raw.startswith("<tool") and (big := big_attr_call(raw)):
        args = big[1]
        name = args.pop("name", "")
        return ToolCall(name, args, big[2]) if name else None
    m = re.match(r"<tool\b([^>]*)>(.*?)(?:</tool>)?\s*$", raw, re.S)
    if not m:
        return None
    head, body = _split_open(m.group(1), m.group(2))
    args = attrs(head)
    name = args.pop("name", "")
    if not name and body.strip().startswith("{"):  # <tool>{"name": ..., "arguments": {...}}</tool>
        return parse_tool(f"<tool_call>{body.strip()}</tool_call>")
    return ToolCall(name, *_lift_args(args, body)) if name else None


def _split_open(head: str, body: str) -> tuple[str, str]:
    """An opening tag never closed with '>' before the content (<tool name="make_doc" path="r.pdf"\\n<h1>Title</h1>):
    the content's own '>' ended the tag, the <h1> was lost and "Title</h1>" became the step's label. The tag ends at
    the first '<' inside it."""
    cut = re.search(r"<(?=[a-zA-Z!/])", head)
    if not cut:
        return head, body
    return head[:cut.start()], head[cut.start():] + ">" + body


# Argument blocks written inside the body instead of as attributes: <parameter name="path">x</parameter>,
# <parameter=path>x</parameter>, <arguments>{"path": "x"}</arguments>, <path>x</path>. make_doc got no path ("Missing
# required argument 'path'") and the parameter tags were written into the document.
_ARG_NAMES = ("path", "format", "title", "url", "query", "command", "source", "template", "method", "server", "tool",
              "file", "save", "name", "lang", "language", "mode", "id", "shell", "cwd", "append", "theme", "style")
_LEAD_ARG = re.compile(
    r'\s*(?:<parameter\s+name\s*=\s*"([\w.-]+)"\s*>(.*?)</parameter>|<parameter=([\w.-]+)>(.*?)</parameter>'
    r'|<(arguments|args|parameters)>\s*(\{.*?\})\s*</\5>|<(' + "|".join(_ARG_NAMES) + r')>([^<]{0,400})</\7>)',
    re.S)
_CONTENT_KEYS = ("content", "body", "html", "markdown", "text", "code", "command", "query")


def _lift_args(args: dict, body: str) -> tuple[dict, str]:
    pos, lifted = 0, {}
    while (m := _LEAD_ARG.match(body, pos)) and m.end() > pos:
        if m.group(1) or m.group(3):
            key, val = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            lifted[key] = val.strip("\n")
        elif m.group(6):
            try:
                obj = json.loads(m.group(6))
            except json.JSONDecodeError:
                break
            if not isinstance(obj, dict):
                break
            lifted.update({k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for k, v in obj.items()})
        else:
            lifted[m.group(7)] = m.group(8).strip()
        pos = m.end()
    if not lifted:
        return args, body
    rest = body[pos:]
    for k in _CONTENT_KEYS:  # the content written as a parameter block is the body
        if k in lifted and not rest.strip():
            rest = lifted.pop(k)
            break
    return {**lifted, **args}, rest


def _is_call(block: str) -> bool:
    """A closed <tool>...</tool> block that is really a call (a name or a JSON body), not the word in prose."""
    return block.startswith("<tool ") and 'name="' in block[:200] or parse_tool(block) is not None


# Raw tool syntax that must never reach the user (any model, any provider).
LEAK = re.compile(r"<parameter=|<function=|</?tool_call>|\[TOOL_CALLS\]|<\|tool_call|<tool\s+name=|\"arguments\"\s*:\s*\{|"
                  r"<tools?\s*=|</?tools\b|\[/?tools?(\s*name)?\s*=|\[/tools?\]|"
                  r"<\|channel\|>|<\|message\|>|<｜DSML｜|<invoke name=|minimax:tool_call|<\|python_tag\|>|"
                  r"\bargument\s+key\s*=\s*\"[\w.-]+\"\s+type\s*=|<\|call>\|",
                  re.I)


def extract_inline_calls(text: str, tool_names: set[str]) -> tuple[list[ToolCall], str]:
    """Final pass over a turn's visible text for formats that can't be detected while streaming:
    Mistral '[TOOL_CALLS][...]' and fenced/bare JSON objects naming a known tool. Returns (calls, cleaned text)."""
    calls: list[ToolCall] = []

    def take(obj) -> bool:
        items = obj if isinstance(obj, list) else [obj]
        found = []
        for it in items:
            if not isinstance(it, dict):
                return False
            name = it.get("name") or (it.get("function") or {}).get("name")
            args = it.get("arguments", it.get("parameters", (it.get("function") or {}).get("arguments", {})))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    return False
            if name not in tool_names or not isinstance(args, dict):
                return False
            found.append(ToolCall(name, {}, "", args))
        calls.extend(found)
        return bool(found)

    def repl(m: re.Match) -> str:
        try:
            return "" if take(json.loads(m.group(1))) else m.group(0)
        except json.JSONDecodeError:
            return m.group(0)

    text = re.sub(r"\[TOOL_CALLS\]\s*(\[.*\])", repl, text, flags=re.S)

    def bracket(m: re.Match) -> str:  # [tool="write_file" path="a.md"]...[/tool] (also [tools=...], <tools="...">)
        if m.group(1) not in tool_names:
            return m.group(0)
        args = attrs(m.group(2))
        calls.append(ToolCall(m.group(1), args, (m.group(3) or "").strip("\n")))
        return ""
    text = re.sub(r'\[tools?\s*(?:name\s*)?=\s*"([\w.-]+)"([^\]]*)\](.*?)(?:\[/tools?\]|$)', bracket, text, flags=re.S | re.I)
    text = re.sub(r'<tools?\s*(?:name\s*)?=\s*"([\w.-]+)"([^>]*)>(.*?)(?:</tools?>|$)', bracket, text, flags=re.S | re.I)
    # The tag with its "<" lost, often inside a fence: ```tool name="stock_photo" folder="images">coffee</tool>```
    # (evren:auto wrote exactly this; nothing ran and the chat showed an empty "tool" code block).
    text = re.sub(r'(?:```[ \t]*)?(?<![\w<])tools?\s+name\s*=\s*"([\w.-]+)"([^>\n]*)>(.*?)(?:</tools?>[ \t]*(?:\n```)?|\n```|$)',
                  bracket, text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?\s*(\{[^`]*?\"name\"[^`]*\})\s*```", repl, text, flags=re.S)
    if not calls and text.strip().startswith("{") and text.strip().endswith("}"):
        text = re.sub(r"^\s*(\{.*\})\s*$", repl, text, flags=re.S)
    if not calls and _NEMO_ARG.search(text):
        found, text = nemotron_args(text, tool_names)
        calls.extend(found)
    if not calls:
        found, text = cli_calls(text, tool_names)
        calls.extend(found)
    if not calls and "edit_video" in tool_names:
        # A video timeline written as a bare JSON fence ({"clips": [...]}) instead of a tool call: it is the edit_video
        # call the model meant (the same way a printed shell command is run), so the render really happens.
        named = re.search(r"[\w./\\-]+\.(?:mp4|mov|mkv)\b", text, re.I)  # the file the reply names is the output

        def timeline(m: re.Match) -> str:
            args = {"output": named.group(0).replace("\\", "/")} if named else {}
            calls.append(ToolCall("edit_video", args, m.group(1).strip()))
            return ""
        text = re.sub(r"```(?:json)?\s*(\{(?:(?!```).)*?\"(?:clips|scenes|photos)\"\s*:(?:(?!```).)*\})\s*```",
                      timeline, text, flags=re.S)
    return calls, text.strip()


# Nemotron 3.5 Super (NVIDIA) wrote its calls as typed argument blocks, often with the brackets lost on the way:
#   argument key="name" type="string"runargumentargument key="arguments" type="array"[{"key":"command",...}]argument
#   <|call>|  ...  calltools
# Nothing ran and the task ended "ok" with that text as its answer (skill_git, 0/2). A call starts at its "name" key;
# its "arguments" key holds a list of {key, type, value} or an object; other keys in the same call are flat arguments.
_NEMO_ARG = re.compile(r'<?\s*argument\s+key\s*=\s*"([\w.-]+)"(?:\s+type\s*=\s*"(\w+)")?\s*>?(.*?)'
                       r'(?:<\s*/\s*argument\s*>|/?argument>?(?=\s*(?:<?\s*argument\s+key|<\|call|</?call|call\s*(?:tools)?\s*$|$))'
                       r'|(?=<?\s*argument\s+key\s*=)|$)', re.S)
_NEMO_END = re.compile(r'\s*(?:<\|call\|?>\|?|</?call>|</?tools?>|\bcall\s*tools\b|\bcalltools\b|\s)*$')


def _typed(value: str, kind: str | None):
    value = value.strip()
    if kind in ("array", "object", "number", "integer", "boolean") or value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def nemotron_args(text: str, tool_names: set[str]) -> tuple[list[ToolCall], str]:
    calls: list[ToolCall] = []
    cur: dict | None = None
    first = last = None
    for m in _NEMO_ARG.finditer(text):
        key, val = m.group(1), _typed(m.group(3), m.group(2))
        first = m.start() if first is None else first
        last = m.end()
        if key == "name" and isinstance(val, str):
            cur = {"name": val.strip(), "args": {}}
            calls.append(cur)  # type: ignore[arg-type]
        elif cur is not None and key in ("arguments", "parameters", "args"):
            if isinstance(val, list):
                for it in val:
                    if isinstance(it, dict) and "key" in it:
                        cur["args"][str(it["key"])] = it.get("value", "")
            elif isinstance(val, dict):
                cur["args"].update(val)
        elif cur is not None:
            cur["args"][key] = val
    found = [ToolCall(c["name"], {}, "", {k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                                         if not isinstance(v, (int, float, bool)) else v for k, v in c["args"].items()})
             for c in calls if c["name"] in tool_names]
    if not found or first is None:
        return [], text
    return found, (text[:first] + _NEMO_END.sub("", text[last:])).strip()


# A tool "called" as a command line or function call in the text, as weak models do when they do not use the
# protocol: write_file path="a.py" content="..."  /  run(shell="python", command="a.py")  (in or out of a fence).
_QVAL = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''
_KV = re.compile(r'(\w+)\s*[=:]\s*(' + _QVAL + r')', re.S)
_CLI = re.compile(r'(?m)^[ \t]*(?:[$>][ \t]*)?([a-z_][\w]*)[ \t]*\(?[ \t]*((?:\w+\s*[=:]\s*(?:' + _QVAL
                  + r')[ \t,]*)+)\)?[ \t]*;?[ \t]*$', re.S)


def _unquote(v: str) -> str:
    q, inner = v[0], v[1:-1]
    try:
        return json.loads('"' + (inner.replace('\\"', '"').replace('"', '\\"') if q == "'" else inner) + '"')
    except json.JSONDecodeError:
        return inner.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")


def cli_calls(text: str, tool_names: set[str]) -> tuple[list[ToolCall], str]:
    """Tool calls written as plain lines (see _CLI). Only known tool names with key="value" arguments count; a fence
    left with nothing but such calls is removed from the visible text."""
    calls: list[ToolCall] = []

    def take(m: re.Match) -> str:
        if m.group(1) not in tool_names:
            return m.group(0)
        args = {k: _unquote(v) for k, v in _KV.findall(m.group(2))}
        if not args:
            return m.group(0)
        calls.append(ToolCall(m.group(1), {}, "", args))
        return ""

    text = _CLI.sub(take, text)
    if calls:
        text = re.sub(r"```[\w+-]*[ \t]*\n\s*```", "", text)  # fences emptied by the calls taken out
    return calls, text


def parse_named(raw: str, names: set[str] | frozenset[str]) -> ToolCall | None:
    """A tool written as its own tag, as weak models do: <research query="..."></research>, <run>dir</run>,
    <web_search query="x"/>. Attributes are the arguments, the inner text is the main argument."""
    if (big := big_attr_call(raw)) and big[0] in names:
        return ToolCall(big[0], big[1], big[2])
    m = re.match(r"<([\w-]+)\b([^>]*?)(/?)>(.*?)(?:</\1>)?\s*$", raw.strip(), re.S)
    if not m or m.group(1) not in names:
        return None
    if m.group(3):
        return ToolCall(m.group(1), attrs(m.group(2)), "")
    head, body = _split_open(m.group(2), m.group(4))
    return ToolCall(m.group(1), *_lift_args(attrs(head), body))


class StreamSplitter:
    """feed() returns a list of (kind, text) with kind in visible | thinking | tool | retract. 'retract' means the
    visible text sent so far was reasoning (a lone closing tag arrived): the caller takes it back; the same text
    follows as 'thinking'. tool_names: the app's tools, also recognized when a model writes one as its own tag."""

    def __init__(self, tool_names: set[str] | frozenset[str] = frozenset()) -> None:
        self.buf = ""
        self.open: tuple[str, str] | None = None
        self.shown: list[str] = []  # visible text so far (for 'retract')
        self.thought = False  # a reasoning block was seen: a later lone closer is not a retraction
        self.names = frozenset(tool_names)
        self.tags = TAGS + [t for n in sorted(self.names, key=len, reverse=True)
                            for t in ((f"<{n} ", f"</{n}>"), (f"<{n}>", f"</{n}>"))]

    def _visible(self, out: list, text: str) -> None:
        if (m := LONE_CLOSE.search(text)) and not self.thought:
            before = "".join(self.shown) + STRAY.sub("", text[:m.start()])
            self.thought, self.shown = True, []
            out.append(("retract", ""))
            if before.strip():
                out.append(("thinking", before))
            text = text[m.end():]
        text = LONE_CLOSE.sub("", STRAY.sub("", text))
        if text:
            self.shown.append(text)
            out.append(("visible", text))

    def _held(self) -> int:
        """Index of a tail that may be the start of a tag or control token (kept until the next chunk), or -1."""
        cut = self.buf.rfind("<")
        if cut < 0:
            return -1
        tail = self.buf[cut:]
        # harmony tokens span several '<|...|>' pieces: keep the whole run from its first '<|'
        start = self.buf.find("<|", max(0, len(self.buf) - 120))
        while start >= 0:
            if HARMONY_RUN.fullmatch(self.buf[start:]):
                return start
            start = self.buf.find("<|", start + 2)
        if any(o.startswith(tail) for o, _ in self.tags) or any(c.startswith(tail) for c in CLOSERS):
            return cut
        # A stray piece of call syntax split between two chunks ("</pa" + "rameter>") is held until it is whole, so
        # STRAY can take it out; otherwise each half went to the chat as text.
        if any(h.startswith(tail) for h in STRAY_HEADS) or (
                len(tail) < 100 and ">" not in tail and any(tail.startswith(h) for h in STRAY_HEADS)) or TAG_TAIL.fullmatch(tail):
            return cut
        return -1

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self.buf += chunk
        out: list[tuple[str, str]] = []
        while True:
            if self.open is None:
                hits = [(self.buf.find(o), i) for i, (o, _) in enumerate(self.tags) if self.buf.find(o) >= 0]
                if not hits:
                    cut = self._held()
                    emit, self.buf = (self.buf[:cut], self.buf[cut:]) if cut >= 0 else (self.buf, "")
                    self._visible(out, emit)
                    return out
                idx, i = min(hits)
                self._visible(out, self.buf[:idx])
                self.buf, self.open = self.buf[idx:], self.tags[i]
                self._scan = 0
            opener, close = self.open
            # Searched from where the last chunk's search stopped (minus a split closing tag): a whole file streamed
            # as one tool call was scanned from its start on every chunk, slower and slower as it grew.
            start = getattr(self, "_scan", 0)
            end = self.buf.find(close, max(0, start - len(close)) if start <= len(self.buf) else 0)
            self._scan = len(self.buf) if end < 0 else 0
            named = opener[1:].strip(" >") in self.names
            if named and (gt := self.buf.find(">")) > 0 and self.buf[gt - 1] == "/" and (end < 0 or gt < end):
                # self-closing <web_search query="x"/>
                block, self.buf = self.buf[:gt + 1], self.buf[gt + 1:]
                out.append(("tool", block)) if parse_named(block, self.names) else self._visible(out, block)
                self.open = None
                continue
            if end < 0:
                if opener in THINK_OPENERS:
                    safe = len(self.buf) - len(close)  # keep a possibly split closing tag
                    if safe > len(opener):
                        out.append(("thinking", self.buf[len(opener):safe]))
                        self.buf = opener + self.buf[safe:]
                        self._scan = 0
                return out
            block, self.buf = self.buf[: end + len(close)], self.buf[end + len(close):]
            if opener in ("<tool ", "<tools ") and (two := split_unclosed(block)):
                block, self.buf = two[0], two[1] + self.buf  # the second call is read on the next pass
            if opener in THINK_OPENERS:
                self.thought = True
                out.append(("thinking", block[len(opener):-len(close)]))
            elif opener == "<tool>" and not _is_call(block):
                self._visible(out, block)  # the word <tool> in prose (HTML, docs), not a call
            elif named and not parse_named(block, self.names):
                self._visible(out, block)
            else:
                out.append(("tool", block))
            self.open = None

    def flush(self) -> list[tuple[str, str]]:
        rest, self.buf = self.buf, ""
        if not rest:
            return []
        if self.open and self.open[0] in THINK_OPENERS:
            return [("thinking", rest[len(self.open[0]):])]
        if self.open and self.open[0] == "<tool>" and not rest[len("<tool>"):].lstrip().startswith("{"):
            out: list[tuple[str, str]] = []
            self._visible(out, rest)  # never closed and no JSON body: plain text
            return out
        if self.open and self.open[0][1:].strip(" >") in self.names:
            block = rest + self.open[1]  # a named tool tag the model never closed: <research query="x">
            if parse_named(block, self.names) and ">" in rest and ATTR.search(rest.split(">", 1)[0]):
                return [("tool", block)]
            out = []
            self._visible(out, rest)
            return out
        if self.open and self.open[0] in ("<tool ", "<tools ") and rest.rstrip().endswith("/>") \
                and parse_tool(rest.rstrip(), self.names):
            return [("tool", rest.rstrip())]  # <tool name="write_file" path="a" content="..."/>: complete, self-closed
        if self.open:
            return [("tool_incomplete", rest + self.open[1])]
        out = []
        self._visible(out, rest)
        return out
