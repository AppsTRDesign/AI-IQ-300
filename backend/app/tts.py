"""Spoken replies with Microsoft's online neural voices (edge-tts): free, no key, each voice labelled female/male.
The text to read is sent to Microsoft's read-aloud service; the browser's offline voices stay as the fallback."""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict

_VOICES: tuple[float, list[dict]] | None = None
_AUDIO: OrderedDict[str, bytes] = OrderedDict()  # recent sentences, so "read again" is instant
AUDIO_CACHE = 200
SPEAKABLE = re.compile(r"\w", re.U)


class TTSError(Exception):
    pass


def _name(v: dict) -> str:
    # "Microsoft Emel Online (Natural) - Turkish (Turkey)" -> "Emel"; multilingual voices keep their suffix
    short = v["ShortName"].split("-", 2)[-1].removesuffix("Neural")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", short)


async def voices(lang: str = "") -> list[dict]:
    """[{id, name, gender: female|male, locale}] for a language code ('tr', 'en'...), cached for a day."""
    global _VOICES
    try:
        import edge_tts
    except ImportError as e:
        raise TTSError("edge-tts is not installed (run install.bat / install.sh)") from e
    if not _VOICES or time.time() - _VOICES[0] > 86400:
        try:
            raw = await asyncio.wait_for(edge_tts.list_voices(), 15)
        except Exception as e:  # offline, blocked
            raise TTSError(f"voice list unavailable: {e}") from e
        _VOICES = (time.time(), [{"id": v["ShortName"], "name": _name(v), "gender": v["Gender"].lower(),
                                  "locale": v["Locale"]} for v in raw])
    lang = lang.lower()
    out = [v for v in _VOICES[1] if not lang or v["locale"].lower().split("-")[0] == lang]
    return sorted(out, key=lambda v: (v["locale"], v["gender"], v["name"]))


def rate_of(rate: float) -> str:
    return f"{round((max(0.5, min(2.0, rate)) - 1) * 100):+d}%"


async def synthesize(text: str, voice: str, rate: float = 1.0) -> bytes:
    """MP3 bytes for one piece of text (a sentence or a few)."""
    text = text.strip()[:3000]
    if not SPEAKABLE.search(text):
        raise TTSError("nothing to read")
    if not re.fullmatch(r"[a-z]{2,3}-[A-Za-z0-9-]+Neural", voice or ""):
        raise TTSError("unknown voice")
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()
    if key in _AUDIO:
        _AUDIO.move_to_end(key)
        return _AUDIO[key]
    import edge_tts
    data = bytearray()
    for attempt in (1, 2):  # the service sometimes drops one request
        try:
            async for chunk in edge_tts.Communicate(text, voice, rate=rate_of(rate)).stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            break
        except Exception as e:
            data.clear()
            if attempt == 2:
                raise TTSError(f"speech service failed: {type(e).__name__}") from e
    _AUDIO[key] = bytes(data)
    while len(_AUDIO) > AUDIO_CACHE:
        _AUDIO.popitem(last=False)
    return _AUDIO[key]
