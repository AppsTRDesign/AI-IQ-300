"""Text -> raw mono float32 samples, per engine. One sentence (or a few) per call; render.py joins them.

opts: rate (0.5-2), emotion (0-1, Chatterbox exaggeration; Piper/Kokoro: a little more variation), lang."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from . import catalog

_PIPER: dict[str, object] = {}
_KOKORO: list = []
_LOCK = threading.Lock()  # ONNX sessions are loaded once; synthesis itself runs in worker threads


class VoiceError(Exception):
    pass


def engine_of(vid: str) -> str:
    return vid.split(":", 1)[0] if ":" in vid and vid.split(":", 1)[0] in ("piper", "kokoro", "chatterbox", "edge") \
        else "edge"


# ------------------------------------------------------------------ Piper
def _piper_voice(name: str):
    with _LOCK:
        if name not in _PIPER:
            if not catalog.piper_installed(name):
                raise VoiceError(f"voice not installed: piper:{name}")
            from piper import PiperVoice
            m, c = catalog.piper_paths(name)
            _PIPER[name] = PiperVoice.load(m, config_path=c)
        return _PIPER[name]


def _piper(name: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    from piper import SynthesisConfig
    voice = _piper_voice(name)
    tune = (catalog.PIPER_EXTRA.get(name) or {}).get("tune") or {}
    rate = max(0.5, min(2.0, float(opts.get("rate") or 1.0)))
    emo = max(0.0, min(1.0, float(opts.get("emotion", 0.5))))
    cfg = SynthesisConfig(length_scale=float(tune.get("length_scale", 1.0)) / rate,
                          noise_scale=float(tune.get("noise_scale", 0.667)) * (0.8 + 0.4 * emo),
                          noise_w_scale=float(tune.get("noise_w_scale", 0.8)) * (0.8 + 0.4 * emo),
                          normalize_audio=True)
    parts, sr = [], 22050
    for ch in voice.synthesize(text, syn_config=cfg):
        parts.append(np.asarray(ch.audio_float_array, dtype=np.float32))
        sr = ch.sample_rate
    if not parts:
        raise VoiceError("piper produced no audio")
    return np.concatenate(parts), sr


# ------------------------------------------------------------------ Kokoro
def _kokoro_model():
    with _LOCK:
        if not _KOKORO:
            if not catalog.kokoro_installed():
                raise VoiceError("voice not installed: kokoro")
            from kokoro_onnx import Kokoro
            files = {k: str(catalog.KOKORO_DIR / f) for k, (f, _) in catalog.KOKORO_FILES.items()}
            _KOKORO.append(Kokoro(files["model"], files["voices"]))
        return _KOKORO[0]


def _kokoro(name: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    lang = catalog.KOKORO_LANG.get(name[:1], ("en-us", ""))[0]
    rate = max(0.5, min(2.0, float(opts.get("rate") or 1.0)))
    samples, sr = _kokoro_model().create(text, voice=name, speed=rate, lang=lang, sentence_pause=0.0)
    return np.asarray(samples, dtype=np.float32), int(sr)


# ------------------------------------------------------------------ Chatterbox (own environment, one worker)
WORKER = Path(__file__).with_name("chatterbox_worker.py")


class _Worker:
    """One long-lived process that keeps the model loaded (loading takes ~1 min on a CPU)."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def ask(self, py: Path, req: dict, timeout: float = 900) -> dict:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self.proc = subprocess.Popen([str(py), "-u", str(WORKER)], stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                             encoding="utf-8", creationflags=flags,
                                             # plain HTTP downloads: the xet backend hung at 0 bytes here
                                             env={**_env(), "HF_HOME": str(catalog.CBX_DIR / "hf"),
                                                  "HF_HUB_DISABLE_XET": "1", "HF_HUB_DOWNLOAD_TIMEOUT": "60",
                                                  "PYTHONIOENCODING": "utf-8"})
            assert self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
            box: list[str] = []
            t = threading.Thread(target=lambda: box.append(self.proc.stdout.readline()), daemon=True)
            t.start()
            t.join(timeout)
            if not box or not box[0]:
                self.stop()
                raise VoiceError("chatterbox did not answer (timed out)")
            ans = json.loads(box[0])
            if not ans.get("ok"):
                raise VoiceError(f"chatterbox: {ans.get('error')}")
            return ans

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


def _env() -> dict:
    import os
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
            "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG")
    return {k: v for k, v in os.environ.items() if k.upper() in keep}


CBX = _Worker()


def _chatterbox(name: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    py = catalog.cbx_python()
    if not py:
        raise VoiceError("voice not installed: chatterbox")
    who, _, lang = name.partition("@")
    ref = ""
    if who.startswith("ref-"):
        p = catalog.REFS_DIR / f"{who[4:]}.wav"
        if not p.exists():
            raise VoiceError(f"reference clip missing: {p.name}")
        ref = str(p)
    out = catalog.CBX_DIR / "out" / f"{threading.get_ident()}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    emo = max(0.0, min(1.0, float(opts.get("emotion", 0.5))))
    CBX.ask(py, {"text": text, "lang": lang or opts.get("lang") or "en", "ref": ref, "out": str(out),
                 "exaggeration": 0.25 + emo * 1.0, "cfg_weight": 0.5 if emo <= 0.6 else 0.35})
    return read_wav(out)


async def chatterbox_warmup(py: Path) -> None:
    out = catalog.CBX_DIR / "out" / "warmup.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(CBX.ask, py, {"text": "Merhaba.", "lang": "tr", "ref": "", "out": str(out),
                                          "exaggeration": 0.5, "cfg_weight": 0.5}, 3600)


# ------------------------------------------------------------------ Edge (online)
async def _edge(voice: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    from .. import tts
    mp3 = await tts.edge_mp3(text, voice, float(opts.get("rate") or 1.0))
    return await asyncio.to_thread(decode, mp3)


# ------------------------------------------------------------------ audio helpers
def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        from .. import toolchain
        toolchain._ffmpeg()
        exe = shutil.which("ffmpeg")
    if not exe:
        raise VoiceError("ffmpeg is missing")
    return exe


def decode(data: bytes, sr: int = 24000) -> tuple[np.ndarray, int]:
    """Any audio bytes -> mono float32 at sr."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    p = subprocess.run([ffmpeg(), "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"],
                       input=data, capture_output=True, creationflags=flags, check=False)
    if p.returncode:
        raise VoiceError(f"decode failed: {p.stderr.decode(errors='replace')[-200:]}")
    return np.frombuffer(p.stdout, dtype=np.float32).copy(), sr


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    import wave
    with wave.open(str(path), "rb") as w:
        sr, n, ch, width = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if width != 2:
        return decode(path.read_bytes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


async def synth(vid: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    engine = engine_of(vid)
    name = vid.split(":", 1)[1] if ":" in vid else vid
    if engine == "edge":
        return await _edge(name, text, opts)
    fn = {"piper": _piper, "kokoro": _kokoro, "chatterbox": _chatterbox}[engine]
    return await asyncio.to_thread(fn, name, text, opts)
