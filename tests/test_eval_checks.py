"""The evaluation checkers (eval/tasks.py) must fail an untouched task and pass a correct solution."""
import shutil
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
import mock_solver  # noqa: E402
import tasks  # noqa: E402


def _seed(tmp_path, task_id):
    ws = tmp_path / task_id
    shutil.copytree(EVAL / "tasks" / tasks.BY_ID[task_id].seed, ws)
    return ws


def _ok(checks):
    return [n for n, ok, _ in checks if not ok]


def test_fix_python_fails_untouched_and_passes_fixed(tmp_path):
    ws = _seed(tmp_path, "fix_python")
    assert "the given tests pass" in _ok(tasks.check_fix(ws, {}))
    (ws / "stats.py").write_text(mock_solver.STATS, encoding="utf-8")
    assert _ok(tasks.check_fix(ws, {})) == []
    (ws / "test_stats.py").write_text("def test_x():\n    pass\n", encoding="utf-8")  # editing the tests is caught
    assert "test_stats.py left unchanged" in _ok(tasks.check_fix(ws, {}))


def test_multi_file_fails_untouched_and_passes_done(tmp_path):
    ws = _seed(tmp_path, "multi_file")
    assert len(_ok(tasks.check_multi(ws, {}))) == 4
    for rel, text in mock_solver.SHOP.items():
        (ws / rel).write_text(text, encoding="utf-8")
    assert _ok(tasks.check_multi(ws, {})) == []


def test_net_drop_check_reads_the_trace(tmp_path):
    ws = tmp_path / "net"
    (ws / "notes").mkdir(parents=True)
    for name, text in mock_solver.PLANETS.items():
        (ws / "notes" / name).write_text(text, encoding="utf-8")
    trace = [{"type": "step", "kind": "retry", "status": "done"},
             *({"type": "step", "tool": "write_file", "status": "done", "args": {"path": f"notes/{n}"}} for n in "abcd")]
    run = {"lang": "tr", "status": "ok", "trace": trace, "net_cut": {"cut_at": 3.0}}
    assert _ok(tasks.check_net(ws, run)) == []
    trace.append({"type": "step", "tool": "write_file", "status": "done", "args": {"path": "notes/a"}})
    assert _ok(tasks.check_net(ws, {**run, "net_cut": {}})) == ["the connection was really cut mid-task",
                                                                  "no finished file written again after the drop"]


@pytest.mark.parametrize("lang", ["tr", "en"])
def test_every_task_has_both_languages(lang):
    for t in tasks.TASKS:
        assert t.prompt[lang] and t.title[lang]
