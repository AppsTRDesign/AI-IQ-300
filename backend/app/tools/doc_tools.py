"""Documents: make_doc and its placeholder / picture checks.

Split out of registry.py (round 2026-11-20). registry imports this module at its end and re-exports every name, so registry.X keeps working; import tools from registry, not from here."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from .. import approvals, policy
from ..config import LANG_DIR, load_settings
from ..process_manager import manager

from .registry import S, ToolResult, _path, _rel, gate, kind_of, tool, unverified_figures  # noqa: F401


# Stand-ins a weak model writes instead of the text: \pdfcontent / \\pdfbaşlığı, {{title}}, ${content}, <CONTENT>,
# [İçerik buraya], [Insert text here], Lorem ipsum, "TODO". LaTeX math ($x^2$, \frac) is real content and stays.
PLACEHOLDER = re.compile(
    r"\\{1,2}(?!(?:frac|sqrt|sum|int|alpha|beta|gamma|delta|pi|sigma|times|cdot|le|ge|neq|infty|left|right|text|mathrm|"
    r"begin|end|over|lim|log|ln|sin|cos|tan|partial|nabla|theta|lambda|mu|omega|approx|pm|rightarrow|to|quad|hat|bar|vec|"
    r"dots|ldots|cdots|textbf|textit|emph|underline)\b)[a-zçğıöşü]*(?:pdf|doc|docx|ppt|pptx|xls|içerik|icerik|başlı|basli|content|title|heading|body|"
    r"section|bölüm|metin|text)[a-zçğıöşü]*\b"
    # <CONTENT> / <BAŞLIK> in capitals only: <title>, <body> are real HTML tags (an HTML document was refused)
    r"|\{\{\s*[\w .çğıöşü-]{1,40}\s*\}\}|\$\{\s*\w{1,40}\s*\}|(?-i:<\s*(?:CONTENT|TEXT|İÇERİK|BAŞLIK|METİN)\s*>)"
    r"|\[\s*(?:içerik|metin|başlık|buraya|insert|content|your|add|placeholder|text here|lorem)[^\]\n]{0,40}\](?!\()"
    r"|\[[^\]\n]{0,30}\b(?:ad[ıi]|ad[ıi]n[ıi]z|isim|ismi|name|tarih|date|şirket|firma|company|marka|brand|telefon|phone|"
    r"adres|address|e-?posta|email|web\s*site|url|fiyat|price|numara|number|yazar|author)\s*\](?!\()"
    # Filler text goes on: "Lorem ipsum dolor sit amet". The bare phrase in a sentence is a mention (a report on this
    # app's guards: "no lorem ipsum") and was refused twice as a placeholder.
    r"|lorem ipsum[\s,.]+dolor", re.I)


def placeholder_marks(content: str) -> list[str]:
    """Placeholder stand-ins in a document's content (outside code blocks and inline code), each once."""
    text = re.sub(r"```.*?```", " ", content, flags=re.S)
    text = re.sub(r"`[^`\n]{1,200}`|<code>.*?</code>", " ", text, flags=re.S)
    return list(dict.fromkeys(m.group(0).strip()[:40] for m in PLACEHOLDER.finditer(text)))


