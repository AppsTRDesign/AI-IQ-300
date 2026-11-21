"""Document templates for make_doc: a look (colours, type, cover style) plus the structure a document of that kind
should have (its sections / sheets / slides). Built-in ones per format, and the user's own made by the Template
Creator (the doc_template tool, after looking at a reference file) in data/doc_templates/*.json.

A template id doubles as a make_doc theme: register() puts its colours into docs_gen.THEMES (so PDF, DOCX, PPTX and
XLSX all use them) and its extra CSS into docs_gen.TEMPLATE_CSS (PDF / HTML type and cover)."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..config import DATA_DIR

USER_DIR = DATA_DIR / "doc_templates"
KINDS = ("pdf", "docx", "xlsx", "pptx")

# id, kinds, colours (accent, dark, tint), font (sans | serif), cover (band | hero | minimal | dark), names, outline
BUILTIN: list[dict] = [
    {"id": "design_report", "kinds": ["pdf", "docx"], "colors": ["#2F5D50", "#1B332C", "#EEF3F0"], "font": "serif",
     "cover": "photo", "name": {"tr": "Tasarım Raporu", "en": "Design Report"},
     "desc": {"tr": "Fotoğraflı kapak, bulgular ve öneriler", "en": "Photo cover, findings and recommendations"},
     "outline": {"tr": ["Özet", "Bağlam ve hedefler", "Araştırma bulguları", "Tasarım önerileri", "Sonraki adımlar"],
                 "en": ["Summary", "Context and goals", "Research findings", "Design recommendations", "Next steps"]}},
    {"id": "experiment_analysis", "kinds": ["pdf", "docx"], "colors": ["#1E6B3A", "#0F3D21", "#EEF6F0"], "font": "serif",
     "cover": "minimal", "name": {"tr": "Deney Analizi", "en": "Experiment Analysis"},
     "desc": {"tr": "Hipotez, yöntem, sonuçlar ve istatistik", "en": "Hypothesis, method, results and statistics"},
     "outline": {"tr": ["Hipotez", "Yöntem", "Sonuçlar", "İstatistiksel anlamlılık", "Karar"],
                 "en": ["Hypothesis", "Method", "Results", "Statistical significance", "Decision"]}},
    {"id": "investment_memo", "kinds": ["pdf", "docx"], "colors": ["#111827", "#000000", "#F3F4F6"], "font": "sans",
     "cover": "band", "name": {"tr": "Yatırım Komitesi Notu", "en": "Investment Committee Memo"},
     "desc": {"tr": "Kısa karar notu: tez, riskler, öneri", "en": "A short decision memo: thesis, risks, recommendation"},
     "outline": {"tr": ["Öneri", "Yatırım tezi", "Finansal özet", "Riskler ve azaltma", "Karar"],
                 "en": ["Recommendation", "Investment thesis", "Financial summary", "Risks and mitigation", "Decision"]}},
    {"id": "project_proposal", "kinds": ["pdf", "docx"], "colors": ["#2563EB", "#1E3A8A", "#EFF4FF"], "font": "sans",
     "cover": "hero", "name": {"tr": "Proje Teklifi", "en": "Project Proposal"},
     "desc": {"tr": "Kapsam, takvim, bütçe ve ekip", "en": "Scope, timeline, budget and team"},
     "outline": {"tr": ["Problem", "Önerilen çözüm", "Kapsam", "Takvim", "Bütçe", "Ekip"],
                 "en": ["Problem", "Proposed solution", "Scope", "Timeline", "Budget", "Team"]}},
    {"id": "meeting_notes", "kinds": ["pdf", "docx"], "colors": ["#7C3AED", "#4C1D95", "#F5F3FF"], "font": "sans",
     "cover": "minimal", "name": {"tr": "Toplantı Notları", "en": "Meeting Notes"},
     "desc": {"tr": "Katılımcılar, kararlar, aksiyonlar", "en": "Attendees, decisions, action items"},
     "outline": {"tr": ["Katılımcılar", "Gündem", "Kararlar", "Aksiyonlar (kim, ne, ne zaman)"],
                 "en": ["Attendees", "Agenda", "Decisions", "Action items (who, what, when)"]}},
    {"id": "resume", "kinds": ["pdf", "docx"], "colors": ["#0D9488", "#134E4A", "#F0FDFA"], "font": "sans",
     "cover": "band", "name": {"tr": "Özgeçmiş", "en": "Résumé"},
     "desc": {"tr": "Tek sayfa, net ve taranabilir", "en": "One page, clear and scannable"},
     "outline": {"tr": ["Profil", "Deneyim", "Eğitim", "Yetenekler", "Projeler"],
                 "en": ["Profile", "Experience", "Education", "Skills", "Projects"]}},
    {"id": "analytics_dashboard", "kinds": ["xlsx"], "colors": ["#0EA5E9", "#0B1220", "#E0F2FE"], "font": "sans",
     "cover": "dark", "name": {"tr": "Analitik Panosu", "en": "Analytics Dashboard"},
     "desc": {"tr": "KPI satırı, aylık trend, kanal kırılımı", "en": "KPI row, monthly trend, channel breakdown"},
     "outline": {"tr": ["Özet (KPI'lar)", "Aylık trend", "Kanallar", "Ham veri"],
                 "en": ["Summary (KPIs)", "Monthly trend", "Channels", "Raw data"]}},
    {"id": "financial_budget", "kinds": ["xlsx"], "colors": ["#1F4E79", "#0F2A44", "#EEF3F8"], "font": "sans",
     "cover": "band", "name": {"tr": "Finansal Bütçe", "en": "Financial Budget"},
     "desc": {"tr": "Gelir, gider, tahmin ve sapma", "en": "Revenue, costs, forecast and variance"},
     "outline": {"tr": ["Özet", "Aylık bütçe", "Gerçekleşen ve sapma", "Varsayımlar"],
                 "en": ["Summary", "Monthly budget", "Actual vs variance", "Assumptions"]}},
    {"id": "operating_calendar", "kinds": ["xlsx"], "colors": ["#EA580C", "#7C2D12", "#FFF7ED"], "font": "sans",
     "cover": "band", "name": {"tr": "Çalışma Takvimi", "en": "Operating Calendar"},
     "desc": {"tr": "Ay ay takvim, etkinlik ve sorumlular", "en": "Month-by-month calendar, events and owners"},
     "outline": {"tr": ["Yıllık görünüm", "Ocak – Aralık", "Etkinlik listesi"],
                 "en": ["Year view", "January – December", "Event list"]}},
    {"id": "project_tracker", "kinds": ["xlsx"], "colors": ["#059669", "#064E3B", "#ECFDF5"], "font": "sans",
     "cover": "band", "name": {"tr": "Proje Takibi", "en": "Project Tracker"},
     "desc": {"tr": "Görevler, sorumlu, durum, tarih", "en": "Tasks, owner, status, dates"},
     "outline": {"tr": ["Görevler", "Kilometre taşları", "Riskler"], "en": ["Tasks", "Milestones", "Risks"]}},
    {"id": "business_review", "kinds": ["pptx"], "colors": ["#3B5BDB", "#1E2A5A", "#EEF2FF"], "font": "sans",
     "cover": "minimal", "name": {"tr": "İş Değerlendirmesi", "en": "Business Review"},
     "desc": {"tr": "Çeyrek sonuçları, öne çıkanlar, plan", "en": "Quarter results, highlights, plan"},
     "outline": {"tr": ["Başlık", "Öne çıkanlar", "Metrikler", "Riskler", "Sonraki çeyrek"],
                 "en": ["Title", "Highlights", "Metrics", "Risks", "Next quarter"]}},
    {"id": "market_trends", "kinds": ["pptx"], "colors": ["#EF4444", "#0A0A0A", "#FEF2F2"], "font": "sans",
     "cover": "dark", "name": {"tr": "Pazar Trendleri Raporu", "en": "Market Trends Report"},
     "desc": {"tr": "Koyu tema, trendler ve fırsatlar", "en": "Dark theme, trends and opportunities"},
     "outline": {"tr": ["Başlık", "Pazar büyüklüğü", "Ana trendler", "Rakipler", "Fırsatlar"],
                 "en": ["Title", "Market size", "Key trends", "Competitors", "Opportunities"]}},
    {"id": "operating_review", "kinds": ["pptx"], "colors": ["#2563EB", "#0B1F4B", "#EFF4FF"], "font": "sans",
     "cover": "dark", "name": {"tr": "Haftalık Operasyon", "en": "Weekly Operating Review"},
     "desc": {"tr": "Haftalık metrik, olay ve aksiyon", "en": "Weekly metrics, incidents and actions"},
     "outline": {"tr": ["Başlık", "Bu hafta", "Metrikler", "Olaylar", "Aksiyonlar"],
                 "en": ["Title", "This week", "Metrics", "Incidents", "Actions"]}},
    {"id": "pitch_deck", "kinds": ["pptx"], "colors": ["#7C3AED", "#2E1065", "#F5F3FF"], "font": "sans",
     "cover": "hero", "name": {"tr": "Yatırımcı Sunumu", "en": "Pitch Deck"},
     "desc": {"tr": "Problem, çözüm, pazar, ekip, talep", "en": "Problem, solution, market, team, ask"},
     "outline": {"tr": ["Başlık", "Problem", "Çözüm", "Pazar", "İş modeli", "Ekip", "Yatırım talebi"],
                 "en": ["Title", "Problem", "Solution", "Market", "Business model", "Team", "The ask"]}},
    # ---- added 2026-11-21: more looks (split / editorial / corner covers, numbered / caps headings, line tables)
    {"id": "annual_report", "kinds": ["pdf", "docx"], "colors": ["#B08D57", "#14213D", "#F7F3EC"], "font": "serif",
     "cover": "editorial", "h2": "number", "table": "lines", "name": {"tr": "Faaliyet Raporu", "en": "Annual Report"},
     "desc": {"tr": "Yıllık sonuçlar, yönetim mesajı, hedefler", "en": "Year results, management letter, goals"},
     "outline": {"tr": ["Yönetim mesajı", "Yılın öne çıkanları", "Finansal sonuçlar", "Operasyonlar", "Sürdürülebilirlik", "Gelecek yıl hedefleri"],
                 "en": ["Letter from management", "Highlights of the year", "Financial results", "Operations", "Sustainability", "Goals for next year"]}},
    {"id": "case_study", "kinds": ["pdf", "docx"], "colors": ["#0F766E", "#042F2E", "#E6F4F2"], "font": "sans",
     "cover": "split", "h2": "caps", "name": {"tr": "Vaka Çalışması", "en": "Case Study"},
     "desc": {"tr": "Müşteri, sorun, çözüm, ölçülen sonuç", "en": "Client, challenge, solution, measured result"},
     "outline": {"tr": ["Müşteri", "Sorun", "Çözüm", "Uygulama", "Sonuçlar (rakamlarla)", "Müşteri görüşü"],
                 "en": ["Client", "Challenge", "Solution", "Implementation", "Results (in numbers)", "Client quote"]}},
    {"id": "white_paper", "kinds": ["pdf", "docx"], "colors": ["#334155", "#0F172A", "#F1F5F9"], "font": "serif",
     "cover": "editorial", "h2": "number", "table": "lines", "name": {"tr": "Teknik Makale (White Paper)", "en": "White Paper"},
     "desc": {"tr": "Derin konu analizi, kaynaklı ve numaralı bölümler", "en": "In-depth topic analysis with sources and numbered sections"},
     "outline": {"tr": ["Yönetici özeti", "Giriş", "Sorunun tanımı", "Analiz", "Önerilen yaklaşım", "Sonuç", "Kaynaklar"],
                 "en": ["Executive summary", "Introduction", "Problem statement", "Analysis", "Proposed approach", "Conclusion", "References"]}},
    {"id": "price_quote", "kinds": ["pdf", "docx"], "colors": ["#2563EB", "#0F172A", "#EFF6FF"], "font": "sans",
     "cover": "corner", "h2": "underline", "table": "soft", "name": {"tr": "Fiyat Teklifi", "en": "Price Quote"},
     "desc": {"tr": "Kalemler, birim fiyat, toplam, koşullar", "en": "Line items, unit prices, total, terms"},
     "outline": {"tr": ["Teklif bilgileri", "Kapsam", "Fiyat tablosu", "Ödeme ve teslim koşulları", "Geçerlilik ve onay"],
                 "en": ["Quote details", "Scope", "Price table", "Payment and delivery terms", "Validity and approval"]}},
    {"id": "product_brochure", "kinds": ["pdf", "docx"], "colors": ["#EA580C", "#431407", "#FFF4EC"], "font": "sans",
     "cover": "photo", "h2": "caps", "name": {"tr": "Ürün Broşürü", "en": "Product Brochure"},
     "desc": {"tr": "Görsel ağırlıklı ürün tanıtımı ve özellikler", "en": "Image-led product overview and features"},
     "outline": {"tr": ["Ürün", "Öne çıkan özellikler", "Teknik özellikler", "Kullanım alanları", "Fiyat ve iletişim"],
                 "en": ["Product", "Key features", "Specifications", "Use cases", "Pricing and contact"]}},
    {"id": "research_paper", "kinds": ["pdf", "docx"], "colors": ["#1D4ED8", "#111827", "#F3F4F6"], "font": "serif",
     "cover": "minimal", "h2": "number", "table": "lines", "name": {"tr": "Akademik Makale", "en": "Research Paper"},
     "desc": {"tr": "Öz, yöntem, bulgular, tartışma, kaynakça", "en": "Abstract, method, findings, discussion, references"},
     "outline": {"tr": ["Öz", "Giriş", "Literatür", "Yöntem", "Bulgular", "Tartışma", "Sonuç", "Kaynakça"],
                 "en": ["Abstract", "Introduction", "Literature", "Method", "Findings", "Discussion", "Conclusion", "References"]}},
    {"id": "sop_manual", "kinds": ["pdf", "docx"], "colors": ["#16A34A", "#14532D", "#F0FDF4"], "font": "sans",
     "cover": "band", "h2": "number", "table": "soft", "name": {"tr": "Prosedür (SOP)", "en": "Standard Procedure (SOP)"},
     "desc": {"tr": "Amaç, kapsam, sorumlular, adım adım işlem", "en": "Purpose, scope, owners, step-by-step process"},
     "outline": {"tr": ["Amaç", "Kapsam", "Sorumluluklar", "Gerekenler", "Adım adım işlem", "Kontrol listesi", "Revizyon geçmişi"],
                 "en": ["Purpose", "Scope", "Responsibilities", "Prerequisites", "Step-by-step procedure", "Checklist", "Revision history"]}},
    {"id": "newsletter", "kinds": ["pdf", "docx"], "colors": ["#DB2777", "#500724", "#FDF2F8"], "font": "sans",
     "cover": "hero", "h2": "caps", "name": {"tr": "Bülten", "en": "Newsletter"},
     "desc": {"tr": "Haberler, duyurular, etkinlikler", "en": "News, announcements, events"},
     "outline": {"tr": ["Bu sayıda", "Öne çıkan haber", "Duyurular", "Etkinlik takvimi", "İletişim"],
                 "en": ["In this issue", "Top story", "Announcements", "Upcoming events", "Contact"]}},
    {"id": "technical_spec", "kinds": ["pdf", "docx"], "colors": ["#0891B2", "#0C1E2C", "#ECFEFF"], "font": "sans",
     "cover": "dark", "h2": "number", "table": "lines", "name": {"tr": "Teknik Şartname", "en": "Technical Specification"},
     "desc": {"tr": "Gereksinimler, mimari, arayüzler, test", "en": "Requirements, architecture, interfaces, testing"},
     "outline": {"tr": ["Genel bakış", "Gereksinimler", "Mimari", "Veri modeli", "API / arayüzler", "Güvenlik", "Test planı"],
                 "en": ["Overview", "Requirements", "Architecture", "Data model", "API / interfaces", "Security", "Test plan"]}},
    {"id": "marketing_plan", "kinds": ["pdf", "docx", "pptx"], "colors": ["#9333EA", "#3B0764", "#FAF5FF"], "font": "sans",
     "cover": "split", "h2": "bar", "name": {"tr": "Pazarlama Planı", "en": "Marketing Plan"},
     "desc": {"tr": "Hedef kitle, kanallar, bütçe, takvim, KPI", "en": "Audience, channels, budget, timeline, KPIs"},
     "outline": {"tr": ["Hedefler", "Hedef kitle", "Konumlandırma", "Kanallar ve taktikler", "Bütçe", "Takvim", "Başarı ölçütleri"],
                 "en": ["Goals", "Target audience", "Positioning", "Channels and tactics", "Budget", "Timeline", "KPIs"]}},
    {"id": "business_plan", "kinds": ["pdf", "docx"], "colors": ["#0B5CAD", "#06223F", "#EAF2FB"], "font": "serif",
     "cover": "corner", "h2": "number", "table": "soft", "name": {"tr": "İş Planı", "en": "Business Plan"},
     "desc": {"tr": "Fikir, pazar, rekabet, gelir modeli, finansal tahmin", "en": "Idea, market, competition, revenue model, forecast"},
     "outline": {"tr": ["Yönetici özeti", "Şirket", "Pazar analizi", "Rekabet", "Ürün / hizmet", "Pazarlama", "Operasyon", "Finansal tahmin"],
                 "en": ["Executive summary", "Company", "Market analysis", "Competition", "Product / service", "Marketing", "Operations", "Financial forecast"]}},
    {"id": "cover_letter", "kinds": ["pdf", "docx"], "colors": ["#475569", "#1E293B", "#F8FAFC"], "font": "serif",
     "cover": "minimal", "h2": "underline", "name": {"tr": "Resmi Yazı / Ön Yazı", "en": "Formal Letter"},
     "desc": {"tr": "Tarih, alıcı, konu, gövde, imza", "en": "Date, recipient, subject, body, signature"},
     "outline": {"tr": ["Alıcı", "Konu", "Giriş", "Gövde", "Kapanış ve imza"],
                 "en": ["Recipient", "Subject", "Opening", "Body", "Closing and signature"]}},
    {"id": "sales_pipeline", "kinds": ["xlsx"], "colors": ["#4F46E5", "#1E1B4B", "#EEF2FF"], "font": "sans",
     "cover": "band", "name": {"tr": "Satış Hunisi", "en": "Sales Pipeline"},
     "desc": {"tr": "Fırsatlar, aşama, olasılık, beklenen gelir", "en": "Deals, stage, probability, expected revenue"},
     "outline": {"tr": ["Özet", "Fırsatlar", "Aşamalara göre", "Satış temsilcisine göre"],
                 "en": ["Summary", "Deals", "By stage", "By sales rep"]}},
    {"id": "inventory", "kinds": ["xlsx"], "colors": ["#D97706", "#451A03", "#FFFBEB"], "font": "sans",
     "cover": "band", "name": {"tr": "Stok Takibi", "en": "Inventory"},
     "desc": {"tr": "Ürün, stok, kritik seviye, tedarikçi", "en": "Item, stock, reorder level, supplier"},
     "outline": {"tr": ["Stok listesi", "Kritik seviyedekiler", "Hareketler", "Tedarikçiler"],
                 "en": ["Stock list", "Below reorder level", "Movements", "Suppliers"]}},
    {"id": "kpi_scorecard", "kinds": ["xlsx"], "colors": ["#10B981", "#022C22", "#ECFDF5"], "font": "sans",
     "cover": "dark", "name": {"tr": "Performans Karnesi", "en": "KPI Scorecard"},
     "desc": {"tr": "Hedef, gerçekleşen, sapma, durum", "en": "Target, actual, variance, status"},
     "outline": {"tr": ["Karne", "Aylık değerler", "Tanımlar"], "en": ["Scorecard", "Monthly values", "Definitions"]}},
    {"id": "personal_budget", "kinds": ["xlsx"], "colors": ["#E11D48", "#4C0519", "#FFF1F2"], "font": "sans",
     "cover": "band", "name": {"tr": "Kişisel Bütçe", "en": "Personal Budget"},
     "desc": {"tr": "Gelir, gider kategorileri, birikim", "en": "Income, expense categories, savings"},
     "outline": {"tr": ["Özet", "Gelirler", "Giderler", "Birikim hedefleri"], "en": ["Summary", "Income", "Expenses", "Savings goals"]}},
    {"id": "product_launch", "kinds": ["pptx"], "colors": ["#F97316", "#1C1917", "#FFF7ED"], "font": "sans",
     "cover": "corner", "name": {"tr": "Ürün Lansmanı", "en": "Product Launch"},
     "desc": {"tr": "Ürün, fayda, hedef kitle, lansman planı", "en": "Product, benefits, audience, launch plan"},
     "outline": {"tr": ["Başlık", "Neden şimdi", "Ürün", "Öne çıkan özellikler", "Hedef kitle", "Lansman takvimi", "Fiyat"],
                 "en": ["Title", "Why now", "The product", "Key features", "Audience", "Launch timeline", "Pricing"]}},
    {"id": "training_workshop", "kinds": ["pptx"], "colors": ["#0EA5E9", "#082F49", "#F0F9FF"], "font": "sans",
     "cover": "minimal", "name": {"tr": "Eğitim / Atölye", "en": "Training Workshop"},
     "desc": {"tr": "Hedefler, modüller, alıştırma, özet", "en": "Objectives, modules, exercise, recap"},
     "outline": {"tr": ["Başlık", "Öğrenme hedefleri", "Modül 1", "Modül 2", "Alıştırma", "Özet ve sorular"],
                 "en": ["Title", "Learning objectives", "Module 1", "Module 2", "Exercise", "Recap and Q&A"]}},
    {"id": "project_kickoff", "kinds": ["pptx"], "colors": ["#14B8A6", "#042F2E", "#F0FDFA"], "font": "sans",
     "cover": "hero", "name": {"tr": "Proje Başlangıcı", "en": "Project Kickoff"},
     "desc": {"tr": "Amaç, kapsam, ekip, takvim, riskler", "en": "Goal, scope, team, timeline, risks"},
     "outline": {"tr": ["Başlık", "Amaç", "Kapsam", "Ekip ve roller", "Takvim", "Riskler", "Sonraki adımlar"],
                 "en": ["Title", "Goal", "Scope", "Team and roles", "Timeline", "Risks", "Next steps"]}},
    {"id": "sales_proposal", "kinds": ["pptx", "pdf"], "colors": ["#1D4ED8", "#0B1437", "#EEF2FF"], "font": "sans",
     "cover": "split", "h2": "caps", "name": {"tr": "Satış Teklifi Sunumu", "en": "Sales Proposal"},
     "desc": {"tr": "Müşteri ihtiyacı, çözüm, değer, fiyat", "en": "Client need, solution, value, pricing"},
     "outline": {"tr": ["Başlık", "İhtiyacınız", "Çözümümüz", "Neden biz", "Referanslar", "Fiyat", "Sonraki adım"],
                 "en": ["Title", "Your need", "Our solution", "Why us", "References", "Pricing", "Next step"]}},
]
BUILTIN.append(
    {"id": "official_letter", "kinds": ["pdf", "docx"], "colors": ["#B91C1C", "#111111", "#F5F5F5"], "font": "serif",
     "font_family": "Times New Roman", "layout": "letter", "margins": "25 25 25 25",
     "name": {"tr": "Resmî Yazı (Antetli)", "en": "Official Letter (Letterhead)"},
     "desc": {"tr": "Antet, ortalı başlık, sağda tarih, iki yana yaslı metin, altbilgide adres",
              "en": "Letterhead, centred title, date on the right, justified text, address in the footer"},
     "sample_header": ["T.C.", "KURUM ADI", "Birim Adı"], "sample_footer": ["Kurum adresi · Telefon · web adresi"],
     "outline": {"tr": ["Başlık", "Giriş", "Gövde", "Sonuç ve imza"], "en": ["Title", "Opening", "Body", "Closing and signature"]}})

# Every template has its own page layout (not only its colours): the first part, the type, the headings and tables
LAYOUT_OF = {"experiment_analysis": "academic", "investment_memo": "memo", "meeting_notes": "memo", "resume": "resume",
             "white_paper": "minimal", "price_quote": "invoice", "research_paper": "academic", "newsletter": "magazine",
             "cover_letter": "letter", "sales_proposal": "invoice", "product_brochure": "magazine"}
FONT_OF = {"investment_memo": "Arial", "meeting_notes": "Segoe UI", "resume": "Calibri", "white_paper": "Georgia",
           "research_paper": "Times New Roman", "experiment_analysis": "Cambria", "cover_letter": "Garamond",
           "newsletter": "Trebuchet MS", "price_quote": "Arial", "technical_spec": "Consolas"}
# Spreadsheets differ by their header look too: lines (no fill, a strong rule), soft (tint), solid, dark, band
XLSX_LOOK = {"financial_budget": ("minimal", "lines"), "operating_calendar": ("minimal", "soft"),
             "inventory": ("minimal", "soft"), "project_tracker": ("hero", "solid"), "personal_budget": ("minimal", "lines")}
for _t in BUILTIN:
    if _t["id"] in XLSX_LOOK:
        _t["cover"], _t["table"] = XLSX_LOOK[_t["id"]]
    _t.setdefault("layout", LAYOUT_OF.get(_t["id"], "report"))
    if _t["id"] in FONT_OF and _t["id"] != "technical_spec":
        _t.setdefault("font_family", FONT_OF[_t["id"]])

# Heading and table styles a template may name (PDF / HTML): h2 bar | number | underline | caps, table solid | lines | soft
H2_STYLES = ("bar", "number", "underline", "caps")
TABLE_STYLES = ("solid", "lines", "soft")
COVERS = ("hero", "band", "minimal", "dark", "photo", "split", "editorial", "corner")

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _valid(t: dict) -> bool:
    return (isinstance(t, dict) and re.fullmatch(r"[a-z0-9_]{2,40}", str(t.get("id", ""))) is not None
            and all(k in KINDS for k in t.get("kinds") or []) and bool(t.get("kinds"))
            and len(t.get("colors") or []) == 3 and all(HEX.match(c) for c in t["colors"]))


def user_templates() -> list[dict]:
    out = []
    for p in sorted(USER_DIR.glob("*.json")) if USER_DIR.is_dir() else []:
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _valid(t):
            out.append({**t, "user": True})
    return out


def all_templates(kind: str = "") -> list[dict]:
    items = BUILTIN + user_templates()
    return [t for t in items if not kind or kind in t["kinds"]]


def get(tid: str) -> dict | None:
    return next((t for t in all_templates() if t["id"] == tid), None)


def text(t: dict, field: str, lang: str):
    v = t.get(field) or {}
    return v.get(lang) or v.get("en") or next(iter(v.values()), "") if isinstance(v, dict) else v


def _extra_css(t: dict) -> str:
    a, d, tint = t["colors"]
    css = ""
    if t.get("font") == "serif":
        css += ('body, h1, h2, h3 { font-family: Georgia, "Times New Roman", "Noto Serif", "DejaVu Serif", serif; }\n'
                "h1, h2 { letter-spacing: -0.2pt; }\n")
    cover = t.get("cover")
    if cover == "minimal":
        css += (f".hero {{ background: #fff !important; color: {d} !important; border: 0; border-top: 4pt solid {a};"
                f" border-radius: 0; padding-left: 0; }} .hero h1, .hero strong, .hero a {{ color: {d} !important; }}"
                f" .hero .lead {{ color: #475569 !important; }} .hero .meta {{ color: {a} !important; }}"
                " .hero::after { display: none; }\n")
    elif cover == "band":
        css += (f".hero {{ background: {d} !important; border-radius: 0; }}"
                f" .hero::after {{ background: {a}; opacity: .35; border-radius: 0; width: 90pt; right: 0; top: 0;"
                " height: 100%; }\n")
    elif cover == "dark":
        css += f".hero {{ background: #0b1220 !important; }} .hero .meta {{ color: {a} !important; }}\n"
    elif cover == "photo":
        css += (f".hero {{ background: linear-gradient(180deg, rgba(0,0,0,.05), rgba(0,0,0,.55)),"
                f" linear-gradient(135deg, {a}, {d}) !important; min-height: 150pt; display: flex; flex-direction: column;"
                " justify-content: flex-end; }\n")
    elif cover == "split":  # a white cover with a solid accent column on the left and a tinted panel
        css += (f".hero {{ background: {tint} !important; color: {d} !important; border-radius: 0; border-left: 14pt solid {a};"
                f" padding: 24pt 22pt 20pt; }} .hero h1, .hero strong, .hero a {{ color: {d} !important; }}"
                f" .hero .lead {{ color: #334155 !important; }} .hero .meta {{ color: {a} !important; font-weight: 600; }}"
                " .hero::after { display: none; }\n")
    elif cover == "editorial":  # magazine look: centred large serif title between two thin rules
        css += (f".hero {{ background: #fff !important; color: {d} !important; border-radius: 0; text-align: center;"
                f" border-top: 1.5pt solid {d}; border-bottom: 0.75pt solid {d}; padding: 26pt 10pt 18pt; }}"
                f" .hero h1 {{ color: {d} !important; font-family: Georgia, 'Times New Roman', serif; font-size: 30pt;"
                f" font-weight: 700; letter-spacing: -0.4pt; }} .hero .lead {{ color: #475569 !important; font-style: italic;"
                f" max-width: 80%; margin-left: auto !important; margin-right: auto !important; }}"
                f" .hero .meta {{ color: {a} !important; letter-spacing: 2pt; }} .hero::after {{ display: none; }}\n")
    elif cover == "corner":  # white cover, a dark corner triangle and an accent stripe
        css += (f".hero {{ background: #fff !important; color: {d} !important; border-radius: 0; border: 0.75pt solid #e2e8f0;"
                f" padding: 26pt 24pt 20pt; }} .hero h1, .hero strong, .hero a {{ color: {d} !important; }}"
                f" .hero .lead {{ color: #475569 !important; }} .hero .meta {{ color: {a} !important; font-weight: 600; }}"
                f" .hero::after {{ background: linear-gradient(225deg, {d} 0 48%, {a} 48% 56%, transparent 56%);"
                " border-radius: 0; width: 120pt; height: 120pt; right: 0; top: 0; opacity: 1; }\n")
    h2 = t.get("h2") or "bar"
    if h2 == "number":  # 01, 02 ... in an accent badge
        css += ("main.doc { counter-reset: sec; }\n"
                f"h2 {{ border-left: 0 !important; padding-left: 0 !important; counter-increment: sec; display: flex;"
                f" align-items: baseline; gap: 8pt; }} h2::before {{ content: counter(sec, decimal-leading-zero);"
                f" font-size: 9.5pt; font-weight: 700; color: #fff; background: {a}; border-radius: 4pt;"
                " padding: 1.5pt 5pt; letter-spacing: .3pt; }\n")
    elif h2 == "underline":
        css += (f"h2 {{ border-left: 0 !important; padding: 0 0 4pt !important; border-bottom: 1.5pt solid {a}; }}\n")
    elif h2 == "caps":
        css += (f"h2 {{ border-left: 0 !important; padding: 0 0 4pt !important; font-size: 11pt; text-transform: uppercase;"
                f" letter-spacing: 1.4pt; color: {a} !important; border-bottom: 0.75pt solid #d9e2ec; }}\n")
    table = t.get("table") or "solid"
    if table == "lines":  # financial-report tables: no box, a strong rule under the header
        css += (f"table {{ border: 0 !important; border-radius: 0 !important; }} th {{ background: transparent !important;"
                f" color: {d} !important; border-bottom: 1.5pt solid {d} !important; text-transform: uppercase; font-size: 8pt;"
                f" letter-spacing: .6pt; }} td {{ border-top: 0 !important; border-bottom: 0.5pt solid #e2e8f0; }}"
                " tbody tr:nth-child(even) td { background: transparent !important; }\n")
    elif table == "soft":
        css += (f"th {{ background: {tint} !important; color: {d} !important; border-bottom: 1pt solid {a}66 !important; }}\n")
    else:
        css += f"table th {{ background: {a}; }}\n"
    css += f"h2 {{ color: {d}; }}\n"
    css += _layout_css(t)
    if mg := page_options(t).get("margin"):  # CSS @page wins over the renderer's option: the template says it here
        css += f"@page {{ margin: {mg['top']} {mg['right']} {mg['bottom']} {mg['left']}; }}\n"
    if fam := (t.get("font_family") or "").strip():  # the reference's own type ("Times New Roman", "Arial")
        fam = re.sub(r"[^\w \-]", "", fam)[:40]
        css += f'body, h1, h2, h3, h4, th, td {{ font-family: "{fam}", {"Georgia, serif" if t.get("font") == "serif" else "Arial, sans-serif"}; }}\n'
    if custom := clean_css(t.get("css") or ""):  # the model's own stylesheet for this template (Template Creator)
        css += "/* template css */\n" + custom + "\n"
    return css


def clean_css(css: str) -> str:
    """A template's own CSS: no remote imports / scripts, at most 12K characters."""
    css = re.sub(r"(?i)</?style[^>]*>|@import[^;]*;|expression\s*\(|javascript:", "", str(css or ""))
    css = re.sub(r"(?i)url\(\s*['\"]?(https?:)?//[^)]*\)", "none", css)  # no remote files (PDF is rendered offline)
    return css[:12000]


