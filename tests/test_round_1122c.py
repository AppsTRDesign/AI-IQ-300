"""Round 2026-11-22c: failures from the Android calculator run (nemotron-3-ultra on NVIDIA). Each test is one thing
seen in its step logs. Run: python -m pytest tests/test_round_1122c.py"""
import asyncio
import sys
from pathlib import Path

import pytest

from app.agents import tooling
from app.agents.checks import plan_steps
from app.agents.continuity import without_todo_line
from app.agents.runstate import Run
from app.tools import shell_tools
from app.tools.registry import TOOLS, ToolContext


def _ctx(root: Path) -> ToolContext:
    return ToolContext("t", root, "full", asyncio.Event())


def _run(todos=None) -> Run:
    r = Run(id="r1", session={"id": "s1"})
    r.todos = [dict(t) for t in todos or []]
    return r


def _todo(monkeypatch, tmp_path, run, args, body):
    monkeypatch.setattr(tooling, "_emit", lambda *a, **k: None)
    return asyncio.run(tooling._run_tool_once(run, _ctx(tmp_path), "todo", args, body))


PLAN = [{"content": "Projeyi derle", "status": "in_progress"}, {"content": "Emülatörü başlat", "status": "pending"},
        {"content": "Ekran görüntüsü al", "status": "pending"}]


def test_an_unclosed_todo_never_takes_the_next_call_as_items(monkeypatch, tmp_path):
    # the list became '<tool name="run" shell="powershell" cwd="...">' and the gradle command line
    body = ('1. Projeyi derle\n2. Emülatörü başlat\n<tool name="run" shell="powershell" cwd="E:\\x\\CalculatorApp">\n'
            '& "E:\\Claude\\LLMChat\\data\\mobile\\gradle\\gradle-8.13\\bin\\gradle.bat" assembleDebug --no-daemon')
    run = _run()
    assert _todo(monkeypatch, tmp_path, run, {}, body).ok
    assert [t["content"] for t in run.todos] == ["Projeyi derle", "Emülatörü başlat"]
    # a list made only of a tag and a command is no plan at all
    junk = '<tool name="run" shell="powershell">\n& "C:\\sdk\\emulator.exe" -avd x'
    assert not asyncio.run(TOOLS["todo"].fn(_ctx(tmp_path), {}, junk)).ok
    assert plan_steps('1. <tool name="run">\n2. & "C:\\a\\b.exe" x\n3. $x = 1') == []


def test_native_call_with_empty_fields_keeps_the_new_list(monkeypatch, tmp_path):
    # advance=false, done=[], start=0, add=[] sent next to a new list: the list was dropped and "[]" became an item
    run = _run(PLAN)
    new = '[{"content": "Düzeni düzelt", "status": "in_progress"}, {"content": "Yeniden derle", "status": "pending"}]'
    res = _todo(monkeypatch, tmp_path, run, {"advance": "False", "done": "[]", "start": "0", "add": "[]"}, new)
    assert res.ok
    contents = [t["content"] for t in run.todos]
    assert "Düzeni düzelt" in contents and "Yeniden derle" in contents and "[]" not in contents


def test_ticking_with_empty_items_ticks_and_never_says_empty(monkeypatch, tmp_path):
    run = _run(PLAN)
    res = _todo(monkeypatch, tmp_path, run, {"done": "[1, 2]", "advance": "False", "add": "[]"}, "[]")
    assert res.ok and [t["status"] for t in run.todos] == ["completed", "completed", "in_progress"]
    # a call that changes nothing shows the list instead of "The list is empty"
    res = _todo(monkeypatch, tmp_path, run, {"advance": "false", "done": "[]"}, "[]")
    assert res.ok and "No change" in res.output and "Ekran görüntüsü al" in res.output


def test_todo_state_is_no_error():
    out = ("exit_code=1 state=failed\n[stderr] adb.exe: no devices\n[To-do 2/7 done; now: Projeyi derle "
           "(./gradlew assembleDebug). When this item is finished: todo advance=true (never retype the list; "
           "add=[...] for new work found on the way).]")
    assert without_todo_line(out).splitlines()[-1] == "[stderr] adb.exe: no devices"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell redirection")
def test_binary_redirect_runs_in_cmd(tmp_path):
    ctx = _ctx(tmp_path)
    argv = shell_tools.build_argv(ctx, "powershell",
                                  '& "E:\\sdk\\platform-tools\\adb.exe" exec-out screencap -p > screenshot.png')
    assert argv[:4] == ["cmd", "/d", "/s", "/c"] and argv[4] == '"E:\\sdk\\platform-tools\\adb.exe" exec-out screencap -p > screenshot.png'
    # PowerShell pipelines and variables stay in PowerShell
    for cmd in ("Get-ChildItem | Out-File a.txt", "$x = 1; adb devices > a.txt", "echo hi > a.txt"):
        assert shell_tools.build_argv(ctx, "powershell", cmd)[0] != "cmd", cmd


@pytest.mark.skipif(sys.platform != "win32", reason="cmd quoting")
def test_cmd_keeps_quotes_out_of_arguments(tmp_path):
    # adb said: filename doesn't end .apk or .apex: "app\build\outputs\apk\debug\app-debug.apk"
    from app.tools.registry import ToolResult  # noqa: F401
    (tmp_path / "a b.txt").write_text("x")
    py = sys.executable
    cmd = f'"{py}" -c "import sys; print(repr(sys.argv[1]))" "a b.txt"'
    res = asyncio.run(TOOLS["run"].fn(_ctx(tmp_path), {"shell": "cmd"}, cmd))
    assert "'a b.txt'" in res.output, res.output


def test_a_non_http_port_is_no_server():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        port = s.getsockname()[1]
        assert not shell_tools._speaks_http(port)  # accepts but never answers HTTP (like Gradle's daemon port)
    finally:
        s.close()
