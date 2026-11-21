"""What a model did after a huge file was written: it killed every python.exe (the app itself) to free a port, a second
server started on a port an old one still held, multi-statement browser JS failed. Run: python -m pytest tests/test_round_1121c.py"""
import os

from app import policy
from app.agents.checks import error_playbook
from app.tools.registry import TOOLS  # noqa: F401  (loads the tools in order)
from app.tools.shell_tools import _port_of


def test_killing_runtimes_by_name_is_refused_in_every_mode():
    for cmd in ("taskkill /f /im python.exe 2>nul & python -m http.server 8080", "Stop-Process -Name python -Force",
                "Get-Process python* | Stop-Process -Force", "pkill -f python", "taskkill /F /IM node.exe",
                "wmic process where \"name='python.exe'\" delete", f"taskkill /PID {os.getpid()} /F"):
        for mode in ("ask", "auto", "full"):
            d = policy.decide_command(cmd, mode)
            assert d.action == "deny" and d.category == "kills_app", (cmd, mode)
    # one process by its id, or another program by name, is still the user's call
    assert policy.decide_command("taskkill /PID 4321 /F", "full").action == "allow"
    assert policy.decide_command("taskkill /f /im chrome.exe", "full").action == "allow"
    assert policy.decide_command("python -m http.server 8080", "full").action == "allow"


def test_bare_port_of_http_server_is_seen():
    assert _port_of("python -m http.server 8080 --bind 127.0.0.1") == 8080
    assert _port_of("python -m http.server --bind 127.0.0.1 8081") == 8081
    assert _port_of("python -m http.server -d dist 9000") == 9000
    assert _port_of("npx serve -l 3000") == 3000
    assert _port_of("python -m http.server") is None


def test_started_server_does_not_finish_test_and_fix_item():
    import types
    from app.agents.tooling import _auto_todo
    from app.tools.registry import ToolResult
    todos = [{"content": "index.html yaz", "status": "completed"},
             {"content": "Tarayıcıda test et ve hataları düzelt", "status": "in_progress"}]
    run = types.SimpleNamespace(todos=todos, written_names=set(), auto_ticked=0, id="r", events=[], session={})
    import app.agents.tooling as tooling
    old = tooling._emit
    tooling._emit = lambda *a, **k: None
    try:
        _auto_todo(run, "start", {}, ToolResult(True, "process_id=x state=running"))
        assert run.todos[1]["status"] == "in_progress"
        run.todos = [{"content": "Sunucuyu başlat", "status": "in_progress"}, {"content": "Testleri çalıştır", "status": "pending"}]
        _auto_todo(run, "start", {}, ToolResult(True, "process_id=x state=running"))
        assert run.todos[0]["status"] == "completed" and run.todos[1]["status"] == "in_progress"
        _auto_todo(run, "run", {}, ToolResult(True, "5 passed"))
        assert run.todos[1]["status"] == "completed"
    finally:
        tooling._emit = old


def test_batch_steps_parse_as_models_write_them():
    import json
    import pytest
    from app.tools.browser_tools import _batch_json
    assert _batch_json('```json\n[{"action": "js", "code": "const a = 1;\n a + 1"},]\n```') == \
        [{"action": "js", "code": "const a = 1;\n a + 1"}]
    with pytest.raises(json.JSONDecodeError):
        _batch_json('[{"action": "js", "code": "document.querySelector("#x")"}]')


def test_numbers_and_durations_as_models_send_them():
    from app.tools.browser_tools import _ms, _num
    assert _num("3s", 1) == 3 and _num("200px", 0) == 200 and _num("", 5) == 5 and _num(None, 2) == 2
    assert _ms("1.5s", 0) == 1500 and _ms("700ms", 0) == 700 and _ms("2 sn", 0) == 2000 and _ms(800, 0) == 800


def test_page_error_names_type_and_place():
    import types
    from app.tools.browser import _page_error
    e = types.SimpleNamespace(name="ReferenceError", message="duration is not defined",
                              stack="ReferenceError: duration is not defined\n    at Game.shake (http://localhost:8081/index.html:3106:21)")
    assert _page_error(e)["text"] == "Uncaught ReferenceError: duration is not defined (at index.html:3106:21)"


def test_browser_own_requests_and_old_navigation_are_not_page_errors():
    import types
    from collections import deque
    from app.tools.browser import BrowserAgent
    a = BrowserAgent()

    class Page:  # hashable, like a Playwright page
        url = "http://localhost:8081/"
    page = Page()
    a.active, a.ids = page, {page: "t1"}
    a.console["t1"] = deque([{"type": "error", "text": "Failed to load resource: 404", "url": "http://localhost:8081/favicon.ico"}])
    a.bad["t1"] = deque(["net::ERR_EMPTY_RESPONSE document http://localhost:8080/", "404 image http://localhost:8081/favicon.ico"])
    assert a.news() == ""
    a.console["t1"].append({"type": "error", "text": "Uncaught TypeError: x is undefined", "url": ""})
    a.bad["t1"] = deque(["404 script http://localhost:8081/game.js"])
    out = a.news()
    assert "TypeError" in out and "game.js" in out and "Page check" in out


def test_playbook_for_console_wait_and_broken_old_server():
    assert "Start-Sleep" in error_playbook("ERROR: Input redirection is not supported, exiting the process immediately.")
    assert "another free port" in error_playbook("Invoke-WebRequest : Temel alınan bağlantı kapatıldı: Bağlantı beklenmedik bir şekilde kapatıldı.")