LAYOUTS = ("report", "letter", "memo", "academic", "magazine", "invoice", "resume", "minimal")


def _layout_css(t: dict) -> str:
    a, d, tint = t["colors"]
    lay = t.get("layout") or "report"
    if lay == "letter":  # official letter: letterhead with logo, centred title, date on the right, justified body
        return (".lh { text-align: center; margin: 0 0 6pt; padding-bottom: 8pt; border-bottom: 0.75pt solid #333; } .lh img { max-height: 70pt; max-width: 60%; display: block;"
                " margin: 0 auto 6pt; } .lh-lines div { font-size: 10.5pt; font-weight: 700; color: #111; line-height: 1.35; }"
                " .lh-lines div:first-child { font-size: 11pt; }"
                " h1.doc-title { text-align: center; font-size: 13pt; font-weight: 700; color: #111; margin: 14pt 0 4pt;"
                " text-transform: uppercase; letter-spacing: .4pt; border: 0; }"
                " .doc-date { text-align: right; font-size: 10pt; margin: 0 0 18pt; color: #111; }"
                " body { color: #111; } main.doc p { text-align: justify; text-indent: 1.25cm; margin-bottom: 6pt; line-height: 1.5; }"
                f" h2 {{ font-size: 12pt !important; color: #111 !important; border-left: 0 !important; padding-left: 0 !important; }}\n")
    if lay == "memo":
        return (f".memo {{ border-bottom: 2pt solid {d}; padding-bottom: 8pt; margin-bottom: 16pt; }}"
                f" .memo .kicker {{ font-size: 26pt; font-weight: 800; letter-spacing: 6pt; color: {a}; }}"
                f" .memo h1 {{ font-size: 17pt; margin: 4pt 0 8pt; color: {d}; }}"
                " .memo table { border: 0 !important; width: auto; margin: 0; font-size: 10pt; }"
                " .memo th { background: transparent !important; color: #64748b !important; padding: 2pt 14pt 2pt 0;"
                " text-transform: uppercase; font-size: 8pt; letter-spacing: 1pt; } .memo td { border: 0 !important; padding: 2pt 0; }\n")
    if lay == "academic":
        return (".acad { text-align: center; margin: 4pt 0 18pt; } .acad h1 { font-size: 20pt; color: #111; margin: 0 0 6pt; }"
                " .acad .acad-date { font-size: 9.5pt; color: #555; font-style: italic; }"
                f" .abstract {{ text-align: justify; margin: 12pt 8% 4pt; padding: 8pt 12pt; border-top: 0.75pt solid {d};"
                f" border-bottom: 0.75pt solid {d}; font-size: 9.8pt; }} .abstract b {{ display: block; text-align: center;"
                " font-variant: small-caps; letter-spacing: 1pt; margin-bottom: 3pt; }"
                " main.doc p { text-align: justify; } h2 { font-size: 12.5pt !important; }\n")
    if lay == "magazine":
        return (f".mag {{ border-top: 6pt solid {d}; padding-top: 8pt; margin-bottom: 14pt; }}"
                f" .mag .mast {{ font-size: 9pt; font-weight: 800; letter-spacing: 4pt; text-transform: uppercase; color: {a}; }}"
                f" .mag h1 {{ font-size: 34pt; line-height: 1.02; margin: 6pt 0 8pt; color: {d}; letter-spacing: -0.8pt; }}"
                " .mag .dek { font-size: 13pt; color: #475569; font-style: italic; margin: 0 0 6pt; }"
                f" .mag .mag-meta {{ font-size: 8pt; letter-spacing: 1.5pt; text-transform: uppercase; color: #64748b;"
                f" border-bottom: 0.75pt solid #cbd5e1; padding-bottom: 6pt; }}"
                " .mag-body { column-count: 2; column-gap: 18pt; } .mag-body h2, .mag-body table, .mag-body .kpis, .mag-body .bars,"
                " .mag-body .callout, .mag-body img { column-span: all; } .mag-body p { text-align: justify; }\n")
    if lay == "invoice":
        return (f".inv {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16pt;"
                f" border-bottom: 2pt solid {d}; padding-bottom: 10pt; margin-bottom: 16pt; }}"
                f" .inv h1 {{ margin: 0; font-size: 22pt; color: {d}; }} .inv .inv-lead {{ color: #475569; margin-top: 4pt; }}"
                f" .inv-box {{ background: {d}; color: #fff; padding: 9pt 14pt; border-radius: 6pt; text-align: right;"
                f" min-width: 120pt; }} .inv-box span {{ display: block; font-size: 7.5pt; letter-spacing: 1.2pt;"
                " text-transform: uppercase; opacity: .75; } .inv-box b { font-size: 13pt; color: #fff; }"
                " table tr:last-child td { font-weight: 700; border-top: 1.5pt solid #1f2933 !important; }\n")
    if lay == "resume":
        return (f".cv {{ text-align: left; border-bottom: 3pt solid {a}; padding-bottom: 8pt; margin-bottom: 12pt; }}"
                f" .cv h1 {{ font-size: 28pt; margin: 0; color: {d}; letter-spacing: -0.5pt; }}"
                f" .cv .cv-role {{ font-size: 12pt; color: {a}; font-weight: 600; margin: 3pt 0 0; }}"
                f" h2 {{ font-size: 10.5pt !important; text-transform: uppercase; letter-spacing: 1.6pt; color: {a} !important;"
                " border-left: 0 !important; padding: 0 0 3pt !important; border-bottom: 0.75pt solid #d9e2ec; margin-top: 14pt !important; }"
                " main.doc { font-size: 10pt; }\n")
    if lay == "minimal":
        return (".min { margin: 24pt 0 26pt; } .min .min-date { font-size: 8pt; letter-spacing: 2.5pt; text-transform: uppercase;"
                f" color: {a}; }} .min h1 {{ font-size: 32pt; font-weight: 300; color: #0f172a; margin: 8pt 0 10pt;"
                " letter-spacing: -0.6pt; line-height: 1.1; } .min .lead { font-size: 12.5pt; color: #64748b; max-width: 85%; }"
                " h2 { font-weight: 400 !important; font-size: 15pt !important; border-left: 0 !important; padding-left: 0 !important; }"
                " main.doc { line-height: 1.75; }\n")
    return ""


