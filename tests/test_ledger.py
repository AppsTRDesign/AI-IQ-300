"""The chat ledger (v0.18.7): the app records what each task did and the next prompt carries a compact view."""
import asyncio
import json
import uuid

from app import sessions
from app.agents import ledger


def _sid():
    return uuid.uuid4().hex[:16]


def _step(tool, status="done", output="", **data):
    return {"kind": "x", "title": tool, "status": status, "detail": "", "data": {"tool": tool, "output": output, **data}}


def test_record_and_view(tmp_path):
    sid = _sid()
    (tmp_path / "app.py").write_text("print(1)\n" * 50, encoding="utf-8")
    (tmp_path / "README.md").write_text("# x", encoding="utf-8")
    info = json.dumps({"now": {"date": "2026-11-23"}, "system": {"os": "Windows 10", "cpu": "i7", "ram": "32 GB",
                                                                "drives": [{"mount": "C:\\", "disk": "SSD, NVMe"}]}})
    steps = [_step("system_info", output=info), _step("write_file"), _step("write_file"),
             _step("run", "error", output="ModuleNotFoundError: No module named 'flask'"), _step("run")]
    ledger.record(sid, tmp_path, request="Flask uygulaması yaz", answer="Uygulama hazır: app.py", status="ok",
                  steps=steps, files=["app.py", "README.md", "gone.txt"], commands=["pip install flask", "python app.py"],
                  todos=[{"content": "Test yaz", "status": "pending"}], model="m")
    led = ledger.load(sid)
    assert led["tasks"] == 1 and "gone.txt" not in led["files"] and led["files"]["app.py"]["size"] > 100
    assert led["tools"] == {"system_info": 1, "write_file": 2, "run": 2}
    assert "flask" in led["failures"][0]["error"] and led["open"] == ["Test yaz"]
    assert "Windows 10" in led["env"]["system_info"]["facts"] and "2026-11-23" not in led["env"]["system_info"]["facts"]
    text = ledger.view(sid)
    assert text.startswith("# Chat ledger") and "`app.py`" in text and "Windows 10" in text and "recall" in text
    assert len(ledger.view(sid, lean=True)) <= ledger.VIEW_CHARS[True]

    # a second task: a file is deleted, newest first, task count grows
    (tmp_path / "README.md").unlink()
    (tmp_path / "test_app.py").write_text("assert True", encoding="utf-8")
    ledger.record(sid, tmp_path, request="test ekle", answer="eklendi", status="ok", steps=[_step("write_file")],
                  files=["test_app.py"], commands=[], todos=[])
    led = ledger.load(sid)
    assert led["tasks"] == 2 and list(led["files"]) == ["app.py", "test_app.py"] and led["open"] == []
    assert ledger.view(sid).index("test_app.py") < ledger.view(sid).index("app.py` (")


def test_recall_tool_reads_parts(tmp_path):
    from app.tools.registry import TOOLS, ToolContext
    sid = _sid()
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    ledger.record(sid, tmp_path, request="r", answer="a", status="ok", steps=[_step("run")], files=["a.txt"],
                  commands=["npm run build", "npm test"], todos=[])
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event(), owner=f"{sid}:run1")
    res = asyncio.run(TOOLS["recall"].fn(ctx, {"part": "commands", "query": "build"}, ""))
    assert res.ok and "npm run build" in res.output and "npm test" not in res.output and "a.txt" not in res.output
    empty = ToolContext("t", tmp_path, "full", asyncio.Event(), owner=f"{_sid()}:run1")
    assert "no recorded tasks" in asyncio.run(TOOLS["recall"].fn(empty, {}, "")).output


def test_prompt_uses_the_ledger_and_memory_group_has_recall(tmp_path):
    from app.agents.checks import GROUP_TOOLS, GROUP_WORDS
    assert "recall" in GROUP_TOOLS["memory"]
    assert GROUP_WORDS["memory"].search("daha önce hangi dosyaları yaptın?")
    assert GROUP_WORDS["memory"].search("what did you change last time")
    sid = _sid()
    assert ledger.view(sid) == ""  # no ledger, no section
    ledger.record(sid, tmp_path, request="r", answer="a", status="ok", steps=[_step("run")], files=[], commands=[], todos=[])
    assert (sessions.path(sid) / ledger.LEDGER).exists()


def test_record_never_raises(tmp_path):
    assert ledger.record("not-a-valid-id", tmp_path, request="", answer="", status="ok", steps=[], files=[],
                         commands=[], todos=[]) == {}
