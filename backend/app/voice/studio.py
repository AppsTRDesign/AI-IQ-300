"""The studio finish: one ffmpeg pass over the whole recording.

Presets (all keep the length, so subtitle timings stay right):
  none       only a peak limit
  natural    rumble cut, a little less mud, a little more presence, gentle compression, -16 LUFS
  podcast    warmer low end, clearer presence, de-esser, firmer compression, -16 LUFS
  broadcast  EBU R128: -23 LUFS, narrow loudness range, strong compression (TV / radio)
  video      YouTube / social: -14 LUFS, bright and forward
  warm       soft top, fuller low end (audiobooks, calm narration)
pitch: semitones (-6..+6), with the tempo kept; room: a small room's early reflections."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

from .engines import VoiceError, ffmpeg

PRESETS = {
    "none": [],
    "natural": ["highpass=f=70", "equalizer=f=250:t=q:w=1:g=-1.5", "equalizer=f=3500:t=q:w=1.2:g=1.5",
                "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=160:makeup=1.5", "LOUD:-16:-1.5:11"],
    "podcast": ["highpass=f=80", "lowshelf=f=140:g=2", "equalizer=f=300:t=q:w=1:g=-2", "equalizer=f=3000:t=q:w=1:g=2.5",
                "deesser=i=0.4", "acompressor=threshold=-22dB:ratio=3.5:attack=8:release=140:makeup=2",
                "LOUD:-16:-1.5:9"],
    "broadcast": ["highpass=f=80", "equalizer=f=3200:t=q:w=1:g=3", "highshelf=f=10000:g=2", "deesser=i=0.5",
                  "acompressor=threshold=-24dB:ratio=4:attack=5:release=120:makeup=3", "LOUD:-23:-2:7"],
    "video": ["highpass=f=80", "equalizer=f=3500:t=q:w=1:g=2.5", "highshelf=f=9000:g=1.5", "deesser=i=0.4",
              "acompressor=threshold=-20dB:ratio=3:attack=8:release=140:makeup=2", "LOUD:-14:-1:9"],
    "warm": ["highpass=f=60", "lowshelf=f=150:g=3", "highshelf=f=8000:g=-2",
             "acompressor=threshold=-20dB:ratio=2:attack=12:release=200:makeup=1.5", "LOUD:-16:-1.5:11"],
}


def chain(preset: str, pitch: float, sr: int, room: bool) -> str:
    parts: list[str] = []
    if pitch:
        f = 2 ** (max(-6.0, min(6.0, float(pitch))) / 12)
        parts += [f"asetrate={int(sr * f)}", f"aresample={sr}", f"atempo={1 / f:.5f}"]
    for p in PRESETS.get(preset, PRESETS["natural"]):
        if p.startswith("LOUD:"):
            i, tp, lra = p[5:].split(":")
            if room:
                parts.append("aecho=0.85:0.8:35|55:0.14|0.09")
            parts.append(f"loudnorm=I={i}:TP={tp}:LRA={lra}")
        else:
            parts.append(p)
    if room and not any(p.startswith("aecho") for p in parts):
        parts.append("aecho=0.85:0.8:35|55:0.14|0.09")
    parts.append("alimiter=limit=0.95:level=disabled")
    return ",".join(parts)


def encode(samples: np.ndarray, sr: int, target: Path, preset: str = "natural", pitch: float = 0.0,
           room: bool = False) -> Path:
    """Float samples -> the finished file (.mp3 / .wav / .m4a / .ogg by extension)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    ext = target.suffix.lower()
    codec = {".wav": ["-c:a", "pcm_s16le"], ".m4a": ["-c:a", "aac", "-b:a", "192k"],
             ".ogg": ["-c:a", "libvorbis", "-q:a", "6"], ".flac": ["-c:a", "flac"]}.get(ext, ["-c:a", "libmp3lame", "-q:a", "2"])
    out_sr = 48000 if preset in ("broadcast", "video") else max(sr, 24000)
    argv = [ffmpeg(), "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
            "-af", chain(preset, pitch, sr, room), "-ar", str(out_sr), *codec, str(target)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    p = subprocess.run(argv, input=np.ascontiguousarray(samples, dtype=np.float32).tobytes(), capture_output=True,
                       creationflags=flags, check=False)
    if p.returncode:
        raise VoiceError(f"studio pass failed: {p.stderr.decode(errors='replace')[-300:]}")
    return target
