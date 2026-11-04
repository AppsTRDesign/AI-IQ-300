"""Web research: search APIs (Google, Yandex, Bing, Brave, Tavily, SearXNG) when configured, then the free ddgs
metasearch library (Google, Yahoo, Bing, Yandex, Brave backends in parallel), Wikipedia/Wikidata and the built-in
keyless engines, and as the last resort the same search pages in a warm background browser; results fused across engines (reciprocal rank fusion), off-topic results dropped, engines that
answer with challenges or unrelated results rested for a while; page reading with a real-browser fallback for JS
pages, structured data (JSON-LD) extraction, an archived copy (Wayback Machine) for pages that cannot be read, and
parallel multi-source research.

Policy: this module does NOT try to defeat bot protection (no challenge solving, fingerprint spoofing or proxy
rotation). When a site blocks automated access, the result says so clearly so the agent uses other sources
instead of treating a block page as content.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from html import unescape
from pathlib import Path
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
class EngineBlocked(Exception):
    """The engine answered with a challenge or rate-limit page instead of results."""


def _check(r: httpx.Response, found: int) -> None:
    if not found and (r.status_code in (202, 403, 429, 503) or re.search(r"anomaly|captcha|challenge", r.text[:20000], re.I)):
        raise EngineBlocked(f"HTTP {r.status_code}")


async def _ddg(c: httpx.AsyncClient, q: str) -> list[dict]:
    r = await c.post("https://html.duckduckgo.com/html/", data={"q": q, "kl": "tr-tr"})
    out = []
    for block in re.findall(r'<div class="result results_links.*?</div>\s*</div>', r.text, re.S):
        m = re.search(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if m:
            out.append({"url": _clean_url(unescape(m.group(1))), "title": _strip(m.group(2)), "snippet": _strip(sn.group(1) if sn else "")})
    _check(r, len(out))
    return out


async def _ddg_lite(c: httpx.AsyncClient, q: str) -> list[dict]:
    r = await c.post("https://lite.duckduckgo.com/lite/", data={"q": q})
    links = re.findall(r"<a rel=\"nofollow\" href=\"([^\"]+)\" class='result-link'>(.*?)</a>", r.text, re.S)
    snips = re.findall(r"<td class='result-snippet'>(.*?)</td>", r.text, re.S)
    _check(r, len(links))
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
    _check(r, len(out))
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


DDGS_BACKENDS = ("google", "yahoo", "bing", "yandex", "brave")


def _ddgs_sync(q: str, backend: str) -> list[dict]:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException
    try:
        rows = DDGS(timeout=6).text(q, region="tr-tr", safesearch="moderate", max_results=10, backend=backend)
    except DDGSException as e:
        if "no results" in str(e).lower():
            return []
        raise
    out = [{"url": r.get("href", ""), "title": r.get("title", ""), "snippet": r.get("body", "")} for r in rows or []]
    # Some ddgs versions glue the following results' titles onto a title ("A | SiteB | SiteC..."): cut each title
    # where the next result's title starts.
    for cur, nxt in zip(out, out[1:]):
        head = nxt["title"][:25]
        if len(head) >= 12 and (at := cur["title"].find(head, 8)) > 0:
            cur["title"] = cur["title"][:at].rstrip(" -|·")
    for r in out:
        r["title"] = r["title"][:160]
    return out


async def _ddgs(q: str, backend: str) -> list[dict]:
    """ddgs (github.com/deedy5/ddgs): a free metasearch library; one backend per call, run in a worker thread."""
    return await asyncio.to_thread(_ddgs_sync, q, backend)


async def _wikidata(c: httpx.AsyncClient, q: str) -> list[dict]:
    """Entities (brands, products, places, people) with a one-line description."""
    r = await c.get("https://www.wikidata.org/w/api.php", headers={"User-Agent": HONEST_UA},
                    params={"action": "wbsearchentities", "search": q, "language": "tr", "uselang": "tr", "format": "json",
                            "limit": 4})
    return [{"url": f"https://www.wikidata.org/wiki/{x['id']}", "title": x.get("label", x["id"]),
             "snippet": x.get("description", "")} for x in r.json().get("search", [])]


async def _google(c: httpx.AsyncClient, q: str, key: str, cx: str) -> list[dict]:
    """Google Programmable Search (Custom Search JSON API): an API key and a search engine ID (cx)."""
    r = await c.get("https://www.googleapis.com/customsearch/v1", params={"key": key, "cx": cx, "q": q, "num": 10})
    r.raise_for_status()
    return [{"url": x["link"], "title": x.get("title", ""), "snippet": x.get("snippet", "")} for x in r.json().get("items", [])]


async def _yandex(c: httpx.AsyncClient, q: str, key: str, folder: str) -> list[dict]:
    """Yandex Search API (Yandex Cloud, v2): an API key and the cloud folder ID; the answer is base64 XML."""
    r = await c.post("https://searchapi.api.cloud.yandex.net/v2/web/search", headers={"Authorization": f"Api-Key {key}"},
                     json={"query": {"searchType": "SEARCH_TYPE_TR", "queryText": q}, "folderId": folder,
                           "responseFormat": "FORMAT_XML", "groupSpec": {"groupsOnPage": "10"}})
    r.raise_for_status()
    xml = base64.b64decode(r.json().get("rawData", "")).decode("utf-8", "replace")
    out = []
    for doc in re.findall(r"<doc\b.*?</doc>", xml, re.S):
        url = re.search(r"<url>(.*?)</url>", doc, re.S)
        title = re.search(r"<title>(.*?)</title>", doc, re.S)
        passage = re.search(r"<passage>(.*?)</passage>", doc, re.S) or re.search(r"<headline>(.*?)</headline>", doc, re.S)
        if url:
            out.append({"url": unescape(url.group(1)), "title": _strip(title.group(1) if title else ""),
                        "snippet": _strip(passage.group(1) if passage else "")})
    return out


async def _bing_api(c: httpx.AsyncClient, q: str, key: str) -> list[dict]:
    """Bing Web Search API v7 (Azure key). Microsoft stopped selling it in 2025; existing keys keep working."""
    r = await c.get("https://api.bing.microsoft.com/v7.0/search", params={"q": q, "count": 10, "mkt": "tr-TR"},
                    headers={"Ocp-Apim-Subscription-Key": key})
    r.raise_for_status()
    return [{"url": x["url"], "title": x.get("name", ""), "snippet": x.get("snippet", "")}
            for x in r.json().get("webPages", {}).get("value", [])]


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


def api_engines(query: str) -> list[tuple[str, object]]:
    """The search APIs the user configured (a key, plus an ID where the API needs one): these are used first."""
    cfg = load_settings().get("search", {})
    out = []
    if (key := get_secret("google_search_key")) and cfg.get("google_cx"):
        out.append(("google", lambda c: _google(c, query, key, cfg["google_cx"])))
    if (key := get_secret("yandex_search_key")) and cfg.get("yandex_folder"):
        out.append(("yandex", lambda c: _yandex(c, query, key, cfg["yandex_folder"])))
    if key := get_secret("bing_search_key"):
        out.append(("bing-api", lambda c: _bing_api(c, query, key)))
    if key := get_secret("brave_api_key"):
        out.append(("brave", lambda c: _brave(c, query, key)))
    if key := get_secret("tavily_api_key"):
        out.append(("tavily", lambda c: _tavily(c, query, key)))
    if cfg.get("searxng_url"):
        out.append(("searxng", lambda c: _searxng(c, query, cfg["searxng_url"])))
    return out


# An engine that answers with a challenge page or with results unrelated to the query (some engines do that to
# automated clients) is rested for a while instead of slowing every search down; it is tried again afterwards.
REST_SECONDS = 600
BLOCK_REST = 120
_RESTING: dict[str, float] = {}
_CACHE: dict[str, tuple[float, list[dict], list[str]]] = {}
CACHE_SECONDS = 600


async def _run(engines: list, query: str, report: dict, terms: set[str]) -> list[tuple[str, list[dict]]]:
    now = time.monotonic()
    live = []
    for name, fn in engines:
        if _RESTING.get(name, 0) > now:
            report[name] = "resting"
        else:
            live.append((name, fn))
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as c:
        got = await asyncio.gather(*(asyncio.wait_for(fn(c), 35 if n.startswith("browser") else 9 if n.startswith("ddgs")
                                                      else 15) for n, fn in live),
                                   return_exceptions=True)
    out = []
    for (name, _), res in zip(live, got):
        if isinstance(res, EngineBlocked):
            report[name] = "blocked"
            _RESTING[name] = now + BLOCK_REST  # usually a short rate limit
        elif isinstance(res, Exception):
            report[name] = "error: " + (str(res)[:120] or type(res).__name__)
        elif not res:
            report[name] = "empty"
        elif terms and sum(1 for r in res if _relevance(terms, r)) < max(1, len(res) * 0.3):
            report[name] = "off-topic"  # e.g. unrelated pages for every query: not trusted for a while
            if name in SCRAPERS:
                _RESTING[name] = now + REST_SECONDS
        else:
            report[name] = f"ok ({len(res)})"
            out.append((name, res))
    return out


SCRAPERS = {"duckduckgo", "bing", "browser-duckduckgo", "browser-bing", "browser-brave", *(f"ddgs-{b}" for b in DDGS_BACKENDS)}
_DDG_LOCK = asyncio.Lock()
_DDG_LAST = [0.0]
DDG_GAP = 2.0  # DuckDuckGo answers bursts with a challenge: searches are spaced out


async def _ddg_any(c: httpx.AsyncClient, q: str) -> list[dict]:
    """DuckDuckGo HTML, then its lite page if the first is refused; one search at a time, spaced out."""
    async with _DDG_LOCK:
        wait = _DDG_LAST[0] + DDG_GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await _ddg(c, q)
        except EngineBlocked:
            await asyncio.sleep(1)
            return await _ddg_lite(c, q)
        finally:
            _DDG_LAST[0] = time.monotonic()


async def search(query: str, limit: int = 8, report: dict | None = None) -> tuple[list[dict], list[str]]:
    """Configured search APIs first; the built-in keyless engines (and Wikipedia/Wikidata) when there are none or
    they found too little. Results are fused across engines: a page several engines return ranks higher, results
    that share no topic word with the query are dropped. report (optional) gets each engine's state."""
    report = {} if report is None else report
    q = re.sub(r"\s+", " ", query).strip()
    if (hit := _CACHE.get(q.lower())) and time.monotonic() - hit[0] < CACHE_SECONDS:
        report["cache"] = "hit"
        return hit[1][: limit * 2], hit[2]
    terms = _terms(q)
    free = [(f"ddgs-{b}", lambda c, b=b: _ddgs(q, b)) for b in DDGS_BACKENDS] + [
        ("wikipedia", lambda c: _wikipedia(c, q)), ("wikidata", lambda c: _wikidata(c, q))]
    scrapers = [("duckduckgo", lambda c: _ddg_any(c, q)), ("bing", lambda c: _bing(c, q))]
    apis = api_engines(q)
    # Configured APIs first: when they found enough, nothing else is asked (fast, and their quota is the user's choice).
    lists = await _run(apis, q, report, terms) if apis else []
    if sum(len(r) for _, r in lists) < 5:
        lists += await _run(free + scrapers, q, report, terms)
    else:
        lists += await _run(free[-2:], q, report, terms)  # Wikipedia/Wikidata always add reference pages
    merged = _fuse(lists, terms)
    if sum(1 for r in merged if not r["engines"][0].startswith("wiki")) < 4:
        # Still thin (APIs off or out of quota, fast engines refusing): the same search pages in the background
        # browser, which renders them like a normal visit. Challenges are never solved: such an engine is skipped.
        lists += await _run(BROWSER_ENGINES(q), q, report, terms)
        merged = _fuse(lists, terms)
    used = [n for n, _ in lists]
    if merged:
        _CACHE[q.lower()] = (time.monotonic(), merged, used)
        if len(_CACHE) > 300:
            _CACHE.pop(next(iter(_CACHE)))
    return merged[: limit * 2], used


