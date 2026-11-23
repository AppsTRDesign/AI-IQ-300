"""Professional document generation: PDF, DOCX, PPTX, XLSX and HTML from one source.

Input is Markdown (headings, lists, tables, links, images, code, quotes, LaTeX math) or HTML. Both become one HTML
structure that every format is built from:
- PDF / HTML: rendered by headless Chromium with a designed stylesheet and KaTeX, so every script (Turkish, Arabic,
  CJK, Cyrillic, Greek, Devanagari...) uses real system fonts, links stay clickable and formulas are typeset.
  Without Chromium, ReportLab with a full-Unicode font is the fallback.
- DOCX: python-docx with real styles, tables, numbered/bulleted lists, hyperlinks, images; formulas as crisp images.
- PPTX: designed 16:9 slides (title slide, section slides, native tables, images, formulas, slide numbers).
- XLSX: JSON rows / sheets or the tables of a Markdown/HTML source, with header style, widths, filters and numbers.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import re
import tempfile
import time
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).parent / "doc_assets"
KATEX = ASSETS / "katex"

THEMES = {  # accent, dark accent, light tint
    "blue": ("#2563EB", "#1E3A8A", "#EFF4FF"), "corporate": ("#1F4E79", "#0F2A44", "#EEF3F8"),
    "green": ("#059669", "#064E3B", "#ECFDF5"), "red": ("#DC2626", "#7F1D1D", "#FEF2F2"),
    "purple": ("#7C3AED", "#4C1D95", "#F5F3FF"), "orange": ("#EA580C", "#7C2D12", "#FFF7ED"),
    "teal": ("#0D9488", "#134E4A", "#F0FDFA"), "gray": ("#374151", "#111827", "#F3F4F6"),
    "dark": ("#0EA5E9", "#0B1220", "#E0F2FE"),
}
DEFAULT_THEME = "corporate"
FONT_STACK = ('"Segoe UI", "Noto Sans", "DejaVu Sans", Arial, "Nirmala UI", "Leelawadee UI", "Segoe UI Historic", '
              '"Microsoft YaHei", "Yu Gothic", "Malgun Gothic", "Noto Sans CJK SC", "Noto Sans Arabic", sans-serif')
MONO_STACK = '"Cascadia Mono", Consolas, "DejaVu Sans Mono", "Courier New", monospace'
RTL_CHARS = re.compile(r"[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]")


# A heading with no space after its #s ("###Ekran Görüntüleme", a weak model's Markdown): CommonMark keeps it as a
# paragraph and "###" was printed in the PDF. A short line with one run of #s and a letter right after it is a heading;
# "#1", "#hashtag #other" and code (masked before this) stay as they are.
_TIGHT_HEADING = re.compile(r"^( {0,3})(#{1,6})(?=[^\W\d_])([^\n#]{1,150})$", re.M)
_HTML_MD_HEADING = re.compile(r"<p>\s*(#{1,6})[ \t]*([^<#\n][^<\n]{0,150}?)\s*</p>")


def _space_headings(text: str) -> str:
    def fix(m: re.Match) -> str:
        if len(m.group(2)) == 1 and " " not in m.group(3).strip():  # a lone "#hashtag" line
            return m.group(0)
        return f"{m.group(1)}{m.group(2)} {m.group(3)}"
    return _TIGHT_HEADING.sub(fix, text)


def _html_md_headings(text: str) -> str:
    """<p>### Heading</p> in HTML content (Markdown mixed into a tag): a real <h3>."""
    return _HTML_MD_HEADING.sub(lambda m: f"<h{len(m.group(1))}>{m.group(2).strip()}</h{len(m.group(1))}>", text)


# ---------------------------------------------------------------- source: Markdown / HTML -> one HTML structure
class Source:
    """The document as an HTML fragment (or a full HTML page the user designed) plus its formulas."""

    def __init__(self, content: str, base_dir: Path | None = None):
        self.base_dir = base_dir
        self.maths: list[tuple[str, bool]] = []
        text = (content or "").replace("\r\n", "\n").strip("\ufeff")
        self.full_page = bool(re.match(r"\s*(<!doctype|<html)", text, re.I))
        self.is_html = self.full_page or bool(re.match(r"\s*<(div|section|article|h[1-6]|p|table|ul|ol|header|main|body|style)\b", text, re.I))
        if self.is_html:
            self.html = self._protect_html(text)
        else:
            self.html = self._markdown(text)
        self.missing: list[str] = []
        self.images = 0
        self._verify_images()
        # charts drawn in the HTML itself (inline SVG, the .bars component) are real visuals too
        self.images += len(re.findall(r'<svg\b|class="[^"]*\bbars\b', self.html))
        plain = re.sub(r"<[^>]+>", " ", self.html)
        letters = max(1, len(re.findall(r"\w", plain)))
        self.rtl = len(RTL_CHARS.findall(plain)) / letters > 0.3

    def _verify_images(self) -> None:
        """Only images that really exist and decode go into a document. A picture the model only named (a chart it
        never created, a made-up URL) would show as a broken icon: it is removed and reported, never faked. Valid
        ones are embedded as data, so every format gets exactly the verified bytes."""
        def check(m: re.Match) -> str:
            tag = m.group(0)
            sm = re.search(r'src\s*=\s*["\']([^"\']+)["\']', tag, re.I)
            src = sm.group(1) if sm else ""
            data = _image_bytes(src, self.base_dir) if src else None
            ready = _png_ready(data) if data else None
            if not ready:
                self.missing.append(src or "(no src)")
                return ""
            self.images += 1
            if src.startswith("data:") or len(data) > 6_000_000:
                return tag
            raw = ready[0].getvalue()
            mime = "image/jpeg" if raw[:2] == b"\xff\xd8" else "image/gif" if raw[:3] == b"GIF" else "image/png"
            return tag.replace(sm.group(0), f'src="data:{mime};base64,{base64.b64encode(raw).decode()}"')
        self.html = re.sub(r"<img\b[^>]*>", check, self.html, flags=re.I)
        if self.missing:  # the empty paragraph / figure a removed image leaves behind
            self.html = re.sub(r"<(p|figure)>\s*</\1>", "", self.html)

    # math: $$..$$, \[..\] (display), $..$, \(..\) (inline); never inside code
    _DISPLAY = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.S)
    _INLINE = re.compile(r"(?<![\\$\w])\$(?![\s$])([^$\n]{1,400}?)(?<![\s\\])\$(?![\w$])|\\\((.+?)\\\)")

    def _math(self, text: str) -> str:
        def disp(m):
            self.maths.append(((m.group(1) or m.group(2)).strip(), True))
            return f"\n\nMATHPH{len(self.maths) - 1}X\n\n"

        def inl(m):
            tex = (m.group(1) or m.group(2) or "").strip()
            if not tex or re.fullmatch(r"[\d.,\s]+", tex):  # "$5" currency, not math
                return m.group(0)
            self.maths.append((tex, False))
            return f"MATHPH{len(self.maths) - 1}X"
        return self._INLINE.sub(inl, self._DISPLAY.sub(disp, text))

    def _markdown(self, text: str) -> str:
        from markdown_it import MarkdownIt
        stash: list[str] = []

        def keep(m):
            stash.append(m.group(0))
            return f"CODEPH{len(stash) - 1}X"
        masked = re.sub(r"```.*?```|~~~.*?~~~|`[^`\n]+`", keep, text, flags=re.S)
        masked = self._math(masked)
        # bare URLs become links (commonmark autolinks); ones already inside [text](url) or <...> stay as they are
        masked = re.sub(r"(?<![<(\[\"'=/\w])(https?://[^\s<>()\[\]\"']+[^\s<>()\[\]\"'.,;:!?])", r"<\1>", masked)
        masked = _space_headings(masked)
        masked = re.sub(r"CODEPH(\d+)X", lambda m: stash[int(m.group(1))], masked)
        # page breaks the model may write
        masked = re.sub(r"^\s*(\\pagebreak|\\newpage|<!--\s*pagebreak\s*-->)\s*$", '<div class="page-break"></div>',
                        masked, flags=re.M)
        md = MarkdownIt("commonmark", {"html": True, "typographer": False}).enable(
            ["table", "strikethrough"])
        return self._restore(md.render(masked))

    def _protect_html(self, text: str) -> str:
        parts = re.split(r"(<(pre|code|script|style|textarea)\b.*?</\2>)", text, flags=re.S | re.I)
        out = []
        i = 0
        while i < len(parts):
            out.append(self._math(_html_md_headings(parts[i])) if i % 3 == 0 else parts[i])
            i += 1 if i % 3 == 0 else (2 if i % 3 == 1 else 1)
        return self._restore("".join(out))

    def _restore(self, html: str) -> str:
        html = re.sub(r"<p>\s*MATHPH(\d+)X\s*</p>", lambda m: f'<div class="math-display" data-i="{m.group(1)}"></div>', html)
        return re.sub(r"MATHPH(\d+)X", lambda m: f'<span class="math{"-display" if self.maths[int(m.group(1))][1] else ""}" '
                      f'data-i="{m.group(1)}"></span>', html)

    def title(self) -> str:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", self.html, re.S | re.I) or re.search(r"<title>(.*?)</title>", self.html, re.S | re.I)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


TEMPLATE_CSS: dict[str, str] = {}  # extra CSS of a document template (doc_templates.py registers it with its colors)
TEMPLATE_SPEC: dict[str, dict] = {}  # the whole template (layout, fonts, margins, header / footer, logo) per theme id
SERIF_STACK = 'Georgia, "Times New Roman", "Noto Serif", "DejaVu Serif", serif'


def _css(theme: str) -> str:
    return _base_css(theme) + TEMPLATE_CSS.get(theme, "")