LABELS = {"date": {"tr": "Tarih", "en": "Date"}, "abstract": {"tr": "Özet", "en": "Abstract"},
          "subject": {"tr": "Konu", "en": "Subject"}, "memo": {"tr": "NOT", "en": "MEMO"}}


def _lbl(k: str, lang: str) -> str:
    return LABELS[k].get(lang) or LABELS[k]["en"]


def asset_dir() -> Path:
    return USER_DIR / "assets"


def logo_uri(t: dict) -> str:
    """The template's logo (saved with it) as a data URI, so the offline PDF renderer and DOCX can embed it."""
    import base64
    name = str(t.get("logo") or "")
    p = asset_dir() / Path(name).name if name else None
    if not p or not p.is_file():
        return ""
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
            ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def layout_body(t: dict, body: str, lang: str, hero) -> str:
    """The document's first part in the template's layout (report = the coloured cover of make_doc)."""
    import time as _time
    lay = t.get("layout") or "report"
    if lay == "report":
        return hero(body, lang)
    m = re.match(r"\s*<h1[^>]*>(.*?)</h1>\s*(<p>(?:(?!<p>).){0,600}?</p>)?", body, re.S)
    title, lead, rest = (m.group(1), (m.group(2) or "")[3:-4], body[m.end():]) if m else ("", "", body)
    if lead and re.search(r"<(img|table|div)", lead):
        rest, lead = f"<p>{lead}</p>" + rest, ""
    date = _time.strftime("%d.%m.%Y" if lang != "en" else "%B %d, %Y")
    logo = logo_uri(t)
    lines = [html.escape(x) for x in (t.get("header") or [])][:6]
    if lay == "letter":
        head = (f'<header class="lh">{f"<img src={chr(34)}{logo}{chr(34)} alt=\"\">" if logo else ""}'
                f'<div class="lh-lines">{"".join(f"<div>{x}</div>" for x in lines)}</div></header>')
        # the content's own date line (a model wrote <p class="doc-date">) replaces the template's: never two dates
        own_date = 'class="doc-date"' in body
        return (head + ("" if own_date else f'<div class="doc-date">{date}</div>') + (f'<h1 class="doc-title">{title}</h1>' if title else "")
                + (f"<p>{lead}</p>" if lead else "") + rest)
    if lay == "memo":
        rows = f"<tr><th>{_lbl('date', lang)}</th><td>{date}</td></tr>" + (
            f"<tr><th>{_lbl('subject', lang)}</th><td>{lead}</td></tr>" if lead else "")
        return (f'<header class="memo"><div class="kicker">{_lbl("memo", lang)}</div><h1>{title}</h1>'
                f"<table>{rows}</table></header>" + rest)
    if lay == "academic":
        ab = f'<div class="abstract"><b>{_lbl("abstract", lang)}</b>{lead}</div>' if lead else ""
        return f'<header class="acad"><h1>{title}</h1><div class="acad-date">{date}</div>{ab}</header>' + rest
    if lay == "magazine":
        name = html.escape(text(t, "name", lang) or "")
        return (f'<header class="mag"><div class="mast">{name}</div><h1>{title}</h1>'
                + (f'<p class="dek">{lead}</p>' if lead else "") + f'<div class="mag-meta">{date}</div></header>'
                + f'<div class="mag-body">{rest}</div>')
    if lay == "invoice":
        return (f'<header class="inv"><div><h1>{title}</h1>' + (f'<div class="inv-lead">{lead}</div>' if lead else "")
                + f'</div><div class="inv-box"><span>{_lbl("date", lang)}</span><b>{date}</b></div></header>' + rest)
    if lay == "resume":
        return f'<header class="cv"><h1>{title}</h1>' + (f'<p class="cv-role">{lead}</p>' if lead else "") + "</header>" + rest
    if lay == "minimal":
        return (f'<header class="min"><div class="min-date">{date}</div><h1>{title}</h1>'
                + (f'<p class="lead">{lead}</p>' if lead else "") + "</header>" + rest)
    return hero(body, lang)