def _fuse(lists: list[tuple[str, list[dict]]], terms: set[str]) -> list[dict]:
    """Reciprocal rank fusion (a page several engines return ranks higher), then the relevance gate."""
    fused: dict[str, dict] = {}
    for name, res in lists:
        for rank, r in enumerate(res):
            if not r.get("url", "").startswith("http"):
                continue
            key = re.sub(r"^https?://(www\.)?|/$", "", r["url"]).lower()
            item = fused.setdefault(key, {**r, "engine": name, "engines": [], "score": 0.0})
            if name in item["engines"]:
                continue
            item["score"] += 1 / (20 + rank)
            item["engines"].append(name)
            if len(r.get("snippet", "")) > len(item.get("snippet", "")):
                item["snippet"] = r["snippet"]
    merged = list(fused.values())
    if terms:
        need = 1 if len(terms) < 3 else 2
        best = max((_relevance(terms, r) for r in merged), default=0)
        merged = [r for r in merged if _relevance(terms, r) >= min(need, best) and best > 0]
        merged.sort(key=lambda r: (-min(_relevance(terms, r), need), -r["score"]))
    else:
        merged.sort(key=lambda r: -r["score"])
    return [{k: v for k, v in r.items() if k != "score"} for r in merged]


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


def structured_data(html: str) -> str:
    """Facts pages publish for search engines (JSON-LD): products with price and rating, places and businesses
    with address, phone and opening hours, articles with dates. Often the most exact part of a page."""
    lines = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I)[:6]:
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items[:8]:
            if not isinstance(it, dict):
                continue
            kind = it.get("@type")
            kind = ", ".join(kind) if isinstance(kind, list) else str(kind or "")
            if not re.search(r"Product|Offer|Place|Business|Restaurant|Store|Hotel|Organization|Event|Article|Review|"
                             r"Recipe|Car|Vehicle", kind):
                continue
            facts = [f"{kind}: {it.get('name') or it.get('headline') or ''}".strip()]
            for k in ("brand", "model", "sku", "description", "telephone", "priceRange", "servesCuisine",
                      "openingHours", "datePublished", "startDate", "url"):
                v = it.get(k)
                if isinstance(v, dict):
                    v = v.get("name")
                if v and not isinstance(v, (dict, list)):
                    facts.append(f"{k}: {str(v)[:200]}")
            if isinstance(addr := it.get("address"), dict):
                facts.append("address: " + ", ".join(str(addr[k]) for k in ("streetAddress", "addressLocality",
                                                                             "addressRegion", "postalCode") if addr.get(k)))
            offers = it.get("offers")
            for o in (offers if isinstance(offers, list) else [offers])[:3]:
                if isinstance(o, dict) and (o.get("price") or o.get("lowPrice")):
                    facts.append(f"price: {o.get('price') or o.get('lowPrice')} {o.get('priceCurrency', '')}".strip())
            if isinstance(rating := it.get("aggregateRating"), dict):
                facts.append(f"rating: {rating.get('ratingValue')} / {rating.get('bestRating', 5)} "
                             f"({rating.get('reviewCount') or rating.get('ratingCount') or '?'} reviews)")
            if isinstance(geo := it.get("geo"), dict) and geo.get("latitude"):
                facts.append(f"location: {geo.get('latitude')},{geo.get('longitude')}")
            lines.append("; ".join(facts))
    return "\n".join(lines[:12])