def _base_css(theme: str) -> str:
    a, d, t = THEMES.get(theme, THEMES[DEFAULT_THEME])
    return f"""
@page {{ size: A4; margin: 18mm 16mm 20mm 16mm; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font-family: {FONT_STACK}; font-size: 10.5pt; line-height: 1.6; color: #1f2933; background: #fff;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; text-rendering: optimizeLegibility; }}
.hero {{ margin: 0 0 16pt; padding: 20pt 22pt 18pt; border-radius: 10pt; color: #fff;
  background: linear-gradient(135deg, {d} 0%, {a} 100%); position: relative; overflow: hidden; break-inside: avoid; }}
.hero::after {{ content: ""; position: absolute; right: -40pt; top: -40pt; width: 160pt; height: 160pt; border-radius: 50%;
  background: rgba(255,255,255,.08); }}
.hero h1 {{ font-size: 25pt; line-height: 1.18; margin: 0; color: #fff; letter-spacing: -0.3pt; position: relative; }}
.hero .lead {{ margin: 8pt 0 0; font-size: 11pt; color: rgba(255,255,255,.88); position: relative; }}
.hero strong, .hero a {{ color: #fff; }}
.hero .meta {{ margin-top: 12pt; font-size: 8.5pt; letter-spacing: .6pt; text-transform: uppercase; color: rgba(255,255,255,.7);
  position: relative; }}
h1 {{ font-size: 19pt; color: {d}; margin: 20pt 0 8pt; line-height: 1.25; }}
h2 {{ font-size: 14.5pt; color: {d}; margin: 20pt 0 8pt; padding: 1pt 0 1pt 10pt; border-left: 4pt solid {a}; }}
h3 {{ font-size: 12pt; color: {a}; margin: 14pt 0 5pt; }}
h4, h5, h6 {{ font-size: 10.5pt; color: {d}; margin: 12pt 0 4pt; }}
h1, h2, h3, h4 {{ break-after: avoid; page-break-after: avoid; }}
p {{ margin: 0 0 8pt; orphans: 3; widows: 3; }}
a {{ color: {a}; text-decoration: none; border-bottom: 0.5pt solid {a}66; word-break: break-word; }}
strong {{ color: #102a43; }}
ul, ol {{ margin: 0 0 9pt; padding-left: 18pt; }}
li {{ margin: 2pt 0; }}
li::marker {{ color: {a}; font-weight: 600; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin: 6pt 0 12pt; font-size: 9.5pt;
  border: 0.75pt solid #d9e2ec; border-radius: 4pt; overflow: hidden; break-inside: auto; }}
thead {{ display: table-header-group; }}
table.keep {{ break-inside: avoid; page-break-inside: avoid; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
th {{ background: {d}; color: #fff; font-weight: 600; text-align: left; padding: 7pt 9pt; border: none; font-size: 9pt;
  letter-spacing: .2pt; }}
td {{ padding: 5pt 8pt; border-top: 0.75pt solid #e4e7eb; vertical-align: top; }}
tbody tr:nth-child(even) td {{ background: {t}; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
blockquote {{ margin: 10pt 0 12pt; padding: 9pt 13pt; background: {t}; border-left: 4pt solid {a}; color: #243b53;
  border-radius: 0 6pt 6pt 0; }}
blockquote strong:first-child {{ color: {d}; }}
blockquote p:last-child {{ margin-bottom: 0; }}
code {{ font-family: {MONO_STACK}; font-size: 9pt; background: #f0f4f8; padding: 1pt 4pt; border-radius: 3pt; }}
pre {{ font-family: {MONO_STACK}; font-size: 8.8pt; line-height: 1.45; background: #0f172a; color: #e2e8f0;
  padding: 9pt 11pt; border-radius: 5pt; white-space: pre-wrap; word-break: break-word; break-inside: avoid; }}
pre code {{ background: none; padding: 0; color: inherit; font-size: inherit; }}
hr {{ border: none; border-top: 1pt solid #d9e2ec; margin: 14pt 0; }}
img {{ max-width: 100%; height: auto; border-radius: 4pt; break-inside: avoid; }}
p > img:only-child {{ display: block; margin: 6pt auto; }}
.math-display {{ display: block; text-align: center; margin: 8pt 0 10pt; overflow-x: auto; break-inside: avoid; }}
.katex {{ font-size: 1.08em; }}
.page-break {{ break-after: page; page-break-after: always; }}
/* Ready-made components for HTML content: KPI cards, a bar chart, a callout, badges, two columns. */
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 104pt), 1fr)); gap: 8pt; margin: 8pt 0 12pt;
  break-inside: avoid; width: 100%; box-sizing: border-box; }}
.kpi {{ border: 0.75pt solid #d9e2ec; border-top: 3pt solid {a}; border-radius: 8pt; padding: 8pt 10pt; background: #fff;
  min-width: 0; overflow: hidden; box-sizing: border-box; display: flex; flex-direction: column; gap: 1pt; }}
.kpi b {{ display: block; font-size: 15.5pt; line-height: 1.15; color: {d}; overflow-wrap: anywhere; word-break: break-word;
  hyphens: auto; }}
.kpi span {{ display: block; font-size: 7.5pt; color: #627d98; text-transform: uppercase; letter-spacing: .3pt; margin-bottom: 2pt;
  overflow-wrap: anywhere; }}
.kpi em {{ display: block; font-style: normal; font-size: 8.5pt; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }}
.kpi b.long {{ font-size: 12pt; }}
.up {{ color: #059669; }} .down {{ color: #dc2626; }}
.bars {{ display: grid; gap: 6pt; margin: 8pt 0 12pt; padding: 10pt 12pt; border: 0.75pt solid #d9e2ec; border-radius: 8pt; break-inside: avoid; }}
.bars > div {{ display: grid; grid-template-columns: 120pt 1fr 70pt; align-items: center; gap: 8pt; font-size: 9.5pt; }}
.bars > div > i {{ display: block; height: 12pt; border-radius: 6pt; background: {t}; position: relative; overflow: hidden; }}
.bars > div > i::after {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: var(--v, 50%); border-radius: 6pt;
  background: linear-gradient(90deg, {a}, {d}); }}
.bars > div > b {{ text-align: right; font-variant-numeric: tabular-nums; color: {d}; }}
.callout {{ margin: 10pt 0 12pt; padding: 9pt 13pt; border-radius: 8pt; background: {t}; border: 0.75pt solid {a}55; color: #243b53; break-inside: avoid; }}
.callout.warn {{ background: #fffbeb; border-color: #f59e0b88; }}
.badge {{ display: inline-block; padding: 1pt 7pt; border-radius: 99pt; background: {t}; color: {d}; font-size: 8.5pt; font-weight: 600; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14pt; }}
[dir=rtl] th {{ text-align: right; }}
[dir=rtl] blockquote {{ border-left: none; border-right: 3pt solid {a}; border-radius: 4pt 0 0 4pt; }}
"""


HERO_DATE = {"tr": "%d.%m.%Y", "de": "%d.%m.%Y", "fr": "%d/%m/%Y", "es": "%d/%m/%Y", "it": "%d/%m/%Y", "en": "%B %d, %Y"}


def _hero(html: str, lang: str) -> str:
    """The first # title (and the paragraph right after it) becomes the coloured cover band of the document."""
    m = re.match(r"\s*<h1[^>]*>(.*?)</h1>\s*(<p>(?:(?!<p>).){0,400}?</p>)?", html, re.S)
    if not m:
        return html
    lead = m.group(2) or ""
    if lead and re.search(r"<(img|table|div)", lead):
        lead = ""
    date = time.strftime(HERO_DATE.get(lang, "%Y-%m-%d"))
    lead_html = f'<p class="lead">{lead[3:-4]}</p>' if lead else ""
    return (f'<header class="hero"><h1>{m.group(1)}</h1>{lead_html}<div class="meta">{date}</div></header>'
            + html[m.end() if lead else m.end(1) + len("</h1>"):])


def _page(src: Source, theme: str, lang: str, title: str) -> str:
    """The full HTML page: the user's own page as is, or the fragment inside the designed template."""
    katex_css = (KATEX / "katex.min.css").as_uri()
    head_extra = f'<link rel="stylesheet" href="{katex_css}">'
    if src.base_dir:
        head_extra = f'<base href="{src.base_dir.resolve().as_uri()}/">' + head_extra
    if src.full_page:
        html = src.html
        if re.search(r"<head[^>]*>", html, re.I):
            return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + '<meta charset="utf-8">' + head_extra, html, count=1, flags=re.I)
        return head_extra + html
    from html import escape
    body = _num_cells(_kpi_fit(src.html))
    spec = TEMPLATE_SPEC.get(theme)
    if spec:  # the template's own layout (letter, memo, academic, magazine...) instead of the coloured cover
        from .doc_templates import layout_body
        body = layout_body(spec, body, lang, _hero)
        lay = spec.get("layout") or "report"
    else:
        body, lay = _hero(body, lang), "report"
    return (f'<!doctype html><html lang="{lang}" dir="{"rtl" if src.rtl else "ltr"}"><head><meta charset="utf-8">'
            f"<title>{escape(title)}</title>{head_extra}<style>{_css(theme)}</style></head>"
            f'<body class="layout-{lay}"><main class="doc">{body}</main></body></html>')


def _kpi_fit(html: str) -> str:
    """A long KPI value ("i5-12400F / 6C-12T", "1.840.000 TL") gets a smaller size, so 4 cards in a row never overflow.
    A short table (up to 14 rows) is kept on one page: its header row was left alone at the foot of a page."""
    if "<table" in html:
        def keep(m: re.Match) -> str:
            attrs = m.group(1) or ""
            if m.group(0).count("<tr") > 14 or "class=" in attrs:
                return m.group(0)
            return f'<table class="keep"{attrs}>' + m.group(0)[m.group(0).index(">") + 1:]
        html = re.sub(r"<table(\s[^>]*)?>.*?</table>", keep, html, flags=re.S | re.I)
    if "kpi" not in html:
        return html
    return re.sub(r"(<div class=[\"']kpi[\"'][^>]*>(?:(?!</div>).)*?)<b>([^<]{11,})</b>",
                  lambda m: f'{m.group(1)}<b class="long">{m.group(2)}</b>', html, flags=re.S)


NUM_CELL = re.compile(r"^\s*[%₺$€£¥]?\s*[-+]?[\d.,\s%₺$€£¥]+(?:\s?(?:TL|USD|EUR|GBP|%))?\s*$")


def _num_cells(html: str) -> str:
    """Numeric columns (amounts, percentages, prices) align right, their header too."""
    if "<table" not in html:
        return html
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = [r.find_all(["td", "th"]) for r in table.find_all("tr")]
        body = [r for r in rows if r and r[0].name == "td"]
        if not body:
            continue
        for ci in range(max(len(r) for r in rows)):
            cells = [r[ci] for r in body if ci < len(r)]
            num = [c for c in cells if NUM_CELL.match(c.get_text()) and re.search(r"\d", c.get_text())]
            if cells and len(num) >= max(1, len(cells) * 0.6):
                for c in [r[ci] for r in rows if ci < len(r)]:
                    c["class"] = (c.get("class") or []) + ["num"]
    return str(soup)


MATH_JS = """(maths) => {
  for (const el of document.querySelectorAll('.math, .math-display')) {
    const [tex, display] = maths[+el.dataset.i] || ['', false];
    try { katex.render(tex, el, {displayMode: !!display, throwOnError: false, output: 'html', strict: 'ignore', trust: false}); }
    catch (e) { el.textContent = tex; }
  }
  if (window.renderMathInElement) renderMathInElement(document.body, {delimiters: [
    {left: '$$', right: '$$', display: true}, {left: '\\\\[', right: '\\\\]', display: true},
    {left: '\\\\(', right: '\\\\)', display: false}], throwOnError: false, ignoredTags: ['script','noscript','style','textarea','pre','code']});
}"""


