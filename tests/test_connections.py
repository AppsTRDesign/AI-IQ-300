"""Settings > Connections (GitHub / Google / Microsoft): what can be checked without the services themselves.
Run: python -m pytest tests/test_connections.py"""
import asyncio
import shutil
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from app import connections as conn


def test_google_client_and_sign_in_url():
    with pytest.raises(conn.ConnError):
        conn.google_client("not-a-client", "x")
    st = conn.google_client("123-abc.apps.googleusercontent.com", "GOCSPX-secret")
    assert st["client_set"] and not st["connected"]
    url = conn.google_start("http://127.0.0.1:8300/api/connections/google/callback", ["gmail", "calendar", "nope"])
    q = parse_qs(urlsplit(url).query)
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"] and q["code_challenge_method"] == ["S256"]
    scopes = q["scope"][0].split()
    assert "https://www.googleapis.com/auth/gmail.modify" in scopes and "https://www.googleapis.com/auth/calendar.events" in scopes
    assert not any("drive" in s for s in scopes)  # only the chosen services ask for access
    assert conn._GOOGLE_PENDING[q["state"][0]]["services"] == ["gmail", "calendar"]
    # every chosen service's product API and MCP API, in the client's own project
    url = conn.google_enable_url("1063276280060-abc.apps.googleusercontent.com", ["calendar", "people"])
    assert url == ("https://console.cloud.google.com/flows/enableapi?apiid=calendar-json.googleapis.com,"
                   "calendarmcp.googleapis.com,people.googleapis.com&project=1063276280060")
    assert conn.google_status()["enable_url"].endswith("&project=123")


def test_http_mcp_answer_with_error_status_is_used(monkeypatch):
    """Google's Workspace MCP servers send the tool list with HTTP 403: it must not be thrown away."""
    from app import mcp_client
    from app.llm import providers

    class Resp:
        status_code, headers = 403, {"content-type": "application/json"}
        async def aread(self):
            return b'{"id": 7, "jsonrpc": "2.0", "result": {"tools": [{"name": "list_events"}]}}'
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def stream(self, *a, **k): return Resp()
    monkeypatch.setattr(providers, "pooled", lambda **k: Client())
    srv = mcp_client.Server("g", {"transport": "http", "url": "https://x/mcp", "headers": {"Authorization": "Bearer t"}})
    res = asyncio.run(srv._http({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}))
    assert res["tools"][0]["name"] == "list_events"


def test_github_helpers():
    assert conn._slug("https://github.com/Owner/Repo.git") == "owner/repo"
    assert conn._slug("git@github.com:owner/repo") == "owner/repo"
    assert conn._slug("https://gitlab.com/a/b.git") == ""
    a = conn._auth_args("tok")
    assert "credential.helper=" in a and any(x.startswith("http.https://github.com/.extraheader=AUTHORIZATION: basic ") for x in a)
    assert not conn.github_status()["connected"]
    with pytest.raises(conn.ConnError):
        asyncio.run(conn.github_repos())


@pytest.mark.skipif(not shutil.which("git"), reason="git not installed")
def test_project_update_from_remote(tmp_path):
    from app import workspace

    def git(cwd, *a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True)
    remote, work, other = tmp_path / "remote.git", tmp_path / "work", tmp_path / "other"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "clone", str(remote), str(work))
    (work / "a.txt").write_text("1")
    git(work, "add", "-A"); git(work, "commit", "-m", "one"); git(work, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(other))
    proj = workspace.create_project("work", str(work))
    # a github.com origin makes it a GitHub project in the list
    git(work, "remote", "add", "gh", "https://github.com/o/r.git")
    (other / "b.txt").write_text("2")
    git(other, "add", "-A"); git(other, "commit", "-m", "two"); git(other, "push", "origin", "main")
    st = asyncio.run(conn.project_git(proj["id"]))
    assert st["ok"] and st["behind"] == 1 and st["dirty"] == 0
    (work / "a.txt").write_text("local edit")
    with pytest.raises(conn.ConnError) as e:
        asyncio.run(conn.project_pull(proj["id"]))
    assert e.value.code == "git_dirty"
    r = asyncio.run(conn.project_pull(proj["id"], stash=True))
    assert r["updated"] == 1 and r["behind"] == 0 and (work / "b.txt").is_file()
    assert (work / "a.txt").read_text() == "local edit"  # the user's change came back after the update
