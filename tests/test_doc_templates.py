"""Document templates: listed per format, registered as make_doc themes, user ones saved / deleted, real output."""
import asyncio

from app.tools import doc_templates as dt
from app.tools import docs_gen


def test_every_format_has_templates():
    for kind in ("pdf", "docx", "xlsx", "pptx"):
        assert len(dt.all_templates(kind)) >= 3
    t = dt.get("design_report")
    assert dt.text(t, "name", "tr") == "Tasarım Raporu" and dt.text(t, "name", "en") == "Design Report"
    assert 'template="design_report"' in dt.instruction(t, "en")


def test_register_makes_themes_and_css():
    dt.register()
    assert docs_gen.THEMES["market_trends"] == tuple(dt.get("market_trends")["colors"])
    assert "Georgia" in docs_gen._css("design_report")  # serif template
    assert "Georgia" not in docs_gen._css("corporate")


def test_previews_are_html_for_each_kind():
    for t in dt.all_templates():
        for k in t["kinds"]:
            page = dt.preview_html(t, "tr", k)
            assert page.startswith("<!doctype html>") and t["colors"][0] in page


def test_user_template_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "USER_DIR", tmp_path / "tpl")
    saved = dt.save_user({"id": "my_brand", "kinds": ["pdf", "pptx"], "colors": ["#123456", "#0b1d2e", "#eef3f8"],
                          "font": "serif", "cover": "band", "name": {"tr": "Markam"}, "outline": {"tr": ["A", "B"]}})
    assert saved["id"] == "my_brand" and dt.get("my_brand")["user"]
    assert "my_brand" in docs_gen.THEMES
    try:
        dt.save_user({"id": "design_report", "kinds": ["pdf"], "colors": ["#000000", "#000000", "#ffffff"]})
        raise AssertionError("a built-in id must be refused")
    except ValueError:
        pass
    assert dt.delete_user("my_brand") and not dt.get("my_brand")


def test_template_document_is_written(tmp_path):
    dt.register()
    out = tmp_path / "r.docx"
    info = asyncio.run(docs_gen.generate("docx", "<h1>Rapor</h1><h2>Özet</h2><p>Metin.</p>", out, theme="investment_memo"))
    assert out.stat().st_size > 2000 and info
    x = tmp_path / "b.xlsx"
    asyncio.run(docs_gen.generate("xlsx", '[{"Ay": "Ocak", "Gelir": 100}]', x, theme="financial_budget"))
    assert x.stat().st_size > 1000
