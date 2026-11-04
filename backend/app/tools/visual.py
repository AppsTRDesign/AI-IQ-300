"""Visual Tester: Playwright screenshot of the app under test + vision-model review."""
from __future__ import annotations

import base64
import time
from pathlib import Path

from ..config import load_settings
from ..llm import router


DOM_REPORT = r"""() => {
  const vw = document.documentElement.clientWidth;
  const vis = (e) => { const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const all = [...document.querySelectorAll('body *')];
  return {
    title: document.title,
    text: (document.body?.innerText || '').replace(/\n{3,}/g, '\n\n').slice(0, 1800),
    headings: [...document.querySelectorAll('h1,h2,h3')].filter(vis).map(h => h.innerText.trim()).slice(0, 12),
    buttons: [...document.querySelectorAll('button,a,input[type=submit]')].filter(vis)
      .map(b => (b.innerText || b.value || b.getAttribute('aria-label') || '').trim()).filter(Boolean).slice(0, 20),
    inputs: document.querySelectorAll('input,textarea,select').length,
    broken_images: [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src).slice(0, 5),
    overflow: all.filter(e => vis(e) && e.getBoundingClientRect().right > vw + 2).length,
    stylesheets: document.styleSheets.length,
    page_width: document.documentElement.scrollWidth, viewport: vw,
  };
}"""


def _dom_text(d: dict | None) -> str:
    if not d:
        return "Screenshot saved (no vision model; the page could not be inspected)."
    lines = ["No vision model: page checked from its DOM instead (do NOT analyse the screenshot file with scripts).",
             f"Title: {d.get('title') or '(none)'}",
             f"Headings: {d.get('headings')}", f"Buttons/links: {d.get('buttons')}", f"Form fields: {d.get('inputs')}",
             f"Stylesheets loaded: {d.get('stylesheets')}",
             f"Broken images: {d.get('broken_images') or 'none'}",
             f"Horizontal overflow: {'yes, ' + str(d.get('overflow')) + ' elements wider than the viewport' if d.get('overflow') else 'none'}"
             f" (page {d.get('page_width')}px / viewport {d.get('viewport')}px)",
             "Visible text:", d.get("text") or "(empty page)"]
    return "\n".join(lines)


async def capture_and_review(url: str, criteria: str, root: Path) -> tuple[str, str, list[str]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "", "Playwright not installed (run install.bat).", []
    shots = root / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    out = shots / f"shot-{int(time.time())}.png"
    console: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda m: m.type == "error" and console.append(m.text))
        page.on("pageerror", lambda e: console.append(str(e)))
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.screenshot(path=str(out), full_page=True)
        try:
            dom = await page.evaluate(DOM_REPORT)
        except Exception:
            dom = None
        await browser.close()
    vision = load_settings().get("vision_model")
    if not vision:
        # Text-only models get a DOM-based check instead (they cannot see the PNG): enough to judge the page
        # without spending turns analysing screenshot pixels with scripts.
        return str(out), _dom_text(dom), console
    prompt = ("You are a UI QA tester. Inspect this screenshot and list concrete visual or layout bugs "
              f"(overlap, broken styles, missing content, unreadable text). Criteria: {criteria or 'general quality'}. "
              "Answer 'LOOKS GOOD' if none.")
    try:
        review = await router.complete(vision, [{"role": "user", "content": prompt,
                                                 "images": [base64.b64encode(out.read_bytes()).decode()]}])
    except Exception as e:  # provider errors are reported, not fatal
        review = f"vision model error: {e}"
    return str(out), review, console
