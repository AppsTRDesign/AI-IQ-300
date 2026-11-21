"""Round 2026-11-21: skill tool companions (doc_template with /docs), date in system_info, more templates and styles,
KPI fit, landscape PDF, gateway providers on their own addresses, calmer stall thresholds."""
import asyncio
import json

from app.agents import orchestrator, streaming
from app.tools import doc_templates as dt
from app.tools import docs_gen, sysinfo
from app import config


def test_docs_skill_brings_doc_template():
    assert "doc_template" in orchestrator.SKILL_COMPANIONS["make_doc"]
    from app.agents import catalog
    tools = set(catalog.skills()["docs"]["tools"])
    assert {"doc_template", "read_document", "make_doc"} <= tools


def test_system_info_has_now():
    d = json.loads(sysinfo.report("now"))["now"]
    assert len(d["date"]) == 10 and d["year"] >= 2025 and d["weekday"] and ":" in d["time"]
    assert d["tr"].split()[1] in ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül",
                                  "Ekim", "Kasım", "Aralık")


def test_more_templates_and_styles():
    assert len(dt.BUILTIN) >= 30
    for k in dt.KINDS:
        assert len(dt.all_templates(k)) >= 8
    dt.register()
    css = docs_gen._css("annual_report")
    assert "counter(sec" in css and "border-bottom: 1.5pt solid" in css  # numbered headings, line tables
    assert "border-left: 14pt solid" in docs_gen._css("case_study")  # split cover
    for t in dt.BUILTIN:
        for k in t["kinds"]:
            assert t["colors"][0] in dt.preview_html(t, "en", k)
        assert t.get("cover", "hero") in dt.COVERS


def test_user_template_keeps_valid_styles(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "USER_DIR", tmp_path / "t")
    t = dt.save_user({"id": "mine", "kinds": ["pdf"], "colors": ["#123456", "#000000", "#ffffff"], "cover": "weird",
                      "h2": "number", "table": "nope"})
    assert t["cover"] == "hero" and t["h2"] == "number" and "table" not in t


def test_reference_analysis_finds_the_palette(tmp_path):
    dt.register()
    out = tmp_path / "ref.pdf"
    asyncio.run(docs_gen.generate("pdf", "<h1>Marka</h1><p>x</p><h2>Bölüm</h2><table><thead><tr><th>a</th></tr></thead>"
                                         "<tr><td>1</td></tr></table>", out, theme="case_study"))
    info = dt.analyze_reference(out)
    assert info["palette"]["accent"] == "#0f766e" and info["font_suggestion"] == "sans"
    assert info["cover_hint"].startswith("split")


def test_kpi_long_value_gets_smaller():
    out = docs_gen._kpi_fit('<div class="kpis"><div class="kpi"><span>CPU</span><b>AMD Radeon RX 580 2048SP</b></div>'
                            '<div class="kpi"><span>RAM</span><b>32 GB</b></div></div>')
    assert '<b class="long">AMD Radeon' in out and "<b>32 GB</b>" in out


def test_landscape_pdf_is_landscape(tmp_path):
    import pypdfium2 as pdfium
    out = tmp_path / "w.pdf"
    asyncio.run(docs_gen.generate("pdf", "<h1>T</h1><p>x</p>", out, landscape=True))
    w, h = pdfium.PdfDocument(str(out))[0].get_size()
    assert w > h


def test_gateway_providers_have_direct_urls():
    s = config.load_settings()["providers"]
    assert s["minimax"]["base_url"].startswith("https://api.minimax")
    assert s["zai"]["base_url"].startswith("https://api.z.ai")
    assert s["bedrock"]["base_url"].startswith("http://127.0.0.1:4000")  # still through a gateway


def test_stall_thresholds_follow_slow_batched_streams():
    # EVREN sends a file's arguments in batches 5-12 s apart: the connection check must not cut it at 30-48 s
    assert streaming.PROBE_CUT >= 90 and streaming.MIDCALL_STALL >= 150 and streaming.PROBE_AFTER >= 30


# --- second part of the round: weak models, loops, broken PDFs, real layouts -----------------------------------------

def test_request_core_drops_app_instructions():
    from app.agents.checks import request_steps, request_parts
    t = ('/docs PDF: [Şablon: X — make_doc template="x" - design only] **Senden istediklerim;**\n'
         "1.) donanımı bul\n2.) araçları listele\n3.) skilleri yaz\n4.) rapor oluştur")
    assert request_steps(t) == ["donanımı bul", "araçları listele", "skilleri yaz", "rapor oluştur"]
    assert request_parts(t) == []


def test_list_loop_is_cut():
    from app.agents.guards import _loop_cut
    items = ["browser_screenshot", "browser_navigate", "browser_inspect", "browser_wait", "browser_tabs"]
    text = "Tools: list_dir, read_file, " + ", ".join(items * 30)
    cut = _loop_cut(text)
    assert cut is not None and cut.count("browser_navigate") == 1
    assert _loop_cut("Paketler: " + ", ".join(f"pkg{i} 1.{i}" for i in range(200))) is None


def test_filler_and_sample_outline_are_refused():
    import app.tools.registry  # noqa: F401  (import order of the tool modules)
    from app.tools.doc_tools import filler_problem
    para = "Bilgisayar donanımı ve yazılım ortamı hakkında bilgi verilmesi gerekmektedir, ayrıntılı olarak."
    md = "# T\n\n" + "".join(f"## {h}\n\n{para}\n\n" for h in ("Problem", "Kapsam", "Bütçe", "Ekip"))
    assert "repeated" in filler_problem(md)
    md2 = "# T\n\n## Problem\n\n" + "a" * 70 + "\n\n## Kapsam\n\n" + "b" * 70 + "\n\n## Ekip\n\n" + "c" * 70
    assert "sample sections" in filler_problem(md2, ["Problem", "Kapsam", "Ekip", "Bütçe"])
    assert filler_problem("# D\n\n## CPU\n\n" + "a" * 80 + "\n\n## RAM\n\n" + "b" * 80, ["Problem", "Kapsam", "Ekip"]) == ""


