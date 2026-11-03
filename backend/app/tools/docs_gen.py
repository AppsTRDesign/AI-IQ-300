"""Office document generation from simple markdown / JSON."""
from __future__ import annotations

import json
from pathlib import Path


def _blocks(md: str):
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            yield "h", min(level, 3), s.lstrip("#").strip()
        elif s.lstrip().startswith(("- ", "* ")):
            yield "li", 0, s.lstrip()[2:]
        elif s.strip():
            yield "p", 0, s


def generate(kind: str, content: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    kind = kind.lower()
    if kind == "docx":
        from docx import Document
        doc = Document()
        for t, lvl, text in _blocks(content):
            if t == "h":
                doc.add_heading(text, lvl)
            elif t == "li":
                doc.add_paragraph(text, style="List Bullet")
            else:
                doc.add_paragraph(text)
        doc.save(target)
    elif kind == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        rows = json.loads(content)
        if rows and isinstance(rows[0], dict):
            ws.append(list(rows[0].keys()))
            rows = [list(r.values()) for r in rows]
        for r in rows:
            ws.append(r)
        wb.save(target)
    elif kind == "pdf":
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        styles = getSampleStyleSheet()
        story = []
        for t, lvl, text in _blocks(content):
            style = styles[f"Heading{lvl}"] if t == "h" else styles["BodyText"]
            story += [Paragraph(("• " if t == "li" else "") + text, style), Spacer(1, 4)]
        SimpleDocTemplate(str(target)).build(story)
    elif kind == "pptx":
        from pptx import Presentation
        prs = Presentation()
        for chunk in content.split("\n---"):
            blocks = list(_blocks(chunk))
            if not blocks:
                continue
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            title = next((b[2] for b in blocks if b[0] == "h"), "")
            slide.shapes.title.text = title
            body = slide.placeholders[1].text_frame
            body.text = ""
            for t, _, text in blocks:
                if text != title:
                    body.add_paragraph().text = text
        prs.save(target)
    else:
        raise ValueError(f"unsupported document type: {kind}")