class _Browser:
    """One headless Chromium for a document (formula images + PDF share it)."""

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        try:
            self.browser = await self.pw.chromium.launch(headless=True)
        except Exception:
            await self.pw.stop()
            raise
        return self

    async def __aexit__(self, *exc):
        try:
            await self.browser.close()
        finally:
            await self.pw.stop()

    async def open(self, html: str, maths: list, scale: float = 1.0, render_math: bool = True):
        tmp = Path(tempfile.mkdtemp(prefix="aiiq-doc-")) / "page.html"
        tmp.write_text(html, encoding="utf-8")
        page = await self.browser.new_page(device_scale_factor=scale)
        await page.goto(tmp.as_uri(), wait_until="load", timeout=60000)
        if render_math:
            await page.add_script_tag(path=str(KATEX / "katex.min.js"))
            await page.add_script_tag(path=str(KATEX / "contrib" / "auto-render.min.js"))
            await page.evaluate(MATH_JS, [list(m) for m in maths])
        try:
            await page.evaluate("document.fonts.ready.then(() => true)")
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        return page, tmp


def _footer(title: str, lines: list[str] | None = None, side: str = "16mm") -> str:
    from html import escape
    t = escape(title[:90])
    if lines:  # a template's own footer (an institution's name and address): centred lines, the page number apart
        body = "".join(f'<div style="font-weight:700;color:#111">{x[2:-2]}</div>' if x.startswith("**") and x.endswith("**")
                       else f"<div>{x}</div>" for x in lines)
        return (f'<div style="width:calc(100% - {side} - {side});font-size:7.5pt;color:#333;margin:0 {side};font-family:Arial,sans-serif;'
                f'position:relative;text-align:center;line-height:1.35;border-top:0.75pt solid #333;padding-top:4pt">{body}<span style="position:absolute;right:0;'
                'bottom:0;color:#829ab1"><span class="pageNumber"></span>/<span class="totalPages"></span></span></div>')
    return (f'<div style="width:100%;font-size:7.5pt;color:#829ab1;padding:0 {side};display:flex;'
            f'justify-content:space-between;font-family:Segoe UI,Arial,sans-serif"><span>{t}</span>'
            '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


async def _pdf(src: Source, target: Path, theme: str, lang: str, landscape: bool) -> dict:
    title = src.title() or target.stem
    opts: dict = {}
    if spec := TEMPLATE_SPEC.get(theme):
        from .doc_templates import page_options
        opts = page_options(spec)
    margin = opts.get("margin") or {"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"}
    async with _Browser() as b:
        page, tmp = await b.open(_page(src, theme, lang, title), src.maths)
        try:
            await page.emulate_media(media="print")
            if landscape:  # the template's @page { size: A4 } wins over the pdf() option: say it in CSS too
                await page.add_style_tag(content="@page { size: A4 landscape; }")
            await page.pdf(path=str(target), format="A4", landscape=landscape, print_background=True,
                           display_header_footer=not src.full_page, header_template="<div></div>",
                           footer_template=_footer(title, opts.get("footer_lines"), margin["left"]),
                           prefer_css_page_size=True, margin=None if src.full_page else margin)
        finally:
            await page.close()
            _rm(tmp)
    return {"engine": "chromium"}


async def _html_out(src: Source, target: Path, theme: str, lang: str) -> dict:
    """A standalone HTML file: formulas typeset in place, KaTeX styles from the CDN for viewing anywhere."""
    title = src.title() or target.stem
    async with _Browser() as b:
        page, tmp = await b.open(_page(src, theme, lang, title), src.maths)
        try:
            html = await page.content()
        finally:
            await page.close()
            _rm(tmp)
    html = re.sub(r'<script[^>]*katex[^>]*>.*?</script>|<script[^>]*auto-render[^>]*>.*?</script>', "", html, flags=re.S)
    html = re.sub(r'<link rel="stylesheet" href="file:[^"]*katex\.min\.css">',
                  '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">', html)
    html = re.sub(r'<base href="file:[^"]*">', "", html)
    target.write_text(html, encoding="utf-8")
    return {"engine": "chromium"}


def _rm(tmp: Path) -> None:
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass


VISUAL_SELECTOR = ".kpis, .bars, .callout, svg"


async def rasterize_components(src: Source, theme: str, lang: str) -> None:
    """Word and PowerPoint cannot lay out the HTML components (KPI cards, bar charts, inline SVG): each becomes a
    crisp image of exactly what the PDF shows, in place."""
    if not re.search(r'<svg\b|class="[^"]*\b(kpis|bars|callout)\b', src.html):
        return
    html = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><style>{_css(theme)}'
            f'body{{width:640px;padding:0}}</style></head><body><main class="doc">{src.html}</main></body></html>')
    try:
        async with _Browser() as b:
            page, tmp = await b.open(html, [], scale=2, render_math=False)
            try:
                n = await page.evaluate("(sel) => { const els = [...document.querySelectorAll(sel)].filter(e => !e.parentElement.closest(sel));"
                                        " els.forEach((e, i) => e.setAttribute('data-ras', i)); return els.length; }", VISUAL_SELECTOR)
                shots = {}
                for i in range(n):
                    shots[i] = base64.b64encode(await page.locator(f'[data-ras="{i}"]').screenshot()).decode()
                src.html = await page.evaluate(
                    "(shots) => { for (const [i, d] of Object.entries(shots)) { const e = document.querySelector(`[data-ras=\"${i}\"]`);"
                    " const img = document.createElement('img'); img.src = 'data:image/png;base64,' + d; const p = document.createElement('p');"
                    " p.appendChild(img); e.replaceWith(p); } return document.querySelector('main').innerHTML; }", shots)
            finally:
                await page.close()
                _rm(tmp)
    except Exception:  # noqa: BLE001 - without Chromium the components stay as plain text
        pass


async def math_images(maths: list[tuple[str, bool]]) -> dict[int, tuple[bytes, int, int]]:
    """Formula -> PNG (3x, transparent) with its CSS size in px: KaTeX in Chromium (full LaTeX); matplotlib's
    mathtext when Chromium is missing."""
    if not maths:
        return {}
    out: dict[int, tuple[bytes, int, int]] = {}
    try:
        body = "".join(f'<div style="display:inline-block;padding:2px 1px" id="m{i}"><span class="{"math-display" if d else "math"}" '
                       f'data-i="{i}"></span></div><br>' for i, (_, d) in enumerate(maths))
        html = (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{(KATEX / "katex.min.css").as_uri()}">'
                f'<style>body{{margin:0;background:transparent;font-size:15px;color:#111;font-family:{FONT_STACK}}}'
                f'.math-display{{display:inline-block}} .katex-display{{margin:0}}</style></head><body>{body}</body></html>')
        async with _Browser() as b:
            page, tmp = await b.open(html, maths, scale=3)
            try:
                for i in range(len(maths)):
                    el = page.locator(f"#m{i}")
                    box = await el.bounding_box()
                    png = await el.screenshot(omit_background=True)
                    out[i] = (png, round(box["width"]), round(box["height"]))
            finally:
                await page.close()
                _rm(tmp)
        return out
    except Exception:
        pass
    for i, (tex, _) in enumerate(maths):
        try:
            from matplotlib import mathtext
            from matplotlib.font_manager import FontProperties
            buf = io.BytesIO()
            mathtext.math_to_image(f"${tex}$", buf, prop=FontProperties(size=14), dpi=300, format="png")
            from PIL import Image
            im = Image.open(io.BytesIO(buf.getvalue()))
            out[i] = (buf.getvalue(), round(im.width / 3.1), round(im.height / 3.1))
        except Exception:
            continue
    return out


TEX_SYMBOLS = {r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\theta": "θ",
               r"\lambda": "λ", r"\mu": "μ", r"\pi": "π", r"\sigma": "σ", r"\phi": "φ", r"\omega": "ω", r"\Delta": "Δ",
               r"\Sigma": "Σ", r"\Omega": "Ω", r"\infty": "∞", r"\times": "×", r"\cdot": "·", r"\leq": "≤", r"\geq": "≥",
               r"\neq": "≠", r"\approx": "≈", r"\pm": "±", r"\rightarrow": "→", r"\to": "→", r"\leftarrow": "←",
               r"\Rightarrow": "⇒", r"\sum": "∑", r"\int": "∫", r"\sqrt": "√", r"\partial": "∂", r"\in": "∈",
               r"\forall": "∀", r"\exists": "∃", r"\nabla": "∇", r"\degree": "°", r"\div": "÷"}


def simple_tex(tex: str) -> bool:
    """A formula plain text shows exactly: letters, digits, operators and Greek/symbol commands, no layout."""
    if re.search(r"\\(frac|dfrac|sqrt|sum|prod|int|lim|begin|left|right|overline|hat|vec|binom|mathbb)|[\^_]", tex):
        return False
    rest = tex
    for k in TEX_SYMBOLS:
        rest = rest.replace(k, "")
    return bool(re.fullmatch(r"[\w\s+\-*/=<>().,:;|!'%]*", rest))


def tex_text(tex: str) -> str:
    """Readable text of a formula where an image cannot go (e.g. inside a slide's text)."""
    t = tex
    for k in sorted(TEX_SYMBOLS, key=len, reverse=True):
        t = t.replace(k, TEX_SYMBOLS[k])
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    t = re.sub(r"\\(text|mathrm|mathbf|mathit|operatorname)\{([^{}]*)\}", r"\2", t)
    return re.sub(r"\\[a-zA-Z]+|[{}]", "", t).strip()


