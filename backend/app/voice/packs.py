"""Voice packs: local text-to-speech engines that each live in their own Python environment.

Every engine here has its own uv environment in data/tts/<env>/venv (engines that share a package, such as the
coqui-tts ones or the VoxCPM2 family, share one), so their pins (torch, numpy, transformers) never touch the app or
each other. uv picks the right PyTorch build for the computer (--torch-backend auto: CUDA on NVIDIA, CPU elsewhere),
so the same pack installs on any machine; what a pack needs is shown before it is installed.

A pack runs as one long-lived worker (pack_worker.py) that keeps its model loaded; idle workers are stopped.
Voice ids: "<engine>:<voice>", e.g. "seda:default", "pocket:female_1"."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import catalog

WORKER = Path(__file__).with_name("pack_worker.py")
CACHE = catalog.ROOT / ".uv-cache"  # on the same drive as the environments, so uv hard-links instead of copying

# tier: light = runs well on any CPU; medium = works on a CPU, a GPU makes it fast; gpu = needs an NVIDIA GPU.
# needs: cpu | gpu_better | cuda;  vram: GB the model needs on a GPU;  mb: download (packages + weights).
# commercial: False when the model's licence does not allow commercial use (shown on the card).
# coqui-tts needs torchcodec (and FFmpeg DLLs on Windows) for audio IO from PyTorch 2.9 on, so its env stays below.
COQUI = ["coqui-tts", "torch>=2.4,<2.9", "torchaudio>=2.4,<2.9", "six",  # six: imported, not declared
         "transformers>=4.57,<5"]  # XTTS's GPT breaks on transformers 5 (no legacy past_key_values)
PACKS: dict[str, dict] = {
    "seda": dict(name="Seda TTS", tier="light", env="seda", mb=420, needs="cpu", license="Apache-2.0",
                 commercial=True, repo="atasoglu/seda-tts-v0.1", pip=["sedalib[tts]>=1.4"], torch=False,
                 emotion=True, sr=22050, gender="female",
                 note="8 emotions + whisper, real time on one CPU thread"),
    "clarvia": dict(name="Clarvia Tiny", tier="light", env="clarvia", mb=120, needs="cpu", license="Apache-2.0",
                    commercial=True, repo="wite-tech/clarvia-tts-tiny", torch=False, sr=24000,
                    pip=["onnxruntime", "numpy", "soundfile", "huggingface_hub",
                         "clarvia-phonemizer @ git+https://huggingface.co/wite-tech/clarvia-phonemizer"],
                    note="4.5M parameters; reads numbers, dates, money and addresses"),
    "supertonic": dict(name="Supertonic 3", tier="light", env="supertonic", mb=450, needs="cpu",
                       license="OpenRAIL-M", commercial=True, repo="Supertone/supertonic-3", torch=False,
                       pip=["supertonic"], sr=44100, note="31 languages, fast on a CPU"),
    "ema": dict(name="EMA Lightning", tier="light", env="ema", mb=900, needs="cpu", license="Apache-2.0",
                commercial=True, repo="canberkkkkkk/ema-lightning", torch=True, pip=["ema-lightning==1.1.2"],
                sr=48000, note="48 kHz, very fast"),
    "ahenkcep": dict(name="Ahenk Cep", tier="light", env="ema", mb=40, needs="cpu", license="CC BY 4.0",
                     commercial=True, repo="ozgurguler/ahenk-cep-tr", torch=True, emotion=True, sr=48000,
                     gender="female",
                     pip=["ema-lightning==1.1.2", "soundfile", "huggingface_hub",
                          "trnorm @ git+https://github.com/ozguradmin/ahenk-turkish-tts"],
                     note="small EMA voice, one designed female voice"),
    "pocket": dict(name="Pocket TTS Türkçe", tier="light", env="pocket", mb=1300, needs="cpu", license="CC BY 4.0",
                   commercial=True, repo="wite-tech/pocket-tts-turkish", torch=True, emotion=True, clone=True,
                   sr=24000, pip=["pocket-tts-turkish"], note="voice cloning, 5 emotions, ~5x real time on a CPU"),
    "mms": dict(name="MMS-TTS (Meta)", tier="medium", env="mms", mb=1000, needs="cpu", license="CC BY-NC 4.0",
                commercial=False, repo="facebook/mms-tts-tur", torch=True, sr=16000,
                pip=["transformers>=4.40", "accelerate"], note="light VITS"),
    "turkvits": dict(name="Türkçe VITS", tier="medium", env="coqui", mb=1400, needs="cpu", license="Apache-2.0",
                     commercial=True, repo="Kur0Keri/turkce-tts-vits", torch=True, sr=16000,
                     pip=COQUI, warn="data_rights",
                     note="audiobook narrator voice; the training data's rights were not cleared by its owner"),
    "openbible": dict(name="VITS OpenBible", tier="medium", env="coqui", mb=1000, needs="cpu",
                      license="CC BY-SA 4.0", commercial=True, repo="multilingual-tts/VITS-OpenBible-Turkish",
                      torch=True, sr=22050, pip=COQUI, note="several narrator voices"),
    "xtts": dict(name="XTTS v2 (Coqui)", tier="medium", env="coqui", mb=2000, needs="gpu_better",
                 license="Coqui CPML", commercial=False, repo="coqui/XTTS-v2", torch=True, clone=True, sr=24000,
                 pip=COQUI, terms="https://coqui.ai/cpml", note="voice cloning, 17 languages"),
    "anka": dict(name="Anka TTS", tier="medium", env="anka", mb=3000, needs="gpu_better", license="CC BY-NC 4.0",
                 commercial=False, repo="krmkayabasi/Anka-TTS", torch=True, clone=True, ref_text=True, sr=24000,
                 pip=["anka-tts[tts]"], note="F5-TTS, two voices + voice cloning"),
    "freya": dict(name="Freya TTS", tier="medium", env="freya", mb=2300, needs="gpu_better", license="Apache-2.0",
                  commercial=True, repo="freyavoice/Freya-TTS", torch=True, sr=48000,
                  pip=["einops", "librosa", "safetensors", "voxcpm", "soundfile"],
                  note="48 kHz, one natural voice"),
    "drifting": dict(name="Drifting TTS", tier="medium", env="drifting", mb=2200, needs="gpu_better",
                     license="CC BY 4.0", commercial=True, repo="Vyvo/drifting-tts-tr-dacvae", torch=True, sr=24000,
                     pip=["drifting-tts[dacvae] @ git+https://github.com/kadirnar/drifting-tts"],
                     note="one-step generation, studio / female / male"),
    "kizagan": dict(name="Kızagan", tier="gpu", env="voxcpm", mb=7500, needs="cuda", vram=8, license="Apache-2.0",
                    commercial=True, repo="AlicanKiraz0/Kizagan-TTS-v1.0", torch=True, clone=True, emotion=True,
                    sr=48000, pip=["voxcpm", "soundfile"], note="VoxCPM2, 48 kHz studio voice"),
    "trendyol": dict(name="Trendyol TTS", tier="gpu", env="voxcpm", mb=5000, needs="cuda", vram=8, license="MIT",
                     commercial=True, repo="Trendyol/Trendyol-TTS", torch=True, emotion=True, sr=48000,
                     pip=["voxcpm", "soundfile"], note="VoxCPM2, 48 kHz"),
    "ahenk": dict(name="Ahenk TTS", tier="gpu", env="voxcpm", mb=5100, needs="cuda", vram=8, license="CC BY 4.0",
                  commercial=True, repo="ozgurguler/ahenk-tts-tr", torch=True, emotion=True, sr=48000,
                  pip=["voxcpm", "soundfile", "scipy",
                       "trnorm @ git+https://github.com/ozguradmin/ahenk-turkish-tts"],
                  note="VoxCPM2 + LoRA, emotional designed voice"),
    "nefes": dict(name="Nefes 0.5", tier="gpu", env="nefes", mb=5200, needs="cuda", vram=16, license="Apache-2.0",
                  commercial=True, repo="alicangunduz/nefes-0.5", torch=True, emotion=True, sr=48000,
                  pip=["nefes-tts @ git+https://huggingface.co/alicangunduz/nefes-0.5"],
                  note="[gül] [iç çek] [fısılda] tags in the text"),
    "fish": dict(name="Fish S2 Pro", tier="gpu", env="fish", mb=13000, needs="cuda", vram=24,
                 license="Fish Audio Research", commercial=False, repo="fishaudio/s2-pro", torch=True, emotion=True,
                 sr=44100, pip=["fish-speech @ git+https://github.com/fishaudio/fish-speech", "ormsgpack"],
                 note="80+ languages, inline emotion control; research use only"),
}
TIERS = ("light", "medium", "gpu")


def pack_of(vid: str) -> str | None:
    e = vid.split(":", 1)[0]
    return e if e in PACKS else None


def env_dir(engine: str) -> Path:
    return catalog.ROOT / PACKS[engine]["env"]


def py_of(engine: str) -> Path:
    v = env_dir(engine) / "venv"
    return v / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def ready_file(engine: str) -> Path:
    return env_dir(engine) / f"{engine}.ready.json"


def info(engine: str) -> dict | None:
    """The facts written after a working install: voices, moods, sample rate, device."""
    try:
        return json.loads(ready_file(engine).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def installed(engine: str) -> bool:
    return py_of(engine).exists() and info(engine) is not None


# ---------------------------------------------------------------- hardware (general: any computer)
_HW: dict | None = None


def hardware() -> dict:
    """{cuda, vram_gb, mps}: what the computer offers the packs. NVIDIA through nvidia-smi; Apple MPS on arm Macs."""
    global _HW
    if _HW is not None:
        return _HW
    hw = {"cuda": False, "vram_gb": 0.0, "mps": sys.platform == "darwin" and os.uname().machine == "arm64"
          if hasattr(os, "uname") else False}
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            out = subprocess.run([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10, creationflags=flags).stdout
            mb = max((float(x) for x in out.split() if x.strip().replace(".", "").isdigit()), default=0)
            hw.update(cuda=mb > 0, vram_gb=round(mb / 1024, 1))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    _HW = hw
    return hw


def fit(engine: str) -> dict:
    """Can this computer run the pack? ok: yes; slow: works, but a GPU makes it practical; no: it cannot."""
    p, hw = PACKS[engine], hardware()
    if p["needs"] == "cuda":
        if not hw["cuda"]:
            return {"state": "no", "reason": "needs_cuda", "vram": p.get("vram", 0)}
        if hw["vram_gb"] and hw["vram_gb"] + 0.5 < p.get("vram", 0):
            return {"state": "no", "reason": "low_vram", "vram": p.get("vram", 0), "have": hw["vram_gb"]}
        return {"state": "ok"}
    if p["needs"] == "gpu_better" and not (hw["cuda"] or hw["mps"]):
        return {"state": "slow", "reason": "cpu_slow"}
    return {"state": "ok"}


# ---------------------------------------------------------------- workers
class Worker:
    """One process per engine that keeps its model loaded. Stopped after IDLE seconds without a request."""
    IDLE = 600

    def __init__(self, engine: str) -> None:
        self.engine = engine
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.last = 0.0

    def ask(self, req: dict, timeout: float = 900) -> dict:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                py = py_of(self.engine)
                if not py.exists():
                    raise RuntimeError(f"voice pack not installed: {self.engine}")
                make_room(self.engine)
                _reaper()
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                log = (env_dir(self.engine) / f"{self.engine}.log").open("ab")
                self.proc = subprocess.Popen([str(py), "-u", str(WORKER), self.engine], stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
                                             creationflags=flags, cwd=str(env_dir(self.engine)), env=worker_env(self.engine))
            assert self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            box: list[str] = []
            t = threading.Thread(target=lambda: box.append(self.proc.stdout.readline()), daemon=True)
            t.start()
            t.join(timeout)
            self.last = time.time()
            if not box or not box[0]:
                self.stop()
                raise RuntimeError(f"{self.engine} did not answer (timed out or stopped); see {self.engine}.log")
            ans = json.loads(box[0])
            self.ram = max(getattr(self, "ram", 0.0), self.used_gb())
            RAM_SEEN[self.engine] = max(RAM_SEEN.get(self.engine, 0.0), self.ram)
            if not ans.get("ok"):
                raise RuntimeError(f"{self.engine}: {ans.get('error')}")
            return ans

    def used_gb(self) -> float:
        """Memory of the worker and its children (a venv's python.exe starts the real interpreter as a child)."""
        try:
            import psutil
            p = psutil.Process(self.proc.pid)
            return sum(x.memory_info().rss for x in [p, *p.children(recursive=True)]) / 1e9
        except Exception:  # noqa: BLE001
            return 0.0

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


WORKERS: dict[str, Worker] = {}


def worker(engine: str) -> Worker:
    w = WORKERS.get(engine)
    if not w:
        w = WORKERS[engine] = Worker(engine)
    return w


def stop_idle() -> None:
    """Free the memory of packs nobody used for a while (the next request loads the model again)."""
    now = time.time()
    for w in WORKERS.values():
        if w.proc and now - w.last > Worker.IDLE and not w.lock.locked():
            w.stop()


RAM_SEEN: dict[str, float] = {}  # engine -> GB its worker really used (measured after each answer)
HEADROOM_GB = 1.5  # left free for the system, the app and the browser
MAX_LOADED = 3  # models kept loaded at once; the least recently used idle one goes first


def ram_need(engine: str) -> float:
    """GB a pack's worker needs: what it used before on this computer, else an estimate from its download."""
    if RAM_SEEN.get(engine):
        return RAM_SEEN[engine]
    p = PACKS[engine]
    weights = max(0.1, (p["mb"] - (1700 if p.get("torch") else 150)) / 1000)
    return round(max(0.6, weights * 2.0 + (0.6 if p.get("torch") else 0.2)), 1)


def free_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:  # noqa: BLE001
        return 99.0


def make_room(engine: str) -> None:
    """Before a model loads: close idle models (least recently used first) while memory is short or more than
    MAX_LOADED are loaded. A model that still does not fit is refused with a clear message: several big models at
    once exhausted the memory of a 32 GB computer and ended in a blue screen."""
    need = ram_need(engine)
    idle = sorted((w for w in WORKERS.values() if w.engine != engine and w.proc and w.proc.poll() is None
                   and not w.lock.locked()), key=lambda w: w.last)
    loaded = sum(1 for w in WORKERS.values() if w.proc and w.proc.poll() is None)
    for w in idle:
        if free_gb() >= need + HEADROOM_GB and loaded < MAX_LOADED:
            break
        w.stop()
        loaded -= 1
        time.sleep(0.5)  # the system takes the memory back
    have = free_gb()
    if have < need + HEADROOM_GB * 0.5:
        raise RuntimeError(f"not enough free memory for {PACKS[engine]['name']}: it needs ~{need:.1f} GB, "
                           f"{have:.1f} GB is free. Close other programs or pick a lighter voice.")


_REAPER: list[threading.Thread] = []


def _reaper() -> None:
    """Idle models are closed in the background too, not only when the voice list is opened."""
    if _REAPER and _REAPER[0].is_alive():
        return

    def loop() -> None:
        while any(w.proc for w in WORKERS.values()):
            time.sleep(60)
            stop_idle()
    t = threading.Thread(target=loop, daemon=True, name="voice-pack-reaper")
    _REAPER[:] = [t]
    t.start()


def worker_env(engine: str) -> dict:
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
            "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG", "SSL_CERT_FILE",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "CUDA_VISIBLE_DEVICES")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(HF_HOME=str(env_dir(engine) / "hf"), HF_HUB_DISABLE_XET="1", HF_HUB_DOWNLOAD_TIMEOUT="60",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1", TOKENIZERS_PARALLELISM="false",
               HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
               ANKA_HOME=str(env_dir(engine) / "anka-home"))  # engines keep their files in the pack, not the home
    return env


