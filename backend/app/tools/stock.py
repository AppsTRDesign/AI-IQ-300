"""Free stock photos for pages the model builds: searched on Openverse (CC-licensed, no key), with Wikimedia Commons as
the second source, downloaded into the working folder and resized, so a page shows real images that never break
(no hotlinks) and every image has its credit."""
from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path

import httpx

UA = "AI-IQ-300/0.10 (local assistant; image search)"
MAX_W = 1600


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "image"


def _photo_name(query: str, i: int) -> str:
    """latte-art.jpg, latte-art-2.jpg...: the first photo has the plain name a model expects (models wrote
    images/latte-art.jpg while the file was latte-art-1.jpg, and the page showed broken images)."""
    return f"{_slug(query)}.jpg" if i == 0 else f"{_slug(query)}-{i + 1}.jpg"


STOP = {"a", "an", "the", "of", "in", "on", "with", "and", "for", "at", "to", "photo", "image", "picture", "shop",
        "store", "products", "product"}


def _words(q: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", q.lower()) if w not in STOP}


def _score(item: dict, words: set[str]) -> float:
    """How many of the query's words the photo's title and tags name (search engines also match the description
    or the uploader's album, which gave a muffin for "coffee shop products")."""
    if not words:
        return 1.0
    text = (item.get("title", "") + " " + " ".join(item.get("tags") or [])).lower()
    return sum(1 for w in words if w in text) / len(words)


async def _english(q: str) -> str:
    """Photo libraries are tagged in English: a query in another language is translated first."""
    if not re.search(r"[^\x00-\x7f]", q) and not re.search(r"\b(ve|ile|bir|için|kahve|dükkan|içi)\b", q, re.I):
        return q
    try:
        r = await asyncio.to_thread(httpx.post, "https://translate.googleapis.com/translate_a/single",
                                    params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t"}, data={"q": q},
                                    timeout=10)
        return "".join(seg[0] for seg in r.json()[0] if seg and seg[0]).strip() or q
    except Exception:
        return q


async def _openverse(c: httpx.AsyncClient, q: str, n: int, wide: bool) -> list[dict]:
    params = {"q": q, "page_size": 20,  # the most an anonymous request may ask for "license_type": "commercial,modification", "mature": "false",
              "category": "photograph"}
    if wide:
        params["aspect_ratio"] = "wide"
    r = await c.get("https://api.openverse.org/v1/images/", params=params)
    r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title") or q, "author": x.get("creator") or "unknown",
             "license": (("" if x.get("license", "").lower() in ("cc0", "pdm") else "CC ")
                         + f"{x.get('license', '').upper()} {x.get('license_version') or ''}").strip(),
             "source": x.get("foreign_landing_url") or x["url"], "tags": [t.get("name", "") for t in x.get("tags") or []]}
            for x in r.json().get("results", []) if x.get("url") and (x.get("width") or 1000) >= 800]


async def _commons(c: httpx.AsyncClient, q: str, n: int, wide: bool) -> list[dict]:
    r = await c.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": max(n * 3, 10),
        "gsrsearch": f"{q} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": MAX_W})
    r.raise_for_status()
    out = []
    for p in (r.json().get("query") or {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        w, h = ii.get("width") or 0, ii.get("height") or 1
        if not ii.get("thumburl") or w < 800 or (wide and w / h < 1.2):
            continue
        author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "unknown")).strip()[:80]
        out.append({"url": ii["thumburl"], "title": p.get("title", q).removeprefix("File:"), "author": author,
                    "license": (meta.get("LicenseShortName") or {}).get("value", "see source"),
                    "source": ii.get("descriptionurl") or ii["thumburl"]})
    return out


