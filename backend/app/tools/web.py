"""Web research: multi-engine search, page reading with a real-browser fallback for JS pages, block-page detection,
and parallel multi-source research.

Policy: this module does NOT try to defeat bot protection (no challenge solving, fingerprint spoofing or proxy
rotation). When a site blocks automated access, the result says so clearly so the agent uses other sources
instead of treating a block page as content.
"""
from __future__ import annotations

import asyncio
import base64
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from ..config import get_secret, load_settings

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}
# Sites whose published robot policy asks for an honest, identifying User-Agent (Wikimedia).
HONEST_UA = "AI-IQ-300/0.3 (local research assistant; https://github.com/AppsTRDesign)"
HONEST_DOMAINS = re.compile(r"(^|\.)(wikipedia|wikimedia|wikidata|wiktionary)\.org$", re.I)


def headers_for(url: str) -> dict:
    host = urlparse(url).hostname or ""
    return {**HEADERS, "User-Agent": HONEST_UA} if HONEST_DOMAINS.search(host) else HEADERS


BLOCK_MARKERS = re.compile(
    r"attention required|just a moment\.\.\.|cf-chl|cf_chl|enable javascript and cookies|checking your browser|"
    r"sorry, you have been blocked|access denied|captcha|are you a robot|unusual traffic|request blocked|"
    r"ddos protection|perimeterx|datadome", re.I)


def _strip(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _clean_url(u: str) -> str:
    if "duckduckgo.com/l/" in u:  # DDG redirect wrapper
        q = parse_qs(urlparse(u if u.startswith("http") else "https:" + u).query)
        return unquote(q.get("uddg", [u])[0])
    if "bing.com/ck/a" in u:  # Bing click tracker: u=a1<base64url of the real URL>
        enc = parse_qs(urlparse(u).query).get("u", [""])[0]
        if enc.startswith("a1"):
            try:
                real = base64.urlsafe_b64decode(enc[2:] + "=" * (-len(enc[2:]) % 4)).decode()
                if real.startswith("http"):
                    return real
            except (ValueError, UnicodeDecodeError):
                pass
    return u


STOP_WORDS = {"ve", "ile", "için", "bir", "en", "the", "and", "for", "of", "in", "a", "to", "nasıl", "nedir", "how", "what"}


def _terms(text: str) -> set[str]:
    """Meaningful query words (numbers such as years are not topic words)."""
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 1 and not w.isdigit() and w not in STOP_WORDS}


def _relevance(query_terms: set[str], r: dict) -> int:
    hay = f"{r['title']} {r['snippet']} {r['url']}".lower()
    return sum(1 for w in query_terms if w in hay or (len(w) > 4 and w[:5] in hay))  # stem match: tarifi ~ tarif


