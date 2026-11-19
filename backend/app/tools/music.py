"""Original background music, generated offline (numpy), free to use: every track is new (a seed picks the key,
progression and patterns), so videos never share the same stock loop.

Styles: corporate (bright, 110 bpm, plucked arpeggios, claps), lofi (80 bpm, 7th chords, swing hats, vinyl crackle),
cinematic (70 bpm, low strings, timpani swells), acoustic (95 bpm, Karplus-Strong guitar picking, shaker), electronic
(124 bpm, four-on-the-floor, saw bass, sidechain pump), ambient (slow pads), calm (soft piano-like pads), upbeat
(alias of corporate with drums up front). Output: 44.1 kHz stereo WAV, mastered (reverb, soft limiter).
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
STYLES = ("corporate", "upbeat", "lofi", "cinematic", "acoustic", "electronic", "ambient", "calm")
# progressions as scale degrees in a major key (0 = I); minor styles shift to the relative minor
PROGRESSIONS = {"pop": [0, 4, 5, 3], "pop2": [5, 3, 0, 4], "doo": [0, 5, 3, 4], "lift": [3, 4, 0, 5], "minor": [5, 3, 0, 4],
                "epic": [5, 2, 3, 4]}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
STYLE_CFG = {
    "corporate": {"bpm": 110, "prog": ["pop", "lift", "doo"], "drums": "pop", "arp": "pluck", "pad": 0.5, "bass": "root8"},
    "upbeat": {"bpm": 118, "prog": ["pop", "pop2"], "drums": "pop", "arp": "pluck", "pad": 0.4, "bass": "root8"},
    "lofi": {"bpm": 80, "prog": ["pop2", "lift"], "drums": "lofi", "arp": "keys", "pad": 0.6, "bass": "root4", "seventh": True,
             "crackle": True},
    "cinematic": {"bpm": 70, "prog": ["minor", "epic"], "drums": "epic", "arp": "none", "pad": 1.0, "bass": "drone", "minor": True},
    "acoustic": {"bpm": 95, "prog": ["pop", "doo", "lift"], "drums": "shaker", "arp": "guitar", "pad": 0.25, "bass": "root4"},
    "electronic": {"bpm": 124, "prog": ["minor", "pop2"], "drums": "house", "arp": "saw", "pad": 0.45, "bass": "saw8", "minor": True,
                   "pump": True},
    "ambient": {"bpm": 66, "prog": ["lift", "pop2"], "drums": "none", "arp": "bell", "pad": 1.0, "bass": "drone"},
    "calm": {"bpm": 72, "prog": ["doo", "pop"], "drums": "none", "arp": "keys", "pad": 0.8, "bass": "root4"},
}


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n)
    return np.concatenate([np.linspace(0, 1, max(a_n, 1)), np.linspace(1, s, max(d_n, 1)), np.full(s_n, s),
                           np.linspace(s, 0, max(r_n, 1))])[:n]


def _tone(freq: float, dur: float, kind: str = "sine", env=(0.01, 0.1, 0.7, 0.2)) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "saw":
        x = 2 * ((t * freq) % 1) - 1
        x = np.convolve(x, np.ones(6) / 6, mode="same")  # a little softer
    elif kind == "square":
        x = np.sign(np.sin(2 * np.pi * freq * t)) * 0.6
    elif kind == "keys":  # electric-piano like: sine + bell partials, decaying
        x = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 6) + 0.12 * np.sin(2 * np.pi * freq * 3.01 * t) * np.exp(-t * 9)
    elif kind == "bell":
        x = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 3)
    else:
        x = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(2 * np.pi * freq * 2 * t)
    return x * _env(n, *env)


def _pluck(freq: float, dur: float, bright: float = 0.5, rng=None) -> np.ndarray:
    """Karplus-Strong string: a guitar-like pluck."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    buf = (rng or np.random).uniform(-1, 1, period)
    out = np.empty(n)
    decay = 0.996 - (1 - bright) * 0.004
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = decay * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return out * _env(n, 0.002, 0.05, 0.8, min(0.3, dur / 2))


