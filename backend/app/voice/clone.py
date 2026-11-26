"""Voice clone studio (voice/studio.py is the studio *finish* of recordings, a different thing): a reference clip -> analysed, cleaned, listened to, tried on every cloning engine, then saved as
the user's own narrator voice.

Cleaning (all numpy/scipy, no download): DC + rumble high-pass, click/pop repair, spectral noise reduction from the
clip's own quiet parts (soft mask smoothed over time and frequency, so no "musical" noise), gentle de-essing,
silence trim with long pauses shortened, loudness to -20 dBFS RMS with a soft peak limit at -1 dBFS. Each step can
be turned off. The clip is analysed before and after: speech seconds, signal-to-noise, noise floor, clipping, peak,
pitch (the gender label) and warnings the user can act on (too short, noisy, clipped, quiet).

Work files live in data/tts/refs/_studio-<id>.wav (raw) and _studio-<id>-clean.wav; names with a leading "_" are
not listed as voices. Saving moves the chosen one to refs/<name>.wav, where every cloning engine finds it."""
from __future__ import annotations

import time
import uuid
import wave
from pathlib import Path

import numpy as np

from . import catalog

SR = 24000
MAX_SECS = 30
KEEP_HOURS = 24
DEFAULTS = {"denoise": 0.7, "declick": True, "highpass": True, "deess": True, "trim": True, "normalize": True}


def _path(sid: str, kind: str) -> Path:
    return catalog.REFS_DIR / (f"_studio-{sid}.wav" if kind == "raw" else f"_studio-{sid}-clean.wav")


def write_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def _frames_rms(x: np.ndarray, n: int) -> np.ndarray:
    k = len(x) // n
    if k == 0:
        return np.array([float(np.sqrt(np.mean(x ** 2)) + 1e-9)])
    return np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1)) + 1e-9


def _db(v: float) -> float:
    return float(20 * np.log10(max(v, 1e-9)))


def analyse(x: np.ndarray, sr: int = SR) -> dict:
    """Speech seconds, SNR, noise floor, clipping, peak, pitch and warnings."""
    n = int(sr * 0.02)
    rms = _frames_rms(x, n)
    floor = float(np.percentile(rms, 10))
    speech = rms > max(floor * 3.2, 10 ** (-50 / 20))
    sp = float(np.sqrt(np.mean(rms[speech] ** 2))) if speech.any() else 0.0
    snr = _db(sp) - _db(floor) if sp else 0.0
    clip = float(np.mean(np.abs(x) > 0.985) * 100)
    peak = _db(float(np.abs(x).max()) if len(x) else 0)
    hz = catalog.pitch_hz(x, sr) if len(x) > sr else 0
    secs = float(speech.sum() * n / sr)
    warn = []
    if secs < 6:
        warn.append("short")
    if snr < 20:
        warn.append("noisy")
    if clip > 0.1:
        warn.append("clipped")
    if sp and _db(sp) < -38:
        warn.append("quiet")
    if len(x) / sr > MAX_SECS:
        warn.append("long")
    return {"seconds": round(len(x) / sr, 1), "speech_s": round(secs, 1), "snr_db": round(snr, 1),
            "noise_db": round(_db(floor), 1), "clip_pct": round(clip, 2), "peak_db": round(peak, 1),
            "pitch_hz": round(hz), "gender": catalog.gender_of(hz), "warnings": warn,
            "score": _score(secs, snr, clip)}


def _score(secs: float, snr: float, clip: float) -> int:
    """0-100: how good a cloning reference this is (length 8-20 s, SNR above 30 dB, no clipping)."""
    s_len = min(1.0, secs / 8) if secs < 20 else max(0.6, 1 - (secs - 20) / 40)
    s_snr = min(1.0, max(0.0, (snr - 8) / 25))
    s_clip = max(0.0, 1 - clip / 2)
    return int(round(100 * (0.35 * s_len + 0.5 * s_snr + 0.15 * s_clip)))


# ---------------------------------------------------------------- cleaning steps
def highpass(x: np.ndarray, sr: int = SR, hz: float = 75) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    x = x - float(np.mean(x))
    return sosfiltfilt(butter(4, hz, "highpass", fs=sr, output="sos"), x).astype(np.float32)


