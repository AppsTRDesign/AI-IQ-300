"""Round 2026-11-22f: nested tags in an mcp call, unquoted argv lists, GitHub words."""
import asyncio

from app.agents.stream_parser import attrs
from app import mcp_client
from app.tools import agent_tools


def test_unquoted_list_attribute():
    got = attrs(' name="run" argv=["git","log","--oneline","-3"]')
    assert got["argv"] == '["git","log","--oneline","-3"]'
    assert attrs(' a="" b=\'x\'') == {"a": "", "b": "x"}


def test_unquoted_object_attribute_and_wrapped_body():
    got = attrs(' name="mcp" server="github" tool="issue_read" arguments={"owner": "a", "repo": "b", "n": {"x": 1}}')
    assert got["arguments"] == '{"owner": "a", "repo": "b", "n": {"x": 1}}' and got["server"] == "github"
    assert agent_tools.unwrap_arg('<argument name="body">{"to": "me"}</argument>') == '{"to": "me"}'
    assert agent_tools.unwrap_arg('<argument name="body">{"a": 1}') == '{"a": 1}'
    assert agent_tools.unwrap_arg('{"a": 1}') == '{"a": 1}'


def test_arguments_wrapper():
    from app.agents.tooling import _unwrap_args
    w = '<arguments>\n{"owner": "a", "repo": "b", "per_page": 3}\n</arguments>'
    assert agent_tools.unwrap_arg(w) == '{"owner": "a", "repo": "b", "per_page": 3}'
    a, b = _unwrap_args("mcp", {"server": "github", "tool": "list_commits"}, w)
    assert b.startswith("{") and a == {"server": "github", "tool": "list_commits"}
    a, b = _unwrap_args("fetch_url", {"url": "<arguments>"}, '<arguments>{"url": "https://x.dev"}</arguments>')
    assert a == {"url": "https://x.dev"} and b == ""
    a, b = _unwrap_args("write_file", {"path": "a.txt"}, "plain text")
    assert a == {"path": "a.txt"} and b == "plain text"


def test_mcp_body_with_other_tool_tag(tmp_path):
    class Ctx:
        root = tmp_path
    res = asyncio.run(agent_tools.mcp(Ctx(), {"server": "git", "tool": "get_issue"},
                                      '<tool name="run" argv=["git","log","-3"]'))
    assert not res.ok and "`run`" in res.output


def test_github_words(monkeypatch):
    class S:
        alive = True
    monkeypatch.setattr(mcp_client, "_servers", {"github": S(), "git": S()})
    monkeypatch.setattr(mcp_client, "hidden_servers", lambda: set())
    assert "github" in mcp_client.named_servers("AI-IQ-300 deposundaki 1 numaralı issue'yu göster")
    assert "github" in mcp_client.named_servers("açık pull request'leri listele")
    assert "github" not in mcp_client.named_servers("Python'da liste nasıl sıralanır?")