def _kick(dur=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 28) + 42
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _snare(dur=0.25, rng=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = (rng or np.random).uniform(-1, 1, n)
    return (0.7 * noise + 0.4 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 18)


def _clap(rng=None):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    noise = (rng or np.random).uniform(-1, 1, n)
    burst = np.exp(-((t * 1000) % 11) * 0.6) * np.exp(-t * 14)
    return noise * burst


def _hat(dur=0.06, rng=None):
    n = int(dur * SR)
    noise = (rng or np.random).uniform(-1, 1, n)
    noise = np.diff(noise, prepend=0)  # brighter
    return noise * np.exp(-np.arange(n) / SR * 60)


def _timpani(freq=65):
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 1.5 * t)) * np.exp(-t * 2.2)


def _place(track: np.ndarray, sound: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sound))
    track[i:j] += sound[: j - i] * gain


def _reverb(x: np.ndarray, size: float = 1.6, mix: float = 0.25, rng=None) -> np.ndarray:
    n = int(size * SR)
    ir = (rng or np.random).uniform(-1, 1, n) * np.exp(-np.arange(n) / SR * (5 / size))
    ir = np.convolve(ir, np.ones(24) / 24, mode="same")  # a dark hall: white-noise tails hissed
    ir[0] = 0
    m = len(x) + n
    nfft = 1 << (m - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x)]
    wet /= max(np.abs(wet).max(), 1e-9)
    return x * (1 - mix) + wet * mix * np.abs(x).max()


