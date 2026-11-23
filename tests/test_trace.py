"""Agent traces (v0.20.0): one JSON-lines file per task, written by the app from its own records."""
import uuid

from app.agents import trace


def _step(t0, tool, status="done", output="", kind="file", **args):
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "title": tool, "status": status, "detail": "", "t0": t0, "ms": 12,
            "data": {"tool": tool, "args": args, "output": output}}


def test_record_load_and_summary():
    sid = uuid.uuid4().hex[:16]
    steps = [_step(3.0, "run", "error", output="\nModuleNotFoundError: No module named 'flask'\nmore", kind="command"),
             _step(1.0, "write_file", path="app.py", content="x" * 1000),
             {"id": "r1", "kind": "retry", "title": "busy", "status": "done", "detail": "503", "t0": 2.0, "data": {}},
             _step(4.0, "run", kind="command")]
    perf = {"turns": [{"wait_ms": 900.4, "total_ms": 2000.0, "out_tokens": 120, "tps": 30.0}, {"wait_ms": 500.0, "total_ms": 800.0}]}
    path = trace.record(sid, "run123abc", model="m:x", status="ok", request="Flask app", started=0.0,
                        timing={"total_ms": 9000, "turns": 2, "out_tokens": 120}, steps=steps, perf=perf,
                        files=["app.py", "app.py"], commands=["python app.py"])
    assert path and path.is_file()
    lines = trace.load(sid, "run123abc")
    assert lines[0]["type"] == "run" and lines[0]["files"] == ["app.py"]
    st = [x for x in lines if x["type"] == "step"]
    assert [x["t"] for x in st] == sorted(x["t"] for x in st)  # time order
    assert st[0]["args"]["content"].startswith("x" * 300) and "(+700)" in st[0]["args"]["content"]  # long values cut
    assert st[2]["error"] == "ModuleNotFoundError: No module named 'flask'"
    s = trace.summary(lines)
    assert s == {**s, "status": "ok", "turns": 2, "tool_calls": 3, "tool_errors": 1, "retries": 1, "seconds": 9.0,
                 "errors_by_tool": {"run": 1}}


def test_record_never_raises_and_keeps_last():
    assert trace.record("not-a-session", "r", model="", status="ok", request="", started=0, timing={}, steps=[],
                        perf=None) is None
    sid = uuid.uuid4().hex[:16]
    for i in range(trace.KEEP + 3):
        trace.record(sid, f"run{i:04d}", model="m", status="ok", request="", started=0, timing={}, steps=[], perf=None)
    assert len(list(trace._dir(sid).glob("*.jsonl"))) == trace.KEEP
