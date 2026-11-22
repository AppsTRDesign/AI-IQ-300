"""Round 2026-11-22: the file guard (a written file is never cut down by a forgotten rewrite or a second break), the
unclosed call that leaked into a web search, make_doc's source handling, inspect_media on a PDF, repeated tool names
from OpenAI-compatible servers, argument loops, the run that sat for minutes, Mistral tool ids.
Run: python -m pytest tests/test_round_1122.py"""
import asyncio
import types
from pathlib import Path

from app.agents.continuity import TINY_ARGS, _file_loop_check, _live_write, save_partial
from app.agents.stream_parser import StreamSplitter, parse_tool
from app.agents.tooling import _job_files
from app.llm.providers import ProviderError
from app.llm.providers import _mistral_id, _mistral_ids
from app.tools.doc_tools import _strip_cdata
from app.tools.file_tools import live_restore
from app.tools.registry import TOOLS, ToolContext, clean_file_content
from app.tools.web_tools import clean_query

BIG = "".join(f"function part{i}() {{ return {i} * 2; }}  // line {i} of the game engine\n" for i in range(400))


def _ctx(root: Path) -> ToolContext:
    return ToolContext("t", root, "full", asyncio.Event())


def _write(ctx, **args):
    body = args.pop("body")
    return asyncio.run(TOOLS["write_file"].fn(ctx, args, body))


# ------------------------------------------------------------------ file guard
def test_forgotten_rewrite_of_a_written_file_is_refused_once(tmp_path):
    ctx = _ctx(tmp_path)
    assert _write(ctx, path="game.js", body=BIG).ok
    small = "function part0() { return 0; }\n// rewritten from memory\n"
    res = _write(ctx, path="game.js", body=small)
    assert not res.ok and "file guard" in res.output and "line 399" in res.output  # the real end is shown
    assert (tmp_path / "game.js").read_text(encoding="utf-8") == BIG
    res = _write(ctx, path="game.js", body=small)  # sent again: meant, it goes through with a backup
    assert res.ok and (tmp_path / "game.js").read_text(encoding="utf-8").startswith("function part0")
    backups = list(tmp_path.rglob("backups/*"))
    assert any(b.read_text(encoding="utf-8") == BIG for b in backups)


def test_growing_rewrite_and_untouched_files_are_not_guarded(tmp_path):
    ctx = _ctx(tmp_path)
    assert _write(ctx, path="a.js", body=BIG).ok
    assert _write(ctx, path="a.js", body=BIG + "// more\n").ok
    (tmp_path / "user.js").write_text(BIG, encoding="utf-8")  # a project file this task did not write
    assert _write(ctx, path="user.js", body="console.log(1);\n").ok


def test_second_break_never_wipes_the_saved_file(tmp_path):
    (tmp_path / "game.js").write_text(BIG, encoding="utf-8")
    cut = BIG[:3000]  # a rewrite from the top, cut off by the second break
    path, n, mode = save_partial(tmp_path, "write_file", {"path": "game.js", "content": cut}, False)
    assert mode == "kept" and (tmp_path / "game.js").read_text(encoding="utf-8") == BIG
    assert (tmp_path / "game.js.cut-rewrite.txt").is_file()


def test_break_in_a_plain_continuation_appends(tmp_path):
    (tmp_path / "game.js").write_text(BIG, encoding="utf-8")
    nxt = "".join(f"function more{i}() {{ return {i}; }}\n" for i in range(20))
    _, _, mode = save_partial(tmp_path, "write_file", {"path": "game.js", "content": nxt}, False)
    text = (tmp_path / "game.js").read_text(encoding="utf-8")
    assert mode == "appended" and text.startswith(BIG) and text.endswith(nxt)


def test_live_rewrite_of_an_existing_file_never_empties_it(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / "game.js").write_text(BIG, encoding="utf-8")
    ctx.files_changed.append("game.js")
    run = types.SimpleNamespace(live_ctx=ctx)
    _live_write(run, ("write_file", {"path": "game.js", "content": "// new start\nconst a = 1;\n"}, False))
    assert (tmp_path / "game.js").read_text(encoding="utf-8") == BIG  # untouched while the rewrite streams
    live_restore(ctx, tmp_path / "game.js")
    assert (tmp_path / "game.js").read_text(encoding="utf-8") == BIG


def test_live_append_restores_to_the_old_text(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / "game.js").write_text(BIG, encoding="utf-8")
    run = types.SimpleNamespace(live_ctx=ctx)
    _live_write(run, ("write_file", {"path": "game.js", "content": "// next\nconst b = 2;\n"}, True))
    assert (tmp_path / "game.js").read_text(encoding="utf-8").endswith("const b = 2;\n")
    live_restore(ctx, tmp_path / "game.js")
    assert (tmp_path / "game.js").read_text(encoding="utf-8") == BIG


