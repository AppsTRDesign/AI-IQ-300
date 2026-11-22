"""Built-in google tool (Google REST APIs with the connected account) - no network: the API call is faked.
Run: python -m pytest tests/test_google_tool.py"""
import asyncio
import base64
import email
import json
from pathlib import Path
from types import SimpleNamespace

from app import connections as conn
from app.tools import registry  # noqa: F401  (loads agent_tools in order)
from app.tools import agent_tools as at


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_gmail_message_readable():
    m = {"id": "1", "threadId": "t", "labelIds": ["UNREAD"], "snippet": "hi",
         "payload": {"mimeType": "multipart/mixed", "headers": [{"name": "From", "value": "a@b.c"}, {"name": "Subject", "value": "Fatura"}],
                     "parts": [{"mimeType": "multipart/alternative", "parts": [
                         {"mimeType": "text/plain", "body": {"data": _b64("Merhaba, fatura ekte.")}},
                         {"mimeType": "text/html", "body": {"data": _b64("<p>Merhaba</p>")}}]},
                         {"mimeType": "application/pdf", "filename": "f.pdf", "body": {"attachmentId": "A1", "size": 10}}]}}
    out = at.gmail_message(m)
    assert out["from"] == "a@b.c" and out["subject"] == "Fatura" and out["text"] == "Merhaba, fatura ekte."
    assert out["attachments"][0]["attachmentId"] == "A1"
    html_only = {"id": "2", "payload": {"mimeType": "text/html", "body": {"data": _b64("<style>x{}</style><b>Selam</b> dünya")}}}
    assert at.gmail_message(html_only)["text"] == "Selam dünya"


def test_gmail_raw_builds_the_mail():
    raw = at.gmail_raw({"to": ["x@y.z", "q@w.e"], "subject": "Konu ğ", "text": "Gövde", "threadId": "T"})
    assert raw["threadId"] == "T"
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw["raw"] + "=" * (-len(raw["raw"]) % 4)))
    assert msg["To"] == "x@y.z, q@w.e" and "Konu" in str(email.header.make_header(email.header.decode_header(msg["Subject"])))
    assert at.gmail_raw({"raw": "abc"}) == {"raw": "abc"}


def _ctx(tmp_path):
    return SimpleNamespace(root=Path(tmp_path), mode="full", files_changed=[], step=lambda *a: None)


def test_google_tool_needs_connection(tmp_path):
    r = asyncio.run(at.google(_ctx(tmp_path), {"url": "https://gmail.googleapis.com/gmail/v1/users/me/messages"}, ""))
    assert not r.ok and "Settings > Connections" in r.output


def test_google_tool_calls(tmp_path, monkeypatch):
    seen = []

    async def fake(method, url, params=None, body=None, raw=None, content_type=""):
        seen.append((method, url, params, body))
        if "/drafts" in url:
            return 200, "application/json", b'{"id": "d1"}'
        if "export" in url:
            return 200, "text/plain", "Fatura 1250 TL".encode()
        if ("alt", "media") in (params or []):
            return 200, "application/pdf", b"%PDF-1"
        if "/messages/" in url:
            return 200, "application/json", json.dumps({"id": "9", "payload": {"mimeType": "text/plain", "headers": [
                {"name": "Subject", "value": "S"}], "body": {"data": _b64("metin")}}}).encode()
        return 403, "application/json", b'{"error": {"message": "Request had insufficient authentication scopes."}}'
    monkeypatch.setattr(conn, "google_connected", lambda: True)
    monkeypatch.setattr(conn, "google_api", fake)
    ctx = _ctx(tmp_path)
    r = asyncio.run(at.google(ctx, {"url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/9?format=full"}, ""))
    assert r.ok and json.loads(r.output)["text"] == "metin"
    assert seen[-1][2] == [("format", "full")]  # the query string goes as params
    r = asyncio.run(at.google(ctx, {"method": "POST", "url": "https://gmail.googleapis.com/gmail/v1/users/me/drafts"},
                              '{"to": "a@b.c", "subject": "S", "text": "T"}'))
    assert r.ok and set(seen[-1][3]) == {"message"} and "raw" in seen[-1][3]["message"]
    r = asyncio.run(at.google(ctx, {"url": "https://www.googleapis.com/drive/v3/files/F/export?mimeType=text/plain"}, ""))
    assert r.output == "Fatura 1250 TL"
    r = asyncio.run(at.google(ctx, {"url": "https://www.googleapis.com/drive/v3/files/F?alt=media", "save": "out/f.pdf"}, ""))
    assert r.ok and (Path(tmp_path) / "out" / "f.pdf").read_bytes() == b"%PDF-1" and ctx.files_changed == ["out/f.pdf"]
    r = asyncio.run(at.google(ctx, {"url": "https://www.googleapis.com/calendar/v3/users/me/calendarList"}, ""))
    assert not r.ok and "Reconnect" in r.output


