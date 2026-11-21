"""Text -> a finished recording: sentences, natural pauses, the studio finish, subtitle timings, several speakers,
and the fallback order (the chosen voice; when it fails, the next voice of the same language and gender).

render(text, target, voice=..., lang=..., gender=..., rate, pitch, emotion, pause, studio, room, speakers, srt)"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import numpy as np

from ..config import load_settings
from . import catalog, engines, studio

SENT = re.compile(r"(?<=[.!?…:;])\s+|\n+")
DIALOG = re.compile(r"^\s*\[?([^\]\n:]{1,24})\]?\s*:\s+(.+)$")
QUALITY_RANK = {"studio": 0, "high": 1, "standard": 2, "basic": 3}


def settings() -> dict:
    return {"defaults": {}, "rate": 1.0, "pitch": 0.0, "emotion": 0.5, "pause": 0.3, "studio": "natural",
               "room": False, "order": ["piper", "kokoro", "chatterbox", "edge"], "disabled": [], "quality": "fast",
            **(load_settings().get("voice") or {})}


def split(text: str, limit: int = 400) -> list[tuple[str, bool]]:
    """[(sentence, ends a paragraph)]; very long sentences are cut at commas (engines lose quality past ~400 chars)."""
    out: list[tuple[str, bool]] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        sents = [s.strip() for s in SENT.split(para) if s and re.search(r"\w", s)]
        for i, s in enumerate(sents):
            while len(s) > limit:
                cut = s.rfind(",", 0, limit)
                cut = cut if cut > 40 else s.rfind(" ", 0, limit)
                out.append((s[:cut + 1].strip(), False))
                s = s[cut + 1:].strip()
            out.append((s, i == len(sents) - 1))
    return out


def lang_of(vid: str) -> str:
    """'tr' from tr-TR-EmelNeural, piper:tr_TR-dfki-medium, chatterbox:default@tr; kokoro by its first letter."""
    if vid.startswith("kokoro:"):
        return catalog.KOKORO_LANG.get(vid[7:8], ("en", "en-US"))[1][:2]
    if vid.startswith("chatterbox:"):
        return vid.rsplit("@", 1)[-1][:2]
    name = vid.split(":", 1)[-1]
    return name[:2].lower()


async def candidates(lang: str, gender: str = "", installed_only: bool = True) -> list[dict]:
    """Voices for a language, best first by the engine order and quality; gender preferred, not required."""
    cfg = settings()
    order = [e for e in cfg["order"] if e not in cfg["disabled"]]
    local = [v for v in await catalog.local_voices(lang) if (v["installed"] or not installed_only)
             and v["engine"] in order and not v.get("own")]
    if cfg["quality"] != "best":  # Chatterbox is slow on a CPU: only when chosen or "best quality" is set
        local = [v for v in local if v["engine"] != "chatterbox"]
    local.sort(key=lambda v: (gender and v["gender"] != gender, order.index(v["engine"]),
                              QUALITY_RANK.get(v["quality"], 3)))
    edge = []
    if "edge" in order:
        try:
            from .. import tts
            edge = [{**v, "engine": "edge"} for v in await tts.voices(lang)]
            main = {"tr": "tr-TR", "en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "pt": "pt-BR"}.get(lang)
            edge.sort(key=lambda v: (gender and v["gender"] != gender, v["locale"] != main))
        except Exception:  # noqa: BLE001 - offline
            edge = []
    out = local + edge
    out.sort(key=lambda v: (bool(gender) and v["gender"] != gender, order.index(v["engine"])))
    return out


async def chain_for(voice: str, lang: str, gender: str = "") -> list[str]:
    """The voice to use first and the ones that follow if it fails."""
    cfg = settings()
    voice = voice.removeprefix("edge:")
    lang = (lang or (lang_of(voice) if voice else "") or "tr")[:2].lower()
    first = voice or cfg["defaults"].get(lang) or ""
    rest = [v["id"] for v in await candidates(lang, gender)]
    if first and gender and not voice:  # the saved default is the other gender: the asked gender wins
        meta = next((v for v in await catalog.local_voices(lang) if v["id"] == first), None)
        if meta and meta["gender"] not in (gender, "unknown"):
            first = ""
    ids = ([first] if first else []) + [x for x in rest if x != first]
    if not ids:
        raise engines.VoiceError(f"no voice for language {lang!r} (install one in Settings > Voices)")
    return ids[:6]


def _trim(x: np.ndarray, sr: int) -> np.ndarray:
    """Silence at both ends removed (pauses are set by us, not by the engine), with 8 ms fades."""
    if not len(x):
        return x
    thr = max(0.008, float(np.abs(x).max()) * 0.02)
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x[:0]
    a, b = max(0, idx[0] - int(sr * 0.02)), min(len(x), idx[-1] + int(sr * 0.06))
    y = x[a:b].copy()
    n = min(len(y) // 2, int(sr * 0.008))
    if n:
        y[:n] *= np.linspace(0, 1, n)
        y[-n:] *= np.linspace(1, 0, n)
    return y


def _resample(x: np.ndarray, sr: int, to: int) -> np.ndarray:
    if sr == to:
        return x
    from math import gcd

    from scipy.signal import resample_poly
    g = gcd(sr, to)
    return resample_poly(x, to // g, sr // g).astype(np.float32)


def parse_dialog(text: str, speakers: dict) -> list[tuple[str, str]] | None:
    """'Ayşe: Merhaba!' lines -> [(speaker, text)] when speakers are given (or two or more names repeat)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    hits = [DIALOG.match(ln) for ln in lines]
    names = {m.group(1).strip() for m in hits if m}
    if not lines or sum(1 for m in hits if m) < max(2, len(lines) * 0.6):
        return None
    if not speakers and len(names) < 2:
        return None
    out, last = [], None
    for ln, m in zip(lines, hits):
        if m:
            last = m.group(1).strip()
            out.append((last, m.group(2).strip()))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + " " + ln.strip())
    return out