def with_lines(tid: str, header: str = "", footer: str = "") -> str:
    """A template with this document's own letterhead / footer lines (make_doc header= / footer=): registered under
    a derived theme id, the saved template stays as it is."""
    from . import docs_gen
    t = get(tid)
    if not t or not (header or footer):
        return tid
    split = (lambda v: [x.strip() for x in re.split(r"\s*\|\s*|\n", v) if x.strip()][:6])
    t2 = {**t, **({"header": split(header)} if header else {}), **({"footer": split(footer)} if footer else {})}
    import hashlib
    t2["id"] = f"{tid}__{hashlib.md5((header + '|' + footer).encode()).hexdigest()[:8]}"
    docs_gen.THEMES[t2["id"]] = tuple(t2["colors"])
    docs_gen.TEMPLATE_CSS[t2["id"]] = _extra_css(t2)
    docs_gen.TEMPLATE_SPEC[t2["id"]] = t2
    return t2["id"]


def page_options(t: dict) -> dict:
    """PDF page settings of a template: margins in mm and the running footer lines."""
    out: dict = {}
    mg = t.get("margins")
    if isinstance(mg, str):
        mg = [x for x in re.split(r"[,\s/]+", mg) if x]
    try:
        if mg and len(mg) in (1, 2, 4):
            v = [float(str(x).lower().replace("mm", "")) for x in mg]
            top, right, bottom, left = (v * 4)[:4] if len(v) == 1 else (v[0], v[1], v[0], v[1]) if len(v) == 2 else v
            if all(3 <= x <= 60 for x in (top, right, bottom, left)):
                out["margin"] = {"top": f"{top}mm", "right": f"{right}mm", "bottom": f"{bottom}mm", "left": f"{left}mm"}
    except ValueError:
        pass
    if foot := [html.escape(x) for x in (t.get("footer") or [])][:5]:
        out["footer_lines"] = foot
        mg = out.get("margin") or {"top": "18mm", "right": "16mm", "bottom": "20mm", "left": "16mm"}
        need = 12 + 4 * len(foot)  # the footer lines are drawn inside the bottom margin
        out["margin"] = {**mg, "bottom": f"{max(float(mg['bottom'][:-2]), need)}mm"}
    return out

