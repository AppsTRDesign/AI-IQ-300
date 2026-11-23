"""v0.19.0: the same error coming back after fixes is named with what was tried - never stopped (no circuit breaker)."""
from types import SimpleNamespace

from app.agents.ledger import error_sig
from app.agents.tooling import recurring_error
from app.tools.registry import ToolResult


def _run(prior=None):
    return SimpleNamespace(err_sigs={}, prior_errs=prior or {})


def test_signature_ignores_paths_numbers_and_names():
    a = error_sig("Traceback (most recent call last):\n  File \"C:\\x\\app.py\", line 12\nModuleNotFoundError: No module named 'flask'")
    b = error_sig("ModuleNotFoundError: No module named 'jinja2' (line 40 of /srv/app/main.py)")
    assert a.startswith("traceback") or "modulenotfounderror" in a
    assert error_sig("Error: Cannot find module './a.js'") == error_sig("Error: Cannot find module './lib/b.js'")
    assert error_sig("npm ERR! code 1 at 12:00") == error_sig("npm ERR! code 7 at 13:05")
    assert b


def test_third_return_explains_but_never_blocks():
    run = _run()
    out = []
    for i in range(7):
        res = recurring_error(run, "run", {}, f"python app.py --try {i}",
                              ToolResult(False, f"TypeError: cannot read property 'x' of undefined at line {i}"))
        out.append(res)
    assert all(not r.ok for r in out)  # a failure stays a failure; nothing is switched off
    assert "[App note]" not in out[0].output and "[App note]" not in out[1].output
    assert "come back 3 times" in out[2].output and "python app.py --try 0" in out[2].output
    assert "[App note]" not in out[3].output and "come back 6 times" in out[5].output
    assert "Keep working on it" in out[5].output


def test_error_from_an_earlier_task_is_named():
    sig = error_sig("Error: listen EADDRINUSE: address already in use :::3000")
    run = _run({sig: 2})
    res = recurring_error(run, "start", {}, "npm run dev", ToolResult(False, "Error: listen EADDRINUSE: address already in use :::5173"))
    assert "task 2" in res.output
