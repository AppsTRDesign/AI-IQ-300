"""v0.19.0: stream / parser regression pack. Each fixture in fixtures/streams.json is a model stream seen in real logs
(or its exact shape). It is fed in chunks of several sizes - 1, 2, 3, 7, 13, 64 characters and whole - because real
streams split anywhere, and the result must be the same every time: the same tool calls with the same arguments, the
visible text keeping what it must and never showing call syntax or hidden reasoning.

To add a case: put the raw stream from a log into the JSON file with what must (not) be visible."""
import json
from pathlib import Path

import pytest

from app.agents.stream_parser import LEAK, StreamSplitter, parse_tool

NAMES = {"write_file", "read_file", "run", "web_search", "research", "todo", "edit_file", "list_dir"}
CASES = json.loads((Path(__file__).parent / "fixtures" / "streams.json").read_text(encoding="utf-8"))
SIZES = (1, 2, 3, 7, 13, 64, 100000)


def _feed(stream: str, size: int):
    sp, out = StreamSplitter(NAMES), []
    for i in range(0, len(stream), size):
        out += sp.feed(stream[i:i + size])
    out += sp.flush()
    shown: list[str] = []
    for k, t in out:  # as the chat shows it: "retract" takes back what was shown so far (it was reasoning)
        if k == "retract":
            shown = []
        elif k == "visible":
            shown.append(t)
    text = "".join(shown)
    calls = [parse_tool(b, NAMES) for k, b in out if k == "tool"]
    return text, [c for c in calls if c]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_stream_fixture(case):
    results = {size: _feed(case["stream"], size) for size in SIZES}
    for size, (text, calls) in results.items():
        where = f"[chunk size {size}]"
        assert [c.name for c in calls] == case["tools"], where
        for k, v in (case.get("args") or {}).items():
            assert {**(calls[0].args or {}), **(calls[0].arguments or {})}.get(k) == v, where
        for frag in case.get("body_has") or []:
            assert any(frag in (c.body or "") or frag in json.dumps(c.arguments, ensure_ascii=False) for c in calls), where
        for frag in case.get("text_has") or []:
            assert frag in text, f"{where} missing {frag!r} in {text!r}"
        for frag in case.get("text_not") or []:
            assert frag not in text, f"{where} leaked {frag!r} in {text!r}"
        if case["tools"]:
            assert not LEAK.search(text), where
    # the visible text is the same however the stream was split (modulo whitespace)
    norm = {" ".join(t.split()) for t, _ in results.values()}
    assert len(norm) == 1, norm