# ------------------------------------------------------------------ search engines
async def _ddg(c: httpx.AsyncClient, q: str) -> list[dict]:
    r = await c.post("https://html.duckduckgo.com/html/", data={"q": q, "kl": "tr-tr"})
    out = []
    for block in re.findall(r'<div class="result results_links.*?</div>\s*</div>', r.text, re.S):
        m = re.search(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if m:
            out.append({"url": _clean_url(unescape(m.group(1))), "title": _strip(m.group(2)), "snippet": _strip(sn.group(1) if sn else "")})
    return out


async def _ddg_lite(c: httpx.AsyncClient, q: str) -> list[dict]:
    r = await c.post("https://lite.duckduckgo.com/lite/", data={"q": q})
    links = re.findall(r"<a rel=\"nofollow\" href=\"([^\"]+)\" class='result-link'>(.*?)</a>", r.text, re.S)
    snips = re.findall(r"<td class='result-snippet'>(.*?)</td>", r.text, re.S)
    return [{"url": _clean_url(unescape(u)), "title": _strip(t), "snippet": _strip(snips[i]) if i < len(snips) else ""}
            for i, (u, t) in enumerate(links)]


async def _bing(c: httpx.AsyncClient, q: str) -> list[dict]:
    r = await c.get(f"https://www.bing.com/search?q={quote_plus(q)}&setlang=tr")
    out = []
    for li in re.findall(r'<li class="b_algo".*?</li>', r.text, re.S):
        m = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
        sn = re.search(r"<p[^>]*>(.*?)</p>", li, re.S)
        if m and m.group(1).startswith("http"):
            out.append({"url": _clean_url(unescape(m.group(1))), "title": _strip(m.group(2)), "snippet": _strip(sn.group(1) if sn else "")})
    return out


async def _wikipedia(c: httpx.AsyncClient, q: str) -> list[dict]:
    out = []
    for lang in ("tr", "en"):
        r = await c.get(f"https://{lang}.wikipedia.org/w/api.php", headers={"User-Agent": HONEST_UA},
                        params={"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 3})
        for it in r.json().get("query", {}).get("search", []):
            out.append({"url": f"https://{lang}.wikipedia.org/wiki/{quote_plus(it['title'].replace(' ', '_'))}",
                        "title": it["title"], "snippet": _strip(it.get("snippet"))})
    return out


async def _brave(c: httpx.AsyncClient, q: str, key: str) -> list[dict]:
    r = await c.get("https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": 10},
                    headers={"X-Subscription-Token": key, "Accept": "application/json"})
    r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title", ""), "snippet": _strip(x.get("description"))}
            for x in r.json().get("web", {}).get("results", [])]


async def _tavily(c: httpx.AsyncClient, q: str, key: str) -> list[dict]:
    r = await c.post("https://api.tavily.com/search", json={"api_key": key, "query": q, "max_results": 10})
    r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", "")[:400]} for x in r.json().get("results", [])]


async def _searxng(c: httpx.AsyncClient, q: str, base: str) -> list[dict]:
    r = await c.get(f"{base.rstrip('/')}/search", params={"q": q, "format": "json"})
    r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", "")} for x in r.json().get("results", [])]


async def search(query: str, limit: int = 8) -> tuple[list[dict], list[str]]:
    """Configured search APIs first (most reliable), then free engines in parallel; results merged and de-duplicated."""
    cfg = load_settings().get("search", {})
    engines = []
    if key := get_secret("brave_api_key"):
        engines.append(("brave", lambda c: _brave(c, query, key)))
    if key := get_secret("tavily_api_key"):
        engines.append(("tavily", lambda c: _tavily(c, query, key)))
    if cfg.get("searxng_url"):
        engines.append(("searxng", lambda c: _searxng(c, query, cfg["searxng_url"])))
    engines += [("duckduckgo", lambda c: _ddg(c, query)), ("bing", lambda c: _bing(c, query)),
                ("duckduckgo-lite", lambda c: _ddg_lite(c, query)), ("wikipedia", lambda c: _wikipedia(c, query))]
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as c:
        results = await asyncio.gather(*(fn(c) for _, fn in engines), return_exceptions=True)
    merged, seen, used = [], set(), []
    for (name, _), res in zip(engines, results):
        if isinstance(res, Exception) or not res:
            continue
        used.append(name)
        for r in res:
            key = re.sub(r"^https?://(www\.)?|/$", "", r["url"])
            if key not in seen and r["url"].startswith("http"):
                seen.add(key)
                merged.append({**r, "engine": name})
    # Off-topic hits (e.g. "2026 calendar" for "2026 cake recipes") are dropped: a result must share at least
    # one topic word with the query when any result does; the rest keep engine order, best matches first.
    terms = _terms(query)
    if terms:
        scored = [(_relevance(terms, r), i, r) for i, r in enumerate(merged)]
        if any(s for s, _, _ in scored):
            need = 1 if len(terms) < 3 else 2
            best = max(s for s, _, _ in scored)
            merged = [r for s, i, r in sorted(scored, key=lambda x: (-min(x[0], need), x[1])) if s >= min(need, best)]
    return merged[: limit * 2], used


# ------------------------------------------------------------------ page reading
def html_to_text(html: str) -> tuple[str, str]:
    title = _strip((re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I) or [None, ""])[1])
    body = html
    for tag in ("article", "main"):
        m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, re.S | re.I)
        if m and len(m.group(1)) > 500:
            body = m.group(1)
            break
    body = re.sub(r"<(script|style|noscript|svg|nav|footer|header|form|iframe)\b[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<(br|/p|/div|/li|/h\d|/tr)\b[^>]*>", "\n", body, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return title, text


def is_blocked(status: int, text: str) -> bool:
    head = text[:4000]
    return status in (401, 403, 429, 503) and bool(BLOCK_MARKERS.search(head)) or \
        (len(text) < 3000 and bool(BLOCK_MARKERS.search(head)))


async def _browser_fetch(url: str) -> tuple[int, str]:
    """Render with a real headless browser (for JS-built pages). Does not attempt to solve challenges."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        try:
            page = await b.new_page(user_agent=UA, locale="tr-TR")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            try:
                await page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            return (resp.status if resp else 0), await page.content()
        finally:
            await b.close()


async def fetch(url: str, max_chars: int = 8000) -> dict:
    """Returns {ok, url, title, text, blocked, via, status}."""
    if not re.match(r"https?://", url):
        return {"ok": False, "url": url, "error": "Only http(s) URLs are supported"}
    status, html, via = 0, "", "http"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers_for(url)) as c:
            r = await c.get(url)
            status, html = r.status_code, r.text
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype and ctype:
                text = r.text if ctype.startswith("text") or "json" in ctype else ""
                return {"ok": r.status_code < 400 and bool(text), "url": str(r.url), "title": "", "text": text[:max_chars],
                        "via": "http", "status": status, "blocked": False,
                        **({} if text else {"error": f"Binary content ({ctype}); not readable as text"})}
    except httpx.HTTPError as e:
        html, status = "", 0
        err = str(e)
    else:
        err = ""
    title, text = html_to_text(html) if html else ("", "")
    # Thin, script-built or blocked pages: try a real browser render once.
    if not html or is_blocked(status, html) or len(text) < 400:
        try:
            status2, html2 = await asyncio.wait_for(_browser_fetch(url), 40)
            t2, x2 = html_to_text(html2)
            if len(x2) > len(text) and not is_blocked(status2, html2):
                status, html, title, text, via = status2, html2, t2, x2, "browser"
            elif is_blocked(status2, html2):
                status, html, via = status2, html2, "browser"
        except Exception as e:
            err = err or str(e)
    if html and is_blocked(status, html):
        return {"ok": False, "blocked": True, "url": url, "status": status, "via": via,
                "error": "BLOCKED: this site's bot protection refused automated access. Do not retry this URL; "
                         "use other sources (search snippets, other sites, official APIs) and say the site could not be read."}
    if not text:
        return {"ok": False, "url": url, "status": status, "error": err or f"No readable content (HTTP {status})"}
    return {"ok": status < 400, "url": url, "status": status, "title": title, "text": text[:max_chars], "via": via,
            "blocked": False}


async def research(query: str, sources: int = 4) -> dict:
    """Search, then read the top non-blocked sources in parallel; returns excerpts with their URLs."""
    results, engines = await search(query, limit=10)
    picked, pages = [], []
    candidates = [r for r in results if not re.search(r"\.(pdf|zip|exe)(\?|$)", r["url"], re.I)]
    fetched = await asyncio.gather(*(fetch(r["url"], 3500) for r in candidates[: sources + 3]), return_exceptions=True)
    for r, f in zip(candidates, fetched):
        if isinstance(f, dict) and f.get("ok") and len(pages) < sources:
            pages.append({"url": r["url"], "title": f.get("title") or r["title"], "excerpt": f["text"]})
        elif isinstance(f, dict) and f.get("blocked"):
            picked.append(r["url"])
    return {"query": query, "engines": engines, "results": results[:10], "pages": pages, "blocked": picked}