def synth(engine: str, voice: str, text: str, opts: dict):
    """Text -> (samples, sr) through the engine's worker."""
    from .engines import read_wav
    out = env_dir(engine) / "out" / f"{engine}-{threading.get_ident()}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    ref = ""
    if voice.startswith("ref-"):
        p = catalog.REFS_DIR / f"{voice[4:]}.wav"
        if not p.exists():
            raise RuntimeError(f"reference clip missing: {p.name}")
        ref = str(p)
    mood = opts.get("mood") or (opts.get("moods") or {}).get(engine) or ""
    worker(engine).ask({"cmd": "say", "text": text, "voice": voice, "mood": mood,
                        "rate": float(opts.get("rate") or 1.0), "ref": ref,
                        "ref_text": ref_text(Path(ref)) if ref and PACKS[engine].get("ref_text") else "",
                        "out": str(out)})
    x, sr = read_wav(out)
    if not ref and len(text) >= 20:
        _learn_gender(engine, voice, x, sr)
    return x, sr


def _learn_gender(engine: str, voice: str, x, sr: int) -> None:
    """A voice installed without a measured gender (big speaker lists on a slow computer) gets one the first time
    it speaks a real sentence, so the "?" in the voice lists fills in by itself."""
    f = ready_file(engine)
    try:
        facts = json.loads(f.read_text(encoding="utf-8"))
        v = next((v for v in facts.get("voices", []) if v.get("name") == voice), None)
        if not v or v.get("gender"):
            return
        hz = catalog.pitch_hz(x, sr)
        if not hz:
            return
        v["gender"], v["pitch_hz"] = catalog.gender_of(hz), round(hz)
        v.pop("error", None)
        f.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass


def ref_text(wav: Path) -> str:
    """What is said in a reference clip (F5-TTS style engines need it): transcribed once with the app's own
    faster-whisper and kept next to the clip as <name>.txt."""
    txt = wav.with_suffix(".txt")
    if txt.exists() and txt.stat().st_mtime >= wav.stat().st_mtime:
        return txt.read_text(encoding="utf-8").strip()
    from ..tools.speech import _transcribe
    segs, _ = _transcribe(wav, "small", None, 0)
    text = " ".join(t for _, _, t in segs).strip()
    txt.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------- install
def uv_exe() -> str:
    return shutil.which("uv") or str(Path(sys.executable).parent / ("uv.exe" if sys.platform == "win32" else "uv"))


async def _run(argv: list[str], cwd: Path, env: dict | None = None, log: Path | None = None) -> str:
    p = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                             cwd=str(cwd), env=env)
    out, _ = await p.communicate()
    text = out.decode("utf-8", "replace")
    if log:
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n$ {' '.join(argv)}\n{text}")
    if p.returncode:
        raise RuntimeError(text[-1200:])
    return text


def _folder_mb(p: Path) -> float:
    total = 0
    for f in p.rglob("*") if p.exists() else []:
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total / 1e6


async def install(engine: str, on=None, force: bool = False) -> dict:
    """Environment (uv, the app's Python version) -> packages (PyTorch build picked for this computer) -> first load,
    which downloads the weights and proves the engine speaks -> voices, moods and measured genders saved."""
    if engine not in PACKS:
        raise ValueError(f"unknown voice pack {engine}")
    p = PACKS[engine]
    if fit(engine)["state"] == "no" and not force:  # force: try it on the CPU anyway (tests; very slow)
        raise RuntimeError(f"{p['name']} cannot run on this computer: {fit(engine)['reason']}")
    d = env_dir(engine)
    d.mkdir(parents=True, exist_ok=True)
    ready_file(engine).unlink(missing_ok=True)
    log = d / f"{engine}.log"
    env = {**os.environ, "UV_CACHE_DIR": str(CACHE), "UV_TORCH_BACKEND": "auto", "UV_LINK_MODE": "hardlink",
           "PYTHONUTF8": "1"}

    def step(f: float) -> None:
        if on:
            on(round(min(0.99, f), 3))

    async def watched(job, folder: Path, mb: float, lo: float, hi: float):
        task = asyncio.ensure_future(job)
        while not task.done():
            await asyncio.sleep(2)
            size = await asyncio.to_thread(_folder_mb, folder)
            step(lo + (hi - lo) * min(0.99, size / max(mb, 1)))
        return task.result()

    venv = d / "venv"
    uv = uv_exe()
    if not py_of(engine).exists():
        await _run([uv, "venv", "--python", f"{sys.version_info.major}.{sys.version_info.minor}", str(venv)], d,
                   env, log)
    step(0.03)
    pkgs = list(p["pip"]) + ["huggingface_hub", "numpy", "soundfile"]
    if p.get("torch") and not any(str(x).startswith("torch") for x in pkgs):
        pkgs += ["torch", "torchaudio"]  # some engines leave PyTorch out of their own requirements
    pkg_mb = 1700 if p.get("torch") else 150
    await watched(_run([uv, "pip", "install", "--python", str(py_of(engine)), *pkgs], d, env, log), venv,
                  pkg_mb, 0.03, 0.45)
    w = worker(engine)
    w.stop()
    weights = max(50, p["mb"] - pkg_mb)
    ans = await watched(asyncio.to_thread(w.ask, {"cmd": "voices"}, 7200), d / "hf", weights, 0.45, 0.9)
    facts = {"voices": ans.get("voices") or [], "moods": ans.get("moods") or [], "sr": ans.get("sr"),
             "device": ans.get("device"), "at": time.time()}
    # one real sentence proves the engine speaks, and the voices without a known gender are measured
    t0 = time.time()
    for i, v in enumerate(facts["voices"]):
        if v.get("gender"):
            continue
        if i >= 12 and time.time() - t0 > 600:  # big speaker lists: the rest stay "unknown" on a slow computer
            break
        try:
            x, sr = await asyncio.to_thread(synth, engine, v["name"], catalog.SAMPLE["tr"], {})
            hz = catalog.pitch_hz(x, sr)
            v["gender"], v["pitch_hz"] = catalog.gender_of(hz), round(hz)
        except Exception as e:  # noqa: BLE001
            v["error"] = str(e)[:200]
    if facts["voices"] and all(v.get("error") for v in facts["voices"][:12]):
        raise RuntimeError(f"{p['name']} installed but could not speak: {facts['voices'][0]['error']}")
    ready_file(engine).write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    step(1.0)
    return facts


