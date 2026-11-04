"""Reading documents for research: PDF, Word, Excel, PowerPoint, OpenDocument, CSV, plain text and images, split into
citable units (PDF page, slide, sheet rows, paragraph or line ranges) so every quote carries its page number.

Scanned pages (no text layer) and images are OCR'd: Windows' built-in OCR engine on Windows (offline, fast, keeps
Turkish and other diacritics), Tesseract when it is installed, RapidOCR as the last resort. Long documents are not
dumped whole: a query returns the best matching passages with their page numbers, a page range returns those pages,
and otherwise an outline of the pages comes back. Extracted documents are cached by path, size and time.
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

DOC_EXTS = {".pdf", ".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods", ".odp", ".csv", ".tsv", ".txt", ".md",
            ".rtf", ".json", ".xml", ".html", ".htm", ".log", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
UNIT = {"tr": {"page": "s.", "slide": "slayt", "sheet": "sayfa", "para": "paragraf", "lines": "satır"},
        "en": {"page": "p.", "slide": "slide", "sheet": "sheet", "para": "para.", "lines": "lines"}}
MAX_OCR_PAGES = 80  # per call; a page range reaches the rest


@dataclass
class Part:
    label: str  # "p. 3", "slide 2", "sheet Sales rows 1-80", "para. 12-20"
    text: str
    ocr: bool = False


@dataclass
class Document:
    kind: str
    parts: list[Part] = field(default_factory=list)
    title: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.parts)


# --------------------------------------------------------------------------------------------------- OCR
def _ocr_windows(images: list, lang: str) -> list[str] | None:
    if sys.platform != "win32":
        return None
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError:
        return None
    tags = [x.language_tag for x in OcrEngine.available_recognizer_languages]
    if not tags:
        return None
    tag = next((t for t in tags if t.split("-")[0] == lang), None) or next((t for t in tags if t.startswith("en")), tags[0])
    engine = OcrEngine.try_create_from_language(Language(tag))
    if engine is None:
        return None
    limit = OcrEngine.max_image_dimension

    async def one(img) -> str:
        img = img.convert("RGBA")
        if max(img.size) > limit:  # the engine refuses bigger bitmaps
            img.thumbnail((limit, limit))
        w = DataWriter()
        w.write_bytes(img.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.RGBA8, img.width, img.height,
                                                     BitmapAlphaMode.PREMULTIPLIED)
        res = await engine.recognize_async(bmp)
        return "\n".join(line.text for line in res.lines)

    async def all_() -> list[str]:
        return [await one(i) for i in images]

    return asyncio.run(all_())  # called from a worker thread: its own event loop


def _ocr_tesseract(images: list, lang: str) -> list[str] | None:
    exe = shutil.which("tesseract")
    if not exe:
        return None
    langs = {"tr": "tur+eng", "en": "eng", "de": "deu+eng", "fr": "fra+eng", "es": "spa+eng"}.get(lang, "eng")
    out = []
    for img in images:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f, "PNG")
        try:
            r = subprocess.run([exe, f.name, "stdout", "-l", langs], capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="replace")
            if r.returncode and "Failed loading language" in r.stderr:
                r = subprocess.run([exe, f.name, "stdout"], capture_output=True, text=True, timeout=120,
                                   encoding="utf-8", errors="replace")
            out.append(r.stdout)
        finally:
            Path(f.name).unlink(missing_ok=True)
    return out


def _ocr_rapid(images: list) -> list[str] | None:
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except Exception:  # not installed, or its runtime does not load on this machine
        return None
    eng = RapidOCR()
    out = []
    for img in images:
        res, _ = eng(np.array(img.convert("RGB")))
        out.append("\n".join(t for _, t, _ in res or []))
    return out


def ocr_images(images: list, lang: str = "tr") -> tuple[list[str], str]:
    """OCR text per image and the engine used ("" when no engine is available)."""
    for name, fn in (("Windows OCR", lambda: _ocr_windows(images, lang)), ("Tesseract", lambda: _ocr_tesseract(images, lang)),
                     ("RapidOCR", lambda: _ocr_rapid(images))):
        try:
            texts = fn()
        except Exception:
            texts = None
        if texts is not None:
            return texts, name
    return ["" for _ in images], ""


# --------------------------------------------------------------------------------------------------- formats
def _pdf(data: bytes, lang: str, pages: tuple[int, int] | None) -> Document:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    doc = Document("pdf", title=(pdf.get_metadata_dict() or {}).get("Title", "") or "")
    n = len(pdf)
    lo, hi = pages or (1, n)
    lo, hi = max(1, lo), min(n, hi)
    unit = UNIT.get(lang, UNIT["en"])["page"]
    texts, scans = {}, []
    for i in range(lo - 1, hi):
        page = pdf[i]
        text = page.get_textpage().get_text_range().replace("\r\n", "\n").replace("\r", "\n")
        texts[i] = text
        if len(text.strip()) < 25 and len(scans) < MAX_OCR_PAGES:
            scans.append(i)  # no text layer: a scanned page (or a picture)
    if scans:
        images = [pdf[i].render(scale=2).to_pil() for i in scans]
        found, engine = ocr_images(images, lang)
        for i, t in zip(scans, found):
            if t.strip():
                texts[i] = t
        if engine:
            doc.notes.append(f"OCR ({engine}) on {len(scans)} scanned page(s)"
                             + ("; diacritics may be missing" if engine == "RapidOCR" else ""))
        else:
            doc.notes.append(f"{len(scans)} page(s) are scanned images and no OCR engine is available")
    for i in range(lo - 1, hi):
        doc.parts.append(Part(f"{unit} {i + 1}", texts.get(i, ""), i in scans))
    if n > hi or lo > 1:
        doc.notes.append(f"pages {lo}-{hi} of {n}")
    doc.title = doc.title or f"{n} pages"
    return doc


def _docx(data: bytes, lang: str) -> Document:
    import docx
    d = docx.Document(io.BytesIO(data))
    unit = UNIT.get(lang, UNIT["en"])["para"]
    doc = Document("docx", title=d.core_properties.title or "")
    paras = [p.text for p in d.paragraphs]
    for t in d.tables:  # tables after the text, row by row
        for row in t.rows:
            paras.append(" | ".join(c.text.strip() for c in row.cells))
    for k in range(0, len(paras), 15):
        chunk = "\n".join(p for p in paras[k:k + 15] if p.strip())
        if chunk:
            doc.parts.append(Part(f"{unit} {k + 1}-{min(k + 15, len(paras))}", chunk))
    return doc


def _xlsx(data: bytes, lang: str) -> Document:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    u = UNIT.get(lang, UNIT["en"])
    doc = Document("xlsx")
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            if any(v is not None for v in r):
                rows.append("\t".join("" if v is None else str(v) for v in r).rstrip())
            if len(rows) >= 5000:
                doc.notes.append(f"sheet {ws.title}: first 5000 rows")
                break
        for k in range(0, len(rows), 80):
            doc.parts.append(Part(f"{u['sheet']} {ws.title} {u['lines']} {k + 1}-{min(k + 80, len(rows))}",
                                  "\n".join(rows[k:k + 80])))
    wb.close()
    return doc


def _pptx(data: bytes, lang: str) -> Document:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    unit = UNIT.get(lang, UNIT["en"])["slide"]
    doc = Document("pptx")
    for i, slide in enumerate(prs.slides, 1):
        texts = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip()]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            texts.append("[notes] " + slide.notes_slide.notes_text_frame.text)
        doc.parts.append(Part(f"{unit} {i}", "\n".join(texts)))
    return doc


def _odf(data: bytes, ext: str, lang: str) -> Document:
    """OpenDocument (odt/ods/odp): content.xml read directly (no extra package)."""
    xml = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8", "replace")
    u = UNIT.get(lang, UNIT["en"])
    doc = Document(ext.lstrip("."))

    def text_of(fragment: str) -> str:
        fragment = re.sub(r"<text:(tab|s)\b[^>]*/>", " ", fragment)
        fragment = re.sub(r"<text:line-break/>|</text:p>|</text:h>|</table:table-row>", "\n", fragment)
        fragment = re.sub(r"</table:table-cell>", "\t", fragment)
        return unescape(re.sub(r"<[^>]+>", "", fragment)).strip()

    if ext == ".odp":
        for i, page in enumerate(re.findall(r"<draw:page\b.*?</draw:page>", xml, re.S), 1):
            doc.parts.append(Part(f"{u['slide']} {i}", text_of(page)))
    elif ext == ".ods":
        for name, body in re.findall(r'<table:table table:name="([^"]*)".*?>(.*?)</table:table>', xml, re.S):
            rows = [r for r in text_of(body).split("\n") if r.strip()]
            for k in range(0, len(rows), 80):
                doc.parts.append(Part(f"{u['sheet']} {unescape(name)} {u['lines']} {k + 1}-{min(k + 80, len(rows))}",
                                      "\n".join(rows[k:k + 80])))
    else:
        paras = [p for p in text_of(re.search(r"<office:text\b.*?</office:text>", xml, re.S).group(0)).split("\n")
                 if p.strip()] if "<office:text" in xml else []
        for k in range(0, len(paras), 15):
            doc.parts.append(Part(f"{u['para']} {k + 1}-{min(k + 15, len(paras))}", "\n".join(paras[k:k + 15])))
    return doc


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(enc)
            if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                raise UnicodeError
            return text
        except UnicodeError:
            continue
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best:
            return str(best)
    except ImportError:
        pass
    return data.decode("cp1254", "replace")


def _text(data: bytes, ext: str, lang: str) -> Document:
    text = _decode(data)
    u = UNIT.get(lang, UNIT["en"])
    if ext in (".csv", ".tsv"):
        rows = list(csv.reader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else (";" if text.count(";") > text.count(",") else ",")))
        lines = ["\t".join(r) for r in rows]
    else:
        if ext in (".html", ".htm", ".xml"):
            text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
            text = unescape(re.sub(r"<[^>]+>", " ", text))
        elif ext == ".rtf":
            text = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1254", "replace"), text)
            text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", text)
        lines = text.split("\n")
    doc = Document(ext.lstrip(".") or "text")
    for k in range(0, len(lines), 60):
        doc.parts.append(Part(f"{u['lines']} {k + 1}-{min(k + 60, len(lines))}", "\n".join(lines[k:k + 60])))
    return doc


def _image(data: bytes, lang: str) -> Document:
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    found, engine = ocr_images([img], lang)
    doc = Document("image", parts=[Part("image", found[0], True)])
    doc.notes.append(f"OCR ({engine})" if engine else "no OCR engine is available")
    return doc


def extract(data: bytes, name: str, lang: str = "tr", pages: tuple[int, int] | None = None) -> Document:
    """Split a document into citable parts. name gives the type (extension); raises ValueError when unsupported."""
    ext = Path(name.split("?")[0]).suffix.lower()
    if data[:5] == b"%PDF-" or ext == ".pdf":
        return _pdf(data, lang, pages)
    if ext in (".docx", ".docm"):
        return _docx(data, lang)
    if ext in (".xlsx", ".xlsm"):
        return _xlsx(data, lang)
    if ext == ".pptx":
        return _pptx(data, lang)
    if ext in (".odt", ".ods", ".odp"):
        return _odf(data, ext, lang)
    if ext in IMAGE_EXTS:
        return _image(data, lang)
    if ext in (".doc", ".xls", ".ppt"):
        raise ValueError(f"old binary Office format ({ext}): save it as {ext}x (or PDF) first")
    if b"\x00" in data[:4000] and ext not in (".txt", ".csv", ".tsv"):
        raise ValueError(f"binary file ({ext or 'no extension'}) is not a readable document")
    return _text(data, ext, lang)


# --------------------------------------------------------------------------------------------------- answers
_CACHE: dict[tuple, Document] = {}


def load(path: Path, lang: str = "tr", pages: tuple[int, int] | None = None) -> Document:
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime, lang, pages)
    if key not in _CACHE:
        _CACHE[key] = extract(path.read_bytes(), path.name, lang, pages)
        while len(_CACHE) > 24:
            _CACHE.pop(next(iter(_CACHE)))
    return _CACHE[key]


def parse_pages(spec: str | None) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", spec or "")
    return (int(m.group(1)), int(m.group(2) or m.group(1))) if m else None


def _terms(q: str) -> list[str]:
    """Query words: longer words and every number (a year, an amount, an article number)."""
    return [w for w in re.findall(r"\w+", q.lower()) if len(w) > 2 or w.isdigit()]


def passages(doc: Document, query: str, limit: int = 8) -> list[tuple[Part, str]]:
    """The best matching passages (a few lines each) with their part labels. Rare words count more than common
    ones, numbers must match as whole numbers, and the query words appearing together count most."""
    terms = _terms(query)
    if not terms:
        return []
    windows = []  # (part, text): a few lines at a time, so a passage points at the right place in its part
    for part in doc.parts:
        lines = [l for l in part.text.split("\n") if l.strip()]
        buf: list[str] = []
        for line in lines:
            buf.append(line)
            if sum(map(len, buf)) >= 420:
                windows.append((part, "\n".join(buf)))
                buf = []
        if buf:
            windows.append((part, "\n".join(buf)))
    lows = [w.lower() for _, w in windows]
    n = len(windows) or 1
    weight = {}
    for t in set(terms):  # inverse document frequency: a word in every passage says little
        df = sum(1 for low in lows if t in low)
        weight[t] = (3.0 if t.isdigit() else 1.0) * (1.0 + (n / (1 + df)) ** 0.5)
    phrase = " ".join(terms)
    scored = []
    for (part, text), low in zip(windows, lows):
        hits = [t for t in set(terms) if (re.search(rf"(?<!\d){t}(?!\d)", low) if t.isdigit() else t in low)]
        if not hits:
            continue
        score = sum(weight[t] for t in hits) * (len(hits) / len(set(terms)))
        if phrase in " ".join(re.findall(r"\w+", low)):
            score *= 3
        scored.append((score, part, text[:900]))
    scored.sort(key=lambda x: -x[0])
    return [(p, w) for _, p, w in scored[:limit]]


def render(doc: Document, query: str = "", budget: int = 14000) -> str:
    """Text for the model: matching passages (query), the whole document when it fits, else an outline."""
    head = f"[{doc.kind}{', ' + doc.title if doc.title else ''}; {len(doc.parts)} parts"
    head += (f"; {'; '.join(doc.notes)}" if doc.notes else "") + "]"
    cite = "Quote with the [label] of the part you used (page, slide, sheet rows, paragraphs, lines)."
    if query:
        found = passages(doc, query)
        if found:
            return "\n\n".join([head, f"Best passages for: {query}. {cite}"] + [f"[{p.label}] {w}" for p, w in found])
        head += f"\nNothing matched '{query}'; outline follows."
    if doc.chars <= budget:
        return "\n\n".join([head, cite] + [f"[{p.label}]{' (OCR)' if p.ocr else ''}\n{p.text.strip()}" for p in doc.parts
                                           if p.text.strip()])
    outline = [f"[{p.label}] {re.sub(r'\s+', ' ', p.text.strip())[:160]}" for p in doc.parts if p.text.strip()]
    return "\n".join([head, "Too long to show whole: read parts with pages=\"a-b\" or ask with query=\"...\". " + cite,
                      ""] + outline[:200])
