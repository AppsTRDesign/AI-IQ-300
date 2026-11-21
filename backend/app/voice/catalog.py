"""The voice catalog: every voice with engine, language, country, gender, quality and whether it is on this computer.

Voice ids: Edge voices keep their own ids (tr-TR-EmelNeural, the ids saved before local voices existed); local voices
are "piper:<name>", "kokoro:<name>", "chatterbox:<default|ref-name>". Gender comes from the voice's metadata; Piper
publishes none, so an installed Piper voice is measured: its median pitch (F0) on a test sentence (male ~85-155 Hz,
female ~165-255 Hz)."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from pathlib import Path

from ..config import DATA_DIR

ROOT = DATA_DIR / "tts"
PIPER_DIR = ROOT / "piper"
KOKORO_DIR = ROOT / "kokoro"
CBX_DIR = ROOT / "chatterbox"
REFS_DIR = ROOT / "refs"  # the user's own reference clips (Chatterbox voice cloning, with consent)
META = ROOT / "voices.json"  # measured genders and other facts about installed voices

HF = "https://huggingface.co"
PIPER_INDEX = f"{HF}/rhasspy/piper-voices/resolve/main/voices.json"
KOKORO_FILES = {  # thewh1teagle/kokoro-onnx model-files-v1.0 (int8: 88 MB, the same voices, faster on a CPU)
    "model": ("kokoro-v1.0.int8.onnx",
              "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"),
    "voices": ("voices-v1.0.bin",
               "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"),
}
KOKORO_MB = 117

# Turkish voices outside the main Piper index (the official repo lists only dfki now) and tuned settings for them.
# 99eren99: a community voice trained on more Turkish speech; its card recommends slower, calmer settings.
PIPER_EXTRA = {
    "tr_TR-fahrettin-medium": {"repo": "speaches-ai/piper-tr_TR-fahrettin-medium", "model": "model.onnx",
                               "config": "config.json", "mb": 63, "lang": "tr", "locale": "tr-TR", "quality": "medium"},
    "tr_TR-fettah-medium": {"repo": "speaches-ai/piper-tr_TR-fettah-medium", "model": "model.onnx",
                            "config": "config.json", "mb": 63, "lang": "tr", "locale": "tr-TR", "quality": "medium"},
    "tr_TR-99eren99-medium": {"repo": "99eren99/piper-turkish-tts", "model": "model.onnx", "config": "config.json",
                              "mb": 64, "lang": "tr", "locale": "tr-TR", "quality": "high", "name": "Eren (topluluk)",
                              "tune": {"length_scale": 1.15, "noise_scale": 0.4, "noise_w_scale": 0.3}},
}
# Known genders (the rest is measured after install)
PIPER_GENDER = {"lessac": "female", "amy": "female", "kathleen": "female", "ljspeech": "female", "kristin": "female",
                "hfc_female": "female", "jenny_dioco": "female", "alba": "female", "cori": "female", "southern_english_female": "female",
                "ryan": "male", "joe": "male", "john": "male", "kusal": "male", "danny": "male", "hfc_male": "male",
                "alan": "male", "northern_english_male": "male", "thorsten": "male", "eva_k": "female", "kerstin": "female",
                "ramona": "female", "siwis": "female", "gilles": "male", "tom": "male", "davefx": "male", "sharvard": "male",
                "faber": "male", "irina": "female", "denis": "male", "dmitri": "male", "ruslan": "male", "huayan": "female",
                "paola": "female", "riccardo": "male", "fahrettin": "male", "dfki": "male",
                "fettah": "female", "99eren99": "male"}  # Turkish ones measured here: 108 / 97 / 182 / 83 Hz
# Kokoro: first letter language, second gender; grades from the model's VOICES.md (A best)
KOKORO_LANG = {"a": ("en-us", "en-US"), "b": ("en-gb", "en-GB"), "e": ("es", "es-ES"), "f": ("fr-fr", "fr-FR"),
               "h": ("hi", "hi-IN"), "i": ("it", "it-IT"), "p": ("pt-br", "pt-BR")}
KOKORO_BEST = {"af_heart": "studio", "af_bella": "studio", "af_nicole": "high", "bf_emma": "high", "af_aoede": "high",
               "af_kore": "high", "af_sarah": "high", "am_fenrir": "high", "am_michael": "high", "am_puck": "high",
               "bm_george": "high", "bm_fable": "high", "bf_isabella": "high", "ff_siwis": "high"}
KOKORO_NAMES = ["af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova",
                "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
                "am_onyx", "am_puck", "am_santa", "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel",
                "bm_fable", "bm_george", "bm_lewis", "ef_dora", "em_alex", "em_santa", "ff_siwis", "hf_alpha",
                "hf_beta", "hm_omega", "hm_psi", "if_sara", "im_nicola", "pf_dora", "pm_alex", "pm_santa"]
# Chatterbox Multilingual languages (README of resemble-ai/chatterbox)
CBX_LANGS = ["ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "ko", "ms", "nl", "no", "pl",
             "pt", "ru", "sv", "sw", "tr", "zh"]
COUNTRY = {"tr": "TR", "en": "US", "de": "DE", "fr": "FR", "es": "ES", "it": "IT", "pt": "BR", "ru": "RU", "ar": "SA",
           "zh": "CN", "ja": "JP", "ko": "KR", "nl": "NL", "pl": "PL", "sv": "SE", "da": "DK", "fi": "FI", "no": "NO",
           "el": "GR", "he": "IL", "hi": "IN", "ms": "MY", "sw": "KE"}

_INDEX: tuple[float, dict] | None = None


def _meta() -> dict:
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_meta(m: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


async def piper_index() -> dict:
    """{name: {lang, locale, quality, speakers, mb, files}} from the official index (cached a day, a copy on disk)."""
    global _INDEX
    if _INDEX and time.time() - _INDEX[0] < 86400:
        return _INDEX[1]
    disk = ROOT / "piper-index.json"
    raw = None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(PIPER_INDEX, follow_redirects=True)
            r.raise_for_status()
            raw = r.json()
        ROOT.mkdir(parents=True, exist_ok=True)
        disk.write_text(json.dumps(raw), encoding="utf-8")
    except Exception:  # noqa: BLE001 - offline: the copy from last time
        try:
            raw = json.loads(disk.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    out = {}
    for name, v in (raw or {}).items():
        files = v.get("files") or {}
        onnx = next((f for f in files if f.endswith(".onnx")), None)
        if not onnx:
            continue
        code = v["language"]["code"]  # tr_TR
        out[name] = {"lang": v["language"]["family"], "locale": code.replace("_", "-"), "quality": v.get("quality"),
                     "speakers": v.get("num_speakers") or 1, "mb": round(files[onnx]["size_bytes"] / 1e6),
                     "model_url": f"{HF}/rhasspy/piper-voices/resolve/main/{onnx}",
                     "config_url": f"{HF}/rhasspy/piper-voices/resolve/main/{onnx}.json",
                     "country": v["language"].get("country_english") or ""}
    for name, x in PIPER_EXTRA.items():
        out.setdefault(name, {"lang": x["lang"], "locale": x["locale"], "quality": x["quality"], "speakers": 1,
                              "mb": x["mb"], "model_url": f"{HF}/{x['repo']}/resolve/main/{x['model']}",
                              "config_url": f"{HF}/{x['repo']}/resolve/main/{x['config']}", "country": "Turkey"})
    _INDEX = (time.time(), out)
    return out


def piper_paths(name: str) -> tuple[Path, Path]:
    return PIPER_DIR / f"{name}.onnx", PIPER_DIR / f"{name}.onnx.json"


def piper_installed(name: str) -> bool:
    m, c = piper_paths(name)
    return m.exists() and c.exists()


def kokoro_installed() -> bool:
    return all((KOKORO_DIR / f).exists() for f, _ in KOKORO_FILES.values())


def cbx_python() -> Path | None:
    import sys
    p = CBX_DIR / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return p if p.exists() and (CBX_DIR / "ready").exists() else None


def _pretty(name: str) -> str:
    base = name.split("-")[1] if "-" in name else name
    return " ".join(w.capitalize() for w in re.split(r"[_]+", base))


def _quality(q: str | None) -> str:
    return {"x_low": "basic", "low": "basic", "medium": "standard", "high": "high"}.get(q or "", "standard")


async def local_voices(lang: str = "") -> list[dict]:
    """All local voices (installed or downloadable) for a language ('' = all)."""
    meta = _meta()
    out: list[dict] = []
    idx = await piper_index()
    for name, v in idx.items():
        if lang and v["lang"] != lang:
            continue
        speaker = name.split("-")[1] if "-" in name else name
        vid = f"piper:{name}"
        extra = PIPER_EXTRA.get(name, {})
        out.append({"id": vid, "engine": "piper", "name": extra.get("name") or _pretty(name), "lang": v["lang"],
                    "locale": v["locale"], "country": v["locale"].split("-")[-1],
                    "gender": (meta.get(vid) or {}).get("gender") or PIPER_GENDER.get(speaker) or "unknown",
                    "quality": "high" if extra.get("quality") == "high" else _quality(v["quality"]),
                    "offline": True, "installed": piper_installed(name), "mb": v["mb"],
                    "multi": v["speakers"] > 1, "speed": "fast"})
    kok = kokoro_installed()
    for n in KOKORO_NAMES:
        code, locale = KOKORO_LANG.get(n[0], ("", ""))
        if not code or (lang and locale.split("-")[0] != lang):
            continue
        out.append({"id": f"kokoro:{n}", "engine": "kokoro", "name": n.split("_", 1)[1].capitalize(),
                    "lang": locale.split("-")[0], "locale": locale, "country": locale.split("-")[1],
                    "gender": "female" if n[1] == "f" else "male", "quality": KOKORO_BEST.get(n, "standard"),
                    "offline": True, "installed": kok, "mb": KOKORO_MB, "shared_download": True, "speed": "fast"})
    cbx = cbx_python() is not None
    for code in CBX_LANGS:
        if lang and code != lang:
            continue
        out.append({"id": f"chatterbox:default@{code}", "engine": "chatterbox", "name": "Chatterbox",
                    "lang": code, "locale": f"{code}-{COUNTRY.get(code, code.upper())}", "country": COUNTRY.get(code, ""),
                    "gender": "female", "quality": "studio", "offline": True, "installed": cbx, "mb": 3500,
                    "shared_download": True, "emotion": True, "speed": "slow"})
        for ref in sorted(REFS_DIR.glob("*.wav")) if REFS_DIR.is_dir() else []:
            rid = f"chatterbox:ref-{ref.stem}@{code}"
            out.append({"id": rid, "engine": "chatterbox", "name": f"{ref.stem} ({code})", "lang": code,
                        "locale": f"{code}-{COUNTRY.get(code, code.upper())}", "country": COUNTRY.get(code, ""),
                        "gender": (meta.get(f"ref:{ref.stem}") or {}).get("gender") or "unknown", "quality": "studio",
                        "offline": True, "installed": cbx, "own": True, "emotion": True, "speed": "slow"})
    return out


# ------------------------------------------------------------------ install / remove
async def _download(url: str, target: Path, on=None) -> None:
    import httpx
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, read=120)) as c:
        async with c.stream("GET", url, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with part.open("wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if on and total:
                        on(done / total)
    part.replace(target)


PROGRESS: dict[str, dict] = {}  # id -> {state: downloading|installing|done|error, frac, error}


async def install(vid: str) -> dict:
    """Download a local voice (Piper: one model; Kokoro: the shared model + voice pack; Chatterbox: see
    install_chatterbox). Returns the voice entry."""
    engine, _, name = vid.partition(":")
    st = PROGRESS[vid] = {"state": "downloading", "frac": 0.0}

    def on(f: float) -> None:
        st["frac"] = round(f, 3)
    try:
        if engine == "piper":
            idx = await piper_index()
            v = idx.get(name)
            if not v:
                raise ValueError(f"unknown Piper voice {name}")
            m, c = piper_paths(name)
            await _download(v["config_url"], c)
            await _download(v["model_url"], m, on)
            st["state"] = "measuring"
            await measure_gender(vid)
        elif engine == "kokoro":
            for i, (fname, url) in enumerate(KOKORO_FILES.values()):
                if not (KOKORO_DIR / fname).exists():
                    await _download(url, KOKORO_DIR / fname, lambda f, i=i: on((i + f) / 2))
        elif engine == "chatterbox":
            await install_chatterbox(on)
        else:
            raise ValueError("this voice needs no download")
        st.update(state="done", frac=1.0)
    except Exception as e:
        st.update(state="error", error=str(e)[:300])
        raise
    return st


def remove(vid: str) -> None:
    engine, _, name = vid.partition(":")
    if engine == "piper":
        for p in piper_paths(name):
            p.unlink(missing_ok=True)
    elif engine == "kokoro":
        shutil.rmtree(KOKORO_DIR, ignore_errors=True)
    elif engine == "chatterbox":
        shutil.rmtree(CBX_DIR, ignore_errors=True)
    PROGRESS.pop(vid, None)


def _folder_mb(p: Path) -> float:
    total = 0
    for f in p.rglob("*") if p.exists() else []:
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total / 1e6


# ------------------------------------------------------------------ Chatterbox: its own environment
CBX_PACKAGES = ["chatterbox-tts"]


async def install_chatterbox(on=None) -> None:
    """A separate Python environment (uv) with PyTorch + Chatterbox: its pins (numpy<2, torch 2.6, transformers)
    would break the app's own packages. Then the model weights download once (first load)."""
    import sys
    CBX_DIR.mkdir(parents=True, exist_ok=True)
    (CBX_DIR / "ready").unlink(missing_ok=True)
    venv = CBX_DIR / "venv"
    uv = shutil.which("uv") or str(Path(sys.executable).parent / ("uv.exe" if sys.platform == "win32" else "uv"))

    async def run(*argv: str, frac: float) -> None:
        p = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.STDOUT, cwd=str(CBX_DIR))
        out, _ = await p.communicate()
        if p.returncode:
            raise RuntimeError(out.decode("utf-8", "replace")[-800:])
        if on:
            on(frac)
    async def watched(job, folder: Path, mb: float, lo: float, hi: float):
        """Progress while a step fills a folder (packages ~1.8 GB, model weights ~3.1 GB): its size against the
        expected size, so the bar moves instead of standing at one number for many minutes."""
        task = asyncio.ensure_future(job)
        while not task.done():
            await asyncio.sleep(2)
            if on:
                size = await asyncio.to_thread(_folder_mb, folder)
                on(lo + (hi - lo) * min(0.99, size / mb))
        return task.result()
    if not venv.exists():
        await run(uv, "venv", "--python", f"{sys.version_info.major}.{sys.version_info.minor}", str(venv), frac=0.03)
    py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    await watched(run(uv, "pip", "install", "--python", str(py), *CBX_PACKAGES, frac=0.35), venv, 1850, 0.03, 0.35)
    # first load downloads the weights (~3.1 GB) and proves the environment works
    from .engines import chatterbox_warmup
    await watched(chatterbox_warmup(py), CBX_DIR / "hf", 3070, 0.35, 0.99)
    (CBX_DIR / "ready").write_text("ok", encoding="utf-8")
    if on:
        on(1.0)


