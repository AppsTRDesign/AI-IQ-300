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
TAGS = [("<tool_call>", "</tool_call>"), ("<function=", "</function>"), ("<tool ", "</tool>"), ("<tool>", "</tool>"),
        ("<think>", "</think>")]
STRAY = re.compile(r"</?tool_call>|</function>")
ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
MAX_OPEN = max(len(o) for o, _ in TAGS)


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


def parse_tool(raw: str) -> ToolCall | None:
    raw = raw.strip()
    if "<function=" in raw:
        return _xml_function(raw)
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
    m = re.match(r"<tool\b([^>]*)>(.*)</tool>\s*$", raw, re.S)
    if not m:
        return None
    args = {k: html.unescape(v) for k, v in ATTR.findall(m.group(1))}
    name = args.pop("name", "")
    return ToolCall(name, args, m.group(2)) if name else None


# Raw tool syntax that must never reach the user (any model, any provider).
LEAK = re.compile(r"<parameter=|<function=|</?tool_call>|\[TOOL_CALLS\]|<\|tool_call|<tool\s+name=|\"arguments\"\s*:\s*\{",
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
    text = re.sub(r"```(?:json)?\s*(\{[^`]*?\"name\"[^`]*\})\s*```", repl, text, flags=re.S)
    if not calls and text.strip().startswith("{") and text.strip().endswith("}"):
        text = re.sub(r"^\s*(\{.*\})\s*$", repl, text, flags=re.S)
    return calls, text.strip()


class StreamSplitter:
    """feed() returns a list of (kind, text) with kind in visible | thinking | tool."""

    def __init__(self) -> None:
        self.buf = ""
        self.open: tuple[str, str] | None = None

    def _visible(self, out: list, text: str) -> None:
        text = STRAY.sub("", text)
        if text:
            out.append(("visible", text))

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self.buf += chunk
        out: list[tuple[str, str]] = []
        while True:
            if self.open is None:
                hits = [(self.buf.find(o), i) for i, (o, _) in enumerate(TAGS) if self.buf.find(o) >= 0]
                if not hits:
                    # keep a possible partial opener (or stray closer) at the end
                    cut = self.buf.rfind("<")
                    tail = self.buf[cut:] if cut >= 0 else ""
                    keep = cut >= 0 and len(tail) < MAX_OPEN + 2 and (
                        any(o.startswith(tail) for o, _ in TAGS) or "</tool_call>".startswith(tail)
                        or "</function>".startswith(tail))
                    emit, self.buf = (self.buf[:cut], tail) if keep else (self.buf, "")
                    self._visible(out, emit)
                    return out
                idx, i = min(hits)
                self._visible(out, self.buf[:idx])
                self.buf, self.open = self.buf[idx:], TAGS[i]
            opener, close = self.open
            end = self.buf.find(close)
            if opener == "<function=":  # Qwen often wraps it: also swallow a trailing </tool_call>
                end = self.buf.find(close)
            if end < 0:
                if opener == "<think>":
                    safe = len(self.buf) - len(close)  # keep a possibly split closing tag
                    if safe > len(opener):
                        out.append(("thinking", self.buf[len(opener):safe]))
                        self.buf = opener + self.buf[safe:]
                return out
            block, self.buf = self.buf[: end + len(close)], self.buf[end + len(close):]
            if opener == "<think>":
                out.append(("thinking", block[len(opener):-len(close)]))
            else:
                out.append(("tool", block))
            self.open = None

    def flush(self) -> list[tuple[str, str]]:
        rest, self.buf = self.buf, ""
        if not rest:
            return []
        if self.open and self.open[0] != "<think>":
            return [("tool_incomplete", rest + self.open[1])]
        if self.open:
            return [("thinking", rest[len(self.open[0]):])]
        rest = STRAY.sub("", rest)
        return [("visible", rest)] if rest else []
