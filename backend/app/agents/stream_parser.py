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
TAGS = [("<tool_call>", "</tool_call>"), ("<function=", "</function>"), ("<tools ", "</tools>"), ("<tools=", "</tools>"),
        ("<tool=", "</tool>"), ("<tool ", "</tool>"), ("<tool>", "</tool>"),
        ("<think>", "</think>"), ("<thinking>", "</thinking>"), ("<reasoning>", "</reasoning>"),
        ("<|channel|>analysis<|message|>", "<|end|>"),  # gpt-oss (harmony) reasoning channel
        ("<|channel|>commentary to=", "<|call|>")]  # gpt-oss (harmony) tool call written as text
HARMONY_RUN = re.compile(r"(?:<\|\w+\|>[\w .=]*)*(?:<\|?\w*\|?)?")  # complete or partial control-token run
THINK_OPENERS = {"<think>", "<thinking>", "<reasoning>", "<|channel|>analysis<|message|>"}
# Closing tags without an opener, and harmony control tokens around the final answer: never shown.
STRAY = re.compile(r"</?tool_call>|</function>|<\|start\|>assistant|<\|channel\|>\w+(?: to=[\w.]+)?"
                   r"(?:\s*<\|constrain\|>\w+)?<\|message\|>|<\|(?:end|return|start|call)\|>")
# A reasoning closer with no opener: the template opened the block in the prompt (DeepSeek-R1 / QwQ style), so
# everything shown before it was reasoning.
LONE_CLOSE = re.compile(r"</(?:think|thinking|reasoning)>")
ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
MAX_OPEN = max(len(o) for o, _ in TAGS)
CLOSERS = ("</tool_call>", "</function>", "</think>", "</thinking>", "</reasoning>")


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
    raw = re.sub(r'^<tools?\s*=\s*"([\w.-]+)"', r'<tool name="\1"', raw)
    raw = re.sub(r"^<tools\b", "<tool", raw)
    return re.sub(r"</tools>\s*$", "</tool>", raw)


def parse_tool(raw: str, names: set[str] | frozenset[str] = frozenset()) -> ToolCall | None:
    raw = _normalize(raw.strip())
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
    m = re.match(r"<tool\b([^>]*)>(.*?)(?:</tool>)?\s*$", raw, re.S)
    if not m:
        return None
    args = {k: html.unescape(v) for k, v in ATTR.findall(m.group(1))}
    name = args.pop("name", "")
    if not name and m.group(2).strip().startswith("{"):  # <tool>{"name": ..., "arguments": {...}}</tool>
        return parse_tool(f"<tool_call>{m.group(2).strip()}</tool_call>")
    return ToolCall(name, args, m.group(2)) if name else None


def _is_call(block: str) -> bool:
    """A closed <tool>...</tool> block that is really a call (a name or a JSON body), not the word in prose."""
    return block.startswith("<tool ") and 'name="' in block[:200] or parse_tool(block) is not None


# Raw tool syntax that must never reach the user (any model, any provider).
LEAK = re.compile(r"<parameter=|<function=|</?tool_call>|\[TOOL_CALLS\]|<\|tool_call|<tool\s+name=|\"arguments\"\s*:\s*\{|"
                  r"<tools?\s*=|</?tools\b|\[/?tools?(\s*name)?\s*=|\[/tools?\]|"
                  r"<\|channel\|>|<\|message\|>",
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
        args = {k: html.unescape(v) for k, v in ATTR.findall(m.group(2))}
        calls.append(ToolCall(m.group(1), args, (m.group(3) or "").strip("\n")))
        return ""
    text = re.sub(r'\[tools?\s*(?:name\s*)?=\s*"([\w.-]+)"([^\]]*)\](.*?)(?:\[/tools?\]|$)', bracket, text, flags=re.S | re.I)
    text = re.sub(r'<tools?\s*(?:name\s*)?=\s*"([\w.-]+)"([^>]*)>(.*?)(?:</tools?>|$)', bracket, text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?\s*(\{[^`]*?\"name\"[^`]*\})\s*```", repl, text, flags=re.S)
    if not calls and text.strip().startswith("{") and text.strip().endswith("}"):
        text = re.sub(r"^\s*(\{.*\})\s*$", repl, text, flags=re.S)
    if not calls:
        found, text = cli_calls(text, tool_names)
        calls.extend(found)
    return calls, text.strip()


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
    m = re.match(r"<([\w-]+)\b([^>]*?)(/?)>(.*?)(?:</\1>)?\s*$", raw.strip(), re.S)
    if not m or m.group(1) not in names:
        return None
    args = {k: html.unescape(v) for k, v in ATTR.findall(m.group(2))}
    return ToolCall(m.group(1), args, m.group(4) if not m.group(3) else "")


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
        if self.open:
            return [("tool_incomplete", rest + self.open[1])]
        out = []
        self._visible(out, rest)
        return out