def test_google_api_only_google_hosts():
    import pytest
    with pytest.raises(conn.ConnError):
        asyncio.run(conn.google_api("GET", "https://evil.example.com/x"))
    with pytest.raises(conn.ConnError):
        asyncio.run(conn.google_api("GET", "http://gmail.googleapis.com/x"))


def test_google_mcp_servers_hidden_and_redirected(tmp_path, monkeypatch):
    from app import mcp_client
    srv = mcp_client.Server("google-drive", {"transport": "http", "url": "https://drivemcp.googleapis.com/mcp/v1", "managed": "google"})
    srv.tools = [{"name": "search_files", "inputSchema": {}}]
    other = mcp_client.Server("time", {"transport": "stdio", "command": "x"})
    other.tools = [{"name": "now", "inputSchema": {}}]
    monkeypatch.setattr(mcp_client, "_servers", {"google-drive": srv, "time": other})
    monkeypatch.setattr(mcp_client.Server, "alive", property(lambda self: True), raising=False)
    # Google accepts the project (Developer Preview): the MCP servers are shown like any other
    monkeypatch.setattr(conn, "google_mcp_blocked", lambda: False)
    assert "google-drive/search_files" in mcp_client.prompt_section("dosyalarımı ara")
    # Google refuses them: hidden, and a call from the history is sent to the google tool
    monkeypatch.setattr(conn, "google_mcp_blocked", lambda: True)
    sec = mcp_client.prompt_section("dosyalarımı ara")
    assert "time/now" in sec and "google-drive" not in sec
    r = asyncio.run(at.mcp(_ctx(tmp_path), {"server": "google-drive", "tool": "search_files"}, '{"query": "x"}'))
    assert not r.ok and "built-in `google` tool" in r.output


def test_google_write_needs_a_body(tmp_path, monkeypatch):
    monkeypatch.setattr(conn, "google_connected", lambda: True)
    r = asyncio.run(at.google(_ctx(tmp_path), {"method": "POST", "url": "https://sheets.googleapis.com/v4/spreadsheets"}, ""))
    assert not r.ok and "body argument" in r.output
    r = asyncio.run(at.google(_ctx(tmp_path), {"method": "PUT", "url": "https://sheets.googleapis.com/v4/spreadsheets/x/values/A1"}, "{}"))
    assert not r.ok


def test_mcp_blocked_flag(monkeypatch):
    store = {}
    monkeypatch.setattr(conn, "_load", lambda name: dict(store.get(name, {"refresh_token": "r"})))
    monkeypatch.setattr(conn, "_store", lambda name, d: store.__setitem__(name, d))
    assert not conn.google_mcp_blocked()
    conn.google_mcp_seen(True)
    assert conn.google_mcp_blocked()
    conn.google_mcp_seen(False)
    assert not conn.google_mcp_blocked()


def test_google_group_words():
    from app.agents.checks import GROUP_WORDS
    for text in ("son 10 okunmamış e-postamı özetle", "bu haftaki takvimim", "Drive'da fatura geçen dosyalar"):
        assert GROUP_WORDS["google"].search(text)
