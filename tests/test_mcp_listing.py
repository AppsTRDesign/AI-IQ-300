"""Every connected MCP server is visible to the model (a first-80 cut hid whole servers), and mcp tool="list" returns
a server's tools with their arguments. Run: python -m pytest tests/test_mcp_listing.py"""
import asyncio
from types import SimpleNamespace

from app.tools import registry  # noqa: F401  (loads agent_tools in the app's order)
from app import mcp_client
from app.tools import agent_tools


def _fake(monkeypatch):
    tools = [("github", {"name": f"gh_tool_{i}", "description": "d", "inputSchema": {"properties": {"q": {"type": "string"}},
                                                                                    "required": ["q"]}}) for i in range(90)]
    tools += [("time", {"name": "get_current_time", "description": "Now", "inputSchema": {}}),
              ("playwright", {"name": "browser_navigate", "description": "Go", "inputSchema": {}})]
    monkeypatch.setattr(mcp_client, "available_tools", lambda: tools)
    monkeypatch.setattr(mcp_client, "servers_cfg", lambda: {"github": {}, "time": {}, "playwright": {}})
    return tools


def test_every_server_listed(monkeypatch):
    _fake(monkeypatch)
    s = mcp_client.prompt_section("")
    assert "time/get_current_time" in s and "playwright/browser_navigate" in s  # detailed despite 90 github tools
    assert "gh_tool_89" in s  # by name in the 'More tools' part
    assert "second browser" in s


def test_mcp_list_tool(monkeypatch):
    tools = _fake(monkeypatch)
    monkeypatch.setattr(mcp_client, "find_tool", lambda s, t: next((x for k, x in tools if k == s and x["name"] == t), None))
    ctx = SimpleNamespace()
    r = asyncio.run(agent_tools.mcp(ctx, {"server": "github", "tool": "list"}, ""))
    assert r.ok and "gh_tool_5" in r.output and "required" in r.output
    r = asyncio.run(agent_tools.mcp(ctx, {"server": "github", "tool": "nope"}, ""))
    assert not r.ok and "gh_tool_0" in r.output
