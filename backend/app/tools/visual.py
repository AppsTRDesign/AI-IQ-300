"""Visual Tester: Playwright screenshot of the app under test + vision-model review."""
from __future__ import annotations

import base64
import time
from pathlib import Path

from ..config import load_settings
from ..llm import router


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
        await browser.close()
    vision = load_settings().get("vision_model")
    if not vision:
        return str(out), "No vision model configured; screenshot saved only.", console
    prompt = ("You are a UI QA tester. Inspect this screenshot and list concrete visual or layout bugs "
              f"(overlap, broken styles, missing content, unreadable text). Criteria: {criteria or 'general quality'}. "
              "Answer 'LOOKS GOOD' if none.")
    try:
        review = await router.complete(vision, [{"role": "user", "content": prompt,
                                                 "images": [base64.b64encode(out.read_bytes()).decode()]}])
    except Exception as e:  # provider errors are reported, not fatal
        review = f"vision model error: {e}"
    return str(out), review, console
