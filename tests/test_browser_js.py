"""browser_inspect what=js runs code the way a console does: expressions in parentheses, several statements, arrow
functions, object literals, top-level let/const of the page; a name hidden in a closure is reported with the page's
globals. Run: python -m pytest tests/test_browser_js.py"""
import asyncio

import pytest

from app.tools.browser_tools import JS_RESULT, JS_RUN

PAGE = ("<html><body><div id=a>hi</div><script>var S = {mode: 'menu', dist: 3}; let L = 7; const C = [1, 2];"
        "(function(){ var hidden = 1; })();</script></body></html>")
CASES = {
    "(S.mode)": "menu",
    "S.mode": "menu",
    "() => S.dist + 1": 4,
    "async () => { await new Promise(r => setTimeout(r, 10)); return L; }": 7,
    "const p = S; p.mode + ',' + p.dist": "menu,3",
    "{a: 1}": {"a": 1},
    "C.length // two items": 2,
    "function f() { return 'x'; }": "x",
    "document.querySelector('#a').textContent": "hi",
    "[1, 2].map((x) => x * 2)": [2, 4],
    "return S.mode": "menu",  # a function body sent as code (was: Illegal return statement)
    "const x = 2;\nreturn x * L;": 14,
    "await Promise.resolve(5)": 5,
    "const r = await Promise.resolve(L); return r + 1;": 8,
}


def test_console_like_evaluation():
    pw = pytest.importorskip("playwright.async_api")

    async def go():
        async with pw.async_playwright() as p:
            try:
                b = await p.chromium.launch()
            except Exception as e:  # no browser installed on this machine
                pytest.skip(str(e))
            page = await b.new_page()
            await page.set_content(PAGE)
            got = {c: await page.evaluate("(c) => (" + JS_RESULT + ")(" + JS_RUN + ")", c) for c in CASES}
            with pytest.raises(Exception, match="hidden is not defined"):
                await page.evaluate("(c) => (" + JS_RESULT + ")(" + JS_RUN + ")", "hidden + 1")
            await b.close()
            return got
    got = asyncio.run(go())
    assert got == CASES