# ---------------------------------------------------------------- images in documents
def _image_bytes(src: str, base_dir: Path | None) -> bytes | None:
    if not src:
        return None
    try:
        if src.startswith("data:"):
            return base64.b64decode(src.split(",", 1)[1])
        if src.startswith(("http://", "https://")):
            import httpx
            r = httpx.get(src, timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            return r.content if r.status_code < 400 else None
        if src.lower().startswith("file:"):  # file:///C:/My%20Folder/x.png -> C:\My Folder\x.png
            from urllib.parse import urlsplit
            from urllib.request import url2pathname
            src = url2pathname(urlsplit(src).path)
        p = Path(src)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return p.read_bytes() if p.is_file() else None
    except Exception:
        return None


def _png_ready(data: bytes) -> tuple[io.BytesIO, int, int] | None:
    """Any raster image as a stream python-docx/pptx accept (WEBP/GIF... become PNG), with its size in px."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        if im.format not in ("PNG", "JPEG", "BMP", "GIF"):
            buf = io.BytesIO()
            im.convert("RGBA").save(buf, "PNG")
            return io.BytesIO(buf.getvalue()), w, h
        return io.BytesIO(data), w, h
    except Exception:
        return None


# ---------------------------------------------------------------- DOCX
PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid",
             "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
             "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
              "textDirection", "tcFitText", "vAlign", "hideMark"]
TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW",
               "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook"]


def _docx(src: Source, target: Path, imgs: dict, theme: str) -> dict:
    from bs4 import BeautifulSoup, NavigableString, Tag
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor, Emu

    accent, dark, tint = (c.lstrip("#") for c in THEMES.get(theme, THEMES[DEFAULT_THEME]))
    rgb = lambda h: RGBColor.from_string(h.upper())  # noqa: E731
    spec = TEMPLATE_SPEC.get(theme) or {}  # a document template: its layout, type, margins, letterhead, footer
    lay = spec.get("layout") or "report"
    BASE = spec.get("font_family") or ("Georgia" if spec.get("font") == "serif" else "Calibri")
    h2style, tstyle = spec.get("h2") or "bar", spec.get("table") or "solid"
    page_opt = {}
    if spec:
        from .doc_templates import page_options
        page_opt = page_options(spec)
    doc = Document()
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Cm(2)
        s.left_margin = s.right_margin = Cm(2.2)
        if mg := page_opt.get("margin"):
            s.top_margin, s.right_margin = Cm(float(mg["top"][:-2]) / 10), Cm(float(mg["right"][:-2]) / 10)
            s.bottom_margin, s.left_margin = Cm(float(mg["bottom"][:-2]) / 10), Cm(float(mg["left"][:-2]) / 10)

    def fonts(style, name=None, size=None, color=None, bold=None):
        name = name or BASE
        style.font.name = name
        rpr = style.element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rpr.append(rf)
        for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rf.set(qn(k), name)
        if size:
            style.font.size = Pt(size)
        if color:
            style.font.color.rgb = rgb(color)
        if bold is not None:
            style.font.bold = bold

    st = doc.styles
    fonts(st["Normal"], size=10.5, color="1F2933")
    st["Normal"].paragraph_format.space_after = Pt(6)
    st["Normal"].paragraph_format.line_spacing = 1.2
    fonts(st["Title"], BASE if BASE != "Calibri" else "Calibri Light", 30, "FFFFFF", False)
    st["Title"].paragraph_format.space_before = Pt(0)
    st["Title"].paragraph_format.space_after = Pt(0)
    st["Title"].paragraph_format.line_spacing = 1.05
    # Headings: clear sizes and spacing, the theme's dark colour, the accent for the third level.
    for i, (sz, col, before, after) in enumerate([(20, dark, 20, 6), (15.5, dark, 18, 6), (12.5, accent, 12, 4),
                                                   (11, dark, 10, 3), (10.5, dark, 8, 2), (10.5, dark, 8, 2)], 1):
        fonts(st[f"Heading {i}"], None, sz, col, True)
        st[f"Heading {i}"].paragraph_format.space_before = Pt(before)
        st[f"Heading {i}"].paragraph_format.space_after = Pt(after)
        st[f"Heading {i}"].paragraph_format.keep_with_next = True
        st[f"Heading {i}"].paragraph_format.line_spacing = 1.1

    def put(parent, el, order):
        """Insert a child at its schema position (Word rejects out-of-order properties as unreadable content)."""
        tag = el.tag.split("}")[1]
        old = parent.find(qn(f"w:{tag}"))
        if old is not None:
            parent.remove(old)
        after = order[order.index(tag) + 1:] if tag in order else []
        for ch in parent:
            name = ch.tag.split("}")[-1]
            if name in after:
                ch.addprevious(el)
                return el
        parent.append(el)
        return el

    def border(par, side="bottom", color=accent, size=12):
        ppr = par._p.get_or_add_pPr()
        pb = ppr.find(qn("w:pBdr"))
        if pb is None:
            pb = put(ppr, OxmlElement("w:pBdr"), PPR_ORDER)
        e = OxmlElement(f"w:{side}")
        for k, v in (("val", "single"), ("sz", str(size)), ("space", "4"), ("color", color)):
            e.set(qn(f"w:{k}"), v)
        put(pb, e, ["top", "left", "bottom", "right", "between", "bar"])

    def shade(el, fill):
        is_cell = hasattr(el, "get_or_add_tcPr")
        pr = el.get_or_add_tcPr() if is_cell else el.get_or_add_pPr()
        sh = OxmlElement("w:shd")
        sh.set(qn("w:val"), "clear")
        sh.set(qn("w:color"), "auto")
        sh.set(qn("w:fill"), fill)
        put(pr, sh, TCPR_ORDER if is_cell else PPR_ORDER)

    def rtl(par):
        if src.rtl:
            put(par._p.get_or_add_pPr(), OxmlElement("w:bidi"), PPR_ORDER)

    def hyperlink(par, url, text, fmt):
        rid = par.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                 is_external=True)
        h = OxmlElement("w:hyperlink")
        h.set(qn("r:id"), rid)
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        if fmt.get("b"):
            rpr.append(OxmlElement("w:b"))
        if fmt.get("i"):
            rpr.append(OxmlElement("w:i"))
        c = OxmlElement("w:color")
        c.set(qn("w:val"), accent)
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rpr.append(c)
        rpr.append(u)
        r.append(rpr)
        t = OxmlElement("w:t")
        t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        h.append(r)
        par._p.append(h)

    def picture(par, data: bytes, width_px: int, height_px: int, max_w_cm=16.5, scale=1.0, inline_h_pt=None):
        ready = _png_ready(data)
        if not ready:
            return False
        stream, w, h = ready
        if inline_h_pt:  # formulas: CSS px at 96 dpi
            emu_w = Emu(int(width_px / 96 * 914400 * scale))
        else:
            emu_w = Emu(int(min(Cm(max_w_cm), Emu(int(w / 96 * 914400)))))
        par.add_run().add_picture(stream, width=emu_w)
        return True

    def inline(par, node, fmt=None):
        fmt = fmt or {}
        for ch in node.children:
            if isinstance(ch, NavigableString):
                text = str(ch)
                if not fmt.get("pre"):
                    text = re.sub(r"\s+", " ", text)
                if not text:
                    continue
                if fmt.get("href"):
                    hyperlink(par, fmt["href"], text, fmt)
                    continue
                run = par.add_run(text)
                run.bold = fmt.get("b") or None
                run.italic = fmt.get("i") or None
                run.underline = fmt.get("u") or None
                run.font.strike = fmt.get("s") or None
                if fmt.get("sup"):
                    run.font.superscript = True
                if fmt.get("sub"):
                    run.font.subscript = True
                if fmt.get("code"):
                    run.font.name = "Consolas"
                    run.font.size = Pt(9.5)
                    run.font.color.rgb = rgb("9B1C1C")
                if fmt.get("color"):
                    run.font.color.rgb = rgb(fmt["color"])
                continue
            if not isinstance(ch, Tag):
                continue
            name = ch.name.lower()
            cls = " ".join(ch.get("class") or [])
            if "math" in cls and ch.get("data-i") is not None:
                i = int(ch["data-i"])
                tex = src.maths[i][0]
                # Simple inline math (a variable, "x = 5", "\alpha") reads best as Word's own math italics, and in
                # coloured table headers an image would be dark on dark: those become text; the rest a typeset image.
                if i in imgs and not (simple_tex(tex) or fmt.get("color")):
                    png, w, h = imgs[i]
                    picture(par, png, w, h, inline_h_pt=True, scale=1.0)
                else:
                    run = par.add_run(tex_text(tex))
                    run.italic = True
                    run.font.name = "Cambria Math"
                    if fmt.get("color"):
                        run.font.color.rgb = rgb(fmt["color"])
                    run.bold = fmt.get("b") or None
                continue
            if name == "br":
                par.add_run().add_break()
            elif name == "img":
                data = _image_bytes(ch.get("src", ""), src.base_dir)
                if not (data and picture(par, data, 0, 0)):
                    par.add_run(ch.get("alt") or "")
            elif name in ("strong", "b"):
                inline(par, ch, {**fmt, "b": True})
            elif name in ("em", "i"):
                inline(par, ch, {**fmt, "i": True})
            elif name == "u":
                inline(par, ch, {**fmt, "u": True})
            elif name in ("s", "del", "strike"):
                inline(par, ch, {**fmt, "s": True})
            elif name == "code":
                inline(par, ch, {**fmt, "code": True})
            elif name == "sup":
                inline(par, ch, {**fmt, "sup": True})
            elif name == "sub":
                inline(par, ch, {**fmt, "sub": True})
            elif name == "a" and ch.get("href", "").startswith(("http", "mailto:")):
                inline(par, ch, {**fmt, "href": ch["href"]})
            else:
                inline(par, ch, fmt)

    first_h1 = [True]
    numbered = [0]

    def restart_numbering(par):
        """A new <ol> starts at 1 (Word would continue the previous list)."""
        try:
            numbering = doc.part.numbering_part.numbering_definitions._numbering
            style_num = doc.styles["List Number"].element.pPr.numPr.numId.val
            abstract = numbering.num_having_numId(style_num).abstractNumId.val
            num = numbering.add_num(abstract)
            ov = num.add_lvlOverride(ilvl=0)
            ov.add_startOverride(1)
            numpr = par._p.get_or_add_pPr().get_or_add_numPr()
            numpr.get_or_add_ilvl().val = 0
            numpr.get_or_add_numId().val = num.numId
        except Exception:
            pass

    skip: set = set()  # elements already placed (the cover's lead paragraph)
    doc_title = [""]

    h2_no = [0]

    def plain_cover(ch):
        """The first title in a template's own layout (letter, memo, academic, magazine, invoice, resume, minimal):
        no coloured block - a letterhead with the logo, or the title in the layout's own place and type."""
        date = time.strftime("%d.%m.%Y")
        if lay == "letter":
            logo = None
            if spec.get("logo"):
                from .doc_templates import asset_dir
                lp = asset_dir() / Path(str(spec["logo"])).name
                logo = lp.read_bytes() if lp.is_file() else None
            if logo:
                lpar = doc.add_paragraph()
                lpar.alignment = WD_ALIGN_PARAGRAPH.CENTER
                picture(lpar, logo, 0, 0, max_w_cm=5.5)
            for k, line in enumerate(spec.get("header") or []):
                hp = doc.add_paragraph()
                hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                hp.paragraph_format.space_after = Pt(0)
                hr = hp.add_run(line)
                hr.font.bold, hr.font.size, hr.font.color.rgb = True, Pt(11 if k == 0 else 10.5), rgb("111111")
            rule = doc.add_paragraph()
            border(rule, "bottom", "333333", 6)
            dp = doc.add_paragraph()
            dp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            dr = dp.add_run(date)
            dr.font.size = Pt(10)
            tp = doc.add_paragraph()
            tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.space_before, tp.paragraph_format.space_after = Pt(10), Pt(14)
            inline(tp, ch)
            for r in tp.runs:
                r.font.bold, r.font.size, r.font.all_caps, r.font.color.rgb = True, Pt(13), True, rgb("111111")
        else:
            centred = lay in ("academic",)
            if lay in ("minimal", "magazine", "memo"):
                kp = doc.add_paragraph()
                kr = kp.add_run({"memo": "NOT" if re.search("[çğışöüİ]", src.html[:3000]) else "MEMO"}.get(lay, date))
                kr.font.size, kr.font.bold, kr.font.color.rgb = Pt(9 if lay != "memo" else 22), True, rgb(accent)
            tp = doc.add_paragraph()
            if centred:
                tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tp.paragraph_format.space_after = Pt(4)
            inline(tp, ch)
            size = {"magazine": 30, "minimal": 28, "resume": 26, "invoice": 22, "memo": 17, "academic": 20}.get(lay, 24)
            for r in tp.runs:
                r.font.size, r.font.color.rgb = Pt(size), rgb(dark)
                r.font.bold = lay != "minimal"
            nxt = ch.find_next_sibling()
            if nxt is not None and nxt.name == "p" and not nxt.find("img") and len(nxt.get_text(strip=True)) < 400:
                lp_ = doc.add_paragraph()
                if centred:
                    lp_.alignment = WD_ALIGN_PARAGRAPH.CENTER
                inline(lp_, nxt)
                for r in lp_.runs:
                    r.font.italic = lay in ("academic", "magazine")
                    r.font.color.rgb = rgb(accent if lay == "resume" else "475569")
                    r.font.size = Pt(12 if lay == "resume" else 11)
                skip.add(id(nxt))
            if lay not in ("minimal", "magazine", "memo"):
                mp = doc.add_paragraph()
                if centred:
                    mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                mr = mp.add_run(date)
                mr.font.size, mr.font.color.rgb = Pt(9), rgb("64748B")
            rule = doc.add_paragraph()
            rule.paragraph_format.space_after = Pt(10)
            border(rule, "top", accent if lay in ("resume", "minimal") else dark, 18 if lay in ("memo", "invoice", "magazine") else 8)
        doc_title[0] = ch.get_text(" ", strip=True)
        first_h1[0] = False

    def block(node, level=0, quote=False):
        for ch in node.children:
            if id(ch) in skip:
                continue
            if isinstance(ch, NavigableString):
                if str(ch).strip():
                    p = doc.add_paragraph()
                    p.add_run(str(ch).strip())
                continue
            if not isinstance(ch, Tag):
                continue
            name = ch.name.lower()
            cls = " ".join(ch.get("class") or [])
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                lvl = int(name[1])
                if lvl == 1 and first_h1[0] and not doc.paragraphs and lay != "report":
                    plain_cover(ch)
                    p = doc.paragraphs[-1]
                elif lvl == 1 and first_h1[0] and not doc.paragraphs:
                    # Cover block: one full-width cell on the theme's dark colour with real padding - the title,
                    # the lead paragraph under it (if the document starts with one) and the date - then an accent rule.
                    cover = doc.add_table(rows=1, cols=1)
                    cover.alignment = WD_TABLE_ALIGNMENT.CENTER
                    cell = cover.rows[0].cells[0]
                    shade(cell._tc, dark)
                    mar = OxmlElement("w:tcMar")
                    for side, v in (("top", 420), ("bottom", 380), ("left", 420), ("right", 420)):
                        e = OxmlElement(f"w:{side}")
                        e.set(qn("w:w"), str(v))
                        e.set(qn("w:type"), "dxa")
                        mar.append(e)
                    put(cell._tc.get_or_add_tcPr(), mar, TCPR_ORDER)
                    noborder = OxmlElement("w:tblBorders")
                    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                        e = OxmlElement(f"w:{side}")
                        e.set(qn("w:val"), "nil")
                        noborder.append(e)
                    put(cover._tbl.tblPr, noborder, TBLPR_ORDER)
                    p = cell.paragraphs[0]
                    p.style = doc.styles["Title"]
                    inline(p, ch, {"color": "FFFFFF"})
                    for r in p.runs:
                        r.font.color.rgb = rgb("FFFFFF")
                    nxt = ch.find_next_sibling()
                    if nxt is not None and nxt.name == "p" and not nxt.find("img") and len(nxt.get_text(strip=True)) < 400:
                        lead = cell.add_paragraph()
                        lead.paragraph_format.space_before = Pt(6)
                        inline(lead, nxt, {"color": "D9E2EC"})
                        for r in lead.runs:
                            r.font.size, r.font.color.rgb = Pt(11.5), rgb("D9E2EC")
                        skip.add(id(nxt))
                    meta = cell.add_paragraph()
                    meta.paragraph_format.space_before = Pt(10)
                    mr = meta.add_run(time.strftime("%d.%m.%Y").upper())
                    mr.font.size, mr.font.color.rgb, mr.font.bold = Pt(8.5), rgb("9FB3C8"), True
                    rule = doc.add_paragraph()
                    rule.paragraph_format.space_after = Pt(10)
                    border(rule, "top", accent, 24)
                    doc_title[0] = ch.get_text(" ", strip=True)
                    first_h1[0] = False
                else:
                    p = doc.add_paragraph(style=f"Heading {min(lvl, 6)}")
                    if lvl == 2 and h2style == "number":
                        h2_no[0] += 1
                        nr = p.add_run(f"{h2_no[0]:02d}  ")
                        nr.font.color.rgb, nr.font.bold = rgb(accent), True
                    inline(p, ch)
                    if lvl == 2 and h2style in ("underline", "caps"):
                        border(p, "bottom", accent if h2style == "underline" else "D9E2EC", 12 if h2style == "underline" else 4)
                    if lvl == 2 and h2style == "caps":
                        for r in p.runs:
                            r.font.all_caps, r.font.size, r.font.color.rgb = True, Pt(11), rgb(accent)
                    if lvl in (1, 2):  # section headings: a thin accent rule under the whole line
                        border(p, "bottom", accent if lvl == 1 else "C7D2E0", 8 if lvl == 1 else 6)
                rtl(p)
            elif name == "p":
                if "math-display" in cls:
                    continue
                kids = [c for c in ch.children if not (isinstance(c, NavigableString) and not str(c).strip())]
                if len(kids) == 1 and isinstance(kids[0], Tag) and "math-display" in " ".join(kids[0].get("class") or []):
                    block(ch, level, quote)
                    continue
                p = doc.add_paragraph()
                if quote:
                    p.paragraph_format.left_indent = Cm(0.6)
                    shade(p._p, tint)
                    border(p, "left", accent, 18)
                if len(kids) == 1 and isinstance(kids[0], Tag) and kids[0].name == "img":
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                inline(p, ch, {"i": True} if quote else None)
                rtl(p)
            elif "math-display" in cls and ch.get("data-i") is not None:
                i = int(ch["data-i"])
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if i in imgs:
                    png, w, h = imgs[i]
                    picture(p, png, w, h, inline_h_pt=True, scale=1.0)
                else:
                    p.add_run(tex_text(src.maths[i][0])).italic = True
            elif name in ("ul", "ol"):
                first = True
                for li in ch.find_all("li", recursive=False):
                    style = ("List Number" if name == "ol" else "List Bullet") + (f" {min(level + 1, 3)}" if level else "")
                    p = doc.add_paragraph(style=style)
                    if name == "ol" and first and level == 0:
                        numbered[0] += 1
                        if numbered[0] > 1:
                            restart_numbering(p)
                    first = False
                    para_kids = []
                    for c in li.children:
                        if isinstance(c, Tag) and c.name in ("ul", "ol"):
                            continue
                        para_kids.append(c)
                    for c in para_kids:
                        if isinstance(c, Tag) and c.name == "p":
                            inline(p, c)
                        elif isinstance(c, Tag):
                            wrap = BeautifulSoup("<span></span>", "html.parser").span
                            wrap.append(c.__copy__())
                            inline(p, wrap)
                        elif str(c).strip():
                            p.add_run(re.sub(r"\s+", " ", str(c)))
                    rtl(p)
                    for sub in li.find_all(["ul", "ol"], recursive=False):
                        wrap = BeautifulSoup("<div></div>", "html.parser").div
                        wrap.append(sub.__copy__())
                        block(wrap, level + 1)
            elif name == "table":
                rows = ch.find_all("tr")
                if not rows:
                    continue
                ncols = max(len(r.find_all(["td", "th"])) for r in rows)
                t = doc.add_table(rows=0, cols=ncols)
                t.style = "Table Grid"
                t.alignment = WD_TABLE_ALIGNMENT.CENTER
                for ri, r in enumerate(rows):
                    cells = r.find_all(["td", "th"])
                    head = all(c.name == "th" for c in cells) and ri == 0
                    row = t.add_row()
                    if head:
                        trpr = row._tr.get_or_add_trPr()
                        th = OxmlElement("w:tblHeader")
                        th.set(qn("w:val"), "true")
                        trpr.append(th)
                    for ci in range(ncols):
                        cell = row.cells[ci]
                        par = cell.paragraphs[0]
                        par.paragraph_format.space_after = Pt(2)
                        if ci < len(cells):
                            txt = cells[ci].get_text(" ", strip=True)
                            if re.fullmatch(r"[-+]?[\d.,\s%₺$€£¥]+(\s?(TL|USD|EUR|GBP|%))?", txt) and re.search(r"\d", txt):
                                par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                            inline(par, cells[ci], {"b": True, "color": "FFFFFF" if tstyle == "solid" else dark} if head else None)
                        if head and tstyle == "solid":
                            shade(cell._tc, accent)
                        elif head and tstyle == "soft":
                            shade(cell._tc, tint)
                        elif head:  # lines: no fill, a strong rule under the header
                            border(par, "bottom", dark, 12)
                        elif ri % 2 == 0 and tstyle == "solid":
                            shade(cell._tc, tint)
                tbl_pr = t._tbl.tblPr
                borders = OxmlElement("w:tblBorders")
                for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                    e = OxmlElement(f"w:{side}")
                    e.set(qn("w:val"), "single")
                    e.set(qn("w:sz"), "4")
                    e.set(qn("w:color"), "D9E2EC")
                    borders.append(e)
                put(tbl_pr, borders, TBLPR_ORDER)
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            elif name == "pre":
                p = doc.add_paragraph()
                shade(p._p, "F1F5F9")
                p.paragraph_format.left_indent = Cm(0.3)
                run = p.add_run(ch.get_text().rstrip("\n"))
                run.font.name = "Consolas"
                run.font.size = Pt(9)
            elif name == "blockquote":
                block(ch, level, True)
            elif name == "hr":
                border(doc.add_paragraph(), color="D9E2EC", size=6)
            elif "page-break" in cls:
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            elif name == "img":
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                data = _image_bytes(ch.get("src", ""), src.base_dir)
                if not (data and picture(p, data, 0, 0)):
                    p.add_run(ch.get("alt") or "")
            elif name in ("script", "style", "head", "title", "meta", "link"):
                continue
            else:
                block(ch, level, quote)

    soup = BeautifulSoup(src.html, "lxml")
    block(soup.body or soup)
    def field(par, code):
        for kind, text in (("begin", None), (None, code), ("end", None)):
            r = par.add_run()
            r.font.size, r.font.color.rgb = Pt(8), rgb("829AB1")
            if kind:
                f = OxmlElement("w:fldChar")
                f.set(qn("w:fldCharType"), kind)
                r._r.append(f)
            else:
                it = OxmlElement("w:instrText")
                it.set(qn("xml:space"), "preserve")
                it.text = text
                r._r.append(it)

    # Running header (the document title, from page 2) and "page x / y" in the footer.
    for sec in doc.sections:
        sec.different_first_page_header_footer = True
        hp = sec.header.paragraphs[0]
        hr_ = hp.add_run((doc_title[0] or src.title())[:90])
        hr_.font.size, hr_.font.color.rgb = Pt(8), rgb("829AB1")
        border(hp, "bottom", "D9E2EC", 4)
        for footer in (sec.footer, sec.first_page_footer):
            p = footer.paragraphs[0]
            if spec.get("footer"):  # the institution's footer lines, centred, a rule above
                fp = p
                border(fp, "top", "333333", 6)
                for k, line in enumerate(spec["footer"][:5]):
                    if k:
                        fp = footer.add_paragraph()
                    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    fp.paragraph_format.space_after = Pt(0)
                    bold = line.startswith("**") and line.endswith("**")
                    fr = fp.add_run(line.strip("*"))
                    fr.font.size, fr.font.bold, fr.font.color.rgb = Pt(7.5), bold, rgb("111111" if bold else "444444")
                p = footer.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            field(p, "PAGE")
            sep = p.add_run(" / ")
            sep.font.size, sep.font.color.rgb = Pt(8), rgb("829AB1")
            field(p, "NUMPAGES")
    doc.core_properties.title = src.title()[:200]
    doc.save(target)
    return {"engine": "python-docx"}


# ---------------------------------------------------------------- PPTX
def _pptx(src: Source, target: Path, imgs: dict, theme: str) -> dict:
    from bs4 import BeautifulSoup, NavigableString, Tag
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    accent, dark, tint = (RGBColor.from_string(c.lstrip("#").upper()) for c in THEMES.get(theme, THEMES[DEFAULT_THEME]))
    white, text_c, muted = RGBColor(255, 255, 255), RGBColor(0x1F, 0x29, 0x33), RGBColor(0x62, 0x7D, 0x98)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]
    spec = TEMPLATE_SPEC.get(theme) or {}
    FONT = spec.get("font_family") or ("Georgia" if spec.get("font") == "serif" else "Segoe UI")
    look = spec.get("cover") or "dark"  # the template's slide look: dark | hero | minimal | split | band ...

    def rect(slide, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE):
        s = slide.shapes.add_shape(shape, x, y, w, h)
        s.fill.solid()
        s.fill.fore_color.rgb = color
        s.line.fill.background()
        s.shadow.inherit = False
        return s

    def text_runs(par, node, fmt=None):
        fmt = fmt or {}
        for ch in node.children:
            if isinstance(ch, NavigableString):
                t = re.sub(r"\s+", " ", str(ch))
                if not t:
                    continue
                r = par.add_run()
                r.text = t
                r.font.bold = fmt.get("b")
                r.font.italic = fmt.get("i")
                if fmt.get("code"):
                    r.font.name = "Consolas"
                if fmt.get("href"):
                    r.hyperlink.address = fmt["href"]
                    r.font.color.rgb = accent
                continue
            if not isinstance(ch, Tag):
                continue
            n = ch.name.lower()
            if "math" in " ".join(ch.get("class") or []) and ch.get("data-i") is not None:
                r = par.add_run()
                r.text = tex_text(src.maths[int(ch["data-i"])][0])
                r.font.italic = True
            elif n in ("strong", "b"):
                text_runs(par, ch, {**fmt, "b": True})
            elif n in ("em", "i"):
                text_runs(par, ch, {**fmt, "i": True})
            elif n == "code":
                text_runs(par, ch, {**fmt, "code": True})
            elif n == "a" and ch.get("href", "").startswith("http"):
                text_runs(par, ch, {**fmt, "href": ch["href"]})
            elif n == "br":
                par.add_run().text = " "
            elif n not in ("ul", "ol"):
                text_runs(par, ch, fmt)

    # sections: a new slide at every h1/h2 (and at hr)
    soup = BeautifulSoup(src.html, "lxml")
    root = soup.body or soup
    flat: list = []

    def collect(node):
        for ch in node.children:
            if isinstance(ch, Tag) and ch.name in ("div", "section", "article", "main") and not (
                    "math-display" in " ".join(ch.get("class") or [])):
                collect(ch)
            elif isinstance(ch, Tag) or str(ch).strip():
                flat.append(ch)
    collect(root)
    sections: list[dict] = []
    cur = {"title": None, "level": 0, "blocks": []}
    for b in flat:
        if isinstance(b, Tag) and b.name in ("h1", "h2"):
            if cur["title"] is not None or cur["blocks"]:
                sections.append(cur)
            cur = {"title": b, "level": int(b.name[1]), "blocks": []}
        elif isinstance(b, Tag) and b.name == "hr":
            if cur["title"] is not None or cur["blocks"]:
                sections.append(cur)
            cur = {"title": None, "level": 2, "blocks": []}
        else:
            cur["blocks"].append(b)
    if cur["title"] is not None or cur["blocks"]:
        sections.append(cur)

    count = [0]

    def footer(slide):
        count[0] += 1
        tb = slide.shapes.add_textbox(W - Inches(1.3), H - Inches(0.5), Inches(1), Inches(0.3))
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        r = p.add_run()
        r.text = str(count[0])
        r.font.size, r.font.color.rgb, r.font.name = Pt(10), muted, FONT

    def title_slide(title: str, subtitle: str):
        if look in ("minimal", "split", "editorial", "corner"):
            return light_title(title, subtitle)
        s = prs.slides.add_slide(blank)
        rect(s, 0, 0, W, H, RGBColor(0x0B, 0x12, 0x20) if look == "dark" and spec else accent if look == "hero" else dark)
        c1 = rect(s, W - Inches(5.2), Inches(-2.2), Inches(7.5), Inches(7.5), accent, MSO_SHAPE.OVAL)
        c1.fill.transparency = 0.0
        c2 = rect(s, W - Inches(3.2), Inches(3.9), Inches(4.6), Inches(4.6), tint, MSO_SHAPE.OVAL)
        for c, a in ((c1, 70000), (c2, 88000)):  # translucent decoration circles
            from pptx.oxml.ns import qn
            srgb = c.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
            alpha = srgb.makeelement(qn("a:alpha"), {"val": str(100000 - a)})
            srgb.append(alpha)
        rect(s, 0, H - Inches(0.25), W, Inches(0.25), accent)
        rect(s, Inches(0.9), Inches(3.55), Inches(1.4), Emu(Inches(0.07)), accent)
        tb_date = s.shapes.add_textbox(Inches(0.9), H - Inches(1.0), Inches(5), Inches(0.4))
        rd = tb_date.text_frame.paragraphs[0].add_run()
        rd.text = time.strftime("%d.%m.%Y")
        rd.font.size, rd.font.color.rgb, rd.font.name = Pt(12), RGBColor(0xCB, 0xD5, 0xE1), FONT
        tb = s.shapes.add_textbox(Inches(0.9), Inches(1.6), W - Inches(1.8), Inches(1.9))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.BOTTOM
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = title
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(40 if len(title) < 50 else 30), True, white, FONT
        if subtitle:
            tb2 = s.shapes.add_textbox(Inches(0.9), Inches(3.8), W - Inches(1.8), Inches(1.6))
            tb2.text_frame.word_wrap = True
            r = tb2.text_frame.paragraphs[0].add_run()
            r.text = subtitle[:300]
            r.font.size, r.font.color.rgb, r.font.name = Pt(18), RGBColor(0xCB, 0xD5, 0xE1), FONT
        count[0] += 1

    def light_title(title: str, subtitle: str):
        """A light title slide: a white page with an accent column (split), a top rule (minimal / editorial) or a
        dark corner (corner) - the template's own look instead of the dark default."""
        s = prs.slides.add_slide(blank)
        rect(s, 0, 0, W, H, RGBColor(0xFF, 0xFF, 0xFF))
        x = Inches(0.9)
        if look == "split":
            rect(s, 0, 0, Inches(4.6), H, accent)
            rect(s, Inches(4.6), 0, Inches(0.12), H, dark)
            x = Inches(5.3)
        elif look == "corner":
            tri = rect(s, W - Inches(3.2), 0, Inches(3.2), Inches(3.2), dark, MSO_SHAPE.RIGHT_TRIANGLE)
            tri.rotation = 180
        else:
            rect(s, x, Inches(1.3), Inches(1.6), Emu(Inches(0.08)), accent)
        tb = s.shapes.add_textbox(x, Inches(1.7), W - x - Inches(0.9), Inches(2.2))
        tb.text_frame.word_wrap = True
        tb.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = title
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(40 if len(title) < 50 else 30), look != "minimal", dark, FONT
        if subtitle:
            tb2 = s.shapes.add_textbox(x, Inches(4.05), W - x - Inches(0.9), Inches(1.6))
            tb2.text_frame.word_wrap = True
            r = tb2.text_frame.paragraphs[0].add_run()
            r.text = subtitle[:300]
            r.font.size, r.font.color.rgb, r.font.name = Pt(18), muted, FONT
        tb_date = s.shapes.add_textbox(x, H - Inches(1.0), Inches(5), Inches(0.4))
        rd = tb_date.text_frame.paragraphs[0].add_run()
        rd.text = time.strftime("%d.%m.%Y")
        rd.font.size, rd.font.color.rgb, rd.font.name, rd.font.bold = Pt(12), accent, FONT, True
        count[0] += 1

    def content_slide(title: str, cont: bool = False):
        s = prs.slides.add_slide(blank)
        rect(s, 0, 0, W, H, RGBColor(0xFA, 0xFB, 0xFD) if look not in ("minimal", "editorial") else RGBColor(0xFF, 0xFF, 0xFF))
        if look not in ("minimal", "editorial"):
            rect(s, 0, 0, Inches(0.18), H, accent)
        rect(s, Inches(0.18), H - Inches(0.08), W, Inches(0.08), tint)
        ft = s.shapes.add_textbox(Inches(0.7), H - Inches(0.5), Inches(8), Inches(0.3))
        fr = ft.text_frame.paragraphs[0].add_run()
        fr.text = deck_title[:80]
        fr.font.size, fr.font.color.rgb, fr.font.name = Pt(10), muted, FONT
        if not cont:
            section_no[0] += 1
        # Title band: a section number in an accent chip, the title beside it, a thin rule under the band.
        rect(s, Inches(0.18), 0, W, Inches(1.35), dark if look == "band" else RGBColor(0xFF, 0xFF, 0xFF))
        chip = rect(s, Inches(0.7), Inches(0.5), Inches(0.62), Inches(0.42), accent, MSO_SHAPE.ROUNDED_RECTANGLE)
        chip.adjustments[0] = 0.3
        cf = chip.text_frame
        cf.margin_left = cf.margin_right = cf.margin_top = cf.margin_bottom = 0
        cf.vertical_anchor = MSO_ANCHOR.MIDDLE
        cp = cf.paragraphs[0]
        cp.alignment = PP_ALIGN.CENTER
        cr = cp.add_run()
        cr.text = f"{section_no[0]:02d}"
        cr.font.size, cr.font.bold, cr.font.color.rgb, cr.font.name = Pt(14), True, white, FONT
        tb = s.shapes.add_textbox(Inches(1.5), Inches(0.3), W - Inches(2.2), Inches(0.85))
        tb.text_frame.word_wrap = True
        tb.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = (title or "") + (" (…)" if cont else "")
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = (Pt(28 if len(title or "") < 50 else 22), True,
                                                                  white if look == "band" else dark, FONT)
        rect(s, Inches(0.7), Inches(1.32), W - Inches(1.4), Emu(Inches(0.02 if look != "minimal" else 0.04)),
             accent if look in ("minimal", "editorial") else RGBColor(0xD9, 0xE2, 0xEC))
        footer(s)
        return s

    section_no = [0]
    TOP, BOTTOM, LEFT = Inches(1.6), H - Inches(0.7), Inches(0.7)
    deck_title = src.title() or target.stem
    WIDTH = W - Inches(1.4)

    cur_w = [WIDTH]  # width of the text column on the current slide (narrower beside a picture)

    def est_lines(text: str, size: int) -> int:
        per = max(20, int(cur_w[0] / Emu(Pt(size * 0.52))))
        return max(1, math.ceil(len(text) / per))

    def visual(kind, node):
        """(PNG stream, width px, height px) of an image or a formula, or None."""
        if kind == "math":
            i = int(node.get("data-i", -1))
            if i not in imgs:
                return None
            png, w, h = imgs[i]
            ready = _png_ready(png)
            return (ready[0], w * 1.6, h * 1.6) if ready else None
        data = _image_bytes(node.get("src", ""), src.base_dir)
        return _png_ready(data) if data else None

    def place(slide, vis, x, y, max_w, max_h):
        stream, w_px, h_px = vis
        ratio = h_px / max(1, w_px)
        w_e = min(max_w, Emu(int(w_px / 96 * 914400)))
        h_e = Emu(int(w_e * ratio))
        if h_e > max_h:
            h_e = max_h
            w_e = Emu(int(h_e / max(ratio, 0.01)))
        slide.shapes.add_picture(stream, x + (max_w - w_e) // 2, y + (max_h - h_e) // 2 if max_h > h_e else y, w_e, h_e)
        return h_e

    for si, sec in enumerate(sections):
        title = sec["title"].get_text(" ", strip=True) if sec["title"] is not None else ""
        blocks = sec["blocks"]
        if si == 0 and sec["level"] == 1:
            # The first # is the title slide; its lead paragraph is the subtitle. Whatever else stands before the
            # first section (KPI cards, a picture, more text) follows on a slide of its own - nothing is dropped.
            lead = blocks[0] if blocks and isinstance(blocks[0], Tag) and blocks[0].name == "p" and not blocks[0].find("img") \
                and blocks[0].get_text(strip=True) else None
            title_slide(title, lead.get_text(" ", strip=True) if lead is not None else "")
            blocks = blocks[1:] if lead is not None else blocks
            if not blocks:
                continue
        slide = content_slide(title)
        y = TOP
        items: list[tuple[str, Any, int]] = []  # (kind, node, level)
        for b in blocks:
            if not isinstance(b, Tag):
                items.append(("p", b, 0))
                continue
            if b.name in ("ul", "ol"):
                def walk(lst, lvl):
                    for li in lst.find_all("li", recursive=False):
                        items.append(("li" if lst.name == "ul" else "oli", li, lvl))
                        for sub in li.find_all(["ul", "ol"], recursive=False):
                            walk(sub, lvl + 1)
                walk(b, 0)
            elif b.name == "table":
                items.append(("table", b, 0))
            elif b.name == "img" or (b.name == "p" and b.find("img") and not b.get_text(strip=True)):
                items.append(("img", b if b.name == "img" else b.find("img"), 0))
            elif "math-display" in " ".join(b.get("class") or []) or (b.name == "p" and b.find(class_="math-display")):
                items.append(("math", b if b.get("data-i") else b.find(class_="math-display"), 0))
            elif b.name in ("h3", "h4", "h5", "h6"):
                items.append(("h", b, 0))
            elif b.name == "pre":
                items.append(("pre", b, 0))
            else:
                items.append(("p", b, 0))
        tf = None
        num = 0
        cur_w[0] = WIDTH
        # Text plus one picture or formula (and no table): text on the left, the visual beside it on the right.
        vis_items = [it for it in items if it[0] in ("img", "math")]
        text_items = [it for it in items if it[0] in ("p", "li", "oli", "h")]
        if len(vis_items) == 1 and text_items and not any(it[0] in ("table", "pre") for it in items) \
                and sum(len(it[1].get_text(" ", strip=True) if isinstance(it[1], Tag) else str(it[1])) for it in text_items) < 900:
            vis = visual(vis_items[0][0], vis_items[0][1])
            if vis:
                items = [it for it in items if it is not vis_items[0]]
                cur_w[0] = int(WIDTH * 0.55)
                col_x = LEFT + cur_w[0] + Inches(0.4)
                panel = rect(slide, col_x - Inches(0.15), TOP - Inches(0.1), W - col_x - Inches(0.4), BOTTOM - TOP + Inches(0.1), tint,
                             MSO_SHAPE.ROUNDED_RECTANGLE)
                panel.adjustments[0] = 0.06
                place(slide, vis, col_x, TOP + Inches(0.2), W - col_x - Inches(0.7), BOTTOM - TOP - Inches(0.4))
        for kind, node, lvl in items:
            if kind in ("p", "li", "oli", "h", "pre"):
                text = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
                if not text:
                    continue
                size = 14 if kind == "pre" else 20 if kind == "h" else 18 if lvl == 0 else 16
                need = Emu(int(Pt(size * 1.45) * est_lines(text, size))) + Emu(Pt(6))
                if y + need > BOTTOM and y > TOP:
                    slide, y, tf = content_slide(title, True), TOP, None
                    cur_w[0] = WIDTH
                if tf is None:
                    box = slide.shapes.add_textbox(LEFT, y, cur_w[0], need)
                    tf = box.text_frame
                    tf.word_wrap = True
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                p.space_after = Pt(6)
                p.level = min(lvl, 4)
                if kind in ("li", "oli"):
                    num = num + 1 if kind == "oli" else 0
                    r = p.add_run()
                    r.text = ("   " * lvl) + (f"{num}. " if kind == "oli" else "•  ")
                    r.font.color.rgb, r.font.bold = accent, True
                if isinstance(node, Tag) and kind != "pre":
                    text_runs(p, node)
                else:
                    r = p.add_run()
                    r.text = text
                for r in p.runs:
                    r.font.size = r.font.size or Pt(size)
                    r.font.name = r.font.name or FONT
                    if r.font.color.type is None:
                        r.font.color.rgb = dark if kind == "h" else text_c
                    if kind == "h":
                        r.font.bold = True
                y += need
                box.height = Emu(min(BOTTOM, y) - box.top)  # the box ends where its text ends (no overlap)
            elif kind == "table":
                rows = node.find_all("tr")
                if not rows:
                    continue
                ncols = max(len(r.find_all(["td", "th"])) for r in rows)
                row_h = Inches(0.45)
                avail_rows = max(2, int((BOTTOM - TOP) / row_h))
                start = 0
                while start < len(rows):
                    chunk = rows[start:start + (avail_rows - 1 if start else avail_rows)]
                    if start and rows[0].find("th"):
                        chunk = [rows[0]] + chunk
                    need = row_h * len(chunk)
                    if y + need > BOTTOM and y > TOP:
                        slide, y, tf = content_slide(title, True), TOP, None
                        chunk = chunk[:max(2, int((BOTTOM - y) / row_h))]
                    shape = slide.shapes.add_table(len(chunk), ncols, LEFT, y, WIDTH, row_h * len(chunk))
                    tbl = shape.table
                    for ri, r in enumerate(chunk):
                        cells = r.find_all(["td", "th"])
                        head = r.find("th") is not None and not r.find("td")
                        for ci in range(ncols):
                            c = tbl.cell(ri, ci)
                            c.fill.solid()
                            c.fill.fore_color.rgb = accent if head else (tint if ri % 2 == 0 else white)
                            p = c.text_frame.paragraphs[0]
                            if ci < len(cells):
                                text_runs(p, cells[ci])
                            for run in p.runs:
                                run.font.size = Pt(14 if ncols <= 4 else 12 if ncols <= 6 else 10)
                                run.font.name = FONT
                                run.font.color.rgb = white if head else text_c
                                run.font.bold = True if head else run.font.bold
                    y += row_h * len(chunk) + Inches(0.2)
                    start += len(chunk) - (1 if start and rows[0].find("th") else 0)
                    tf = None
                    if start < len(rows):
                        slide, y = content_slide(title, True), TOP
            elif kind in ("img", "math"):
                vis = visual(kind, node)
                if not vis:
                    continue
                if BOTTOM - y < Inches(1.5):
                    slide, y, tf = content_slide(title, True), TOP, None
                h_e = place(slide, vis, LEFT, y, WIDTH, min(BOTTOM - y, Inches(4.2)))
                y += min(h_e, BOTTOM - y) + Inches(0.2)
                tf = None
    if not prs.slides:
        title_slide(src.title() or target.stem, "")
    prs.core_properties.title = src.title()[:200]
    prs.save(target)
    return {"engine": "python-pptx", "slides": len(prs.slides)}


# ---------------------------------------------------------------- XLSX
def _cell_value(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s.startswith("="):
        return s  # a formula
    m = re.fullmatch(r"([-+]?)([\d.,]+)\s*(%?)", s)
    if m and re.search(r"\d", m.group(2)):
        num = m.group(2)
        if "," in num and "." in num:
            num = num.replace(".", "").replace(",", ".") if num.rfind(",") > num.rfind(".") else num.replace(",", "")
        elif "," in num:
            num = num.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", num) else num.replace(",", "")
        try:
            f = float(m.group(1) + num)
            return f / 100 if m.group(3) else (int(f) if f.is_integer() and "." not in num else f)
        except ValueError:
            return v
    return v


def _sheets_from(content: str) -> list[tuple[str, list[list]]]:
    text = (content or "").strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        data = None
    out: list[tuple[str, list[list]]] = []

    def rows_of(rows):
        if isinstance(rows, dict) and "rows" in rows:
            head = rows.get("columns") or rows.get("headers")
            rows = ([head] if head else []) + list(rows["rows"])
        if rows and isinstance(rows, list) and isinstance(rows[0], dict):
            keys = list(dict.fromkeys(k for r in rows for k in r))
            return [keys] + [[r.get(k) for k in keys] for r in rows]
        return [list(r) if isinstance(r, (list, tuple)) else [r] for r in (rows or [])]
    if isinstance(data, list):
        out.append(("Sheet1", rows_of(data)))
    elif isinstance(data, dict):
        sheets = data.get("sheets", {k: v for k, v in data.items() if k not in ("title", "subtitle")})
        if isinstance(sheets, list):
            for i, s in enumerate(sheets, 1):
                out.append((str(s.get("name") or f"Sheet{i}"), rows_of(s)))
        else:
            for name, rows in sheets.items():
                out.append((str(name), rows_of(rows)))
    else:  # Markdown / HTML tables: one sheet per table, named after the heading above it
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(Source(text).html, "lxml")
        for i, t in enumerate(soup.find_all("table"), 1):
            h = t.find_previous(["h1", "h2", "h3", "h4"])
            name = h.get_text(" ", strip=True) if h else f"Sheet{i}"
            out.append((name, [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]))
    return out


def _xlsx(content: str, target: Path, theme: str) -> dict:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    accent, dark, tint = (c.lstrip("#") for c in THEMES.get(theme, THEMES[DEFAULT_THEME]))
    spec = TEMPLATE_SPEC.get(theme) or {}
    # The template's sheet look: dark (a dark header and tab), band (the dark colour), soft (tint header, dark text),
    # lines (no fill, a strong rule) - the default an accent header with zebra rows.
    look = ("dark" if spec.get("cover") == "dark" else "band" if spec.get("cover") == "band" else
            spec.get("table") if spec.get("table") in ("soft", "lines") else "solid")
    font_name = spec.get("font_family") or ("Georgia" if spec.get("font") == "serif" else "Calibri")
    sheets = _sheets_from(content)
    if not sheets:
        raise ValueError("xlsx needs JSON rows/sheets or Markdown tables")
    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="D9E2EC")
    used = set()
    for name, rows in sheets:
        clean = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31] or "Sheet"
        base, n = clean, 2
        while clean.lower() in used:
            clean = f"{base[:28]} {n}"
            n += 1
        used.add(clean.lower())
        ws = wb.create_sheet(clean)
        ws.sheet_properties.tabColor = dark if look in ("dark", "band") else accent
        for r in rows:
            ws.append([_cell_value(v) for v in r])
        if not rows:
            continue
        ncols = max(len(r) for r in rows)
        strong = Side(style="medium", color=dark)
        for c in ws[1]:
            c.font = Font(bold=True, name=font_name, color="FFFFFF" if look in ("solid", "dark", "band") else dark)
            if look in ("solid", "dark", "band"):
                c.fill = PatternFill("solid", fgColor={"dark": "0B1220", "band": dark}.get(look, accent))
            elif look == "soft":
                c.fill = PatternFill("solid", fgColor=tint)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = (Border(bottom=strong) if look == "lines" else Border(top=thin, bottom=thin, left=thin, right=thin))
        for ri, row in enumerate(ws.iter_rows(min_row=2), 2):
            for c in row:
                c.font = Font(name=font_name)
                c.border = (Border(bottom=Side(style="hair", color="CBD5E1")) if look == "lines"
                            else Border(top=thin, bottom=thin, left=thin, right=thin))
                if ri % 2 == 1 and look in ("solid", "dark", "band"):
                    c.fill = PatternFill("solid", fgColor=tint)
                if isinstance(c.value, float) and isinstance(rows[ri - 1][c.column - 1] if c.column - 1 < len(rows[ri - 1]) else None, str) \
                        and str(rows[ri - 1][c.column - 1]).strip().endswith("%"):
                    c.number_format = "0.00%"
                elif isinstance(c.value, float):
                    c.number_format = "#,##0.00"
                elif isinstance(c.value, int) and abs(c.value) >= 10000:
                    c.number_format = "#,##0"
        for ci in range(1, ncols + 1):
            width = max((len(str(ws.cell(row=r, column=ci).value or "")) for r in range(1, min(ws.max_row, 500) + 1)), default=8)
            ws.column_dimensions[get_column_letter(ci)].width = min(60, max(9, width * 1.15 + 2))
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{ws.max_row}"
        ws.row_dimensions[1].height = 22
    if spec:  # the template's sheet design: title band, KPI boxes, chart, Gantt, calendar... (xlsx_design.py)
        from . import xlsx_design
        title = ""
        try:
            d = json.loads(content)
            title = str(d.get("title") or "") if isinstance(d, dict) else ""
        except (ValueError, TypeError):
            m = re.search(r"^#\s+(.+)$|<h1[^>]*>(.*?)</h1>", content or "", re.M)
            title = (m.group(1) or m.group(2)) if m else ""
        title = re.sub(r"<[^>]+>", "", title).strip() or target.stem.replace("_", " ").replace("-", " ").title()
        lang = "tr" if re.search(r"[çğışöüİ]", content or "") else "en"
        try:
            xlsx_design.apply(wb, {**spec, "id": theme}, title[:80], (accent, dark, tint), lang)
        except Exception as e:  # noqa: BLE001 - the plain table is still written
            print(f"xlsx design skipped: {e}")
    wb.save(target)
    return {"engine": "openpyxl", "sheets": [s for s, _ in sheets]}


