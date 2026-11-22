"""Browser actions on a real page: wait by selector / glob url / load state, typing into the focused element,
scrolling from the middle of the window (the wheel used to fire at 0,0 over a fixed header) and inside a panel.
Run: python -m pytest tests/test_browser_actions.py"""
import asyncio
from types import SimpleNamespace

import pytest

from app.tools import browser_tools as bt

PAGE = """<html><body style="margin:0">
<div style="position:fixed;top:0;left:0;right:0;height:80px;background:#333">header</div>
<div style="height:4000px;padding-top:100px"><input id=f><div id=late></div></div>
<script>setTimeout(() => { document.getElementById('late').innerHTML = '<b class=ok>ready</b>'; }, 300);</script>
</body></html>"""

PANEL = """<html><body style="margin:0;overflow:hidden">
<div id=p style="height:100vh;overflow:auto"><div style="height:5000px">long</div></div></body></html>"""


def test_wait_type_scroll():
    pw = pytest.importorskip("playwright.async_api")
    ctx = SimpleNamespace(root=None, settings={}, permission_mode="full")

    async def go():
        async with pw.async_playwright() as p:
            try:
                b = await p.chromium.launch()
            except Exception as e:  # no browser installed on this machine
                pytest.skip(str(e))
            page = await b.new_page(viewport={"width": 800, "height": 600})
            await page.set_content(PAGE)
            old = (bt.AGENT.active, bt.AGENT.pages, bt.AGENT.ids)
            bt.AGENT.active, bt.AGENT.pages, bt.AGENT.ids = page, [page], {page: "t1"}
            try:
                out = {}
                out["sel"] = (await bt._wait(ctx, {"selector": ".ok", "timeout": 5}))[0]
                out["load"] = (await bt._wait(ctx, {"load": "load", "timeout": 5}))[0]
                await page.goto("data:text/html,<p>x</p>#/app/done")
                out["glob"] = (await bt._wait(ctx, {"url": "**/done", "timeout": 3}))[0]
                await page.set_content(PAGE)
                await page.focus("#f")
                out["type"] = (await bt._type(ctx, {"text": "merhaba"}))[0]
                out["value"] = await page.input_value("#f")
                out["scroll"] = (await bt._scroll(ctx, {"direction": "down", "amount": 2}))[0]
                out["y"] = await page.evaluate("scrollY")
                await page.set_content(PANEL)
                out["panel"] = (await bt._scroll(ctx, {"direction": "down"}))[0]
                out["panel_top"] = await page.evaluate("document.getElementById('p').scrollTop")
            finally:
                bt.AGENT.active, bt.AGENT.pages, bt.AGENT.ids = old
                await b.close()
            return out
    out = asyncio.run(go())
    assert out["sel"] == ".ok is visible"
    assert "load" in out["load"]
    assert out["glob"].startswith("address now")
    assert out["value"] == "merhaba" and "focused <input>" in out["type"]
    assert out["y"] > 0, out["scroll"]
    assert out["panel_top"] > 0 and "inside the panel" in out["panel"]