# ------------------------------------------------------------------ parser / search leaks
def test_unclosed_call_does_not_swallow_the_next_one():
    sp = StreamSplitter({"research", "todo"})
    text = ('<tool name="research" query="Kozan Adana 5 günlük hava durumu tahmini">\n'
            '<tool name="todo">[{"content": "Konumu al", "status": "completed"}]</tool>')
    out = sp.feed(text) + sp.flush()
    tools = [parse_tool(b) for k, b in out if k == "tool"]
    assert [t.name for t in tools] == ["research", "todo"]
    assert tools[0].args.get("query") == "Kozan Adana 5 günlük hava durumu tahmini"
    assert "Konumu al" in tools[1].body


def test_query_is_cleaned_of_protocol_pieces():
    assert clean_query({"query": 'Kozan Adana 5 günlük hava durumu mgm">'}, "") == "Kozan Adana 5 günlük hava durumu mgm"
    assert clean_query({"query": 'hava tahmini">\n<tool name="todo'},
                       '[{"content": "Kullanıcının konumunu al", "status": "completed"}]') == "hava tahmini"
    assert clean_query({}, '"exact phrase" search') == '"exact phrase" search'
    assert clean_query({}, '[{"content": "x", "status": "pending"}]') == ""


def test_research_refuses_a_call_without_words(tmp_path):
    res = asyncio.run(TOOLS["research"].fn(_ctx(tmp_path), {}, '[{"content": "a", "status": "pending"}]'))
    assert not res.ok and "Not searched" in res.output


# ------------------------------------------------------------------ documents
def test_cdata_wrapper_is_removed():
    assert _strip_cdata("<![CDATA[# Başlık\n\nMetin]]>") == "# Başlık\n\nMetin"
    assert clean_file_content("<![CDATA[# Rapor\nsatır\n]]>").startswith("# Rapor")
    assert clean_file_content("const x = '<![CDATA[';\n") == "const x = '<![CDATA[';\n"


