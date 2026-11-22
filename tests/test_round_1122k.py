"""Round 2026-11-22k (8300 history scan): long Linear/Notion bodies broke MCP argument parsing; `| head -20` in
PowerShell; a top-level `return` / IIFE in browser js code."""
import asyncio
import sys

import pytest

from app.tools import registry  # noqa: F401
from app.tools.registry import TOOLS, ToolContext
from app.tools.agent_tools import mcp_args
from app.tools.browser_tools import JS_RUN


def test_mcp_args_takes_raw_line_breaks_and_a_trailing_sentence():
    raw = '{"title": "Bug", "description": "line one\nline two\tTabbed"}\nThis creates the issue.'
    val = mcp_args(raw)
    assert val["title"] == "Bug" and "line two" in val["description"]
    assert mcp_args('```json\n{"q": "name contains \\\'fatura\\\'",}\n```') == {"q": "name contains 'fatura'"}
    with pytest.raises(ValueError):
        mcp_args("[1, 2]")


def test_vendor_call_wrapper_split_between_chunks_never_shows():
    from app.agents.stream_parser import StreamSplitter

    def shown(chunks):
        sp = StreamSplitter(frozenset({"run"}))
        out = [x for c in chunks for x in sp.feed(c)] + sp.flush()
        return "".join(t for k, t in out if k == "visible")
    assert shown(["Bakıyorum.\n</minimax:", "tool_call>"]).strip() == "Bakıyorum."
    assert shown(["</mini", "max:tool_call>\n"]).strip() == ""
    assert shown(["<foo:tool_calls>", "x"]).strip() == "x"
    assert shown(["a < b ve c<", "d olur"]) == "a < b ve c<d olur"  # ordinary text stays whole


def test_js_runner_covers_function_bodies():
    # the runner tries an expression, then statements, then an (async) function body for a top-level return
    assert "return|await|yield" in JS_RUN and "async () => {" in JS_RUN


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell")
def test_head_and_tail_in_powershell(tmp_path):
    async def go(cmd):
        ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
        return await TOOLS["run"].fn(ctx, {"shell": "powershell"}, cmd)
    r = asyncio.run(go('"a","b","c","d" | head -2'))
    assert r.ok and "a" in r.output and "c" not in r.output.split("exit_code")[0].split("state=")[-1], r.output
    (tmp_path / "f.txt").write_text("1\n2\n3\n4\n5\n", encoding="utf-8")
    r = asyncio.run(go("tail -n 2 f.txt"))
    assert r.ok and "4" in r.output and "5" in r.output, r.output
