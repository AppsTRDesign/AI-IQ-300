"""Round 2026-11-22j: removing a tool - 'delete if there' / 'is it still there?' commands came back failed and started
debug turns; a status poll between restarts was called a loop; `run list_dir`; paths with spaces."""
import asyncio
import sys

import pytest

from app.tools import registry  # noqa: F401
from app.tools.registry import TOOLS, ToolContext
from app.tools.shell_tools import probe_miss, PS_QUIET, _last_statement
from app.agents.tooling import changes_state


def test_probe_miss():
    assert probe_miss("npm list -g ruflo", "C:\\Users\\x\\AppData\\Roaming\\npm\n`-- (empty)")
    assert probe_miss("Get-Command ruflo", "")
    assert probe_miss("where ruflo", "[stderr] INFO: Could not find files for the given pattern(s).")
    assert probe_miss("pip show nope", "[stderr] WARNING: Package(s) not found: nope")
    assert not probe_miss("npm install -g ruflo", "")  # not a lookup
    assert not probe_miss("grep foo x.txt", "[stderr] grep: invalid option -- 'Q'")  # a real error


def test_quiet_detection():
    for c in ('Remove-Item -Recurse -Force ".claude-flow" -ErrorAction SilentlyContinue',
              "Get-Command ruflo -ea 0", "ls .claude-flow, .mcp.json 2>$null", "x; Remove-Item a -ErrorAction Ignore"):
        assert PS_QUIET.search(_last_statement(c)), c
    assert not PS_QUIET.search(_last_statement("Remove-Item a -ErrorAction SilentlyContinue; Remove-Item b"))


def test_state_changes_reset_the_loop_count():
    assert not changes_state("run", {}, "ruflo task status task-1")
    assert not changes_state("run", {}, "Start-Sleep -Seconds 10; ruflo task status task-1")
    assert not changes_state("run", {}, "Get-Content .claude-flow\\logs\\daemon.log -Tail 50")
    assert changes_state("run", {}, "ruflo daemon start --headless")
    assert changes_state("run", {}, "ruflo providers configure -p Ollama")
    assert changes_state("edit_file", {"path": "a"}, "")
    assert not changes_state("google", {"method": "GET"}, "")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell")
def test_silenced_powershell_errors_are_not_failures(tmp_path):
    async def go(cmd):
        ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
        return await TOOLS["run"].fn(ctx, {"shell": "powershell"}, cmd)
    r = asyncio.run(go('Remove-Item -Recurse -Force "nope-dir" -ErrorAction SilentlyContinue'))
    assert r.ok and "exit_code=0" in r.output, r.output
    r = asyncio.run(go("Get-Command surely-not-a-command-xyz -ErrorAction SilentlyContinue"))
    assert r.ok, r.output
    r = asyncio.run(go("Get-Content nope.txt"))  # not silenced: still a failure
    assert not r.ok
    r = asyncio.run(go("list_dir"))  # an app tool typed as a command
    assert r.ok and "app tool" in r.output, r.output