async def _speak(pieces: list[tuple[str, bool, str]], opts: dict) -> tuple[np.ndarray, int, list, list[str]]:
    """pieces: [(text, paragraph end, voice chain key)] -> (samples, sr, segments, voices used)."""
    sr_out = 0
    audio: list[np.ndarray] = []
    segs: list[tuple[float, float, str, str]] = []
    used: list[str] = []
    t = 0.0
    sem = asyncio.Semaphore(4)
    chains: dict[str, list[str]] = opts["_chains"]

    async def one(text: str, key: str) -> tuple[np.ndarray, int, str]:
        async with sem:
            last = None
            for vid in list(chains[key]):
                try:
                    x, sr = await engines.synth(vid, text, {**opts, "lang": opts.get("lang")})
                    if chains[key][0] != vid:  # keep the voice that works for the rest of this speaker
                        chains[key] = [vid] + [c for c in chains[key] if c != vid]
                    return x, sr, vid
                except Exception as e:  # noqa: BLE001
                    last = e
            raise engines.VoiceError(f"every voice failed: {last}")

    # local engines run on the CPU: the first piece alone (it settles the chain), the rest a few at a time
    first = await one(pieces[0][0], pieces[0][2]) if pieces else None
    rest = await asyncio.gather(*(one(p[0], p[2]) for p in pieces[1:]))
    results = ([first] if first else []) + list(rest)
    for n, ((text, para, key), (x, sr, vid)) in enumerate(zip(pieces, results)):
        sr_out = sr_out or sr
        x = _trim(_resample(x, sr, sr_out), sr_out)
        if not len(x):
            continue
        audio.append(x)
        segs.append((t, t + len(x) / sr_out, text, key))
        t += len(x) / sr_out
        gap = float(opts["pause"]) * (2.0 if para else 1.0)
        if n + 1 < len(pieces) and pieces[n + 1][2] != key:
            gap = max(gap, 0.45)  # a new speaker breathes first
        audio.append(np.zeros(int(sr_out * gap), dtype=np.float32))
        t += gap
        if vid not in used:
            used.append(vid)
    if not audio:
        raise engines.VoiceError("nothing to read")
    lead = np.zeros(int(sr_out * 0.15), dtype=np.float32)
    segs = [(a + 0.15, b + 0.15, s, k) for a, b, s, k in segs]
    return np.concatenate([lead, *audio]), sr_out, segs, used


def stamp(t: float) -> str:
    h, rest = divmod(t, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def srt_text(segs: list) -> str:
    return "\n".join(f"{i + 1}\n{stamp(a)} --> {stamp(b)}\n{s}\n" for i, (a, b, s, *_rest) in enumerate(segs))


async def render(text: str, target: Path, voice: str = "", lang: str = "", gender: str = "", rate: float | None = None,
                 pitch: float | None = None, emotion: float | None = None, pause: float | None = None,
                 preset: str | None = None, room: bool | None = None, speakers: dict | None = None,
                 srt: bool = False) -> dict:
    cfg = settings()
    text = (text or "").strip()
    if not re.search(r"\w", text):
        raise engines.VoiceError("nothing to read")
    lang = (lang or (lang_of(voice) if voice else "") or load_settings().get("language") or "tr")[:2].lower()
    opts = {"rate": float(rate or cfg["rate"]), "emotion": float(cfg["emotion"] if emotion is None else emotion),
            "pause": float(cfg["pause"] if pause is None else pause), "lang": lang, "_chains": {}}
    dialog = parse_dialog(text, speakers or {})
    pieces: list[tuple[str, bool, str]] = []
    if dialog:
        # every speaker: the voice given for them, or a gender ("female"/"male"), else alternate female / male
        alt = ["female", "male"]
        for i, name in enumerate(dict.fromkeys(n for n, _ in dialog)):
            want = str((speakers or {}).get(name) or "")
            g = want if want in ("female", "male") else alt[i % 2]
            opts["_chains"][name] = await chain_for("" if want in ("female", "male", "") else want, lang, g)
        for name, line in dialog:
            sents = split(line)
            pieces += [(s, end, name) for s, end in sents]
    else:
        opts["_chains"]["_"] = await chain_for(voice, lang, gender)
        pieces = [(s, end, "_") for s, end in split(text)]
    samples, sr, segs, used = await _speak(pieces, opts)
    await asyncio.to_thread(studio.encode, samples, sr, target, preset or cfg["studio"],
                            float(cfg["pitch"] if pitch is None else pitch), bool(cfg["room"] if room is None else room))
    out = {"path": target, "voice": used[0] if used else "", "voices": used, "duration": round(len(samples) / sr, 2),
           "segments": [{"start": round(a, 2), "end": round(b, 2), "text": s, "speaker": None if k == "_" else k}
                        for a, b, s, k in segs], "chars": len(text), "bytes": target.stat().st_size,
           "engine": engines.engine_of(used[0]) if used else "", "lang": lang}
    wanted = voice.removeprefix("edge:")
    if wanted and used and used[0] != wanted:
        out["fallback_from"] = wanted
    if srt:
        p = target.with_suffix(".srt")
        p.write_text(srt_text(segs), encoding="utf-8")
        out["srt"] = p
    return out
