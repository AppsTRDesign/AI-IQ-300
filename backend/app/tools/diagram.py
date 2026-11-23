"""render_diagram: Mermaid code (or the first ```mermaid block of a .md file) -> a PNG or SVG file, drawn in the same
look as the chat's diagrams (frontend/src/lib/diagramTheme.js is the one source of the theme) by Mermaid in a
headless Chromium. No Node, no mermaid-cli download: the app already has Playwright and the Mermaid package.

registry imports this module at its end, like the other tool modules."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import policy
from ..config import ROOT
from .registry import S, ToolResult, _network_gate, _path, _rel, gate, tool

THEME_JS = ROOT / "frontend" / "src" / "lib" / "diagramTheme.js"
MERMAID_JS = ROOT / "frontend" / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.6.0/dist/mermaid.min.js"
FENCE = re.compile(r"```(?:mermaid|mmd)\s*\n(.*?)```", re.S | re.I)
FONT = "'Segoe UI', 'Inter', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:%(bg)s;font-family:%(font)s}#out{display:inline-block;padding:24px}
#out svg{display:block}#out p{margin:0;line-height:1.35}</style></head>
<body><div id="out"></div></body></html>"""


def mermaid_of(text: str) -> str:
    """The diagram code: a ```mermaid fence inside Markdown, or the text itself."""
    m = FENCE.search(text or "")
    return (m.group(1) if m else text or "").strip()


async def render(code: str, out: Path, dark: bool = False, scale: float = 2.0) -> tuple[int, int]:
    """Draw the diagram into out (.png or .svg). Returns (width, height) in CSS px. Raises ValueError for a
    diagram Mermaid cannot parse (its message), RuntimeError when no browser / Mermaid is available."""
    from playwright.async_api import async_playwright
    theme = THEME_JS.read_text(encoding="utf-8").replace("export function", "function")
    bg = "#17171a" if dark else "#ffffff"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(device_scale_factor=max(1.0, min(4.0, scale)))
            await page.set_content(PAGE % {"bg": bg, "font": FONT})
            if MERMAID_JS.is_file():
                await page.add_script_tag(path=str(MERMAID_JS))
            else:
                await page.add_script_tag(url=MERMAID_CDN)
            await page.add_script_tag(content=theme)
            res = await page.evaluate("""async ([code, dark, font, svgOnly]) => {
                mermaid.initialize(diagramConfig(dark, font, svgOnly));
                try {
                  const { svg } = await mermaid.render("d" + Date.now(), code);
                  document.getElementById("out").innerHTML = svg;
                  const s = document.querySelector("#out svg").getBoundingClientRect();
                  return { svg, w: Math.ceil(s.width), h: Math.ceil(s.height) };
                } catch (e) { return { error: String(e && e.message || e) }; }
            }""", [code, dark, FONT, out.suffix.lower() == ".svg"])
            if res.get("error"):
                raise ValueError(res["error"].split("\n")[0][:400])
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() == ".svg":
                out.write_text(res["svg"], encoding="utf-8")
            else:
                await page.locator("#out").screenshot(path=str(out), omit_background=False)
            return res["w"], res["h"]
        finally:
            await browser.close()


@tool("render_diagram", '<tool name="render_diagram" path="diagrams/flow.png">flowchart TD\n  A["Start"] --> B["End"]</tool>',
      "Save a Mermaid diagram (flowchart, sequence, state, ER, Gantt, mind map, timeline...) as a picture file in the "
      "app's diagram style: PNG (sharp, 2x) or SVG (vector), light or dark. Give the Mermaid code, or source= a .md / "
      ".mmd file whose first ```mermaid block is drawn. Use it when the user wants the diagram as an image / file / for "
      "a document; in the chat itself a ```mermaid block is enough (the chat draws it). Never matplotlib for diagrams.",
      {"code": S("Mermaid code (without the ``` fence)"), "source": S("Optional: a .md/.mmd file in the working folder"),
       "path": S("Output file: .png (default diagrams/diagram.png) or .svg"),
       "theme": S("light (default) or dark", enum=["light", "dark"]),
       "scale": {"type": "number", "description": "PNG pixel density 1-4 (default 2)"}},
      main="code", required=())
async def render_diagram(ctx, args, body):
    code = str(body or args.get("code") or "").strip()
    if src := str(args.get("source") or "").strip():
        f = _path(ctx, src)
        if not f.is_file():
            return ToolResult(False, f"source not found: {src}")
        code = f.read_text(encoding="utf-8", errors="replace")
    code = mermaid_of(code)
    if not code:
        return ToolResult(False, "Give the Mermaid code (or source= a .md file with a ```mermaid block).")
    rel = str(args.get("path") or "diagrams/diagram.png").strip()
    if Path(rel).suffix.lower() not in (".png", ".svg"):
        rel = str(Path(rel).with_suffix(".png"))
    target = _path(ctx, rel)
    if msg := await gate(ctx, {"tool": "render_diagram", "path": str(target)},
                         policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    if not MERMAID_JS.is_file() and (msg := await _network_gate(ctx, {"tool": "render_diagram", "url": MERMAID_CDN})):
        return ToolResult(False, msg)
    try:
        scale = float(args.get("scale") or 2)
    except (TypeError, ValueError):
        scale = 2.0
    try:
        w, h = await render(code, target, str(args.get("theme") or "").lower() == "dark", scale)
    except ValueError as e:
        return ToolResult(False, f"Mermaid could not draw it: {e}. Fix the code (quote labels with special "
                                 "characters, close every subgraph with end) and call again.")
    except Exception as e:  # noqa: BLE001 - no browser / no network
        return ToolResult(False, f"render_diagram failed: {e}")
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    return ToolResult(True, f"saved {out} ({w}x{h} px{'' if out.endswith('.svg') else f' at {scale:g}x'}). It is shown "
                            "to the user; mention the path.", {"path": out, "images": [out] if out.endswith(".png") else []})