# ---------------------------------------------------------------- PDF fallback (no Chromium)
def _pdf_reportlab(src: Source, target: Path, theme: str) -> dict:
    """ReportLab with DejaVu Sans (full Latin/Cyrillic/Greek incl. ç ğ ı İ ö ş ü): headings, paragraphs, lists,
    tables, links; formulas as readable text."""
    import matplotlib
    from bs4 import BeautifulSoup, Tag
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from html import escape
    fdir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fdir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fdir / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")
        base = "DejaVu"
    except Exception:
        base = "Helvetica"
    a, d, t = THEMES.get(theme, THEMES[DEFAULT_THEME])
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName=base, fontSize=10, leading=14)
    hs = {i: ParagraphStyle(f"h{i}", parent=body, fontName=base + "-Bold",
                            fontSize={1: 20, 2: 15, 3: 12}.get(i, 11), leading={1: 25, 2: 19, 3: 15}.get(i, 14),
                            textColor=colors.HexColor(d if i != 3 else a), spaceBefore=8, spaceAfter=4) for i in range(1, 7)}

    def rich(node) -> str:
        out = []
        for ch in node.children:
            if isinstance(ch, Tag):
                n = ch.name
                cls = " ".join(ch.get("class") or [])
                if "math" in cls and ch.get("data-i") is not None:
                    out.append("<i>" + escape(tex_text(src.maths[int(ch["data-i"])][0])) + "</i>")
                elif n in ("strong", "b"):
                    out.append(f"<b>{rich(ch)}</b>")
                elif n in ("em", "i"):
                    out.append(f"<i>{rich(ch)}</i>")
                elif n == "a" and ch.get("href"):
                    out.append(f'<a href="{escape(ch["href"])}" color="{a}">{rich(ch)}</a>')
                elif n == "br":
                    out.append("<br/>")
                else:
                    out.append(rich(ch))
            else:
                out.append(escape(re.sub(r"\s+", " ", str(ch))))
        return "".join(out)
    story = []
    soup = BeautifulSoup(src.html, "lxml")
    for el in (soup.body or soup).find_all(["h1", "h2", "h3", "h4", "p", "li", "table", "pre", "div"]):
        if el.find_parent(["table", "li"]) and el.name != "li":
            continue
        if el.name.startswith("h"):
            story.append(Paragraph(rich(el), hs[int(el.name[1])]))
        elif el.name in ("p", "pre"):
            story.append(Paragraph(rich(el), body))
        elif el.name == "li":
            story.append(Paragraph("• " + rich(el), ParagraphStyle("li", parent=body, leftIndent=12)))
        elif el.name == "div" and "math-display" in " ".join(el.get("class") or []):
            story.append(Paragraph("<i>" + escape(tex_text(src.maths[int(el["data-i"])][0])) + "</i>",
                                   ParagraphStyle("m", parent=body, alignment=1)))
        elif el.name == "table":
            rows = [[Paragraph(rich(c), body) for c in r.find_all(["td", "th"])] for r in el.find_all("tr")]
            if rows:
                tb = Table(rows, repeatRows=1)
                tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(a)),
                                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(t)]),
                                        ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                story += [tb, Spacer(1, 8)]
        story.append(Spacer(1, 3))
    SimpleDocTemplate(str(target), leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title=src.title()).build(story)
    return {"engine": "reportlab"}