def register() -> None:
    """Every template's colours and CSS become a make_doc theme of the same id."""
    from . import docs_gen
    for t in all_templates():
        docs_gen.THEMES[t["id"]] = tuple(t["colors"])
        docs_gen.TEMPLATE_CSS[t["id"]] = _extra_css(t)
        docs_gen.TEMPLATE_SPEC[t["id"]] = t


def save_user(t: dict) -> dict:
    t = {k: t[k] for k in ("id", "kinds", "colors", "font", "cover", "h2", "table", "name", "desc", "outline", "reference",
                           "layout", "margins", "header", "footer", "css", "logo", "font_family") if k in t}
    if t.get("layout") not in LAYOUTS:
        t.pop("layout", None)
    for k in ("header", "footer"):
        if isinstance(t.get(k), str):
            t[k] = [x.strip() for x in re.split(r"\s*\|\s*|\n", t[k]) if x.strip()]
        if not t.get(k):
            t.pop(k, None)
        else:
            t[k] = [str(x)[:160] for x in t[k]][:6]
    if "css" in t:
        t["css"] = clean_css(t["css"])
        if not t["css"].strip():
            t.pop("css")
    if t.get("cover") not in COVERS:
        t["cover"] = "hero"
    if t.get("h2") not in H2_STYLES:
        t.pop("h2", None)
    if t.get("table") not in TABLE_STYLES:
        t.pop("table", None)
    if not _valid(t):
        raise ValueError("a template needs id (a-z, 0-9, _), kinds (pdf/docx/xlsx/pptx) and 3 colours (#rrggbb)")
    if any(b["id"] == t["id"] for b in BUILTIN):
        raise ValueError(f"'{t['id']}' is a built-in template: choose another id")
    USER_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DIR / f"{t['id']}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    register()
    return t


def delete_user(tid: str) -> bool:
    p = USER_DIR / f"{tid}.json"
    if not re.fullmatch(r"[a-z0-9_]{2,40}", tid) or not p.exists():
        return False
    p.unlink()
    return True


# ---------------------------------------------------------------- reference file analysis (Template Creator)
def _hex(c) -> str | None:
    """pdfplumber / python-docx colour -> #rrggbb (None for none / grey levels of text)."""
    try:
        if c is None:
            return None
        if isinstance(c, str):
            c = c.lstrip("#")
            return f"#{c.lower()}" if re.fullmatch(r"[0-9a-fA-F]{6}", c) else None
        if isinstance(c, (int, float)):
            c = (c, c, c)
        c = tuple(c)
        if len(c) == 4:  # CMYK
            k = c[3]
            c = tuple((1 - x) * (1 - k) for x in c[:3])
        if len(c) == 1:
            c = (c[0],) * 3
        return "#" + "".join(f"{max(0, min(255, round(float(x) * 255 if float(x) <= 1 else float(x)))):02x}" for x in c[:3])
    except (TypeError, ValueError):
        return None


def _saturated(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    return (mx - mn) / 255


def _lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _palette(counts: dict[str, float]) -> dict:
    """accent = the most used saturated colour, dark = the darkest frequent one, tint = the lightest non-white one."""
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    colourful = [h for h, _ in items if _saturated(h) > 0.18 and 0.12 < _lum(h) < 0.85]
    darks = [h for h, _ in items if _lum(h) < 0.25 and h != "#000000"]
    tints = [h for h, _ in items if 0.86 < _lum(h) < 0.985]
    return {"accent": colourful[0] if colourful else None, "dark": darks[0] if darks else None,
            "tint": tints[0] if tints else None, "top": [h for h, _ in items[:10]]}


MM = 25.4 / 72  # PDF points -> millimetres


def _page_facts(page) -> dict:
    """Where things are on a reference page: size, text margins, the lines with their size / alignment / zone
    (header, body, footer), so the model can rebuild the layout (letterhead, centred title, date on the right...)."""
    W, H = float(page.width), float(page.height)
    words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False, use_text_flow=True)
    rows: dict[int, list] = {}
    for w in words:
        rows.setdefault(round(w["top"] / 3), []).append(w)
    lines = []
    for _, ws in sorted(rows.items()):
        ws.sort(key=lambda w: w["x0"])
        # one visual row may hold two columns of text far apart: split at big gaps
        group = [ws[0]]
        for w in ws[1:]:
            if w["x0"] - group[-1]["x1"] > 40:
                lines.append(group)
                group = [w]
            else:
                group.append(w)
        lines.append(group)
    out_lines = []
    for g in lines:
        x0, x1 = min(w["x0"] for w in g), max(w["x1"] for w in g)
        top = min(w["top"] for w in g)
        size = round(max(w["size"] for w in g), 1)
        mid = (x0 + x1) / 2
        align = "center" if abs(mid - W / 2) < W * 0.05 and (x1 - x0) < W * 0.8 else (
            "right" if W - x1 < W * 0.12 and x0 > W * 0.45 else "left")
        zone = "header" if top < H * 0.18 else "footer" if top > H * 0.85 else "body"
        txt = " ".join(w["text"] for w in g)[:120]
        bold = any(re.search(r"bold|black|heavy", w.get("fontname", ""), re.I) for w in g)
        out_lines.append({"text": txt, "size": size, "bold": bold, "align": align, "zone": zone,
                          "x_mm": round(x0 * MM), "y_mm": round(top * MM),
                          "font": re.sub(r"^[A-Z]{6}\+", "", g[0].get("fontname", ""))})
    body = [w for w in words if H * 0.12 < w["top"] < H * 0.88]
    facts = {"page_mm": [round(W * MM), round(H * MM)], "orientation": "landscape" if W > H else "portrait",
             "lines": out_lines[:60]}
    if body:
        facts["text_area_mm"] = {"left": round(min(w["x0"] for w in body) * MM),
                                 "right": round((W - max(w["x1"] for w in body)) * MM),
                                 "top": round(min(w["top"] for w in words) * MM),
                                 "bottom": round((H - max(w["bottom"] for w in words)) * MM)}
    sizes: dict[float, int] = {}
    for w in words:
        sizes[round(w["size"], 1)] = sizes.get(round(w["size"], 1), 0) + len(w["text"])
    if sizes:
        facts["body_size_pt"] = max(sizes, key=sizes.get)
    graphics = [{"x0": float(o["x0"]), "top": float(o["top"]), "x1": float(o["x1"]), "bottom": float(o["bottom"])}
                for o in list(page.images) + list(page.curves)
                if (o["x1"] - o["x0"]) < W * 0.6 and (o["bottom"] - o["top"]) < H * 0.3
                and (o["x1"] - o["x0"]) > 2 and (o["bottom"] - o["top"]) > 2]  # no rules / dashes of guide lines
    facts["graphics"] = _clusters(graphics)
    return facts


