"""Eval tasks added in v0.20.1 (web research, three skill tasks): each checker fails an untouched task and passes the
scripted solution of the mock solver."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))
import mock_solver  # noqa: E402
import tasks  # noqa: E402


def _seed(tmp_path, task_id):
    t = tasks.BY_ID[task_id]
    ws = tmp_path / task_id
    if t.seed:
        shutil.copytree(EVAL / "tasks" / t.seed, ws)
    ws.mkdir(exist_ok=True)
    if t.setup:
        t.setup(ws)
    return ws


def _bad(checks):
    return [n for n, ok, _ in checks if not ok]


def _skill(name):
    return {"trace": [{"type": "step", "kind": "skill", "title": name, "status": "done", "tool": "use_skill"}], "lang": "en"}


def test_research_needs_facts_sources_and_web_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "_url_alive", lambda u: (True, "200"))
    ws = _seed(tmp_path, "research")
    assert len(_bad(tasks.check_research(ws, {"trace": []}))) >= 8
    (ws / "research").mkdir()
    (ws / "research" / "report.md").write_text(mock_solver.RESEARCH, encoding="utf-8")
    web = [{"type": "step", "tool": "research", "status": "done"}, {"type": "step", "tool": "fetch_url", "status": "done"}]
    assert _bad(tasks.check_research(ws, {"trace": web})) == []
    # an answer from memory without sources is not research
    (ws / "research" / "report.md").write_text("Python 3.13.0: 2024-10-07. PEP 703. Rust 1.0: 2015-05-15. "
                                               "SQLite: public domain. 3433 days.", encoding="utf-8")
    bad = _bad(tasks.check_research(ws, {"trace": []}))
    assert "every fact has its source next to it" in bad and "searched the web (>= 2 web tool calls)" in bad


def test_research_flags_invented_links(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "_url_alive", lambda u: (False, "404") if "sqlite" in u else (True, "200"))
    ws = _seed(tmp_path, "research")
    (ws / "research").mkdir()
    (ws / "research" / "report.md").write_text(mock_solver.RESEARCH, encoding="utf-8")
    assert _bad(tasks.check_research(ws, {"trace": []}))[0] == "the cited pages really exist (no 404 / dead site)"


def test_review_finds_the_planted_problems(tmp_path):
    ws = _seed(tmp_path, "skill_review")
    assert "review.md exists" in _bad(tasks.check_review(ws, {"trace": []}))
    (ws / "review.md").write_text(mock_solver.REVIEW, encoding="utf-8")
    assert _bad(tasks.check_review(ws, _skill("code-review"))) == []
    (ws / "app" / "db.py").write_text("# fixed\n", encoding="utf-8")  # the task said: report only
    assert _bad(tasks.check_review(ws, _skill("code-review"))) == ["code left unchanged (review only)"]


@pytest.mark.skipif(not tasks._MERMAID_JS.is_file(), reason="frontend/node_modules not installed")
def test_flowchart_is_parsed_by_mermaid(tmp_path):
    ws = _seed(tmp_path, "skill_flowchart")
    (ws / "diagrams").mkdir()
    (ws / "diagrams" / "order.mmd").write_text(mock_solver.FLOW, encoding="utf-8")
    assert _bad(tasks.check_flowchart(ws, _skill("flowchart"))) == []
    # no loop back to the stock check, one decision only
    (ws / "diagrams" / "order.mmd").write_text("flowchart TD\n A[Order] --> B{In stock?}\n B -->|Yes| C[Pay]\n"
                                               " B -->|No| D[Supplier]\n C --> E[Ship]\n E --> F[Track]\n F --> G[End]\n",
                                               encoding="utf-8")
    bad = _bad(tasks.check_flowchart(ws, {"trace": []}))
    assert "two decisions as diamonds" in bad and "the restock loop goes back to the stock check (a cycle)" in bad
    (ws / "diagrams" / "order.mmd").write_text("flowchart TD\n A[x --> ", encoding="utf-8")
    assert "Mermaid parses and draws it" in _bad(tasks.check_flowchart(ws, {"trace": []}))


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_task_checked_with_git_itself(tmp_path):
    ws = _seed(tmp_path, "skill_git")
    assert (ws / ".env").is_file() and (ws / "__pycache__").is_dir()
    assert _bad(tasks.check_git(ws, {"trace": []}))[0] == "a git repository"
    script = mock_solver.GIT.replace("MSG", "İlk sürüm")
    subprocess.run([sys.executable, "-c", script], cwd=ws, check=True, capture_output=True)
    assert _bad(tasks.check_git(ws, _skill("git"))) == []
    (ws / "app.py").write_text("changed\n", encoding="utf-8")
    assert _bad(tasks.check_git(ws, _skill("git"))) == ["nothing left uncommitted"]


def test_scripted_solver_covers_every_task():
    for t in tasks.TASKS:
        steps, _ = mock_solver.script(t.prompt["tr"])
        assert steps != ["Merhaba."], t.id
        steps, _ = mock_solver.script(t.prompt["en"])
        assert steps != ["Merhaba."], t.id
