"""PowerPoint preview as positioned shapes: every slide's background, text boxes (font size, bold, colour,
alignment), pictures (embedded, data URLs), tables and filled shapes at their real place in % of the slide.
Browsers cannot render .pptx; this draws a faithful copy without LibreOffice."""
from __future__ import annotations

import base64
from pathlib import Path

EMU_PER_PT = 12700


def _rgb(color) -> str | None:
    try:
        if color is not None and color.type is not None and color.rgb is not None:
            return f"#{color.rgb}"
    except (AttributeError, ValueError, KeyError):
        pass
    return None


def _fill(shape) -> str | None:
    """Solid fill as #rrggbb, or rgba(...) when the colour has an alpha (translucent decorations)."""
    try:
        f = shape.fill
        if f.type == 1:  # MSO_FILL.SOLID
            hexc = _rgb(f.fore_color)
            if not hexc:
                return None
            from pptx.oxml.ns import qn
            clr = f._xPr.find(qn("a:solidFill"))
            clr = clr.find(qn("a:srgbClr")) if clr is not None else None
            a = clr.find(qn("a:alpha")) if clr is not None else None
            if a is not None:
                r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
                return f"rgba({r},{g},{b},{int(a.get('val', '100000')) / 100000:.3f})"
            return hexc
    except (AttributeError, ValueError, TypeError, KeyError):
        pass
    return None


def _radius(shape) -> str | None:
    """CSS border-radius for the auto shape's geometry: ovals round, rounded rectangles a little."""
    try:
        t = int(shape.auto_shape_type)
    except (AttributeError, ValueError, NotImplementedError, TypeError):
        return None
    return {9: "50%", 5: "6%"}.get(t)  # MSO_SHAPE.OVAL, MSO_SHAPE.ROUNDED_RECTANGLE


def _runs(tf, default_pt: float) -> list[dict]:
    paras = []
    for p in tf.paragraphs:
        runs = []
        for r in p.runs:
            f = r.font
            runs.append({"t": r.text, "b": bool(f.bold), "i": bool(f.italic),
                         "pt": round(f.size.pt, 1) if f.size else None, "c": _rgb(f.color) if f.color else None})
        if not runs and not p.text:
            paras.append({"runs": [], "empty": True})
            continue
        if not runs:
            runs = [{"t": p.text, "b": False, "i": False, "pt": None, "c": None}]
        align = {1: "left", 2: "center", 3: "right", 4: "justify"}.get(int(p.alignment) if p.alignment else 0)
        bullet = None
        try:
            from pptx.oxml.ns import qn
            ppr = p._p.pPr
            bu = ppr.find(qn("a:buChar")) if ppr is not None else None
            if bu is not None:
                bullet = bu.get("char") or "•"
            elif ppr is not None and ppr.find(qn("a:buAutoNum")) is not None:
                bullet = "#"
        except (AttributeError, ValueError):
            pass
        before = after = 0.0
        try:
            from pptx.oxml.ns import qn
            ppr = p._p.pPr
            for tag, name in (("a:spcBef", "before"), ("a:spcAft", "after")):
                el = ppr.find(qn(tag)) if ppr is not None else None
                pts = el.find(qn("a:spcPts")) if el is not None else None
                if pts is not None:
                    v = int(pts.get("val", "0")) / 100
                    before, after = (v, after) if name == "before" else (before, v)
        except (AttributeError, ValueError):
            pass
        paras.append({"runs": runs, "level": p.level or 0, "align": align, "bullet": bullet, "before": before, "after": after,
                      "pt": next((x["pt"] for x in runs if x["pt"]), None) or default_pt})
    return paras


def _box(shape, W: int, H: int) -> dict:
    return {"x": round((shape.left or 0) / W * 100, 3), "y": round((shape.top or 0) / H * 100, 3),
            "w": round((shape.width or 0) / W * 100, 3), "h": round((shape.height or 0) / H * 100, 3)}