def remove(engine: str) -> None:
    """Remove a pack; its environment goes too when no other installed pack shares it."""
    worker(engine).stop()
    ready_file(engine).unlink(missing_ok=True)
    env = PACKS[engine]["env"]
    if not any(installed(e) for e, p in PACKS.items() if p["env"] == env and e != engine):
        for e, p in PACKS.items():
            if p["env"] == env:
                worker(e).stop()
        shutil.rmtree(env_dir(engine), ignore_errors=True)


# ---------------------------------------------------------------- catalog entries
def voices(lang: str = "") -> list[dict]:
    """One entry per installed voice, or one per pack that is not installed yet (lang: only Turkish packs, except
    Supertonic / XTTS / Fish which speak many languages but are listed under Turkish here)."""
    if lang and lang != "tr":
        return []
    out = []
    for e, p in PACKS.items():
        facts = info(e) if installed(e) else None
        base = {"engine": e, "pack": e, "pack_name": p["name"], "lang": "tr", "locale": "tr-TR", "country": "TR", "offline": True,
                "quality": "studio" if p["tier"] == "gpu" else "high", "tier": p["tier"], "license": p["license"],
                "commercial": p["commercial"], "needs": p["needs"], "fit": fit(e), "mb": p["mb"],
                "emotion": bool(p.get("emotion")), "clone": bool(p.get("clone")), "warn": p.get("warn", ""),
                "terms": p.get("terms", ""), "note": p["note"], "shared_download": True,
                "speed": "fast" if p["tier"] == "light" else "slow"}
        if not facts:
            out.append({**base, "id": f"{e}:default", "name": p["name"], "gender": p.get("gender", "unknown"),
                        "installed": False})
            continue
        for v in facts["voices"]:
            if v.get("error"):
                continue
            label = p["name"] if v["name"] == "default" else f"{p['name']} · {v['name']}"
            out.append({**base, "id": f"{e}:{v['name']}", "name": label, "gender": v.get("gender") or "unknown",
                        "installed": True, "moods": facts.get("moods") or []})
        if p.get("clone"):
            meta = catalog._meta()
            for ref in catalog.own_refs():
                out.append({**base, "id": f"{e}:ref-{ref.stem}", "name": f"{ref.stem} · {p['name']}",
                            "gender": (meta.get(f"ref:{ref.stem}") or {}).get("gender") or "unknown",
                            "installed": True, "own": True})
    return out