def _clusters(boxes: list[dict], gap: float = 12) -> list[dict]:
    """Merge overlapping / close drawing boxes (a vector logo is hundreds of curves) into a few regions."""
    out: list[dict] = []
    for b in sorted(boxes, key=lambda b: (b["top"], b["x0"])):
        for c in out:
            if b["x0"] <= c["x1"] + gap and b["x1"] >= c["x0"] - gap and b["top"] <= c["bottom"] + gap and b["bottom"] >= c["top"] - gap:
                c.update(x0=min(c["x0"], b["x0"]), top=min(c["top"], b["top"]), x1=max(c["x1"], b["x1"]),
                         bottom=max(c["bottom"], b["bottom"]))
                break
        else:
            out.append(dict(b))
    big = [c for c in out if (c["x1"] - c["x0"]) > 14 and (c["bottom"] - c["top"]) > 14]
    return sorted(big, key=lambda c: -(c["x1"] - c["x0"]) * (c["bottom"] - c["top"]))[:6]


def _drop_guides(img, box):
    """Crop `box` from the page, whitening the grey / black pixels of thin lines that run on past the box on both
    sides (layout guides, dashed rules that touch a logo); the logo's own strokes end inside the box."""
    import numpy as np
    from PIL import Image as _Im
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    x0, y0, x1, y1 = box
    H, W = a.shape[:2]
    ink = a.min(axis=2) < 200
    grey = (a.max(axis=2) - a.min(axis=2)) < 40
    reach = 30  # px beyond the box
    out = a[y0:y1, x0:x1].copy()
    for y in range(y0, min(y1, H)):
        left = ink[y, max(0, x0 - reach):x0].any()
        right = ink[y, x1:min(W, x1 + reach)].any()
        if left and right:
            row = out[y - y0]
            m = grey[y, x0:x1] & ink[y, x0:x1]
            row[m] = 255
    for x in range(x0, min(x1, W)):
        up = ink[max(0, y0 - reach):y0, x].any()
        down = ink[y1:min(H, y1 + reach), x].any()
        if up and down:
            col = out[:, x - x0]
            m = grey[y0:y1, x] & ink[y0:y1, x]
            col[m] = 255
    return _Im.fromarray(out.clip(0, 255).astype("uint8"))


def _drop_hairlines(im):
    """Thin grey lines across a crop (a layout guide, a dashed rule) are whitened: rows / columns at most 4 px thick,
    only grey pixels, with blank rows on both sides."""
    import numpy as np
    from PIL import Image as _Im
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    ink = a.min(axis=2) < 235
    grey = (a.max(axis=2) - a.min(axis=2)) < 40  # black or grey, not a colour
    for axis in (0, 1):
        n = a.shape[axis]
        line_ink = ink.any(axis=1 - axis)
        only_grey = ~(ink & ~grey).any(axis=1 - axis)
        i = 0
        while i < n:
            if line_ink[i] and only_grey[i]:
                j = i
                while j < n and line_ink[j] and only_grey[j]:
                    j += 1
                before = i == 0 or not line_ink[i - 1]
                after = j >= n or not line_ink[j]
                if j - i <= 4 and ((before and after) or i == 0 or j >= n):  # a guide line at the crop edge
                    if axis == 0:
                        a[i:j, :, :] = 255
                    else:
                        a[:, i:j, :] = 255
                    ink[i:j, :] if axis == 0 else ink[:, i:j]
                i = j
            else:
                i += 1
    return _Im.fromarray(a.clip(0, 255).astype("uint8"))


def save_reference_images(path: Path, folder: Path) -> list[str]:
    """The reference's first page as a picture (for a vision check) and crops of its graphics (logos)."""
    import pypdfium2 as pdfium
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    pdf = pdfium.PdfDocument(str(path))
    page = pdf[0]
    scale = 3
    img = page.render(scale=scale).to_pil().convert("RGB")
    full = folder / f"{path.stem}_page1.png"
    pv = img.copy()
    pv.thumbnail((1600, 1600))
    pv.save(full)
    saved.append(full.name)
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as doc:
            regions = _page_facts(doc.pages[0]).get("graphics") or []
    except Exception:  # noqa: BLE001
        regions = []
    if regions:  # the crops come from the page drawn without hairlines (guide / dashed / ruled lines over a logo)
        try:
            import pypdfium2.raw as pdfium_c
            clean = pdfium.PdfDocument(str(path))[0]
            for obj in list(clean.get_objects()):
                if obj.type == pdfium_c.FPDF_PAGEOBJ_PATH:
                    x0, y0, x1, y1 = obj.get_pos()
                    if (x1 - x0) < 2.5 or (y1 - y0) < 2.5:
                        clean.remove_obj(obj)
            clean.gen_content()
            img = clean.render(scale=scale).to_pil().convert("RGB")
        except Exception:  # noqa: BLE001 - the normal drawing still works
            pass
    for i, r in enumerate(regions[:4], 1):
        pad = 8
        box = tuple(int(v * scale) for v in (max(0, r["x0"] - pad), max(0, r["top"] - pad), r["x1"] + pad, r["bottom"] + pad))
        crop = _drop_hairlines(_drop_guides(img, box))
        try:  # trim the white around it
            from PIL import ImageChops, Image as _Im
            diff = ImageChops.difference(crop, _Im.new("RGB", crop.size, (255, 255, 255)))
            bb = ImageChops.add(diff, diff, 2.0, -20).getbbox()
            if bb:
                crop = crop.crop(bb)
        except Exception:  # noqa: BLE001
            pass
        f = folder / f"{path.stem}_graphic{i}.png"
        crop.save(f)
        saved.append(f.name)
    return saved


def analyze_reference(path: Path) -> dict:
    """Colours, fonts, heading sizes / texts and the cover's look of a reference file, for doc_template create."""
    ext = path.suffix.lower()
    out: dict = {"file": path.name}
    counts: dict[str, float] = {}

    def add(h, w=1.0):
        if h and h not in ("#ffffff",):
            counts[h] = counts.get(h, 0) + w
    fonts: dict[str, int] = {}
    headings: list[str] = []
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            out["pages"] = len(pdf.pages)
            for i, page in enumerate(pdf.pages[:4]):
                for ch in page.chars[:20000]:
                    fonts[re.sub(r"^[A-Z]{6}\+", "", ch.get("fontname", ""))] = fonts.get(re.sub(r"^[A-Z]{6}\+", "", ch.get("fontname", "")), 0) + 1
                    add(_hex(ch.get("non_stroking_color")), 0.2)
                for r in page.rects[:2000]:
                    add(_hex(r.get("non_stroking_color")), max(1.0, (r.get("width", 0) * r.get("height", 0)) / 2000))
                big = sorted({(round(w["size"]), w["text"]) for w in page.extract_words(extra_attrs=["size"])
                              if w.get("size", 0) >= 13}, key=lambda x: -x[0])
                if i == 0 and big:
                    out["title_size_pt"] = big[0][0]
                lines: dict[float, list] = {}
                for w in page.extract_words(extra_attrs=["size"]):
                    if w.get("size", 0) >= 12.5:
                        lines.setdefault(round(w["top"]), []).append(w["text"])
                headings += [" ".join(v) for v in lines.values()][:12]
                if i == 0:
                    first = page.crop((0, 0, page.width, page.height * 0.3))
                    fills = [_hex(r.get("non_stroking_color")) for r in first.rects]
                    wide = [r for r in first.rects if r.get("width", 0) > page.width * 0.6 and r.get("height", 0) > 40]
                    tall_left = [r for r in first.rects if r.get("x0", 99) < 60 and r.get("width", 0) < 40 and r.get("height", 0) > 40]
                    out["cover_hint"] = ("split (a narrow colour column at the left of the cover)" if tall_left else
                                         "band / hero (a wide filled block at the top)" if wide else
                                         "minimal / editorial (no large filled block at the top)")
                    out["cover_fills"] = [f for f in dict.fromkeys(fills) if f][:6]
                    out["layout_facts"] = _page_facts(page)
        try:  # the rendered first page: what the eye sees (gradients, images)
            import pypdfium2 as pdfium
            img = pdfium.PdfDocument(str(path))[0].render(scale=0.5).to_pil().convert("RGB")
            for c, rgb in img.quantize(colors=12).convert("RGB").getcolors(100000) or []:
                add("#%02x%02x%02x" % rgb, c / 400)
        except Exception:  # noqa: BLE001
            pass
    elif ext == ".docx":
        from docx import Document
        d = Document(str(path))
        for p in d.paragraphs[:400]:
            if p.style.name.lower().startswith(("heading", "title", "başlık")) and p.text.strip():
                headings.append(p.text.strip()[:80])
            for r in p.runs:
                if r.font.name:
                    fonts[r.font.name] = fonts.get(r.font.name, 0) + len(r.text)
                if r.font.color is not None and r.font.color.type is not None and r.font.color.rgb is not None:
                    add(_hex(str(r.font.color.rgb)), 0.5 + len(r.text) / 50)
        for st in d.styles:
            try:
                if st.font is not None and st.font.color is not None and st.font.color.rgb is not None:
                    add(_hex(str(st.font.color.rgb)), 2)
                if st.font is not None and st.font.name:
                    fonts[st.font.name] = fonts.get(st.font.name, 0) + 1
            except (AttributeError, ValueError):
                pass
        xml = d.element.xml
        for h in re.findall(r'w:fill="([0-9A-Fa-f]{6})"', xml):
            add(_hex(h), 3)
    elif ext == ".pptx":
        from pptx import Presentation
        prs = Presentation(str(path))
        for slide in list(prs.slides)[:12]:
            for sh in slide.shapes:
                try:
                    if sh.fill.type == 1:
                        add(_hex(str(sh.fill.fore_color.rgb)), 3)
                except (AttributeError, ValueError, TypeError):
                    pass
                if sh.has_text_frame:
                    for p in sh.text_frame.paragraphs:
                        for r in p.runs:
                            if r.font.name:
                                fonts[r.font.name] = fonts.get(r.font.name, 0) + 1
                            try:
                                add(_hex(str(r.font.color.rgb)), 0.5)
                            except (AttributeError, ValueError, TypeError):
                                pass
            if slide.shapes.title is not None and slide.shapes.title.text.strip():
                headings.append(slide.shapes.title.text.strip()[:80])
        for xml_part in [prs.slide_masters[0].part.part_related_by] if False else []:  # (theme colours via the XML below)
            pass
        try:
            theme = next(p for p in prs.part.package.iter_parts() if "theme" in str(p.partname))
            for h in re.findall(rb'srgbClr val="([0-9A-Fa-f]{6})"', theme.blob):
                add(_hex(h.decode()), 1)
        except StopIteration:
            pass
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        from PIL import Image
        img = Image.open(path).convert("RGB")
        img.thumbnail((600, 600))
        for c, rgb in img.quantize(colors=12).convert("RGB").getcolors(100000) or []:
            add("#%02x%02x%02x" % rgb, c / 400)
    else:
        raise ValueError("reference must be a .pdf, .docx, .pptx or an image")
    out["palette"] = _palette(counts)
    cover_dark = [h for h in out.get("cover_fills") or [] if _lum(h) < 0.25]
    if cover_dark:  # the cover's own dark block says more than body text colour
        out["palette"]["dark"] = cover_dark[0]
    main_fonts = [f for f, _ in sorted(fonts.items(), key=lambda kv: -kv[1]) if f][:5]
    out["fonts"] = main_fonts
    out["font_suggestion"] = ("serif" if any(re.search(r"georgia|times|serif|garamond|cambria|merriweather|playfair|minion", f, re.I)
                                             and not re.search(r"sans", f, re.I) for f in main_fonts[:2]) else "sans")
    out["headings"] = list(dict.fromkeys(h for h in headings if 2 <= len(h) <= 80))[:14]
    if ext == ".pdf":  # a broken font map ("M�llî Eğ�t�m"): the same OCR repair as read_document
        from . import docread
        lines = (out.get("layout_facts") or {}).get("lines") or []
        joined = "\n".join([x["text"] for x in lines] + out["headings"])
        if docread.broken_chars(joined):
            doc = docread.load(path)
            mapping = {chr(int(a, 16)): b for note in doc.notes for a, b in re.findall(r"U\+([0-9A-F]{4,6})->(\S)", note)}
            fix = (lambda s: "".join(mapping.get(c, c) for c in s))
            for x in lines:
                x["text"] = fix(x["text"])
            out["headings"] = [fix(h) for h in out["headings"]]
            if mapping:
                out["note"] = "the PDF's font map was broken; letters repaired with OCR"
    return out


