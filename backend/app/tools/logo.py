"""Logo maker helpers: transparent cut-outs of generated symbols, and the AI's brand directions (validated)."""
from __future__ import annotations

import io
import re

SUGGEST = """You are a senior brand designer. For the brand you get, propose 3 different logo directions. Reply with ONE
JSON object and nothing else:
{"variants": [{"name": "<2-3 words, LANG>", "why": "<one sentence, LANG>", "font": "sans|serif|display|mono|script|condensed",
  "weight": 400-900, "uppercase": true|false, "letter_spacing": -2..12, "layout": "icon_left|icon_top|text_only|badge",
  "shape": "none|circle|rounded|hexagon", "colors": {"primary": "#RRGGBB", "secondary": "#RRGGBB", "text": "#RRGGBB"},
  "icon_prompt": "<an English description of a simple symbol for the brand, no text>", "tagline": "<short, LANG>"}]}
Make the three really different (e.g. modern geometric, warm handcrafted, bold premium). Colours must contrast on white."""

FONTS = {"sans", "serif", "display", "mono", "script", "condensed"}
LAYOUTS = {"icon_left", "icon_top", "text_only", "badge"}
SHAPES = {"none", "circle", "rounded", "hexagon"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean_variants(items: list) -> list[dict]:
    out = []
    for v in items[:3]:
        if not isinstance(v, dict):
            continue
        cols = v.get("colors") if isinstance(v.get("colors"), dict) else {}
        out.append({
            "name": str(v.get("name") or "")[:40], "why": str(v.get("why") or "")[:200],
            "font": v.get("font") if v.get("font") in FONTS else "sans",
            "weight": max(300, min(900, int(v.get("weight") or 700))) if str(v.get("weight") or "").isdigit() else 700,
            "uppercase": bool(v.get("uppercase")),
            "letter_spacing": max(-4, min(20, float(v.get("letter_spacing") or 0))) if isinstance(v.get("letter_spacing"), (int, float)) else 0,
            "layout": v.get("layout") if v.get("layout") in LAYOUTS else "icon_left",
            "shape": v.get("shape") if v.get("shape") in SHAPES else "none",
            "colors": {k: (cols.get(k) if HEX.match(str(cols.get(k) or "")) else d)
                       for k, d in (("primary", "#2563EB"), ("secondary", "#F59E0B"), ("text", "#111827"))},
            "icon_prompt": str(v.get("icon_prompt") or "")[:300], "tagline": str(v.get("tagline") or "")[:80],
        })
    return out


def cutout(data: bytes, soft: tuple[int, int] = (18, 70)) -> bytes:
    """PNG with the plain background around a picture made transparent: the background colour is read from the
    corners, only background connected to the edges is removed (white details inside the symbol stay), edges are
    soft, and the result is trimmed to the symbol with a small margin."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if max(im.size) > 1024:
        im.thumbnail((1024, 1024))
    w, h = im.size
    corners = [im.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    bg = tuple(sorted(c[i] for c in corners)[1] for i in range(3))
    diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L")
    # distance -> alpha: under soft[0] is background, over soft[1] is the symbol
    lo, hi = soft
    alpha = diff.point(lambda d: 0 if d <= lo else 255 if d >= hi else int((d - lo) * 255 / (hi - lo)))
    # keep background-like pixels that are not connected to the border (white inside the symbol)
    near = diff.point(lambda d: 255 if d < hi else 0)
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if near.getpixel(xy) == 255:
            ImageDraw.floodfill(near, xy, 128)
    inside = near.point(lambda v: 255 if v == 255 else 0)  # near-bg but enclosed: keep opaque
    alpha = ImageChops.lighter(alpha, inside).filter(ImageFilter.GaussianBlur(0.6))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        pad = int(max(w, h) * 0.03)
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))
        out = out.crop(box)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