def _shapes(shapes, W: int, H: int, out: list, depth: int = 0) -> None:
    for sh in shapes:
        try:
            st = int(sh.shape_type) if sh.shape_type is not None else 0
        except (NotImplementedError, ValueError):
            st = 0
        if st == 6 and depth < 4:  # group
            _shapes(sh.shapes, W, H, out, depth + 1)
            continue
        box = _box(sh, W, H)
        if st == 13 or getattr(sh, "image", None) is not None and st != 14:  # picture
            try:
                img = sh.image
                out.append({"kind": "image", **box, "src": f"data:{img.content_type};base64,"
                                                          f"{base64.b64encode(img.blob).decode()}"})
            except (AttributeError, ValueError, KeyError):
                pass
            continue
        if getattr(sh, "has_table", False) and sh.has_table:
            rows = [[c.text for c in r.cells] for r in sh.table.rows][:40]
            out.append({"kind": "table", **box, "rows": rows})
            continue
        if getattr(sh, "has_chart", False) and sh.has_chart:
            try:
                ch = sh.chart
                series = [{"name": s.name, "values": [v for v in s.values][:30]} for s in ch.plots[0].series][:6]
                cats = [str(c) for c in ch.plots[0].categories][:30]
                out.append({"kind": "chart", **box, "series": series, "categories": cats})
            except (AttributeError, IndexError, ValueError, KeyError):
                out.append({"kind": "rect", **box, "fill": "#eef2f7"})
            continue
        fill = _fill(sh)
        # Text without its own size takes the placeholder's default from the slide master, as PowerPoint shows it:
        # a title 40-44 pt (centered on a title slide), a subtitle 24 pt, body text 28/24/20 pt by level with bullets.
        ph = None
        try:
            ph = int(sh.placeholder_format.type) if sh.is_placeholder else None
        except (AttributeError, ValueError):
            ph = None
        base = {1: 40, 3: 44, 4: 24}.get(ph, 18 if ph is None else 24)
        text = _runs(sh.text_frame, base) if getattr(sh, "has_text_frame", False) and sh.has_text_frame else []
        for p in text:
            if p.get("runs") is not None and ph in (2, 7) and not any(r.get("pt") for r in p["runs"]):
                p["pt"] = (28, 24, 20, 18)[min(p.get("level", 0), 3)]
            if ph in (3, 4) and not p.get("align"):
                p["align"] = "center"
            if ph in (2, 7) and not p.get("bullet"):
                p["bullet"] = "•"
        if fill or any(p.get("runs") for p in text):
            anchor = None
            try:
                anchor = {1: "top", 3: "middle", 4: "bottom"}.get(int(sh.text_frame.vertical_anchor or 0))
            except (AttributeError, ValueError, TypeError):
                pass
            out.append({"kind": "text" if any(p.get("runs") for p in text) else "rect", **box, "fill": fill, "paras": text,
                        "radius": _radius(sh), "title": ph in (1, 3),
                        "valign": anchor or ("middle" if ph in (1, 3, 4) else "top")})


def slides(path: Path) -> dict:
    from pptx import Presentation
    prs = Presentation(str(path))
    W, H = prs.slide_width or 12192000, prs.slide_height or 6858000
    out = []
    for s in prs.slides:
        bg = None
        try:
            if s.background.fill.type == 1:
                bg = _rgb(s.background.fill.fore_color)
        except (AttributeError, ValueError, TypeError, KeyError):
            pass
        items: list = []
        # the layout / master shapes first (band, logo, footer), then the slide's own
        try:
            _shapes([x for x in s.slide_layout.shapes if not x.is_placeholder], W, H, items)
        except (AttributeError, ValueError):
            pass
        _shapes(s.shapes, W, H, items)
        title = s.shapes.title.text_frame.text.strip() if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        notes = s.notes_slide.notes_text_frame.text.strip() if s.has_notes_slide and s.notes_slide.notes_text_frame else ""
        lines = [p.text.strip() for sh in s.shapes if getattr(sh, "has_text_frame", False) and sh.has_text_frame
                 and sh != s.shapes.title for p in sh.text_frame.paragraphs if p.text.strip()]
        out.append({"title": title, "lines": lines[:40], "notes": notes[:2000], "bg": bg, "shapes": items})
    return {"slides": out, "ratio": W / H, "width_pt": W / EMU_PER_PT}
