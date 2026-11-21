"""Internet drops: detection, UI events, tasks and tools waiting for the connection (round 2026-11-20)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import netwatch  # noqa: E402
from app.agents import tooling  # noqa: E402
from app.events import bus  # noqa: E402
from app.tools.registry import ToolResult  # noqa: E402


def _reset():
    netwatch.STATE.update({"online": True, "since": 0, "down_at": None, "last_down_secs": 0})


def _net_events(since):
    return [e["payload"] for e in bus.recent("system") if e["type"] == "net" and e["seq"] > since]


def test_offline_is_confirmed_and_pushed_then_back_online(monkeypatch):
    _reset()
    answers = iter([False, False, False, True])
    monkeypatch.setattr(netwatch, "probe", lambda: next(answers))
    monkeypatch.setattr(netwatch, "INTERVAL_DOWN", 0.01)
    start = bus.last_seq
    assert asyncio.run(netwatch.check_now()) is False
    assert netwatch.is_online() is False
    assert asyncio.run(netwatch.wait_online()) is True
    events = _net_events(start)
    assert [e["online"] for e in events] == [False, True]
    assert "down_secs" in events[-1]


def test_one_good_probe_never_reports_offline(monkeypatch):
    _reset()
    answers = iter([False, True])
    monkeypatch.setattr(netwatch, "probe", lambda: next(answers))
    start = bus.last_seq
    assert asyncio.run(netwatch.check_now()) is True
    assert _net_events(start) == []


def test_wait_online_stops_when_the_task_is_stopped(monkeypatch):
    _reset()
    monkeypatch.setattr(netwatch, "probe", lambda: False)
    cancel = asyncio.Event()
    cancel.set()
    assert asyncio.run(netwatch.wait_online(cancel)) is False


def test_network_errors_are_told_apart():
    assert netwatch.looks_like_network("mock: connection lost (ReadError: )")
    assert netwatch.looks_like_network("[Errno 11001] getaddrinfo failed")
    assert not netwatch.looks_like_network("model is busy (503)")
    assert not netwatch.looks_like_network("invalid api key")


def test_which_tools_need_the_internet():
    assert tooling._needs_net("web_search", {"query": "x"})
    assert tooling._needs_net("fetch_url", {"url": "https://example.com"})
    assert not tooling._needs_net("fetch_url", {"url": "http://localhost:8000/"})
    assert not tooling._needs_net("browser_navigate", {"url": "http://127.0.0.1:5173"})
    assert not tooling._needs_net("write_file", {"path": "a.txt"})


def test_a_web_tool_waits_offline_and_runs_once_back(monkeypatch):
    """A failed search used to reach the model as 'nothing found' and the repeat guard refused it afterwards."""
    _reset()
    calls = []

    async def once(run, ctx, name, args, body, allowed=None):
        calls.append(netwatch.is_online())
        return ToolResult(True, "results") if len(calls) > 1 else \
            ToolResult(False, "search failed: ConnectError getaddrinfo failed")

    steps = []
    monkeypatch.setattr(tooling, "_run_tool_once", once)
    monkeypatch.setattr(tooling, "_step", lambda run, kind, title, *a, **k: steps.append((kind, title, k.get("data"))) or "s1")
    probes = iter([False, False] + [True] * 10)
    monkeypatch.setattr(netwatch, "probe", lambda: next(probes))
    monkeypatch.setattr(netwatch, "INTERVAL_DOWN", 0.01)

    class R:
        cancel = asyncio.Event()
        seen = {'web_search:{"query": "x"}:'}

    run = R()
    res = asyncio.run(tooling._run_tool(run, None, "web_search", {"query": "x"}, ""))
    assert res.ok and res.output == "results"
    assert calls == [True, True]  # first try failed with a network error while 'online', the retry ran once back
    assert ("retry", "offline") in [(k, t) for k, t, _ in steps]
    assert all(d.get("until_online") for k, t, d in steps if t == "offline")
    assert run.seen == set()  # the repeat guard does not refuse the same search after the drop