# ------------------------------------------------------------------ gender from pitch
def pitch_hz(samples, sr: int) -> float:
    """Median fundamental frequency of voiced frames (autocorrelation, 60-400 Hz). 0 when nothing is voiced."""
    import numpy as np
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    frame, hop = int(sr * 0.04), int(sr * 0.01)
    lo, hi = int(sr / 400), int(sr / 60)
    rms_all = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    f0 = []
    for i in range(0, len(x) - frame, hop):
        w = x[i:i + frame]
        if np.sqrt(np.mean(w ** 2)) < rms_all * 0.6:
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, "full")[frame - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        k = int(np.argmax(seg)) + lo
        if ac[k] / ac[0] > 0.45:
            f0.append(sr / k)
    return float(np.median(f0)) if len(f0) > 5 else 0.0


def gender_of(hz: float) -> str:
    return "unknown" if not hz else "male" if hz < 160 else "female"


SAMPLE = {"tr": "Merhaba, bu ses videolarınızı ve metinlerinizi seslendirecek.",
          "en": "Hello, this voice will narrate your videos and your texts."}


async def measure_gender(vid: str) -> str:
    from . import engines
    lang = vid.split(":", 1)[1][:2]
    try:
        samples, sr = await engines.synth(vid, SAMPLE.get(lang, SAMPLE["en"]), {})
        hz = pitch_hz(samples, sr)
    except Exception:  # noqa: BLE001
        return "unknown"
    m = _meta()
    m[vid] = {**(m.get(vid) or {}), "gender": gender_of(hz), "pitch_hz": round(hz)}
    _save_meta(m)
    return m[vid]["gender"]


def save_reference(name: str, wav: Path, gender_hz: float) -> str:
    m = _meta()
    m[f"ref:{name}"] = {"gender": gender_of(gender_hz), "pitch_hz": round(gender_hz), "consent": time.time()}
    _save_meta(m)
    return m[f"ref:{name}"]["gender"]
