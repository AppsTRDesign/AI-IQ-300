"""Machine translation for UI language files and catalog metadata (Google gtx endpoint, deep-translator fallback)."""
from __future__ import annotations

import re
import time

import httpx

from .config import LANG_DIR


def installed_languages() -> list[str]:
    return sorted(f.stem for f in LANG_DIR.glob("*.json"))


def plan_parts(texts: list[str], limit: int = 1800) -> list[list[int]]:
    """Split strings into parts of at most `limit` characters (one line per string). Small parts keep Google's line
    structure intact and let a long file show its progress part by part."""
    parts: list[list[int]] = [[]]
    size = 0
    for i, t in enumerate(texts):
        n = len(t) + 1
        if parts[-1] and size + n > limit:
            parts.append([])
            size = 0
        parts[-1].append(i)
        size += n
    return [p for p in parts if p]


def translate_parts(texts: list[str], target: str, source: str = "en", on_part=None, workers: int = 3) -> list[str]:
    """Translate part by part, a few parts at a time. on_part(index, state, error) reports each part
    ("running" / "done" / "failed"). A part that keeps failing keeps its source text, so the rest still lands."""
    from concurrent.futures import ThreadPoolExecutor

    parts = plan_parts(texts)
    out = list(texts)

    def run(k: int) -> None:
        idx = parts[k]
        if on_part:
            on_part(k, "running", "")
        try:
            res = translate_all([texts[i] for i in idx], target, source)
            for i, r in zip(idx, res):
                out[i] = r or texts[i]
            if on_part:
                on_part(k, "done", "")
        except Exception as e:  # noqa: BLE001
            if on_part:
                on_part(k, "failed", str(e)[:200])

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(run, range(len(parts))))
    return out


def translate_all(texts: list[str], target: str, source: str = "en") -> list[str]:
    """Translate in a few large requests (one line per string) instead of one request per string, which
    triggers Google's rate limit. Placeholders like {project} are protected. source="auto" detects the language."""

    def gtx(text: str) -> str:
        # deep-translator's /m endpoint now answers 302 (reported as TooManyRequests); the gtx API works.
        r = httpx.post("https://translate.googleapis.com/translate_a/single",
                       params={"client": "gtx", "sl": source, "tl": target, "dt": "t"}, data={"q": text}, timeout=30)
        r.raise_for_status()
        return "".join(seg[0] for seg in r.json()[0] if seg and seg[0])

    def call(text: str) -> str:
        for attempt in range(4):
            try:
                try:
                    return gtx(text)
                except (httpx.HTTPError, ValueError, IndexError, TypeError):
                    from deep_translator import GoogleTranslator
                    return GoogleTranslator(source=source, target=target).translate(text) or ""
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        return ""

    protected, slots = [], []
    for t in texts:
        found = re.findall(r"\{\w+\}", t)
        slots.append(found)
        for i, ph in enumerate(found):
            t = t.replace(ph, f"[{i}]")
        protected.append(t.replace("\n", " "))
    out: list[str] = []
    chunk: list[str] = []

    def flush():
        if not chunk:
            return
        res = call("\n".join(chunk)).split("\n")
        if len(res) != len(chunk):  # line structure lost: fall back to per-item for this chunk
            res = []
            for c in chunk:
                res.append(call(c))
                time.sleep(0.25)
        out.extend(r.strip() for r in res)
        chunk.clear()
        time.sleep(0.4)

    for t in protected:
        if chunk and sum(len(c) + 1 for c in chunk) + len(t) > 1800:
            flush()
        chunk.append(t)
    flush()
    for i, found in enumerate(slots):
        for j, ph in enumerate(found):
            out[i] = re.sub(rf"\[\s*{j}\s*\]", ph, out[i])
    return out