def instruction(t: dict, lang: str) -> str:
    """What the model is told when the user picks this template (sent with the request)."""
    # Only the design comes from the template. Weak models took its sample outline as the document ("Problem /
    # Budget / Team" over a hardware report, the same filler paragraph under every heading).
    head = (" For this letterhead layout pass header=\"organisation | unit\" and footer=\"address | phone | web\" "
            "lines of THIS document's own organisation." if (t.get("layout") == "letter" and not t.get("header")) else "")
    return (f"make_doc template=\"{t['id']}\" - the template gives the DESIGN only (layout, colours, type); the "
            "title and every heading come from THIS request's own content, never the template's name or sample "
            "sections." + head)


# ---------------------------------------------------------------- thumbnails (real HTML in the template's look)
SAMPLE = {"tr": ("Bu sayfa şablonun gerçek görünümüdür; belge aynı düzenle üretilir.",
                 "Kısa bir paragraf metni, şablonun yazı tipini, satır aralığını ve hizalamasını gösterir."),
          "en": ("This page is the template's real look; documents are made in the same layout.",
                 "A short paragraph shows the template's type, line spacing and alignment.")}


def _sample_html(t: dict, lang: str) -> str:
    """Sample content shaped like the document the layout is for (a memo's subject and decisions, an invoice's line
    items and total, a résumé's experience, a paper's abstract...), so every thumbnail looks like its own document."""
    tr = lang == "tr"
    lead, para = SAMPLE.get(lang, SAMPLE["en"])
    name = html.escape(text(t, "name", lang))
    outline = [html.escape(x) for x in (text(t, "outline", lang) or [])][:4] or ["1", "2", "3"]
    lay = t.get("layout") or "report"
    if lay == "letter":
        sig = "Saygılarımla,<br><b>Ad Soyad</b><br>Unvan" if tr else "Sincerely,<br><b>Full Name</b><br>Title"
        return (f"<h1>{name}</h1><p>{para} {para}</p><p>{para}</p><p>{lead}</p>"
                f"<p style='text-align:right;text-indent:0;margin-top:24pt'>{sig}</p>")
    if lay == "memo":
        rows = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in
                       ([("Karar 1", "Onaylandı", "Ayşe"), ("Karar 2", "Ertelendi", "Ali"), ("Karar 3", "Açık", "Ekip")] if tr else
                        [("Decision 1", "Approved", "Ann"), ("Decision 2", "Deferred", "Al"), ("Decision 3", "Open", "Team")]))
        return (f"<h1>{name}</h1><p>{lead}</p><h2>{outline[0]}</h2><p>{para}</p><h2>{outline[1 % len(outline)]}</h2>"
                f"<table><thead><tr><th>{'Konu' if tr else 'Item'}</th><th>{'Durum' if tr else 'Status'}</th>"
                f"<th>{'Sorumlu' if tr else 'Owner'}</th></tr></thead>{rows}</table><p>{para}</p>")
    if lay == "academic":
        return (f"<h1>{name}</h1><p>{para} {lead}</p>" + "".join(f"<h2>{s}</h2><p>{para} {para}</p>" for s in outline[:3])
                + "<table><thead><tr><th>N</th><th>M</th><th>SD</th><th>p</th></tr></thead>"
                  "<tr><td>120</td><td>4,21</td><td>0,83</td><td>0,012</td></tr><tr><td>118</td><td>3,86</td><td>0,91</td><td>0,034</td></tr></table>")
    if lay == "magazine":
        return f"<h1>{name}</h1><p>{lead}</p>" + "".join(f"<h2>{s}</h2><p>{para} {para} {para}</p>" for s in outline[:3])
    if lay == "invoice":
        items = [("Danışmanlık" if tr else "Consulting", 10, 1500), ("Tasarım" if tr else "Design", 4, 2200),
                 ("Lisans" if tr else "Licence", 1, 4800)]
        rows = "".join(f"<tr><td>{a}</td><td>{q}</td><td>{p:,}</td><td>{q * p:,}</td></tr>".replace(",", ".") for a, q, p in items)
        total = f"{sum(q * p for _, q, p in items):,}".replace(",", ".")
        return (f"<h1>{name}</h1><p>{'Müşteri' if tr else 'Client'}: ACME A.Ş. · No 2026-041</p><h2>{outline[0]}</h2><p>{para}</p>"
                f"<table><thead><tr><th>{'Kalem' if tr else 'Item'}</th><th>{'Adet' if tr else 'Qty'}</th>"
                f"<th>{'Birim' if tr else 'Unit'}</th><th>{'Tutar' if tr else 'Amount'}</th></tr></thead>{rows}"
                f"<tr><td>{'Toplam' if tr else 'Total'}</td><td></td><td></td><td>{total}</td></tr></table>"
                f"<h2>{outline[-1]}</h2><p>{para}</p>")
    if lay == "resume":
        job = ("<p><b>{r}</b> · {c} · 2022–2026</p><ul><li>{p}</li><li>{p}</li></ul>")
        badges = "".join(f'<span class="badge">{x}</span> ' for x in ("Python", "SQL", "React", "Figma", "Excel"))
        return (f"<h1>{'Ad Soyad' if tr else 'Full Name'}</h1><p>{'Kıdemli Ürün Tasarımcısı' if tr else 'Senior Product Designer'}</p>"
                f"<h2>{outline[0]}</h2><p>{para}</p><h2>{outline[1 % len(outline)]}</h2>"
                + job.format(r="Ürün Tasarımcısı" if tr else "Product Designer", c="ACME", p=lead)
                + job.format(r="UX Uzmanı" if tr else "UX Specialist", c="Beta", p=lead)
                + f"<h2>{outline[3 % len(outline)]}</h2><p>{badges}</p>")
    if lay == "minimal":
        return f"<h1>{name}</h1><p>{lead}</p>" + "".join(f"<h2>{s}</h2><p>{para} {para}</p>" for s in outline[:3])
    parts = [f"<h1>{name}</h1><p>{lead}</p>"]
    for i, sec in enumerate(outline):
        parts.append(f"<h2>{sec}</h2><p>{para}</p>")
        if i == 0:
            parts.append('<div class="kpis"><div class="kpi"><span>KPI</span><b>84%</b><em class="up">+6%</em></div>'
                         '<div class="kpi"><span>KPI</span><b>12,4K</b><em>2026</em></div>'
                         '<div class="kpi"><span>KPI</span><b>+18%</b><em class="up">Q4</em></div></div>')
        if i == 1:
            parts.append("<table><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>"
                         + "<tr><td>Lorem</td><td>1.240</td><td>18%</td></tr>" * 3 + "</table>")
    return "".join(parts)


def _real_page(t: dict, lang: str) -> str:
    """A PDF / Word template's thumbnail: a sample document rendered by make_doc's own HTML engine on an A4 sheet."""
    from . import docs_gen
    register()
    if t.get("sample_header") or t.get("sample_footer"):  # a built-in letterhead shows its sample lines here only
        t = {**t, "header": t.get("header") or t.get("sample_header"), "footer": t.get("footer") or t.get("sample_footer"),
             "id": t["id"] + "__thumb"}
        docs_gen.THEMES[t["id"]] = tuple(t["colors"])
        docs_gen.TEMPLATE_CSS[t["id"]] = _extra_css(t)
        docs_gen.TEMPLATE_SPEC[t["id"]] = t
    page = docs_gen._page(docs_gen.Source(_sample_html(t, lang)), t["id"], lang, text(t, "name", lang))
    opt = page_options(t)
    mg = opt.get("margin") or {"top": "18mm", "right": "16mm", "bottom": "20mm", "left": "16mm"}
    foot = "".join(f"<div>{x}</div>" for x in opt.get("footer_lines") or [])
    sheet = (f"<style>html{{zoom:.44;background:#e5e7eb}} body{{width:210mm;height:297mm;margin:14px auto;background:#fff;"
             f"box-shadow:0 8px 30px #0003;padding:{mg['top']} {mg['right']} {mg['bottom']} {mg['left']};overflow:hidden;"
             "position:relative} .tfoot{position:absolute;left:0;right:0;bottom:6mm;text-align:center;font:7.5pt Arial;"
             f"color:#333}}</style>")
    return page.replace("</head>", sheet + "</head>", 1).replace("</main>", f'</main><div class="tfoot">{foot}</div>', 1)


async def render_preview(t: dict, lang: str, out: Path) -> Path:
    """A sample page of a PDF / Word template rendered to PNG (the model compares it with the reference picture)."""
    from playwright.async_api import async_playwright
    out.parent.mkdir(parents=True, exist_ok=True)
    page_html = _real_page(t, lang).replace("html{zoom:.44;", "html{zoom:1;", 1)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        try:
            pg = await b.new_page(viewport={"width": 860, "height": 1180})
            await pg.set_content(page_html)
            await pg.wait_for_timeout(200)
            await pg.screenshot(path=str(out), full_page=False)
        finally:
            await b.close()
    return out