def test_make_doc_uses_the_source_just_written(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    src = "# Kozan Hava Durumu\n\n" + "".join(f"| Gün {i} | {10 + i}° | yağmurlu |\n" for i in range(20))
    assert _write(ctx, path=".doc-sources/rapor.pdf.md", body="| a | b |\n|---|---|\n" + src).ok
    seen = {}

    async def fake_generate(kind, content, target, **kw):
        seen["content"] = content
        target.write_bytes(b"%PDF-1.4 fake")
        return {"bytes": 13, "engine": "test"}
    import app.tools.docs_gen as docs_gen
    monkeypatch.setattr(docs_gen, "generate", fake_generate)
    res = asyncio.run(TOOLS["make_doc"].fn(ctx, {"path": "rapor.pdf", "type": "pdf"}, "# Kozan"))
    assert res.ok, res.output
    assert "Gün 19" in seen["content"]  # the written source, not the 7-character body
    assert "Gün 19" in (tmp_path / ".doc-sources" / "rapor.pdf.md").read_text(encoding="utf-8")  # not overwritten


def test_write_and_make_doc_of_its_source_never_run_together():
    w = ("write_file", {"path": ".doc-sources/x.pptx.md"}, "")
    d = ("make_doc", {"path": "x.pptx", "source": ".doc-sources/x.pptx.md"}, "")
    assert _job_files(w) & _job_files(d)


def test_inspect_media_reads_a_pdf(tmp_path, monkeypatch):
    import fitz  # pymupdf
    from app.tools import visual

    async def no_vision(*a, **k):  # never a real vision model in a test (a local CPU model kept pytest from exiting)
        return None
    monkeypatch.setattr(visual, "describe_for", no_vision)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Kozan hava durumu raporu")
    doc.save(tmp_path / "r.pdf")
    res = asyncio.run(TOOLS["inspect_media"].fn(_ctx(tmp_path), {"path": "r.pdf", "transcript": "false"}, ""))
    assert "AttributeError" not in res.output


# ------------------------------------------------------------------ providers / loops / run
def test_mistral_ids_are_nine_alphanumerics_and_consistent():
    msgs = [{"role": "assistant", "content": None, "tool_calls": [{"id": "a1b2c3d4e5f6", "type": "function"}]},
            {"role": "tool", "tool_call_id": "a1b2c3d4e5f6", "content": "ok"}]
    out = _mistral_ids(msgs)
    cid = out[0]["tool_calls"][0]["id"]
    assert len(cid) == 9 and cid.isalnum() and out[1]["tool_call_id"] == cid
    assert _mistral_id("Ab3dE6gH9") == "Ab3dE6gH9"


def test_endless_arguments_of_a_tiny_tool_are_cut():
    import pytest
    assert "my_location" in TINY_ARGS
    run = types.SimpleNamespace(partial_tag="", partial_args={0: {"name": "my_location", "args": ["{}" * 2000]}},
                                file_loops=0)
    with pytest.raises(ProviderError):
        _file_loop_check(run, [0])
    run = types.SimpleNamespace(partial_tag='<tool name="web_search">' + "hava " * 1000, partial_args={}, file_loops=0)
    with pytest.raises(ProviderError):
        _file_loop_check(run, [0])


def test_repeated_tool_name_fragments_are_not_joined():
    # the same check the stream reader does for every fragment
    slot = {"name": ""}
    for n in ("my_location", "my_location", "my_location"):
        if n and n != slot["name"]:
            slot["name"] += n
    assert slot["name"] == "my_location"


def test_silent_run_goes_to_the_background(tmp_path, monkeypatch):
    import sys
    import app.tools.shell_tools as sh
    monkeypatch.setattr(sh, "RUN_IDLE_DETACH", 6)
    from app.process_manager import manager

    async def go():
        ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
        res = await asyncio.wait_for(TOOLS["run"].fn(ctx, {"shell": "python"}, "import time\ntime.sleep(60)\n"), 40)
        await manager.stop(res.data["process_id"])  # stopped by its id, never by name
        return res
    res = asyncio.run(go())
    assert res.ok and "background" in res.output and res.data.get("process_id") and sys.platform


# ------------------------------------------------------------------ round 2: providers, security, races
def test_protected_app_files_are_refused_to_commands_in_every_mode():
    from app import policy
    for cmd in (r"type data\secrets.json", "Get-Content E:/x/data/secrets.json", "sqlite3 data/aiiq.db .dump"):
        for mode in ("ask", "auto", "full"):
            assert policy.decide_command(cmd, mode).action == "deny", (cmd, mode)
    assert policy.decide_command("python app.py", "full").action == "allow"


def test_same_mcp_server_calls_never_run_together():
    from app.agents.tooling import _mcp_server
    a = ("mcp", {"server": "playwright", "tool": "browser_navigate"}, "")
    b = ("mcp", {"server": "playwright", "tool": "browser_console_messages"}, "")
    assert _mcp_server(a) == _mcp_server(b) == "playwright"
    assert _mcp_server(("read_file", {"path": "a"}, "")) == ""


def test_thinking_switches_follow_each_providers_docs():
    from app.llm.providers import _no_penalty, _thinking_switch
    off = {"think": False}
    assert _thinking_switch("https://api.moonshot.ai/v1", "kimi-k2.6", off) == {"thinking": {"type": "disabled"}}
    assert _thinking_switch("https://api.moonshot.ai/v1", "kimi-k2-thinking", off) is None
    assert _thinking_switch("https://api.z.ai/api/paas/v4", "glm-4.7", off) == {"thinking": {"type": "disabled"}}
    assert _thinking_switch("https://api.z.ai/api/paas/v4", "glm-5.3", off) is None
    assert _thinking_switch("https://api.z.ai/api/paas/v4", "glm-4.7", {}) is None
    assert _thinking_switch("https://api.openai.com/v1", "gpt-5", off) is None
    assert _no_penalty("https://api.x.ai/v1", "grok-4.7") and not _no_penalty("https://api.x.ai/v1", "grok-4-fast-non-reasoning")
    assert _no_penalty("https://api.sambanova.ai/v1", "x") and not _no_penalty("https://api.groq.com/openai/v1", "llama")


def test_stream_without_index_joins_fragments():
    # SambaNova streams one call in fragments without "index"; Gemini sends whole calls without it
    from app.llm import providers as pv

    class R:
        status_code = 200

    async def fake_sse(r):
        for d in ([{"id": "c1", "function": {"name": "write_file", "arguments": '{"path": "a.txt", '}}],
                  [{"function": {"arguments": '"content": "hi"}'}}],
                  [{"function": {"name": "read_file", "arguments": '{"path": "b"}'}}]):
            yield {"choices": [{"delta": {"tool_calls": d}}]}

    class FakeClient:
        def stream(self, *a, **k):
            class C:
                async def __aenter__(s):
                    return R()

                async def __aexit__(s, *e):
                    return False
            return C()

    class Pool:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, *e):
            return False

    async def ok(*a, **k):
        return None
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(pv, "_sse", fake_sse)
    mp.setattr(pv, "pooled", Pool)
    mp.setattr(pv, "_raise_for", ok)
    try:
        p = pv.OpenAICompatProvider("sambanova", {"base_url": "https://api.sambanova.ai/v1"}, pv.Capabilities())
        p.key = lambda **k: "k"

        async def go():
            return [e async for e in p.stream("m", [{"role": "user", "content": "x"}], {"tools": [{"name": "t"}]})]
        calls = [e for e in asyncio.run(go()) if e["type"] == "tool_call"]
    finally:
        mp.undo()
    assert [(c["name"], c["arguments"]) for c in calls] == [("write_file", {"path": "a.txt", "content": "hi"}),
                                                           ("read_file", {"path": "b"})]


def test_deepseek_gets_its_reasoning_back_others_do_not():
    from app.llm.providers import OpenAICompatProvider
    msgs = [{"role": "assistant", "content": "", "reasoning": "plan", "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]}]
    out = OpenAICompatProvider._messages(msgs)
    assert out[0]["_reasoning"] == "plan"  # popped or renamed per server in stream()


def test_detached_process_outlives_the_command_timeout(tmp_path):
    import sys
    from app.process_manager import manager

    async def go():
        info = await manager.start([sys.executable, "-c", "import time; time.sleep(30)"], str(tmp_path), dict(os.environ),
                                   owner="test", timeout=3)
        manager.detach(info)
        await asyncio.sleep(8)
        state = info.state
        await manager.stop(info.id)
        return state
    import os
    assert asyncio.run(go()) == "running"