# ---------------------------------------------------------------- entry point
KINDS = ("pdf", "docx", "pptx", "xlsx", "html")


async def generate(kind: str, content: str, target: Path, *, base_dir: Path | None = None, theme: str | None = None,
                   lang: str = "en", landscape: bool = False) -> dict:
    """Write `target` as `kind` from Markdown/HTML (JSON rows also for xlsx). Returns details (engine, pages...)."""
    kind = (kind or target.suffix).lower().lstrip(".")
    if kind in ("doc", "word"):
        kind = "docx"
    if kind in ("ppt", "powerpoint"):
        kind = "pptx"
    if kind in ("xls", "excel"):
        kind = "xlsx"
    if kind == "htm":
        kind = "html"
    if kind not in KINDS:
        raise ValueError(f"unsupported document type: {kind} (use {', '.join(KINDS)})")
    theme = theme if theme in THEMES else DEFAULT_THEME
    target.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if kind == "xlsx":
        info = await asyncio.to_thread(_xlsx, content, target, theme)
    else:
        src = await asyncio.to_thread(Source, content, base_dir)  # image checks may download: off the event loop
        if kind == "pdf":
            try:
                info = await _pdf(src, target, theme, lang, landscape)
            except Exception as e:  # no Chromium: still a correct PDF with full Turkish/Unicode text
                info = {**await asyncio.to_thread(_pdf_reportlab, src, target, theme), "note": f"chromium: {e}"[:200]}
        elif kind == "html":
            try:
                info = await _html_out(src, target, theme, lang)
            except Exception:
                target.write_text(_page(src, theme, lang, src.title() or target.stem), encoding="utf-8")
                info = {"engine": "template"}
        else:
            await rasterize_components(src, theme, lang)
            imgs = await math_images(src.maths)
            info = await asyncio.to_thread(_docx if kind == "docx" else _pptx, src, target, imgs, theme)
        info["formulas"] = len(src.maths)
        info["images"] = src.images
        if src.missing:
            info["missing_images"] = src.missing[:10]
    info["ms"] = int((time.monotonic() - t0) * 1000)
    info["bytes"] = target.stat().st_size
    return info