def declick(x: np.ndarray, k: float = 7.0) -> np.ndarray:
    """Short impulses (clicks, pops, mouth noise) far from the local median are replaced by it."""
    from scipy.signal import medfilt
    med = medfilt(x, 7).astype(np.float32)
    dev = np.abs(x - med)
    mad = medfilt(dev, 401) + 1e-5
    bad = dev > k * mad * 1.4826 + 0.02
    if not bad.any():
        return x
    bad = np.convolve(bad.astype(np.float32), np.ones(5), "same") > 0  # a couple of samples around each click
    y = x.copy()
    y[bad] = med[bad]
    return y


def _stft(x: np.ndarray, n: int = 1024, hop: int = 256):
    from scipy.signal import stft
    return stft(x, nperseg=n, noverlap=n - hop, boundary="even")[2]


def _istft(z, length: int, n: int = 1024, hop: int = 256) -> np.ndarray:
    from scipy.signal import istft
    y = istft(z, nperseg=n, noverlap=n - hop, boundary=True)[1]
    y = y[:length]
    return np.pad(y, (0, max(0, length - len(y)))).astype(np.float32)


def denoise(x: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """Spectral noise reduction: the noise profile is the quietest 15% of frames, the gain a soft mask smoothed
    over time and frequency with a floor (strength 0..1 -> up to ~24 dB less noise, speech untouched)."""
    from scipy.ndimage import uniform_filter
    if strength <= 0:
        return x
    z = _stft(x)
    mag = np.abs(z)
    energy = mag.mean(axis=0)
    quiet = energy <= np.percentile(energy, 15)
    noise = np.median(mag[:, quiet], axis=1, keepdims=True) if quiet.any() else np.percentile(mag, 10, axis=1, keepdims=True)
    over = 1.0 + 1.5 * strength
    gain = np.clip(1 - over * (noise / (mag + 1e-9)) ** 2, 0, 1)
    gain = uniform_filter(gain, size=(3, 5))  # smooth: no warbling "musical noise"
    floor = 10 ** (-(6 + 18 * strength) / 20)
    gain = np.maximum(gain, floor)
    return _istft(z * gain, len(x))


def deess(x: np.ndarray, sr: int = SR, amount: float = 0.5) -> np.ndarray:
    """Harsh 5-10 kHz sibilance is turned down only in frames where it dominates."""
    z = _stft(x)
    f = np.linspace(0, sr / 2, z.shape[0])
    band = (f >= 5000) & (f <= min(10000, sr / 2 - 1))
    if not band.any():
        return x
    e_band = (np.abs(z[band]) ** 2).sum(axis=0)
    e_all = (np.abs(z) ** 2).sum(axis=0) + 1e-12
    ratio = e_band / e_all
    g = np.where(ratio > 0.35, 1 - amount * np.clip((ratio - 0.35) / 0.4, 0, 1), 1.0)
    z[band] *= g[None, :]
    return _istft(z, len(x))


def trim(x: np.ndarray, sr: int = SR, max_pause: float = 0.45) -> np.ndarray:
    """Leading/trailing silence cut (150 ms kept), pauses longer than max_pause shortened to it."""
    n = int(sr * 0.02)
    rms = _frames_rms(x, n)
    thr = max(float(np.percentile(rms, 10)) * 3.2, 10 ** (-55 / 20))
    on = rms > thr
    if not on.any():
        return x
    pad = int(0.15 / 0.02)
    first, last = max(0, int(np.argmax(on)) - pad), min(len(on), len(on) - int(np.argmax(on[::-1])) + pad)
    keep, run = [], 0
    limit = int(max_pause / 0.02)
    for i in range(first, last):
        run = 0 if on[i] else run + 1
        if run <= limit:
            keep.append(i)
    idx = np.concatenate([np.arange(i * n, min((i + 1) * n, len(x))) for i in keep]) if keep else np.arange(len(x))
    y = x[idx]
    fade = min(len(y) // 2, int(sr * 0.01))
    if fade:
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
    return y


def normalize(x: np.ndarray, target_db: float = -20.0, peak_db: float = -1.0) -> np.ndarray:
    n = int(SR * 0.02)
    rms = _frames_rms(x, n)
    speech = rms > float(np.percentile(rms, 10)) * 3.2
    level = float(np.sqrt(np.mean(rms[speech] ** 2))) if speech.any() else float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    y = x * (10 ** (target_db / 20) / max(level, 1e-6))
    lim = 10 ** (peak_db / 20)
    over = np.abs(y) > lim * 0.8
    if over.any():  # soft knee above 80% of the ceiling instead of hard clipping
        k = lim * 0.8
        s = np.sign(y[over])
        y[over] = s * (k + (lim - k) * np.tanh((np.abs(y[over]) - k) / (lim - k)))
    return y.astype(np.float32)


def clean(x: np.ndarray, opts: dict | None = None) -> np.ndarray:
    o = {**DEFAULTS, **(opts or {})}
    y = x.astype(np.float32)
    if o.get("highpass"):
        y = highpass(y)
    if o.get("declick"):
        y = declick(y)
    if float(o.get("denoise") or 0) > 0:
        y = denoise(y, float(o["denoise"]))
    if o.get("deess"):
        y = deess(y)
    if o.get("trim"):
        y = trim(y)
    y = y[: SR * MAX_SECS]
    if o.get("normalize"):
        y = normalize(y)
    return y


# ---------------------------------------------------------------- sessions
def sweep() -> None:
    """Studio work files older than a day go."""
    if not catalog.REFS_DIR.is_dir():
        return
    old = time.time() - KEEP_HOURS * 3600
    for f in catalog.REFS_DIR.glob("_studio-*"):  # clips and their transcripts
        try:
            if f.stat().st_mtime < old:
                f.unlink()
        except OSError:
            pass


def start(x: np.ndarray, opts: dict | None = None) -> dict:
    sweep()
    sid = uuid.uuid4().hex[:12]
    x = x[: SR * 90]  # a longer recording is fine to bring; the clean one is cut to 30 s of speech
    write_wav(_path(sid, "raw"), x / max(1e-6, float(np.abs(x).max())) * 0.97 if np.abs(x).max() > 1 else x)
    return redo(sid, opts)


def redo(sid: str, opts: dict | None = None) -> dict:
    raw = _path(sid, "raw")
    if not raw.exists():
        raise FileNotFoundError(sid)
    x = read(raw)
    y = clean(x, opts)
    write_wav(_path(sid, "clean"), y)
    return {"id": sid, "before": analyse(x), "after": analyse(y), "options": {**DEFAULTS, **(opts or {})}}


def ok_id(sid: str) -> bool:
    return len(sid) == 12 and all(c in "0123456789abcdef" for c in sid)


def file_of(sid: str, kind: str) -> Path:
    return _path(sid, "raw" if kind == "raw" else "clean")


def voice_name(sid: str, kind: str) -> str:
    """The ref-<name> a cloning engine reads for a studio try (the file stays in the studio)."""
    return f"ref-_studio-{sid}" if kind == "raw" else f"ref-_studio-{sid}-clean"


def save(sid: str, name: str, kind: str = "clean") -> dict:
    src = file_of(sid, kind)
    if not src.exists():
        raise FileNotFoundError(sid)
    dst = catalog.REFS_DIR / f"{name}.wav"
    x = read(src)
    write_wav(dst, x)
    hz = catalog.pitch_hz(x, SR)
    gender = catalog.save_reference(name, dst, hz)
    return {"name": name, "seconds": round(len(x) / SR, 1), "gender": gender, "pitch_hz": round(hz)}


def clone_engines() -> list[dict]:
    """Every installed engine that clones from a reference clip."""
    from . import packs
    out = []
    for e, p in packs.PACKS.items():
        if p.get("clone") and packs.installed(e):
            out.append({"engine": e, "name": p["name"], "commercial": bool(p.get("commercial", True)),
                        "license": p["license"], "speed": packs.fit(e).get("state")})
    if catalog.cbx_python() is not None:
        out.append({"engine": "chatterbox", "name": "Chatterbox", "commercial": True,
                    "speed": "ok" if packs.hardware().get("cuda") else "slow"})
    rank = {"ok": 0, "slow": 1, "no": 2}
    return sorted(out, key=lambda x: rank.get(x.get("speed") or "ok", 1))  # fastest on this computer first
