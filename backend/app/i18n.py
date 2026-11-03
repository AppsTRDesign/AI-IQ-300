"""Machine translation for UI language files and catalog metadata (Google gtx endpoint, deep-translator fallback)."""
from __future__ import annotations

import re
import time

import httpx

from .config import LANG_DIR


def installed_languages() -> list[str]:
    return sorted(f.stem for f in LANG_DIR.glob("*.json"))


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
        if sum(len(c) + 1 for c in chunk) + len(t) > 3500:
            flush()
        chunk.append(t)
    flush()
    for i, found in enumerate(slots):
        for j, ph in enumerate(found):
            out[i] = re.sub(rf"\[\s*{j}\s*\]", ph, out[i])
    return out