async def _archived(url: str) -> tuple[str, str]:
    """The latest Wayback Machine copy of a page (raw original HTML) and its date, or ("", "")."""
    raw, _, day = await _archived_raw(url)
    return (raw.decode("utf-8", "replace"), day) if raw else ("", "")


async def _archived_raw(url: str) -> tuple[bytes, str, str]:
    """The latest Wayback Machine copy as (bytes, content type, date), or (b"", "", "")."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": HONEST_UA}) as c:
            snap = (await c.get("https://archive.org/wayback/available", params={"url": url})).json()
            closest = (snap.get("archived_snapshots") or {}).get("closest") or {}
            if not closest.get("available"):
                return "", ""
            ts = closest["timestamp"]
            r = await c.get(re.sub(r"/web/(\d+)/", r"/web/\1id_/", closest["url"], count=1))
            if r.status_code < 400:
                return r.content, r.headers.get("content-type", ""), f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return b"", "", ""


def is_blocked(status: int, text: str) -> bool:
    head = text[:4000]
    return status in (401, 403, 429, 503) and bool(BLOCK_MARKERS.search(head)) or \
        (len(text) < 3000 and bool(BLOCK_MARKERS.search(head)))


class _WarmBrowser:
    """One headless Chromium kept running in the background while it is used (started on first need, closed
    after IDLE seconds without use), so a browser search or page render costs a page load, not a browser start.
    Images, media and fonts are not loaded (text only, much faster)."""
    IDLE = 300

    def __init__(self):
        self.lock = asyncio.Lock()
        self.pw = self.browser = None
        self.last = 0.0
        self.reaper: asyncio.Task | None = None

    async def context(self):
        async with self.lock:
            if not (self.browser and self.browser.is_connected()):
                from playwright.async_api import async_playwright
                self.pw = await async_playwright().start()
                self.browser = await self.pw.chromium.launch(headless=True)
            self.last = time.monotonic()
            if not self.reaper or self.reaper.done():
                self.reaper = asyncio.create_task(self._reap())
        ctx = await self.browser.new_context(user_agent=UA, locale="tr-TR", viewport={"width": 1280, "height": 900})
        await ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font")
                        else route.continue_())
        return ctx

    async def _reap(self):
        while True:
            await asyncio.sleep(30)
            async with self.lock:
                if time.monotonic() - self.last > self.IDLE and self.browser:
                    try:
                        await self.browser.close()
                        await self.pw.stop()
                    except Exception:
                        pass
                    self.pw = self.browser = None
                    return

    async def render(self, url: str, settle: float = 6) -> tuple[int, str, object]:
        """(status, html, context): the caller may read more from the page, then closes the context."""
        ctx = await self.context()
        page = await ctx.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        try:
            await page.wait_for_load_state("networkidle", timeout=settle * 1000)
        except Exception:
            pass
        self.last = time.monotonic()
        return (resp.status if resp else 0), await page.content(), ctx


BROWSER = _WarmBrowser()


async def _browser_fetch(url: str) -> tuple[int, str]:
    """Render with the background browser (for JS-built pages). Does not attempt to solve challenges."""
    status, html, ctx = await BROWSER.render(url)
    await ctx.close()
    return status, html


async def _browser_engine(url: str, item: str, title: str, snippet: str) -> list[dict]:
    """Results of a search page rendered in the background browser, read from its DOM."""
    status, html, ctx = await BROWSER.render(url, settle=4)
    try:
        page = ctx.pages[0]
        rows = await page.eval_on_selector_all(item, """(els, sel) => els.map(e => {
            const a = e.querySelector(sel[0]); const s = e.querySelector(sel[1]);
            return a ? {url: a.href, title: a.innerText.trim(), snippet: s ? s.innerText.trim() : ""} : null;
        }).filter(Boolean)""", [title, snippet])
    finally:
        await ctx.close()
    out = [{**r, "url": _clean_url(r["url"])} for r in rows if r["url"].startswith("http")]
    if not out and (status in (202, 403, 429) or BLOCK_MARKERS.search(html[:20000])
                    or re.search(r"anomaly|home-error", html[:200000])):
        raise EngineBlocked(f"HTTP {status}")
    return out[:10]


def BROWSER_ENGINES(q: str) -> list:  # noqa: N802 (a list factory, like api_engines)
    k = quote_plus(q)
    return [
        ("browser-duckduckgo", lambda c: _browser_engine(f"https://duckduckgo.com/?q={k}&kl=tr-tr&ia=web",
                                                         "article[data-testid=result]", "a[data-testid=result-title-a]",
                                                         "[data-result=snippet]")),
        ("browser-bing", lambda c: _browser_engine(f"https://www.bing.com/search?q={k}&setlang=tr", "li.b_algo",
                                                   "h2 a", ".b_caption p, p")),
        ("browser-brave", lambda c: _browser_engine(f"https://search.brave.com/search?q={k}&source=web",
                                                    "div.snippet[data-type=web]", ".result-content a, a",
                                                    ".snippet-description, .generic-snippet, .content")),
    ]


DOC_TYPES = re.compile(r"pdf|msword|officedocument|opendocument|ms-excel|ms-powerpoint|text/csv|"
                       r"tab-separated|rtf|image/(png|jpe?g|tiff|bmp|webp)", re.I)
MAX_DOC_BYTES = 40_000_000


async def read_doc_bytes(data: bytes, name: str, query: str = "", max_chars: int = 14000) -> tuple[str, str]:
    """A downloaded document as page-labelled text (OCR for scans), plus its title."""
    from . import docread
    doc = await asyncio.to_thread(docread.extract, data, name)
    return docread.render(doc, query, budget=max_chars)[:max_chars], doc.title


async def fetch(url: str, max_chars: int = 8000, query: str = "") -> dict:
    """Returns {ok, url, title, text, blocked, via, status}. Documents (PDF, Word, Excel, PowerPoint, OpenDocument,
    CSV, images) are read with page numbers; query picks the matching passages of a long document."""
    if not re.match(r"https?://", url):
        return {"ok": False, "url": url, "error": "Only http(s) URLs are supported"}
    status, html, via = 0, "", "http"
    from .docread import DOC_EXTS
    ext = Path(urlparse(url).path).suffix.lower()
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers_for(url)) as c:
            r = await c.get(url)
            status, html = r.status_code, r.text
            ctype = r.headers.get("content-type", "")
            if status < 400 and (DOC_TYPES.search(ctype) or (ext in DOC_EXTS and "html" not in ctype)):
                if len(r.content) > MAX_DOC_BYTES:
                    return {"ok": False, "url": url, "status": status, "error": "Document too large (over 40 MB)"}
                name = Path(urlparse(str(r.url)).path).name or "document"
                if "." not in name:  # no extension in the URL: take it from the content type
                    name += next((e for k, e in (("pdf", ".pdf"), ("wordprocessingml", ".docx"), ("spreadsheetml", ".xlsx"),
                                                  ("presentationml", ".pptx"), ("opendocument.text", ".odt"),
                                                  ("opendocument.spreadsheet", ".ods"), ("opendocument.presentation", ".odp"),
                                                  ("csv", ".csv"), ("png", ".png"), ("jpeg", ".jpg")) if k in ctype), "")
                try:
                    text, title = await read_doc_bytes(r.content, name, query, max(max_chars, 6000))
                except Exception as e:
                    return {"ok": False, "url": url, "status": status, "error": f"Document not readable: {str(e)[:200]}"}
                return {"ok": bool(text.strip()), "url": str(r.url), "title": title or name, "text": text, "via": "document",
                        "status": status, "blocked": False}
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
    blocked = bool(html and is_blocked(status, html))
    if (blocked or not text or status >= 400) and (ext in DOC_EXTS and ext not in (".html", ".htm", ".xml", ".txt")):
        # A document that cannot be downloaded live: its archived copy, read as a document and clearly dated.
        raw, ctype, day = await _archived_raw(url)
        if raw and (raw[:5] == b"%PDF-" or DOC_TYPES.search(ctype) or not raw.lstrip()[:1] == b"<"):
            try:
                text, title = await read_doc_bytes(raw, Path(urlparse(url).path).name, query, max(max_chars, 6000))
                return {"ok": True, "url": url, "status": 200, "title": title, "via": "archive", "blocked": False,
                        "archived": day, "text": f"[Archived copy from {day} (web.archive.org); the live document could "
                                                 f"not be read]\n{text}"}
            except Exception:
                pass
    if blocked or not text or status >= 400:
        # The live page cannot be read (blocked, gone, empty): the latest archived copy, clearly dated.
        old, day = await _archived(url)
        t3, x3 = html_to_text(old) if old else ("", "")
        if len(x3) >= 200:
            facts = structured_data(old)
            return {"ok": True, "url": url, "status": 200, "title": t3, "via": "archive", "blocked": False, "archived": day,
                    "text": (f"[Archived copy from {day} (web.archive.org); the live page could not be read]\n"
                             + (f"[Structured data]\n{facts}\n\n" if facts else "") + x3)[:max_chars]}
    if blocked:
        return {"ok": False, "blocked": True, "url": url, "status": status, "via": via,
                "error": "BLOCKED: this site's bot protection refused automated access and no archived copy exists. "
                         "Do not retry this URL; use other sources (search snippets, other sites, official APIs) and "
                         "say the site could not be read."}
    if not text:
        return {"ok": False, "url": url, "status": status, "error": err or f"No readable content (HTTP {status})"}
    facts = structured_data(html)
    meta = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{40,400})', html, re.I)
    head = (f"[Structured data]\n{facts}\n\n" if facts else "") + (f"{unescape(meta.group(1))}\n\n" if meta else "")
    return {"ok": status < 400, "url": url, "status": status, "title": title, "text": (head + text)[:max_chars], "via": via,
            "blocked": False}


async def research(query: str, sources: int = 4) -> dict:
    """Search, then read the top non-blocked sources in parallel; returns excerpts with their URLs."""
    results, engines = await search(query, limit=10)
    picked, pages = [], []
    # Documents (PDF, Office, OpenDocument, CSV) are sources too: their passages about the question come with page numbers.
    candidates = [r for r in results if not re.search(r"\.(zip|rar|7z|exe|msi|dmg|iso)(\?|$)", r["url"], re.I)]
    fetched = await asyncio.gather(*(fetch(r["url"], 3500, query) for r in candidates[: sources + 3]), return_exceptions=True)
    for r, f in zip(candidates, fetched):
        if isinstance(f, dict) and f.get("ok") and len(pages) < sources:
            pages.append({"url": r["url"], "title": f.get("title") or r["title"], "excerpt": f["text"]})
        elif isinstance(f, dict) and f.get("blocked"):
            picked.append(r["url"])
    return {"query": query, "engines": engines, "results": results[:10], "pages": pages, "blocked": picked}