def _save(data: bytes, target: Path) -> tuple[int, int]:
    """Re-encoded as a web-sized JPEG (a 6000 px original would make the page slow)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, "JPEG", quality=84, optimize=True, progressive=True)
    return im.width, im.height


async def find(query: str, folder: Path, n: int = 3, wide: bool = True) -> list[dict]:
    """Up to n downloaded photos: [{path, width, height, title, author, license, source}]. Several subjects in one
    query ("coffee shop interior, coffee cup, latte art") are searched one by one (together they matched nothing),
    at least one photo each."""
    n = max(1, min(int(n or 3), 8))
    parts = [p.strip() for p in re.split(r"[,;|\n]+|\s+(?:ve|and)\s+", query) if p.strip()]
    if len(parts) > 1:
        each = max(1, n // len(parts))
        found = await asyncio.gather(*(_find_one(p, folder, each, wide) for p in parts[:8]))
        return [x for group in found for x in group]
    return await _find_one(query, folder, n, wide)


def _simpler(query: str) -> list[str]:
    """Shorter versions of a query, most specific first: a long descriptive query ("pour over coffee brewing barista
    hands") matched nothing, while its core ("pour over coffee", "coffee brewing") has many photos."""
    w = [x for x in re.findall(r"[a-z]+", query.lower()) if x not in STOP or x in ("shop", "store")]
    out = []
    for cand in (w[:3], w[-2:], w[:2], w[1:3], w[-1:], w[:1]):
        q = " ".join(cand)
        if q and q != query.lower() and q not in out:
            out.append(q)
    return out


def _cache_dir() -> Path:
    from ..config import DATA_DIR
    return DATA_DIR / "stock_cache"


def _from_cache(query: str, folder: Path, n: int, wide: bool) -> list[dict] | None:
    """Photos found before for the same query: copied at once (no search, no download)."""
    import json
    import shutil
    meta = _cache_dir() / f"{_slug(query)}-{int(wide)}.json"
    try:
        items = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    items = [x for x in items if (_cache_dir() / x["file"]).is_file()]
    if len(items) < n:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i, x in enumerate(items[:n]):
        target = folder / _photo_name(query, i)
        shutil.copyfile(_cache_dir() / x["file"], target)
        out.append({**{k: v for k, v in x.items() if k != "file"}, "path": target})
    return out


def _to_cache(query: str, wide: bool, got: list[dict]) -> None:
    import json
    import shutil
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        items = []
        for i, g in enumerate(got):
            name = f"{_slug(query)}-{int(wide)}-{i + 1}.jpg"
            shutil.copyfile(g["path"], d / name)
            items.append({**{k: v for k, v in g.items() if k not in ("path", "tags")}, "file": name})
        (d / f"{_slug(query)}-{int(wide)}.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


async def _find_one(query: str, folder: Path, n: int, wide: bool) -> list[dict]:
    query = await _english(query)
    if cached := _from_cache(query, folder, n, wide):
        return cached
    try:  # a slow photo host never holds the task: what arrived in time is used
        got = await asyncio.wait_for(_find_fresh(query, folder, n, wide), 30)
    except asyncio.TimeoutError:
        got = []
    if got:
        _to_cache(query, wide, got)
    return got


async def _find_fresh(query: str, folder: Path, n: int, wide: bool) -> list[dict]:
    got = await _search(query, folder, n, wide)
    for q in _simpler(query):  # nothing (or too little) for the whole phrase: its core words
        if len(got) >= n:
            break
        got += await _search(q, folder, n - len(got), wide, offset=len(got) + 1, name=query)
    if not got and wide:  # the last resort: any aspect ratio
        got = await _search(query, folder, n, False, offset=99, name=query)
    # Final names in order: <query>-1.jpg, -2.jpg... (the searches saved under temporary names)
    for i, g in enumerate(got):
        final = folder / _photo_name(query, i)
        if g["path"] != final:
            g["path"].replace(final)
            g["path"] = final
    return got


async def _search(query: str, folder: Path, n: int, wide: bool, offset: int = 0, name: str = "") -> list[dict]:
    words = _words(query)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as c:
        found: list[dict] = []
        for source in (_openverse, _commons):
            try:
                got = await source(c, query, n, wide)
            except (httpx.HTTPError, ValueError, KeyError):
                continue
            # The most relevant first (stable: the engine's own order breaks ties); photos naming none of the
            # query's words are dropped.
            found += sorted((x for x in got if _score(x, words) > 0), key=lambda x: -_score(x, words))
            if len(found) >= n * 2:
                break

        async def get(item: dict, i: int) -> dict | None:
            try:
                r = await c.get(item["url"])
                if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                    return None
                target = folder / f".{_slug(name or query)}-{offset}-{i}.tmp.jpg"
                w, h = await asyncio.to_thread(_save, r.content, target)
                return {**item, "path": target, "width": w, "height": h}
            except Exception:  # a broken or unsupported file: the next candidate is used
                return None

        done: list[dict] = []
        for start in range(0, len(found), n):  # one small batch at a time until n images are saved
            batch = await asyncio.gather(*(get(x, start + k) for k, x in enumerate(found[start:start + n])))
            done += [b for b in batch if b]
            if len(done) >= n:
                break
        for extra in done[n:]:  # saved in the same batch but not needed
            extra["path"].unlink(missing_ok=True)
        return done[:n]
