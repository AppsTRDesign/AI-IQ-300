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


# Seconds each vision model needed for a description (moving average), learned while the app runs and saved:
# the fastest working model is asked first, a slow or silent one falls back to the next.
_SPEED_FILE = None
_SPEED: dict[str, float] = {}
VISION_NAMES = __import__("re").compile(r"[-_:.]vl\b|vl[-_:]|vision|llava|pixtral|moondream|minicpm-v|qvq", __import__("re").I)


def _speeds() -> dict[str, float]:
    global _SPEED_FILE
    if _SPEED_FILE is None:
        import json
        from ..config import DATA_DIR
        _SPEED_FILE = DATA_DIR / "vision_speed.json"
        try:
            _SPEED.update({k: float(v) for k, v in json.loads(_SPEED_FILE.read_text(encoding="utf-8")).items()})
        except (OSError, ValueError):
            pass
    return _SPEED


def _learn(model: str, seconds: float) -> None:
    import json
    sp = _speeds()
    sp[model] = round(seconds if model not in sp else sp[model] * 0.6 + seconds * 0.4, 1)
    try:
        _SPEED_FILE.write_text(json.dumps(sp, indent=1), encoding="utf-8")
    except OSError:
        pass


def _vision_candidates(configured: str, exclude: str) -> list[str]:
    """The configured vision model first (unless it proved slow), then other cloud models whose API reports
    vision, fastest known first. Local models are not used: they would compete with the task's own model."""
    from ..config import load_settings as _ls
    settings = _ls()
    found = []
    local_ok: list[str] = []
    for pid, (_, data) in list(router._MODEL_CACHE.items()):
        cfg = settings["providers"].get(pid) or {}
        if not router.usable(pid, cfg):
            continue
        if cfg.get("local"):
            # A small local vision model (moondream, qwen2.5-vl 3B, llava-phi...) is free and offline: used last,
            # and only when it fits in the free memory next to everything else (never the big chat model itself).
            try:
                from ..llm.memguard import free_memory
                room = free_memory() - 3 * 1024 ** 3
            except Exception:
                room = 0
            local_ok += [f"{pid}:{m['id']}" for m in data.get("models", [])
                         if m.get("vision") and m.get("size") and m["size"] < min(room, 6 * 1024 ** 3)]
            continue
        found += [f"{pid}:{m['id']}" for m in data.get("models", []) if m.get("vision")]
    sp = _speeds()
    # Models measured before (data/vision_speed.json) stay candidates even before the model lists are loaded (right
    # after a start, or in a helper process): the configured model alone failing left no fallback.
    found += [m for m in sp if not (settings["providers"].get(m.partition(":")[0]) or {}).get("local")
              and router.usable(m.partition(":")[0], settings["providers"].get(m.partition(":")[0]) or {})]
    # Unknown speed: models made for images (qwen-vl, llava, pixtral...) are usually far faster at it than large
    # general models that also accept images.
    guess = lambda m: sp.get(m, 20 if VISION_NAMES.search(m) else 60)  # noqa: E731
    # The configured model gets a small head start; a model measured to be much faster still goes first.
    pool = {m for m in [configured, *found] if m and m != exclude}
    best = sorted(pool, key=lambda m: guess(m) * (0.8 if m == configured else 1.0))[:4]
    return best + [m for m in local_ok if m not in best and m != exclude][:1]


async def describe_for(model: str, image: Path, request: str = "", budget: float = 70) -> tuple[str, str] | None:
    """When the model running the task cannot see images, a vision model looks at the screenshot and describes it.
    Settings > Models' vision model is asked first; when it is slow, busy or answers empty, the next vision-capable
    cloud model takes over (fastest known first), all within `budget` seconds. Returns (model, description), or
    None when not needed / no vision model is set. Tall pages are cut to their first 2400 px, 1280 px wide."""
    vision = load_settings().get("vision_model") or ""
    # (The vision model may be the chat model itself: when that model is not marked as seeing images in the chat, it
    # still gets the picture here, in its own request; before, nothing described the page then.)
    if not vision or (model and router.supports_images(model)) or not image.is_file():  # model "": always describe
        return None
    import asyncio
    import io

    from PIL import Image
    img = Image.open(image).convert("RGB")
    if img.width > 1280:
        img = img.resize((1280, int(img.height * 1280 / img.width)))
    if img.height > 2400:
        img = img.crop((0, 0, img.width, 2400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    data = base64.b64encode(buf.getvalue()).decode()
    # Short on purpose: the page text comes with the tool result anyway; the vision model adds what only eyes see.
    # A verbatim transcript (1500 tokens) took 60 s, a focused description takes 5-15 s.
    prompt = ("In at most 180 words, describe this screenshot for someone who cannot see it: the layout from top to "
              "bottom, the main headings and buttons, images and what they show, the colour scheme, and any visual "
              "problem (overlap, cut-off text, broken images, empty areas). " + (f"The user's request: {request[:300]}" if request else ""))
    notes: list[str] = []

    async def ask(cand: str) -> tuple[str, str]:
        t0 = time.monotonic()
        try:
            seen = (await router.complete(cand, [{"role": "user", "content": prompt, "images": [data]}],
                                          {"think": False, "max_tokens": 450})).strip()
        except Exception as e:  # noqa: BLE001 - a failing vision model never fails the screenshot
            _learn(cand, 60)
            raise RuntimeError(f"{cand}: {str(e)[:120] or type(e).__name__}") from None
        if len(seen) < 40:
            _learn(cand, 60)
            raise RuntimeError(f"{cand}: empty answer")
        _learn(cand, time.monotonic() - t0)
        return cand, seen

    # One request at a time, fastest known model first; a model that is too slow is cancelled before the next one
    # starts. No racing requests: a provider queues the requests of one key (a 4 s model waited 55 s behind another).
    sp = _speeds()
    deadline = time.monotonic() + budget
    for cand in _vision_candidates(vision, model):
        left = deadline - time.monotonic()
        if left < 5:
            break
        # A model gets about three times its usual time (at least 15 s); then it is cancelled and the next one asked.
        wait = min(left, max(15.0, 3 * sp.get(cand, 20)))
        try:
            return await asyncio.wait_for(ask(cand), wait)
        except asyncio.TimeoutError:
            notes.append(f"{cand}: no answer in {int(wait)} s")
            _learn(cand, 60)
        except RuntimeError as e:
            notes.append(str(e))
    return vision, ("(no vision model could describe it in time: " + ("; ".join(notes) or "no answer") +
                    "; use the page text instead)")
