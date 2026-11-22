"""Round 2026-11-22g: the hardware-report run - a corrupted PDF (save= on an upload), a title leak in the step label,
cut tags, the seam of a continued file, skill tool limits. Every model writes these shapes, not only one."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app import connections as conn
from app.tools import registry  # noqa: F401
from app.tools import agent_tools as at
from app.tools.registry import TOOLS
from app.tools.file_tools import repair_seam
from app.tools.doc_tools import _doc_name
from app.agents.stream_parser import StreamSplitter, parse_tool

H = "<h1>Bilgisayar Donanım Raporu</h1>\n<p>x</p>"


def _ctx(tmp_path):
    return SimpleNamespace(root=Path(tmp_path), mode="full", files_changed=[], step=lambda *a: None)


def _parse(raw):
    sp = StreamSplitter()
    parts = sp.feed("ok " + raw + " done") + sp.flush() if hasattr(sp, "flush") else sp.feed("ok " + raw + " done")
    calls = [parse_tool(t, set(TOOLS)) for k, t in parts if k == "tool"]
    assert calls and calls[0], parts
    return calls[0]


def test_make_doc_tag_shapes_keep_the_title_in_the_body():
    shapes = [
        f'<tool name="make_doc" path="Donanim_Raporu.pdf">{H}</tool>',
        f'<tool name="make_doc"><parameter name="path">Donanim_Raporu.pdf</parameter><parameter name="content">{H}</parameter></tool>',
        f'<tool name="make_doc"><arguments>{{"path": "Donanim_Raporu.pdf"}}</arguments>{H}</tool>',
        f'<tool name="make_doc"><path>Donanim_Raporu.pdf</path>{H}</tool>',
        f'<tool=make_doc path="Donanim_Raporu.pdf">{H}</tool>',
        f'<tool name="make_doc" path="Donanim_Raporu.pdf"\n{H}</tool>',
        f'<tool name="make_doc" path="Donanim_Raporu.pdf" <h1>Bilgisayar Donanım Raporu</h1><p>x</p></tool>',
    ]
    for raw in shapes:
        c = _parse(raw)
        assert c.name == "make_doc", raw
        assert c.args.get("path") == "Donanim_Raporu.pdf", (raw, c.args)
        assert "<h1>Bilgisayar Donanım Raporu</h1>" in c.body, (raw, c.body[:80])
        assert not any("</h1>" in str(v) for v in c.args.values()), (raw, c.args)


def test_doc_name_without_path():
    assert _doc_name({}, H) == "Bilgisayar_Donanım_Raporu.pdf"
    assert _doc_name({"type": "docx", "title": "Aylık rapor"}, "") == "Aylık_rapor.docx"
    assert _doc_name({}, '[{"a": 1}]') == "document.xlsx"
    assert _doc_name({"source": ".doc-sources/Rapor.pdf.partial.md"}, "") == "Rapor.pdf"
    assert _doc_name({}, "# Başlık\nmetin") == "Başlık.pdf"


def test_repair_seam_drops_orphan_and_closes_table():
    old = "<h2>Diskler</h2>\n<table><tbody><tr><td>C:</td></tr>\n"
    new = "content</h2>\n<h2>Ağ</h2><p>x</p>"
    out = repair_seam(old, new)
    assert not out.startswith("content") and out.startswith("</tbody></table>") and "<h2>Ağ</h2>" in out
    assert repair_seam("plain text", "next") == "next"
    # a real closing tag of the line before the seam stays
    assert repair_seam("<p>open <b>bold", "</b> rest</p>").startswith("</b>")


def test_google_save_is_get_only_and_json_never_overwrites_a_pdf(tmp_path, monkeypatch):
    calls = []

    async def fake(method, url, params=None, body=None, raw=None, content_type=""):
        calls.append((method, url))
        return 200, "application/json", b'{"id": "x"}'

    async def fake_up(method, url, params, metadata, path, mime):
        calls.append(("UP", method, url, metadata.get("name")))
        return 200, "application/json", json.dumps({"id": "F1", "name": metadata.get("name"), "size": str(path.stat().st_size),
                                                   "webViewLink": "https://drive.google.com/file/d/F1/view"}).encode()

    monkeypatch.setattr(conn, "google_api", fake)
    monkeypatch.setattr(conn, "google_upload", fake_up)
    ctx = _ctx(tmp_path)
    pdf = Path(tmp_path) / "Rapor.pdf"
    pdf.write_bytes(b"%PDF-1.7 " + b"x" * 5000)
    # a GET whose answer is JSON never lands in a .pdf
    r = asyncio.run(at.google(ctx, {"url": "https://www.googleapis.com/drive/v3/files/F1", "save": "Rapor.pdf"}, ""))
    assert not r.ok and pdf.read_bytes().startswith(b"%PDF")
    # save= on the upload URL (what the weak model did) is turned into a real upload, the PDF stays intact
    r = asyncio.run(at.google(ctx, {"method": "POST", "url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                                    "save": "Rapor.pdf"}, '{"name": "Rapor.pdf"}'))
    assert r.ok and "webViewLink" in r.output and pdf.read_bytes().startswith(b"%PDF"), r.output
    assert calls[-1][0] == "UP" and calls[-1][2].startswith("https://www.googleapis.com/upload/drive/v3/files")
    # file= on the plain Drive URL goes to the upload endpoint; /files/<id> becomes PATCH
    r = asyncio.run(at.google(ctx, {"method": "POST", "url": "https://www.googleapis.com/drive/v3/files/F1", "file": "Rapor.pdf"}, ""))
    assert r.ok and calls[-1][1] == "PATCH" and "/upload/drive/v3/files/F1" in calls[-1][2]
    r = asyncio.run(at.google(ctx, {"method": "POST", "url": "https://www.googleapis.com/upload/drive/v3/files", "file": "yok.pdf"}, ""))
    assert not r.ok and "not found" in r.output


def test_upload_size_mismatch_is_reported(tmp_path, monkeypatch):
    async def fake_up(method, url, params, metadata, path, mime):
        return 200, "application/json", b'{"id": "F", "size": "128"}'

    monkeypatch.setattr(conn, "google_upload", fake_up)
    (Path(tmp_path) / "a.pdf").write_bytes(b"%PDF" + b"0" * 900)
    r = asyncio.run(at.google(_ctx(tmp_path), {"method": "POST", "url": "https://www.googleapis.com/upload/drive/v3/files",
                                               "file": "a.pdf"}, ""))
    assert not r.ok and "128 bytes" in r.output


def test_download_refuses_a_web_page_under_a_binary_name(tmp_path, monkeypatch):
    import asyncio as aio
    import httpx
    from app.tools import web_tools

    def handler(req):
        if req.url.path.endswith("login"):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>Sign in</html>")
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-new")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler),
                                                               **{k: v for k, v in kw.items() if k != "transport"}))

    async def allow(*a, **k):
        return ""
    monkeypatch.setattr(web_tools, "gate", allow)
    ctx = SimpleNamespace(root=Path(tmp_path), mode="full", files_changed=[], cancel=aio.Event(), step=lambda *a: None)
    f = Path(tmp_path) / "r.pdf"
    f.write_bytes(b"%PDF-good")
    r = aio.run(web_tools._download(ctx, "https://x.test/login", "r.pdf"))
    assert not r.ok and "web page" in r.output and f.read_bytes() == b"%PDF-good"
    r = aio.run(web_tools._download(ctx, "https://x.test/file.pdf", "r.pdf"))
    assert r.ok and f.read_bytes() == b"%PDF-new"


def test_skill_base_tools_always_allowed():
    from app.agents.orchestrator import SKILL_BASE
    assert {"run", "list_dir", "read_file", "write_file", "system_info", "use_skill"} <= SKILL_BASE
    assert SKILL_BASE <= set(TOOLS) | {"todo", "need_tools", "use_skill"}