def preview_html(t: dict, lang: str, kind: str = "") -> str:
    a, d, tint = t["colors"]
    kind = kind if kind in t["kinds"] else t["kinds"][0]
    if kind in ("pdf", "docx"):
        try:
            return _real_page(t, lang)
        except Exception:  # noqa: BLE001 - the drawn thumbnail below still works
            pass
    name = html.escape(text(t, "name", lang))
    outline = [html.escape(x) for x in (text(t, "outline", lang) or [])]
    serif = t.get("font") == "serif"
    font = 'Georgia, "Times New Roman", serif' if serif else '"Segoe UI", Arial, sans-serif'
    base = (f"<!doctype html><html><head><meta charset='utf-8'><style>html,body{{margin:0;height:100%;overflow:hidden;"
            f"font-family:{font};-webkit-font-smoothing:antialiased}}*{{box-sizing:border-box}}")
    if kind in ("xlsx", "pptx"):  # drawn as what the layout makes (template_thumbs.py)
        from . import template_thumbs as tt
        try:
            return (tt.xlsx_thumb(t, text(t, "name", lang), lang) if kind == "xlsx"
                    else tt.pptx_thumb(t, text(t, "name", lang), text(t, "outline", lang) or [], lang))
        except Exception:  # noqa: BLE001 - the simple thumbnail below
            pass
    if kind == "xlsx":
        cols = "ABCDEFG"
        head = "".join(f"<th>{c}</th>" for c in cols)
        dark = t.get("cover") == "dark"
        bg, fg = ("#0b1220", "#e2e8f0") if dark else ("#fff", "#1f2933")
        xth = {"lines": f"background:#fff;color:{d};border-bottom:2px solid {d} !important",
               "soft": f"background:{tint};color:{d}"}.get(t.get("table"), f"background:{'#0b1220' if dark else a};color:#fff")
        kpi = "".join(f"<div class='k'><span>{html.escape(x)}</span><b>{v}</b></div>"
                      for x, v in zip((outline + ["", "", ""])[:3], ("31,500", "4,480", "$403,700")))
        rows = "".join("<tr>" + "".join(f"<td>{'' if j else i + 1}</td>" for j in range(7)) + "</tr>" for i in range(14))
        return (base + f"body{{background:{bg};color:{fg};font-size:9px}}.bar{{background:{d};color:#fff;padding:7px 9px;"
                f"font-weight:700;font-size:12px}}.ks{{display:flex;gap:5px;padding:6px}}.k{{flex:1;border:1px solid {a}55;"
                f"border-radius:4px;padding:4px 6px}}.k span{{display:block;font-size:7px;opacity:.7}}.k b{{font-size:13px;color:{a}}}"
                f"table{{border-collapse:collapse;width:100%}}th{{{xth};font-weight:600;font-size:8px}}"
                f"td,th{{border:1px solid {'#1e293b' if dark else '#e5e7eb'};height:13px;padding:0 3px}}"
                f"tr:nth-child(even) td{{background:{'#111a2e' if dark else tint}}}</style></head><body>"
                f"<div class='bar'>{name}</div><div class='ks'>{kpi}</div><table><tr>{head}</tr>{rows}</table></body></html>")
    if kind == "pptx":
        dark = t.get("cover") in ("dark", "hero")
        bg = (f"linear-gradient(135deg,{d},{a})" if t.get("cover") == "hero" else "#0a0a0a" if t.get("cover") == "dark"
              else "#fff")
        fg = "#fff" if dark else d
        return (base + f"body{{background:#e5e7eb;display:grid;place-items:center}}.s{{width:92%;aspect-ratio:16/9;"
                f"background:{bg};color:{fg};border-radius:6px;padding:9% 8%;box-shadow:0 6px 18px #0002;position:relative;"
                f"display:flex;flex-direction:column;justify-content:center}}.s small{{color:{a if not dark else '#fff'};"
                f"opacity:.85;font-size:9px;letter-spacing:.08em;text-transform:uppercase}}.s h1{{margin:6px 0 4px;"
                f"font-size:22px;line-height:1.1}}.s p{{margin:0;font-size:9px;opacity:.75}}.s i{{position:absolute;left:8%;"
                f"bottom:12%;width:22%;height:3px;background:{a}}}</style></head><body><div class='s'><small>2026</small>"
                f"<h1>{name}</h1><p>{' · '.join(outline[1:4])}</p><i></i></div></body></html>")
    cover = t.get("cover")
    year = "2026"
    if cover == "photo":
        hero = (f"<div style='height:40%;background:linear-gradient(180deg,#0000,#0008),radial-gradient(circle at 75% 30%,{a}aa,transparent 55%),"
                f"linear-gradient(135deg,{a},{d});display:flex;flex-direction:column;justify-content:flex-end;padding:10px 12px;"
                f"color:#fff'><small style='font-size:6px;letter-spacing:.2em;opacity:.8'>{year}</small>"
                f"<b style='font-size:14px;line-height:1.1'>{name}</b></div>")
    elif cover == "minimal":
        hero = (f"<div style='border-top:4px solid {a};margin:12px 12px 4px;padding-top:10px;text-align:center'>"
                f"<div style='font-size:6px;letter-spacing:.25em;color:{a};text-transform:uppercase'>{year}</div>"
                f"<div style='font-size:15px;color:{d};font-weight:700;margin-top:5px;line-height:1.1'>{name}</div></div>")
    elif cover == "band":
        hero = (f"<div style='background:{d};color:#fff;padding:12px;display:flex;justify-content:space-between;gap:6px'>"
                f"<div><small style='font-size:6px;opacity:.7;letter-spacing:.2em'>{year}</small><br><b style='font-size:13px;line-height:1.1'>{name}</b></div>"
                f"<span style='width:26px;background:{a};margin:-12px -12px -12px 0'></span></div>")
    elif cover == "dark":
        hero = (f"<div style='background:#0b1220;color:#fff;padding:14px 12px'><small style='font-size:6px;color:{a};"
                f"letter-spacing:.2em'>{year}</small><div style='font-size:14px;font-weight:700;line-height:1.1;margin-top:3px'>{name}</div>"
                f"<div style='height:3px;width:30%;background:{a};margin-top:6px'></div></div>")
    elif cover == "split":
        hero = (f"<div style='background:{tint};border-left:9px solid {a};color:{d};padding:14px 10px'>"
                f"<small style='font-size:6px;color:{a};font-weight:700;letter-spacing:.2em'>{year}</small>"
                f"<div style='font-size:14px;font-weight:700;line-height:1.1;margin-top:3px'>{name}</div></div>")
    elif cover == "editorial":
        hero = (f"<div style='margin:10px 12px 4px;border-top:2px solid {d};border-bottom:1px solid {d};padding:12px 0 9px;"
                f"text-align:center;color:{d}'><div style='font-family:Georgia,serif;font-size:16px;font-weight:700;line-height:1.1'>{name}</div>"
                f"<div style='font-size:6px;letter-spacing:.3em;color:{a};margin-top:5px'>{year}</div></div>")
    elif cover == "corner":
        hero = (f"<div style='position:relative;border:1px solid #e2e8f0;margin:8px;padding:16px 10px 12px;color:{d};overflow:hidden'>"
                f"<span style='position:absolute;right:0;top:0;width:44px;height:44px;background:linear-gradient(225deg,{d} 0 48%,"
                f"{a} 48% 58%,transparent 58%)'></span><small style='font-size:6px;color:{a};font-weight:700'>{year}</small>"
                f"<div style='font-size:14px;font-weight:700;line-height:1.1;margin-top:3px;max-width:75%'>{name}</div></div>")
    else:
        hero = (f"<div style='background:linear-gradient(135deg,{d},{a});color:#fff;padding:14px 12px;margin:8px;"
                f"border-radius:6px;position:relative;overflow:hidden'><span style='position:absolute;right:-14px;top:-14px;"
                f"width:50px;height:50px;border-radius:50%;background:#ffffff22'></span><small style='font-size:6px;"
                f"opacity:.8;letter-spacing:.2em'>{year}</small><div style='font-size:14px;font-weight:700;line-height:1.1'>{name}</div></div>")
    h2s = t.get("h2") or "bar"
    h2css = {"bar": f"border-left:3px solid {a};padding-left:5px",
             "number": "", "underline": f"border-bottom:1.5px solid {a};padding-bottom:2px",
             "caps": f"text-transform:uppercase;letter-spacing:.12em;color:{a};font-size:7px;border-bottom:1px solid #e5e7eb;padding-bottom:2px"}[h2s if h2s in H2_STYLES else "bar"]
    tbl = t.get("table") or "solid"
    th = {"solid": f"background:{a};color:#fff", "lines": f"background:#fff;color:{d};border-bottom:1.5px solid {d}",
          "soft": f"background:{tint};color:{d}"}[tbl if tbl in TABLE_STYLES else "solid"]
    kpis = "".join(f"<div class='k'><i></i><b>{v}</b></div>" for v in ("84%", "12,4K", "+18%"))
    secs = []
    for i, x in enumerate(outline[:3]):
        num = f"<em>{i + 1:02d}</em>" if h2s == "number" else ""
        secs.append(f"<h2>{num}{x}</h2><p class='l'></p><p class='l s'></p>")
        if i == 0:
            secs.append(f"<div class='ks'>{kpis}</div>")
        if i == 1:
            secs.append("<table><tr><th></th><th></th><th></th></tr>" + "<tr><td></td><td></td><td></td></tr>" * 3 + "</table>")
    return (base + f"body{{background:#e5e7eb;display:grid;place-items:center}}.pg{{width:74%;height:96%;background:#fff;"
            f"box-shadow:0 6px 18px #0002;overflow:hidden}}h2{{font-size:8px;color:{d};margin:8px 12px 3px;{h2css}}}"
            f"h2 em{{font-style:normal;background:{a};color:#fff;border-radius:2px;padding:0 3px;margin-right:4px;font-size:7px}}"
            f".l{{height:4px;background:#e5e7eb;margin:3px 12px;border-radius:2px}}.l.s{{width:60%}}"
            f".ks{{display:flex;gap:4px;margin:5px 12px}}.k{{flex:1;border:1px solid #e2e8f0;border-top:2px solid {a};border-radius:3px;"
            f"padding:3px 4px}}.k i{{display:block;height:2px;width:50%;background:#cbd5e1;margin-bottom:2px}}.k b{{font-size:8px;color:{d}}}"
            f"table{{width:calc(100% - 24px);margin:5px 12px;border-collapse:collapse}}th{{{th};height:7px}}"
            f"td{{height:6px;border-bottom:1px solid #eef2f6}}tr:nth-child(odd) td{{background:{tint if tbl == 'solid' else '#fff'}}}"
            f"</style></head><body><div class='pg'>{hero}{''.join(secs)}</div></body></html>")
