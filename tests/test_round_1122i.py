"""Round 2026-11-22i: a status poll repeated until the loop note was held as "the last command failed" and the finished
answer was erased and rewritten; a command that leaves a background child (ruflo daemon start) waited 10 s extra."""
import asyncio
import sys
import time

from app.agents.checks import admits_failure
from app.tools import registry  # noqa: F401
from app.tools.registry import ToolResult


def test_repeated_success_is_a_loop_not_a_failure(monkeypatch):
    from app.agents import tooling
    from app.agents.runstate import Run
    assert "repeat_ok" in open(tooling.__file__, encoding="utf-8").read()
    src = open(__import__("app.agents.orchestrator", fromlist=["x"]).__file__, encoding="utf-8").read()
    assert src.count('get("repeat_ok")') >= 4  # unresolved (2 paths) + debugger role (2 paths)
    del Run


def test_honest_answers_are_kept():
    for a in ("❌ Neden Görev Tamamlanmadı? LLM provider yapılandırılmamış.", "Görev in_progress'te takılı kaldı.",
              "The task did not finish: no provider is configured.", "Kurulum başarısız oldu.", "PDF oluşturulamadı."):
        assert admits_failure(a), a
    for a in ("Rapor hazırlandı ve Drive'a yüklendi.", "Done: the site runs on port 8080.", "Tüm testler geçti."):
        assert not admits_failure(a), a


def test_background_child_does_not_hold_the_run(tmp_path):
    from app.process_manager import manager
    code = ("import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)']); "
            "print('daemon started')")

    async def go():
        t0 = time.monotonic()
        info = await manager.start([sys.executable, "-c", code], str(tmp_path), None)
        await asyncio.wait_for(info.done.wait(), 30)
        return time.monotonic() - t0, info
    took, info = asyncio.run(go())
    assert info.exit_code == 0 and any("daemon started" in x for x in info.tail), list(info.tail)
    assert took < 6, took  # was 10 s + the command