def filler_problem(content: str, outline: list[str] | None = None) -> str:
    """A document that only looks written: the same paragraph under several headings (a weak model filled a
    template's sample sections "Problem / Proposed solution / Scope / Budget / Team" with one sentence about a
    computer), or the template's sample outline used as the headings. Returns what is wrong, or ''."""
    text = re.sub(r"```.*?```", " ", content, flags=re.S)
    paras = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p)).strip().lower()
             for p in re.split(r"\n\s*\n|</p>|<br\s*/?>\s*<br\s*/?>", text)]
    paras = [p for p in paras if len(p) >= 60 and not p.startswith(("#", "|", "-", "*"))]
    seen: dict[str, int] = {}
    for p in paras:
        seen[p] = seen.get(p, 0) + 1
    if (rep := max(seen.values(), default=0)) >= 3:
        return f"the same paragraph is repeated under {rep} headings - write each section's own real content"
    if outline:
        raw = re.findall(r"^#{1,3}[ \t]+([^\n]+)$", text, re.M) + re.findall(r"<h[12][^>]*>(.*?)</h[12]>", text, re.S)
        heads = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>|[#*\d.)]", " ", h)).strip().lower() for h in raw]
        sample = {o.strip().lower() for o in outline if o.strip()}
        same = [h for h in heads if h in sample]
        if len(sample) >= 3 and len(same) >= max(3, int(len(sample) * 0.6)):
            return ("the headings are the template's sample sections (" + ", ".join(same[:5]) + "), not this "
                    "request's content - the template is only the design: write the title and headings from what the "
                    "user asked for")
    return ""


def _anchor_images(ctx, content: str, base_dir: Path, target: Path) -> str:
    """Pictures of a document by the path the model gave, found wherever they really are: next to the source text,
    next to the document, in the task folder or its working folder, or (one file of that name) anywhere in the
    project. The source text lives in docs/.doc-sources/, so `images/grafik.png` - written from the task folder -
    was looked up in docs/.doc-sources/images/ and every chart was dropped, again and again."""
    def find(src: str) -> str:
        s = src.strip().strip("<>").split(" ")[0]
        if not s or re.match(r"(https?|data|file):", s, re.I):
            return src
        bases = [base_dir, target.parent, ctx.root, _path(ctx, ctx.shell_cwd or ".")]
        bases += [b.parent for b in list(bases)]
        def rel(p: Path) -> str:  # from the folder the document resolves pictures in (Markdown refuses file: links)
            try:
                return os.path.relpath(p.resolve(), base_dir.resolve()).replace("\\", "/")
            except ValueError:  # another drive
                return p.resolve().as_posix()
        for b in bases:
            p = (b / s)
            if p.is_file():
                return rel(p)
        name = Path(s).name
        hits = [p for p in ctx.root.rglob(name) if "node_modules" not in p.parts and ".git" not in p.parts][:2]
        return rel(hits[0]) if len(hits) == 1 else src
    content = re.sub(r"(!\[[^\]]*\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))", lambda m: m.group(1) + find(m.group(2)) + m.group(3),
                     content)
    return re.sub(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", lambda m: m.group(1) + find(m.group(2)) + m.group(3),
                  content, flags=re.I)


@tool("make_doc", '<tool name="make_doc" type="pdf|docx|pptx|xlsx|html" path="docs/report.pdf" theme="corporate">'
      'markdown, HTML or JSON content</tool>',
      "Generate a professional document (designed layout, every language and script, clickable links, LaTeX math). "
      "pdf/docx/pptx/html take full Markdown (headings, **bold**, lists, tables, links, images, code, > quotes, "
      "$inline$ and $$display$$ LaTeX) or HTML; in pptx every # / ## heading (or ---) starts a slide, the first # "
      "alone is the title slide. xlsx takes JSON rows, {\"sheets\": {\"Name\": rows}} or Markdown tables (one sheet "
      "each; numbers become real numbers). For pdf/docx/pptx/html write HTML (preferred: it is the document's own "
      "structure in every format; a fragment, the designed template styles it; Markdown only for short notes): <h1>, <h2>, <p>, <table>, plus ready components: KPI cards <div class=\"kpis\"><div "
      "class=\"kpi\"><span>USD/TRY</span><b>50,36</b><em class=\"up\">+0,22%</em></div>...</div>, a bar chart <div "
      "class=\"bars\"><div style=\"--v:76%\"><span>USD</span><i></i><b>50,36</b></div>...</div> (--v = bar length in "
      "% of the largest value), <div class=\"callout\">note</div>, <span class=\"badge\">tag</span>, <div "
      "class=\"cols\">two columns</div>, inline <svg> charts. They need no image file and also work in docx/pptx. "
      "Large content: write it to a .md/.html file first (write_file, append "
      "parts) and pass source=that file instead of content. Write real data and real source URLs, never placeholders.",
      {"type": S("Document type", enum=["pdf", "docx", "pptx", "xlsx", "html"]), "path": S("Output path"),
       "content": S("Markdown / HTML, or JSON rows for xlsx"),
       "source": S("Optional: a .md/.html/.json file in the working folder to convert instead of content"),
       "theme": S("Color theme", enum=["corporate", "blue", "green", "red", "purple", "orange", "teal", "gray", "dark"]),
       "template": S("Optional document template id (doc_template action=list shows them): its colours, type and "
                     "cover; write the sections / sheets / slides it names"),
       "landscape": {"type": "boolean", "description": "PDF in landscape (wide tables)"},
       "header": S("Optional, with a letterhead template: this document's own letterhead lines (organisation | unit)"),
       "footer": S("Optional, with a template: this document's own footer lines (address | phone | web)")},
      main="content", required=("path",))
async def make_doc(ctx, args, body):
    from .docs_gen import generate
    from . import doc_templates
    target = _path(ctx, args["path"])
    if not (args.get("template") or "").strip():
        # The user picked a template for this request (its chip puts make_doc template="id" into the message) and the
        # model left it out - weak models dropped it on the second make_doc call and the letter came out as a blue
        # report. It is applied when the template supports this format.
        m = re.search(r'make_doc template="([a-z0-9_]{2,40})"', getattr(ctx, "goal", "") or "")
        kind = (args.get("type") or target.suffix.lstrip(".")).lower()
        if m and (t0 := doc_templates.get(m.group(1))) and kind in t0["kinds"]:
            args = {**args, "template": m.group(1)}
    if tid := (args.get("template") or "").strip():
        doc_templates.register()
        if not doc_templates.get(tid):
            return ToolResult(False, f"unknown template '{tid}': doc_template action=list shows the ids")
        args = {**args, "theme": tid}
        if args.get("header") or args.get("footer"):  # this document's own letterhead / footer lines
            args["theme"] = doc_templates.with_lines(tid, str(args.get("header") or ""), str(args.get("footer") or ""))
    content = body
    base_dir = ctx.root
    if args.get("source"):
        src = _path(ctx, args["source"])
        if not src.is_file():
            return ToolResult(False, f"source not found: {args['source']}")
        content = src.read_text(encoding="utf-8", errors="replace")
        base_dir = src.parent
    if not (content or "").strip():
        return ToolResult(False, "No content: pass Markdown/HTML/JSON as content, or source=<file>.")
    content = _anchor_images(ctx, content, base_dir, target)
    tpl = doc_templates.get(tid) if tid else None
    lang_ = getattr(ctx, "lang", None) or "en"
    outline = (doc_templates.text(tpl, "outline", lang_) or []) if tpl else []
    from ..agents.checks import request_core
    goal = request_core(getattr(ctx, "goal", "") or "").lower()  # the user's own words, not the template chip's
    if outline and sum(o.lower() in goal for o in outline) >= 2:
        outline = []  # the user asked for these sections themselves
    if tpl and not tpl.get("user"):
        # The template's own name as the document's title ("Proje Teklifi" over a hardware report): weak models
        # copied it. A user's own template may carry their organisation's title on purpose.
        names = {str(v).strip().lower() for v in (tpl.get("name") or {}).values() if v}
        m = re.search(r"^#\s+(.+)$|<h1[^>]*>(.*?)</h1>", content, re.M | re.S)
        h1 = re.sub(r"<[^>]+>", "", (m.group(1) or m.group(2)) if m else "").strip().lower()
        if h1 and h1 in names and h1 not in goal:
            return ToolResult(False, f"Not generated: the title is the template's name ('{h1}'), not this document's. "
                                     "The template is only the design: write a title from the user's request and content.")
    if problem := filler_problem(content, outline):
        return ToolResult(False, f"Not generated: {problem}. Call make_doc again with the real content.")
    if holes := placeholder_marks(content):
        # A weak model sent the document's outline with stand-ins (\\pdfcontent, {{title}}, [İçerik buraya]) instead of
        # the text itself: such a file looks finished but says nothing.
        return ToolResult(False, "The content has placeholders instead of real text: " + ", ".join(holes[:6])
                          + ". Write the actual text of every part (in the user's language, real data and sources), "
                            "then call make_doc again. No template markers, variables or backslash commands.")
    if msg := await gate(ctx, {"tool": "make_doc", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        info = await generate(args.get("type") or target.suffix.lstrip("."), content, target, base_dir=base_dir,
                              theme=args.get("theme"), lang=getattr(ctx, "lang", None) or "en",
                              landscape=str(args.get("landscape", "")).lower() in ("true", "1", "yes"))
    except ValueError as e:
        return ToolResult(False, str(e))
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    # The document's source stays next to it: a later "add a chart / change the table" edits this text and
    # converts again, instead of rebuilding the document from memory (a PDF itself cannot be edited).
    src_rel = args.get("source") or ""
    if not src_rel:
        try:
            keep = target.parent / ".doc-sources" / f"{target.name}.md"
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_text(content, encoding="utf-8")
            src_rel = _rel(ctx, keep)
        except OSError:
            src_rel = ""
    extra = ", ".join(f"{k}: {v}" for k, v in info.items() if k in ("slides", "sheets", "formulas", "images", "engine") and v)
    if kind_of(args, target) != "xlsx":
        extra += f". The document contains {info.get('images', 0)} image(s)/chart(s)"
    if miss := info.get("missing_images"):
        # The document was written without them: the model must know, so it never tells the user they are there.
        extra += (f". WARNING: {len(miss)} image(s) were NOT included because the file does not exist or is not an "
                  f"image: {', '.join(miss)}. The document has NO such picture. If a chart/image is wanted, create it "
                  "for real first (run with shell=python and matplotlib: plt.savefig('chart.png')), check it exists, "
                  "then call make_doc again with ![caption](chart.png). Never claim an image that was not included")
    if bad := unverified_figures(ctx, content):
        extra += (f". WARNING: {len(bad)} figures in this document appear in NO source read in this task: "
                  f"{', '.join(bad[:12])}. Numbers must come from the sources: read them again (research / fetch_url) "
                  "and correct the document, or state clearly which values are your own calculation. Do not present "
                  "unverified numbers as facts")
    if src_rel:
        extra += (f". Source text: {src_rel} (to change this document later: edit_file that source, then make_doc "
                  f"source={src_rel} with the same path)")
    return ToolResult(True, f"generated {rel} ({info.get('bytes', 0) // 1024} KB{', ' + extra if extra else ''})",
                      {"path": rel, "source": src_rel, "images": info.get("images", 0),
                       **{k: v for k, v in info.items() if k in ("slides", "sheets", "engine")}})


@tool("doc_template", '<tool name="doc_template" action="create" id="brand_report" kinds="pdf,docx" colors="#123456,#0b1d2e,#eef3f8" layout="report" cover="hero" name="Brand Report" outline="Summary | Market | Plan"></tool>',
      "Document templates for make_doc (the user picks them in the chat; Template Creator makes new ones). A template "
      "is a full design, not only colours: a page layout, type, margins, letterhead / footer, logo, heading and table "
      "styles and your own CSS. action=list shows them. action=inspect reference=<file> (pdf, docx, pptx or an image) "
      "reads a reference in one step: palette, fonts, sizes, every text line with its zone (header / body / footer), "
      "alignment and position in mm, text margins, and it saves the page as a picture plus crops of its graphics "
      "(logos) in template_ref/ - look at the page picture with inspect_media to see the design. action=create saves "
      "the template: id (a-z, 0-9, _), kinds, colors (accent, dark, tint #rrggbb), layout (report = coloured cover | "
      "letter = official letter: letterhead with logo + header lines, centred title, date on the right, justified "
      "body, footer lines | memo | academic | magazine | invoice | resume | minimal), cover (for report: hero|band|"
      "minimal|dark|photo|split|editorial|corner), h2 (bar|number|underline|caps), table (solid|lines|soft), font "
      "(sans|serif), font_family (e.g. Times New Roman), margins in mm (top right bottom left), header (letterhead "
      "lines, | between), footer (footer lines on every page, | between), logo (an image file from the working folder, "
      "e.g. template_ref/x_graphic1.png), css (your own CSS for details the options cannot express; classes: .lh "
      "letterhead, .doc-title, .doc-date, .hero, main.doc, h2, table, .kpi), name, description, outline. Reproduce the "
      "reference as closely as these allow. action=preview id=<id> renders a sample page of a template to "
      "template_ref/<id>_preview.png - compare it with the reference picture (inspect_media) and create again with "
      "fixes if it differs. action=delete removes one the user made. Use it: make_doc template=<id>.",
      {"action": S("list | inspect | create | preview | delete", enum=["list", "inspect", "create", "preview", "delete"]),
       "id": S("Template id"), "kinds": S("Formats, comma separated: pdf, docx, xlsx, pptx"),
       "colors": S("accent, dark, tint (#rrggbb, comma separated)"), "font": S("sans | serif"),
       "font_family": S("A font name of the reference (Times New Roman, Arial, Georgia...)"),
       "layout": S("report | letter | memo | academic | magazine | invoice | resume | minimal"),
       "cover": S("report layout cover: hero | band | minimal | dark | photo | split | editorial | corner"),
       "h2": S("Section heading style: bar | number | underline | caps"), "table": S("Table style: solid | lines | soft"),
       "margins": S("Page margins in mm: top right bottom left (e.g. 25 20 25 25)"),
       "header": S("Letterhead lines (letter layout), | between"), "footer": S("Footer lines on every page, | between"),
       "logo": S("Logo image file in the working folder"), "css": S("Your own CSS for this template"),
       "name": S("Display name"), "description": S("One line: what it is for"),
       "outline": S("Sections / sheets / slides, separated by |"), "reference": S("The reference file it was made from")},
      main="outline", required=("action",))
async def doc_template(ctx, args, body):
    from . import doc_templates as dt
    action = (args.get("action") or "list").strip().lower()
    lang = getattr(ctx, "lang", None) or "en"
    if action == "list":
        rows = [f"- {t['id']} ({', '.join(t['kinds'])}, layout {t.get('layout') or 'report'}"
                f"{', yours' if t.get('user') else ''}): {dt.text(t, 'name', lang)} - "
                + " | ".join(dt.text(t, 'outline', lang) or []) for t in dt.all_templates()]
        return ToolResult(True, "Document templates (make_doc template=<id>):\n" + "\n".join(rows))
    if action == "inspect":
        ref = (args.get("reference") or args.get("path") or body or "").strip()
        if not ref:
            return ToolResult(False, "give reference=<file in the working folder> (pdf, docx, pptx or an image)")
        p = _path(ctx, ref)
        if not p.is_file():
            return ToolResult(False, f"reference not found: {ref}")
        try:
            info = await asyncio.to_thread(dt.analyze_reference, p)
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, f"could not read the reference: {e}")
        pics = []
        if p.suffix.lower() == ".pdf":
            try:
                pics = await asyncio.to_thread(dt.save_reference_images, p, ctx.root / "template_ref")
            except Exception:  # noqa: BLE001
                pics = []
        pal = info.get("palette") or {}
        colors = f"{pal.get('accent') or '#2563eb'},{pal.get('dark') or '#0f172a'},{pal.get('tint') or '#eff4ff'}"
        extra = ""
        if pics:
            extra = ("\nSaved in template_ref/: " + ", ".join(pics) + f". Look at template_ref/{pics[0]} with "
                     "inspect_media to see the layout; a graphicN.png that is a logo can be given as logo=.")
        return ToolResult(True, "Reference analysis (use these for doc_template action=create):\n"
                          + json.dumps(info, ensure_ascii=False, indent=1)
                          + f'\nSuggested: colors="{colors}" font="{info.get("font_suggestion")}"' + extra, info)
    if action == "delete":
        ok = dt.delete_user((args.get("id") or "").strip())
        return ToolResult(ok, "deleted" if ok else "no such template of the user (built-in ones cannot be deleted)")
    if action == "preview":
        t = dt.get((args.get("id") or "").strip())
        if not t:
            return ToolResult(False, "no such template: doc_template action=list shows the ids")
        out = ctx.root / "template_ref" / f"{t['id']}_preview.png"
        try:
            await dt.render_preview(t, lang, out)
        except Exception as e:  # noqa: BLE001
            return ToolResult(False, f"preview failed: {e}")
        return ToolResult(True, f"sample page of '{t['id']}' saved: {_rel(ctx, out)} - compare it with the reference "
                                "picture (inspect_media) and fix the template with create if it differs.",
                          {"path": _rel(ctx, out)})
    colors = [c.strip() for c in re.split(r"[,\s]+", args.get("colors") or "") if c.strip()]
    outline = [x.strip() for x in re.split(r"\s*\|\s*|\n", args.get("outline") or body or "") if x.strip()][:12]
    name = (args.get("name") or args.get("id") or "").strip()[:60]
    tid = re.sub(r"[^a-z0-9_]+", "_", (args.get("id") or name).lower()).strip("_")[:40]
    t = {"id": tid,
         "kinds": [k.strip().lower() for k in (args.get("kinds") or "pdf,docx").split(",") if k.strip()],
         "colors": colors[:3], "font": "serif" if str(args.get("font")).lower() == "serif" else "sans",
         "cover": (args.get("cover") or "hero").strip().lower(), "name": {lang: name, "en": name},
         "h2": (args.get("h2") or "").strip().lower(), "table": (args.get("table") or "").strip().lower(),
         "layout": (args.get("layout") or "report").strip().lower(),
         "desc": {lang: (args.get("description") or "").strip()[:160]}, "outline": {lang: outline},
         "reference": (args.get("reference") or "").strip()[:200]}
    for k in ("margins", "header", "footer", "css", "font_family"):
        if args.get(k):
            t[k] = args[k]
    if logo := (args.get("logo") or "").strip():
        lp = _path(ctx, logo)
        if not lp.is_file() or lp.suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
            return ToolResult(False, f"logo not found or not an image: {logo}")
        dt.asset_dir().mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lp, dt.asset_dir() / f"{tid}{lp.suffix.lower()}")
        t["logo"] = f"{tid}{lp.suffix.lower()}"
    try:
        saved = dt.save_user(t)
    except ValueError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, f"template '{saved['id']}' saved ({', '.join(saved['kinds'])}, layout "
                            f"{saved.get('layout') or 'report'}); the user now sees it in the template gallery. Check it: "
                            f"doc_template action=preview id={saved['id']}. Use it: make_doc template=\"{saved['id']}\".",
                      {"template": saved["id"]})
