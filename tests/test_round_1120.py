"""Round 2026-11-20 (v0.15.0): fixes found in the step logs of long real runs (PHP shop, Kotlin calculator, Android
SDK update). Each test is one failure seen live.
Run: python -m pytest tests/test_round_1120.py"""
import asyncio
from pathlib import Path

from app.agents import orchestrator as orch
from app.agents.stream_parser import StreamSplitter, parse_tool
from app.tools import editing, mobile, registry
from app.tools.registry import TOOLS, ToolContext

NAMES = frozenset(TOOLS)
JS = ("'use strict';\nconst Icons = {\n  cart: '<svg viewBox=\"0 0 24 24\" fill=\"none\"><path d=\"M1 1h4\"/></svg>',"
      "\n};\nconst f = (a) => a > 1;\n")


def _ctx(root: Path) -> ToolContext:
    return ToolContext("t", root, "full", asyncio.Event())


def _split(text: str, step: int = 7):
    s, out = StreamSplitter(NAMES), []
    for i in range(0, len(text), step):
        out += s.feed(text[i:i + step])
    return out + s.flush()


def _tools(text: str):
    return [parse_tool(x, NAMES) for k, x in _split(text) if k == "tool"]


# --- tag protocol: a whole file written as an attribute ---------------------------------------------------------

def test_content_attribute_keeps_the_whole_file():
    # every write of app.js stopped at  cart: '<svg viewBox=  (the value ended at its first quote)
    for raw in (f'<tool name="write_file" path="a.js" content="{JS}"></tool>',
                f'<tool name="write_file" path="a.js" content="{JS}"/>',
                f'<write_file path="a.js" content="{JS}"></write_file>'):
        (call,) = _tools(raw)
        assert call.name == "write_file" and call.args["content"] == JS and call.args["path"] == "a.js"


def test_short_attributes_after_the_content_stay_arguments():
    (call,) = _tools(f'<tool name="write_file" path="a.js" content="{JS}" append="true"></tool>')
    assert call.args["append"] == "true" and call.args["content"] == JS


def test_old_and_new_as_attributes_are_split():
    (call,) = _tools('<tool name="edit_file" path="a.js" old="if (a) { x(); }" new="if (b) { y(); }"></tool>')
    assert call.args["old"] == "if (a) { x(); }" and call.args["new"] == "if (b) { y(); }"


def test_body_calls_are_unchanged():
    (call,) = _tools(f'<tool name="write_file" path="a.js">{JS}</tool>')
    assert call.body == JS and call.args == {"path": "a.js"}
    (q,) = _tools('<tool name="web_search" query="agp 8.11 compileSdk 36"></tool>')
    assert q.args == {"query": "agp 8.11 compileSdk 36"}


# --- edit_file blocks --------------------------------------------------------------------------------------------

def test_triple_equals_in_code_is_not_the_divider():
    block = "<<<<<<< SEARCH\n  if (a === b) {\n    run();\n  }\n=======\n  if (a !== b) {\n    run();\n  }\n>>>>>>> REPLACE"
    assert editing.parse_blocks(block) == [("  if (a === b) {\n    run();\n  }", "  if (a !== b) {\n    run();\n  }")]


def test_an_edit_never_writes_conflict_markers(tmp_path):
    (tmp_path / "a.js").write_text("const a = 1;\nconst b = 2;\n", encoding="utf-8")
    body = "<<<<<<< SEARCH\nconst a = 1;\n=======\nconst a = 3;\n=======\n>>>>>>> REPLACE"
    r = asyncio.run(TOOLS["edit_file"].fn(_ctx(tmp_path), {"path": "a.js"}, body))
    assert not r.ok and "=======" not in (tmp_path / "a.js").read_text(encoding="utf-8")


# --- write_file guards ---------------------------------------------------------------------------------------------

def test_empty_new_file_is_refused(tmp_path):
    r = asyncio.run(TOOLS["write_file"].fn(_ctx(tmp_path), {"path": "assets/js/app-core-utils.txt"}, ""))
    assert not r.ok and not (tmp_path / "assets/js/app-core-utils.txt").exists()
    ok = asyncio.run(TOOLS["write_file"].fn(_ctx(tmp_path), {"path": "pkg/__init__.py"}, ""))
    assert ok.ok


def test_garbled_path_is_refused(tmp_path):
    r = asyncio.run(TOOLS["write_file"].fn(_ctx(tmp_path), {"path": "hes-ap-ma-kine-s-i / b u i l d . g r a d l e"},
                                           "x = 1\n"))
    assert not r.ok and "garbled" in r.output
    assert not registry.garbled_path("app/build.gradle.kts") and not registry.garbled_path("My Docs/a b.txt")


def test_app_lines_are_taken_out_of_file_content(tmp_path):
    asyncio.run(TOOLS["write_file"].fn(_ctx(tmp_path), {"path": "a.js"},
                                       "const a = 1;\n[To-do item continues below]\nconst b = 2;\n"))
    assert "To-do" not in (tmp_path / "a.js").read_text(encoding="utf-8")


def test_broken_characters_are_reported(tmp_path):
    r = asyncio.run(TOOLS["write_file"].fn(_ctx(tmp_path), {"path": "b.kts"}, "// Kök build dosyas��\n"))
    assert r.ok and "broken character" in r.output


