"""Round 2026-11-22d (Playwright MCP run): argument names repaired, files the MCP server saved reach the working folder.
Run: python -m pytest tests/test_round_1122d.py"""
from types import SimpleNamespace

from app import mcp_client
from app.tools import agent_tools as at


def test_mcp_argument_aliases_and_defaults():
    click = {"properties": {"element": {"type": "string"}, "target": {"type": "string"}}, "required": ["target"]}
    args, fixed = at.mcp_repair(click, {"ref": "e19"})
    assert args == {"target": "e19"} and fixed == ["ref -> target"]
    shot = {"properties": {"filename": {"type": "string"}, "fullPage": {"type": "boolean"},
                           "scale": {"type": "string", "enum": ["css", "device"], "default": "css"}},
            "required": ["scale"]}
    args, _ = at.mcp_repair(shot, {"path": "a.png", "fullPage": True})
    assert args["scale"] == "css" and args["path"] == "a.png"  # path is not required here: left alone
    ev = {"properties": {"function": {"type": "string"}}, "required": ["function"]}
    args, _ = at.mcp_repair(ev, {"expression": "document.title"})
    assert args == {"function": "() => (document.title)"}
    args, _ = at.mcp_repair(ev, {"script": "() => 1"})
    assert args == {"function": "() => 1"}
    # an argument the tool really has is never renamed
    own = {"properties": {"ref": {}, "target": {}}, "required": ["target"]}
    assert at.mcp_repair(own, {"ref": "x"})[0] == {"ref": "x"}


def test_mcp_arguments_as_models_write_them():
    assert at.mcp_args('{"query": "name contains \\\'fatura\\\'"}') == {"query": "name contains 'fatura'"}
    assert at.mcp_args('```json\n{"a": 1,}\n```') == {"a": 1}
    assert at.mcp_args("{'a': true}") == {"a": True}
    assert at.mcp_args("") == {}
    import pytest
    with pytest.raises(ValueError):
        at.mcp_args("name contains fatura")


def test_google_preview_error_explained():
    out = at.mcp_known_error("google-gmail", "Access to this tool requires that your Google Cloud project (1) is "
                             "enrolled in the Google Workspace Developer Preview Program. Please see ...")
    assert "not a scope or sign-in problem" in out
    assert "Developer Preview" in at.mcp_known_error("google-drive", "The caller does not have permission")
    assert at.mcp_known_error("github", "The caller does not have permission") == "The caller does not have permission"


def test_mcp_saved_files_copied_into_working_folder(tmp_path, monkeypatch):
    server_home, work = tmp_path / "srv", tmp_path / "work"
    (server_home / ".playwright-mcp").mkdir(parents=True)
    work.mkdir()
    (server_home / ".playwright-mcp" / "page-1.png").write_bytes(b"png")
    monkeypatch.setattr(mcp_client, "server_dir", lambda s: str(server_home))
    out = ("### Result\n- [Screenshot of full page](.playwright-mcp\\page-1.png)\n"
           "path: '.playwright-mcp\\\\page-1.png',\n- [Snapshot](.playwright-mcp\\missing.yml)")
    res = at.mcp_files_home(SimpleNamespace(root=work), "playwright", out)
    assert (work / ".playwright-mcp" / "page-1.png").read_bytes() == b"png"
    assert "copied into the working folder: .playwright-mcp/page-1.png]" in res
    # no stdio home (http server): unchanged
    monkeypatch.setattr(mcp_client, "server_dir", lambda s: None)
    assert at.mcp_files_home(SimpleNamespace(root=work), "x", out) == out
