"""Breaks never cost the model its reasoning, streaming providers are not cut as 'silent writers', deleted chats get
no orphan messages, and system_info reports the software side too.
Run: python -m pytest tests/test_continuity.py"""
import json

from app import db
from app.agents import orchestrator as o
from app.llm import router
from app.tools import sysinfo


class _Run:
    def __init__(self, thinking="", secs=0.0):
        self.last_thinking, self.think_secs, self.carry_thinking, self.no_think = thinking, secs, "", False


def test_reasoning_is_carried_into_the_retry_and_thinking_is_turned_off():
    run = _Run("Plan: write server/src/index.ts, then routes, then admin panel. " * 60, 240)
    msgs = [{"role": "user", "content": "build it"}]
    assert o._carry_thinking(run, msgs)
    note = msgs[-1]["content"]
    assert note.startswith(o.THINK_CARRY) and "<previous_reasoning>" in note and "4 min" in note
    assert run.no_think and run.last_thinking == ""


def test_a_second_break_keeps_one_carry_message_and_the_earlier_plan():
    run = _Run("First plan step A. " * 100, 100)
    msgs = [{"role": "user", "content": "task"}]
    o._carry_thinking(run, msgs)
    run.last_thinking = ""  # the retry broke before it reasoned again
    o._carry_thinking(run, msgs)
    carries = [m for m in msgs if str(m["content"]).startswith(o.THINK_CARRY)]
    assert len(carries) == 1 and "First plan step A." in carries[0]["content"]


def test_carry_goes_before_a_continued_answer_and_is_capped():
    run = _Run("x" * 40000, 60)
    msgs = [{"role": "user", "content": "task"}, {"role": "assistant", "content": "half answer"},
            {"role": "user", "content": o.CONTINUE_TAG + " continue"}]
    o._carry_thinking(run, msgs)
    assert msgs[-1]["content"].startswith(o.CONTINUE_TAG)
    assert msgs[1]["content"].startswith(o.THINK_CARRY) and len(msgs[1]["content"]) < o.CARRY_MAX + 2000


def test_short_reasoning_is_not_carried():
    run = _Run("ok", 1)
    msgs = [{"role": "user", "content": "hi"}]
    assert not o._carry_thinking(run, msgs) and len(msgs) == 1 and not run.no_think


def test_a_streaming_provider_is_never_switched_to_the_text_protocol():
    router.mark_streams_tool_args("probeprov:model-a")
    assert router.streams_tool_args("probeprov:model-b")  # the provider's parser streams for all its models
    router.disable_native_tools("probeprov:model-a", persist=True)
    saved = json.loads(router._STREAM_TOOLS.read_text(encoding="utf-8")) if router._STREAM_TOOLS.exists() else []
    assert "probeprov:model-a" not in saved
    router._NO_NATIVE_TOOLS.discard("probeprov:model-a")


def test_no_message_is_stored_for_a_deleted_chat():
    assert db.add_message("no-such-chat-xyz", "assistant", "late answer") == 0


def test_old_file_bodies_leave_no_content_pattern_to_copy():
    msgs = [{"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "write_file",
                                                                 "arguments": {"path": "a.ts", "content": "x = 1;\n" * 400}}]}]
    msgs += [{"role": "user", "content": f"m{i}"} for i in range(8)]
    o.shrink_old_steps(msgs, 1)
    body = msgs[1]["tool_calls"][0]["arguments"]["content"]
    assert body.startswith(o.OLD_STEP_MARK) and "x = 1" not in body and "\n" not in body


def _tool(name, root, files_changed=(), body="", **args):
    import asyncio
    from app.tools.registry import TOOLS, ToolContext
    ctx = ToolContext("t", root, "full", asyncio.Event())
    ctx.files_changed.extend(files_changed)
    return asyncio.run(TOOLS[name].fn(ctx, args, body))


def test_append_without_path_goes_to_the_file_being_written(tmp_path):
    (tmp_path / "admin.js").write_text("const a = 1;\n", encoding="utf-8")
    r = _tool("write_file", tmp_path, ["shots/x.png", "admin.js"], "const b = 2;\n", append="true")
    assert r.ok and "path was missing" in r.output
    assert (tmp_path / "admin.js").read_text(encoding="utf-8").count("const") == 2


def test_search_pattern_given_as_regex_value(tmp_path):
    (tmp_path / "a.ts").write_text("export function foo() {}\n", encoding="utf-8")
    r = _tool("search_code", tmp_path, regex="^export (function|const)")
    assert r.ok and "a.ts" in r.output


def test_system_info_software_part(tmp_path):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "package.json").write_text(json.dumps({"name": "srv", "dependencies": {"express": "^4"}}),
                                                      encoding="utf-8")
    d = json.loads(sysinfo.report("software", tmp_path))["software"]
    assert d["working_folder"]["path"] == str(tmp_path)
    assert d["working_folder"]["manifests"][0]["dependencies"] == ["express"]
    assert "httpx" in d["python_packages"] and "download" in d["github"] and "skills" in d