def test_lorem_ipsum_mentioned_is_not_a_placeholder():
    assert registry.placeholder_marks("Raporlarda lorem ipsum kullanılmaz; gerçek veri yazılır.") == []
    assert registry.placeholder_marks("Lorem ipsum dolor sit amet, consectetur.")


# --- todo ------------------------------------------------------------------------------------------------------------

def test_todo_takes_the_json_weak_models_write(tmp_path):
    for body in ('[{"content": "Kur", "status": "pending"},]', "```json\n[{'content': 'Kur', 'status': 'pending'}]\n```",
                 "1. Kur\n2. [x] Test et"):
        r = asyncio.run(TOOLS["todo"].fn(_ctx(tmp_path), {}, body))
        assert r.ok, body
    assert not asyncio.run(TOOLS["todo"].fn(_ctx(tmp_path), {}, "advance=true")).ok


def test_item_naming_several_files_waits_for_all(monkeypatch):
    run = orch.Run.__new__(orch.Run)
    run.todos = [{"content": "index.php, style.css ve app.js yaz", "status": "in_progress"},
                 {"content": "Test et", "status": "pending"}]
    run.written_names, run.auto_ticked, run.events = set(), 0, None
    from app.agents import tooling
    monkeypatch.setattr(tooling, "_emit", lambda *a, **k: None)  # _auto_todo lives in tooling (split 2026-11-20)
    ok = registry.ToolResult(True, "created", {"path": "index.php"})
    orch._auto_todo(run, "write_file", {"path": "index.php"}, ok)
    assert run.todos[0]["status"] == "in_progress"
    for f in ("style.css", "app.js"):
        orch._auto_todo(run, "write_file", {"path": f}, registry.ToolResult(True, "created", {"path": f}))
    assert run.todos[0]["status"] == "completed"


# --- streaming: leaks, loops -------------------------------------------------------------------------------------------

def test_stray_call_syntax_never_reaches_the_chat():
    d = "｜DSML｜"
    text = (f"Not: yazıyorum.<{d}function_calls>\n<{d}invoke name=\"write_file\">\n<{d}parameter name=\"path\" "
            f"string=\"true\">a.txt</{d}parameter>\n<{d}parameter name=\"content\" string=\"true\">merhaba</{d}parameter>"
            f"\n</{d}invoke>\n</{d}function_calls> tamam</parameter>")
    parts = _split(text)
    shown = "".join(x for k, x in parts if k == "visible")
    assert "DSML" not in shown and "</parameter>" not in shown and "tamam" in shown
    (call,) = [parse_tool(x, NAMES) for k, x in parts if k == "tool"]
    assert call.name == "write_file" and call.arguments == {"path": "a.txt", "content": "merhaba"}


def test_word_salad_is_cut():
    salad = " ".join(["exit withdraw retreat pull back step aside stand down yield surrender submit comply"] * 20)
    assert orch._salad_cut("I will write the file now.\n" + salad) == "I will write the file now."
    assert orch._salad_cut("This is a normal sentence, with punctuation. " * 60) is None


def test_split_rule_follows_the_setting(monkeypatch):
    from app.agents import continuity  # split_hint lives there (split 2026-11-20)
    monkeypatch.setattr(continuity, "load_settings", lambda: {"agent": {"split_write_chars": 0}})
    assert "ONE call" in orch.split_hint() and "8,000" not in orch.split_hint()
    monkeypatch.setattr(continuity, "load_settings", lambda: {"agent": {"split_write_chars": 12000}})
    assert "12,000" in orch.split_hint()


# --- history: files read stay readable -----------------------------------------------------------------------------------

def test_unchanged_reads_stay_whole_and_changed_ones_shrink():
    css = "x" * 5000
    msgs = [{"role": "user", "content": "task"}]
    for i in range(6):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"r{i}", "name": "read_file", "arguments": {"path": f"f{i}.css"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"r{i}", "name": "read_file", "content": css})
    msgs.append({"role": "assistant", "content": "", "tool_calls": [
        {"id": "w", "name": "edit_file", "arguments": {"path": "f0.css", "old": "x", "new": "y"}}]})
    msgs.append({"role": "tool", "tool_call_id": "w", "name": "edit_file", "content": "edited"})
    msgs += [{"role": "user", "content": "x"}] * 6
    orch.shrink_old_steps(msgs, 1, keep_reads=40000)
    assert orch.OLD_STEP_MARK in msgs[2]["content"]  # f0.css was changed after the read: stale, shortened
    assert msgs[4]["content"] == css  # f1.css unchanged: still whole


# --- Android -------------------------------------------------------------------------------------------------------------

def test_sdk_inventory_lists_what_is_installed(tmp_path):
    for d in ("platforms/android-36", "build-tools/37.0.0", "system-images/android-36/google_apis/x86_64",
              "platform-tools"):
        (tmp_path / d).mkdir(parents=True)
    inv = mobile.sdk_inventory(tmp_path)
    assert inv["platforms"] == ["android-36"] and inv["build_tools"] == ["37.0.0"]
    assert inv["system_images"] == ["system-images;android-36;google_apis;x86_64"] and inv["platform_tools"]
    assert mobile.COMPAT["36"]["agp"] == "8.11.1" and mobile.COMPAT["36"]["gradle"] == "8.13"