def test_broken_font_map_letters_are_voted_back():
    from app.tools import docread
    text = "Millî Eğ�t�m Akadem�s� tarafından kullanılacak f�z�k� belge " * 3
    bad = docread.broken_chars(text)
    assert "�" in bad
    fixed, mapping = docread.repair_glyphs(text, "Millî Eğitim Akademisi tarafından kullanılacak fiziki belge", bad, "tr")
    assert mapping == {"�": "i"} and "Eğitim Akademisi" in fixed and "fiziki" in fixed
    sinhala = "Mඈllî Eğඈtඈm Akademඈsඈ tarafından kullanılacak fඈzඈkඈ/elektronඈk belge şablonudur " * 2
    assert "ඈ" in docread.broken_chars(sinhala)


def test_same_answer_again_is_detected():
    a = ("Rapor PDF formatında oluşturuldu. Raporun içeriği şu şekilde: 1. Problem 2. Önerilen çözüm 3. Kapsam "
         "4. Takvim 5. Bütçe 6. Ekip. Raporun tamamı rapor.pdf dosyasında kaydedilmiştir.")
    assert orchestrator._same_as_before(a + " Başlıklar güncellendi.", [{"role": "assistant", "content": a}])
    assert not orchestrator._same_as_before("Tamamen farklı bir cevap metni " * 6, [{"role": "assistant", "content": a}])


def test_layouts_build_their_own_first_part():
    dt.register()
    body = "<h1>Basın Duyurusu</h1><p>Kısa.</p><h2>A</h2><p>x</p>"
    hero = lambda h, lang: "HERO" + h  # noqa: E731
    assert dt.layout_body(dt.get("project_proposal"), body, "tr", hero).startswith("HERO")
    letter = dt.layout_body(dt.get("official_letter"), body, "tr", hero)
    assert 'class="lh"' in letter and 'class="doc-date"' in letter and letter.index("doc-date") < letter.index("doc-title")
    assert 'class="memo"' in dt.layout_body(dt.get("investment_memo"), body, "tr", hero)
    assert dt.page_options(dt.get("official_letter"))["margin"]["left"] == "25.0mm"
    assert {t.get("layout") for t in dt.BUILTIN} >= {"report", "letter", "memo", "academic", "magazine", "invoice", "resume", "minimal"}
    assert "clean" in dt.clean_css("@import url(http://x); .a{background:url(https://x/y.png)} /* clean */")
    assert "http" not in dt.clean_css("@import url(http://x); .a{background:url(https://x/y.png)}")


# --- v0.18.2 --------------------------------------------------------------------------------------------------------

def test_foreign_stems_do_not_hit_turkish_words():
    from app.agents.checks import VISUAL_ASK, SMALL_TALK
    assert VISUAL_ASK.search("müşterilere bakım olacağını bildiren kısa bir resmî yazı") is None
    assert VISUAL_ASK.search("raporda bir grafik olsun") and VISUAL_ASK.search("Erstelle einen Bericht mit einem Bild")
    assert SMALL_TALK.search("hallo") and SMALL_TALK.search("merhaba")


def test_xlsx_designs_frame_the_table(tmp_path):
    import openpyxl
    dt.register()
    rows = [{"Ay": "Ocak", "Ziyaretçi": 3100}, {"Ay": "Şubat", "Ziyaretçi": 3500}, {"Ay": "Toplam", "Ziyaretçi": 6600}]
    out = tmp_path / "d.xlsx"
    asyncio.run(docs_gen.generate("xlsx", json.dumps({"title": "Pano", "sheets": {"S": rows}}), out, theme="analytics_dashboard"))
    ws = openpyxl.load_workbook(out).worksheets[0]
    assert ws["A1"].value == "Pano" and ws["A5"].value == "=SUM(B8:B9)" and len(ws._charts) == 1  # own total left out
    cal = tmp_path / "c.xlsx"
    asyncio.run(docs_gen.generate("xlsx", json.dumps({"sheets": {"E": [{"Etkinlik": "Fuar", "Tarih": "2026-03-10"}]}}),
                                  cal, theme="operating_calendar"))
    assert openpyxl.load_workbook(cal).sheetnames[0] in ("Takvim", "Calendar")


def test_thumbnails_differ_per_layout():
    pages = {t["id"]: dt.preview_html(t, "tr", "xlsx") for t in dt.all_templates("xlsx")}
    assert "polyline" in pages["analytics_dashboard"] and "Ocak" in pages["operating_calendar"]
    assert len(set(pages.values())) == len(pages)
    assert "Kalem" in dt._sample_html(dt.get("price_quote"), "tr") and "Ad Soyad" in dt._sample_html(dt.get("resume"), "tr")


def test_letter_lines_per_document_and_no_placeholders():
    dt.register()
    assert not dt.get("official_letter").get("header")  # the sample letterhead is only for the thumbnail
    tid = dt.with_lines("official_letter", "ABC Yazılım A.Ş. | Bilgi İşlem", "Ankara | abc.com.tr")
    assert tid != "official_letter" and docs_gen.TEMPLATE_SPEC[tid]["header"] == ["ABC Yazılım A.Ş.", "Bilgi İşlem"]
