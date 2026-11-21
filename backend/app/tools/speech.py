"""Speech <-> text for the agent.

speech_to_text: any audio or video file -> a transcript with timestamps and an .srt subtitle file (faster-whisper on
the CPU, offline; the model downloads once). text_to_speech: text -> a finished recording from the voice catalog
(local Piper / Kokoro / Chatterbox voices, then Microsoft's online voices), with the studio finish, timings and dialogs
(backend/app/voice)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

_MODELS: dict = {}
SIZES = ("tiny", "base", "small", "medium")


def _stamp(t: float, comma: bool = True) -> str:
    h, rest = divmod(t, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", "," if comma else ".")


def _transcribe(path: Path, size: str, lang: str | None, minutes: float) -> tuple[list[tuple[float, float, str]], str]:
    from faster_whisper import WhisperModel
    size = size if size in SIZES else "base"
    model = _MODELS.get(size) or WhisperModel(size, device="cpu", compute_type="int8")
    _MODELS[size] = model
    # The audio is decoded with ffmpeg (16 kHz mono), not by faster-whisper's own PyAV reader: PyAV 19 dropped the
    # argument it passes ("open() got an unexpected keyword argument 'metadata_errors'"), so every transcript failed.
    from ..voice.engines import decode
    audio, _ = decode(path.read_bytes(), 16000)
    segments, info = model.transcribe(audio, language=lang or None, vad_filter=True, beam_size=1)
    out = []
    for s in segments:
        if minutes and s.start > minutes * 60:
            break
        out.append((s.start, s.end, s.text.strip()))
    return out, info.language


async def speech_to_text(path: Path, out_dir: Path, lang: str | None = None, size: str = "base",
                         minutes: float = 0) -> dict:
    """{language, text, srt, txt, segments}: writes <name>.srt and <name>.txt next to the working folder."""
    segs, found = await asyncio.to_thread(_transcribe, path, size, lang, minutes)
    srt = out_dir / f"{path.stem}.srt"
    txt = out_dir / f"{path.stem}.txt"
    srt.write_text("\n".join(f"{i + 1}\n{_stamp(a)} --> {_stamp(b)}\n{t}\n" for i, (a, b, t) in enumerate(segs)),
                   encoding="utf-8")
    txt.write_text("\n".join(t for _, _, t in segs) + "\n", encoding="utf-8")
    return {"language": found, "text": table(segs), "srt": srt, "txt": txt, "segments": len(segs),
            "duration": segs[-1][1] if segs else 0}


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m:02d}:{s:02d}"


def table(segs: list[tuple[float, float, str]]) -> str:
    """The transcript as a Markdown table (start-end | text): shown to the user as it is, readable at a glance."""
    if not segs:
        return ""
    rows = [f"| {_mmss(a)}–{_mmss(b)} | {t.replace('|', '/')} |" for a, b, t in segs]
    return "| Time | Text |\n|---|---|\n" + "\n".join(rows)


def _chunks(text: str, limit: int = 2500) -> list[str]:
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+|\n{2,}", text):
        if len(cur) + len(sent) + 1 > limit and cur:
            parts.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


async def pick_voice(lang: str, voice: str = "", gender: str = "") -> str:
    """The voice that will be used first (the catalog of Settings > Voices: local voices, then Microsoft's)."""
    from ..voice import render
    return (await render.chain_for(voice, lang or "tr", (gender or "").lower()))[0]


async def text_to_speech(text: str, target: Path, lang: str = "tr", voice: str = "", gender: str = "",
                         rate: float | None = None, **tone) -> dict:
    """Any length, any voice of the catalog, the studio finish; tone: pitch, emotion, pause, preset, room,
    speakers ({name: voice id | female | male} for 'Name: line' dialogs), srt (write subtitles next to it)."""
    from ..voice import render
    voice = (voice or "").strip()
    return await render.render(text, target, voice=voice, lang=(lang or "")[:3], gender=(gender or "").lower(),
                               rate=rate, **{k: v for k, v in tone.items() if v is not None})
