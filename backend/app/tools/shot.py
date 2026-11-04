"""Web page screenshots with headless Chromium (Playwright): device presets, full page, one element, dark mode,
PNG/JPEG or PDF output. Lazy-loaded images are scrolled into view before a full-page capture."""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

DEVICES = {
    "desktop": {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1},
    "laptop": {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 1},
    "tablet": {"viewport": {"width": 820, "height": 1180}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True},
    "mobile": {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
               "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"},
}
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0.0.0 Safari/537.36")
MAX_HEIGHT = 16000  # full-page captures taller than this are cut (very long feeds never end)

# Scrolls down in viewport steps so lazy images and infinite sections load, then returns to the top.
SCROLL = """async (limit) => {
  const step = innerHeight * 0.8;
  for (let y = 0; y < Math.min(document.body.scrollHeight, limit); y += step) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  scrollTo(0, 0); await new Promise(r => setTimeout(r, 200));
}"""


# What the screenshot shows, as text: models that cannot see images describe the page from this, not from guesses.
SEEN = r"""(sel) => {
  const root = (sel && document.querySelector(sel)) || document.body;
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const pick = (q, n) => [...root.querySelectorAll(q)].filter(vis).map((e) => e.innerText.trim().replace(/\s+/g, ' '))
    .filter(Boolean).slice(0, n);
  const bg = getComputedStyle(document.body).backgroundColor;
  return { headings: pick('h1,h2,h3', 10), buttons: pick('button,a[role=button],nav a', 14),
           images: [...root.querySelectorAll('img')].filter(vis).length, background: bg,
           text: (root.innerText || '').replace(/\n{3,}/g, '\n\n').trim().slice(0, 1500) };
}"""


def default_name(url: str, fmt: str) -> str:
    host = re.sub(r"[^\w.-]+", "-", urlparse(url).netloc or Path(urlparse(url).path).stem or "page").strip("-.")
    return f"screenshots/{host or 'page'}-{time.strftime('%Y%m%d-%H%M%S')}.{fmt}"


async def capture(url: str, out: Path, *, device: str = "desktop", width: int | None = None, height: int | None = None,
                  full_page: bool = True, selector: str = "", dark: bool = False, wait_ms: int = 0,
                  hide: str = "", lang: str = "en") -> dict:
    """Returns {title, width, height, final_url} and writes the image or PDF to `out`."""
    from playwright.async_api import async_playwright
    opts = dict(DEVICES.get(device, DEVICES["desktop"]))
    if width or height:
        vp = opts["viewport"]
        opts["viewport"] = {"width": int(width or vp["width"]), "height": int(height or vp["height"])}
    opts.setdefault("user_agent", DESKTOP_UA)
    fmt = out.suffix.lstrip(".").lower()
    out.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(**opts, color_scheme="dark" if dark else "light",
                                                locale="tr-TR" if lang == "tr" else "en-US")
            page = await context.new_page()
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass  # pages with endless polling still get captured
            if hide:
                await page.add_style_tag(content=f"{hide} {{ display: none !important; }}")
            if full_page and not selector and fmt != "pdf":
                await page.evaluate(SCROLL, MAX_HEIGHT)
            if wait_ms:
                await page.wait_for_timeout(min(int(wait_ms), 15000))
            size = await page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
            seen = await page.evaluate(SEEN, selector or None)
            if fmt == "pdf":
                await page.emulate_media(media="screen")
                await page.pdf(path=str(out), print_background=True, width=f"{opts['viewport']['width']}px",
                               height=f"{min(size[1], MAX_HEIGHT)}px")
            else:
                kw = {"path": str(out), "type": "jpeg" if fmt in ("jpg", "jpeg") else "png"}
                if kw["type"] == "jpeg":
                    kw["quality"] = 90
                if selector:
                    el = page.locator(selector).first
                    try:
                        await el.wait_for(state="visible", timeout=5000)
                    except Exception:
                        raise ValueError(f"no visible element matches the selector {selector!r} on this page") from None
                    await el.screenshot(**kw, timeout=15000)
                    box = await el.bounding_box() or {}
                    size = [round(box.get("width", 0)), round(box.get("height", 0))]
                elif full_page and size[1] > MAX_HEIGHT:
                    await page.screenshot(**kw, clip={"x": 0, "y": 0, "width": opts["viewport"]["width"], "height": MAX_HEIGHT},
                                          full_page=True)
                else:
                    await page.screenshot(**kw, full_page=full_page)
            return {"title": await page.title(), "final_url": page.url, "status": resp.status if resp else 0, **seen,
                    "width": size[0] if selector else opts["viewport"]["width"],
                    "height": size[1] if full_page or selector else opts["viewport"]["height"]}
        finally:
            await browser.close()