def generate(style: str, seconds: float, target: Path, seed: int = 0) -> Path:
    """Writes a new track of the style (at least `seconds` long, ending with a fade) to target (.wav)."""
    style = style if style in STYLE_CFG else "corporate"
    cfg = STYLE_CFG[style]
    rng = np.random.default_rng(seed or None)
    bpm = cfg["bpm"] * rng.uniform(0.96, 1.04)
    beat = 60 / bpm
    bar = beat * 4
    key = int(rng.integers(0, 12))
    root = 48 + key  # C3..B3
    prog = PROGRESSIONS[rng.choice(cfg["prog"])]
    bars = max(4, int(np.ceil((seconds + 2) / bar)))
    n = int((bars * bar + 3) * SR)
    music = np.zeros(n)
    drums = np.zeros(n)
    bass = np.zeros(n)
    arp_pattern = rng.permutation([0, 1, 2, 1, 3, 2, 1, 2]).tolist()
    for b in range(bars):
        deg = prog[b % len(prog)]
        chord_root = root + MAJOR[deg % 7] + (12 if deg >= 7 else 0)
        third = MAJOR[(deg + 2) % 7] - MAJOR[deg % 7]
        fifth = MAJOR[(deg + 4) % 7] - MAJOR[deg % 7]
        third %= 12
        fifth %= 12
        notes = [chord_root, chord_root + third, chord_root + fifth]
        if cfg.get("seventh"):
            notes.append(chord_root + (MAJOR[(deg + 6) % 7] - MAJOR[deg % 7]) % 12)
        t0 = b * bar
        # pad
        if cfg["pad"]:
            for m in notes:
                _place(music, _tone(_hz(m + 12), bar * 1.02, "saw" if style in ("cinematic", "electronic") else "sine",
                                    (0.4 if style != "electronic" else 0.05, 0.3, 0.8, 0.6)), t0, 0.09 * cfg["pad"])
        # bass
        b_root = _hz(chord_root - 12)
        if cfg["bass"] == "drone":
            _place(bass, _tone(b_root, bar * 1.05, "sine", (0.6, 0.2, 0.9, 0.6)), t0, 0.32)
        elif cfg["bass"] in ("root8", "saw8"):
            for k in range(8):
                _place(bass, _tone(b_root * (2 if k % 4 == 3 else 1), beat / 2 * 0.9, "saw" if cfg["bass"] == "saw8" else "sine",
                                   (0.005, 0.08, 0.6, 0.05)), t0 + k * beat / 2, 0.30)
        else:
            for k in range(4):
                _place(bass, _tone(b_root, beat * 0.95, "sine", (0.01, 0.1, 0.7, 0.1)), t0 + k * beat, 0.32)
        # arpeggio / lead texture
        kind = cfg["arp"]
        if kind != "none":
            steps = 8 if kind in ("pluck", "saw", "guitar") else 4
            for k in range(steps):
                m = notes[arp_pattern[k % len(arp_pattern)] % len(notes)] + (24 if kind in ("bell", "keys") else 12)
                at = t0 + k * bar / steps + (beat / 6 if style == "lofi" and k % 2 else 0)  # lofi swing
                dur = bar / steps * (1.6 if kind in ("keys", "bell") else 1.0)
                if kind == "guitar":
                    snd = _pluck(_hz(m), dur * 1.8, 0.6, rng)
                elif kind == "pluck":
                    snd = _tone(_hz(m), dur, "square", (0.002, 0.12, 0.15, 0.08)) * 0.5 + _tone(_hz(m), dur, "sine", (0.002, 0.15, 0.2, 0.1))
                elif kind == "saw":
                    snd = _tone(_hz(m), dur * 0.8, "saw", (0.003, 0.1, 0.3, 0.05))
                else:
                    snd = _tone(_hz(m), dur, kind, (0.005, 0.4, 0.3, 0.4))
                _place(music, snd, at, 0.11 if kind != "guitar" else 0.22)
        # drums
        d = cfg["drums"]
        if d in ("pop", "house"):
            for k in range(4):
                _place(drums, _kick(), t0 + k * beat, 0.9)
            for k in (1, 3):
                _place(drums, _clap(rng) if d == "pop" else _snare(rng=rng), t0 + k * beat, 0.35)
            for k in range(8):
                _place(drums, _hat(rng=rng), t0 + k * beat / 2 + (beat / 4 if d == "house" else 0), 0.16 if k % 2 else 0.1)
        elif d == "lofi":
            for k in (0, 2.5):
                _place(drums, _kick(0.4), t0 + k * beat, 0.7)
            for k in (1, 3):
                _place(drums, _snare(rng=rng), t0 + k * beat, 0.25)
            for k in range(8):
                _place(drums, _hat(0.05, rng), t0 + k * beat / 2 + (beat / 6 if k % 2 else 0), 0.08)
        elif d == "shaker":
            for k in range(8):
                _place(drums, _hat(0.09, rng) * 0.7, t0 + k * beat / 2, 0.12 if k % 2 else 0.07)
            _place(drums, _kick(0.4), t0, 0.45)
            _place(drums, _kick(0.4), t0 + 2 * beat, 0.35)
        elif d == "epic" and b % 2 == 1:
            _place(drums, _timpani(_hz(chord_root - 24)), t0 + 3 * beat, 0.6)
    if cfg.get("pump"):  # sidechain pump: the pads duck on every kick
        t = np.arange(n) / SR
        pump = 0.45 + 0.55 * np.clip(((t % beat) / beat) * 2.2, 0, 1)
        music *= pump
        bass *= pump
    mix = _reverb(music, 2.2 if style in ("cinematic", "ambient") else 1.4, 0.3, rng) + bass + drums * 0.9
    if cfg.get("crackle"):
        crackle = (rng.random(n) > 0.9993) * rng.uniform(-1, 1, n) * 0.25 + rng.normal(0, 0.004, n)
        mix += crackle
    # master: high-pass the mud, soft limit, normalise, fade out
    mix -= np.convolve(mix, np.ones(400) / 400, mode="same") * 0.6
    mix = np.convolve(mix, np.array([0.2, 0.3, 0.3, 0.2]), mode="same")  # gentle top-end roll-off
    mix = np.tanh(mix / (np.abs(mix).max() + 1e-9) * 1.6)
    total = int((seconds + 1.5) * SR)
    mix = mix[:total]
    fade = int(min(3.0, seconds / 4) * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.89
    # a little stereo width: the reverb tail delayed on one side
    delay = int(0.012 * SR)
    right = np.concatenate([np.zeros(delay), mix[:-delay]]) * 0.35 + mix * 0.65
    stereo = np.stack([mix, right], axis=1)
    pcm = (stereo * 32767).astype(np.int16)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return target
