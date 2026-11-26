"""Runs INSIDE one engine's own environment (data/tts/<engine>/venv), never in the app's Python.

    python pack_worker.py <engine>

One JSON request per stdin line -> one JSON answer per stdout line; the model stays loaded between requests.
  {"cmd": "say", "text": "...", "voice": "female_1", "mood": "", "rate": 1.0, "ref": "", "out": "x.wav"}
  {"cmd": "voices"}  -> {"ok": true, "voices": [{"name": .., "gender": ..}], "moods": [..], "sr": ..}
Each adapter imports its package lazily, so this file has no dependency of its own (numpy comes with every engine).
Text arrives already split into sentences by the app (render.py)."""
from __future__ import annotations

import json
import os
import sys
import wave

ENGINE = sys.argv[1] if len(sys.argv) > 1 else ""


def device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001 - ONNX-only engines have no torch
        pass
    return "cpu"


def to_np(x):
    import numpy as np
    if hasattr(x, "detach"):
        x = x.detach().float().cpu().numpy()
    x = np.asarray(x, dtype=np.float32)
    if x.ndim > 1:  # (1, n), (n, 1) or (channels, n)
        x = x.reshape(-1) if 1 in x.shape else x.mean(axis=0 if x.shape[0] < x.shape[1] else 1)
    return x


def write_wav(path: str, x, sr: int) -> None:
    import numpy as np
    pcm = (np.clip(to_np(x), -1, 1) * 32767).astype("int16").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm)


def snapshot(repo: str, **kw) -> str:
    from huggingface_hub import snapshot_download
    return snapshot_download(repo, **kw)


def github_src(repo: str, branch: str = "main") -> str:
    """A GitHub repository's source, downloaded once as a zip into the pack folder (no git needed on the computer).
    Returns its folder; the caller puts it on sys.path or runs from it."""
    import io
    import shutil
    import urllib.request
    import zipfile
    dest = os.path.join(os.getcwd(), repo.split("/")[-1])
    if os.path.isdir(dest) and os.listdir(dest):
        return dest
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    tmp = dest + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(tmp)
    inner = os.path.join(tmp, os.listdir(tmp)[0])
    shutil.move(inner, dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return dest


def _voxcpm_compat() -> None:
    """Engines written for another VoxCPM release pass arguments the installed one does not take (Nefes passes
    seed=...): seed becomes torch.manual_seed (same reproducible take), other unknown arguments are dropped."""
    import inspect

    import torch
    import voxcpm
    cls = getattr(voxcpm, "VoxCPM", None)
    if not cls or getattr(cls, "_aiiq_compat", False):
        return
    for name in ("generate", "_generate"):
        fn = getattr(cls, name, None)
        if not fn:
            continue
        params = inspect.signature(fn).parameters
        if any(p.kind == p.VAR_KEYWORD for p in params.values()):
            continue

        def wrap(self, *a, _fn=fn, _ok=set(params), **kw):
            if "seed" in kw and "seed" not in _ok:
                s = kw.pop("seed")
                if s is not None:
                    torch.manual_seed(int(s))
            return _fn(self, *a, **{k: v for k, v in kw.items() if k in _ok})
        setattr(cls, name, wrap)
    cls._aiiq_compat = True


def call(fn, *args, **kw):
    """Call with the keyword arguments the function accepts (packages differ in what they take)."""
    import inspect
    try:
        params = inspect.signature(fn).parameters
        if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
            kw = {k: v for k, v in kw.items() if k in params}
    except (TypeError, ValueError):
        pass
    return fn(*args, **kw)


# ---------------------------------------------------------------- adapters
class Base:
    sr = 24000
    moods: list[str] = []

    def voices(self) -> list[dict]:
        return [{"name": "default", "gender": ""}]

    def say(self, text: str, voice: str, mood: str, rate: float, ref: str):
        raise NotImplementedError


class Seda(Base):
    def __init__(self):
        from sedalib import Synthesizer
        self.m = Synthesizer.from_pretrained()
        self.sr = int(self.m.sample_rate)
        styles = list(getattr(self.m, "styles", None) or ["normal"])
        self.moods = [f"{s}/{e}" if s != "normal" else e for s in styles for e in self.m.emotions_for(s)]

    def voices(self):
        names = list(getattr(self.m, "speakers", None) or getattr(self.m, "voices", None) or [])
        return [{"name": str(n), "gender": ""} for n in names] or [{"name": "default", "gender": "female"}]

    def say(self, text, voice, mood, rate, ref):
        style, _, emo = mood.rpartition("/") if "/" in mood else ("normal", "", mood)
        kw = {"style": style or "normal"}
        if emo:
            kw["emotion"] = emo
        if voice and voice != "default":
            kw["speaker"] = voice
        if rate and rate != 1.0:
            kw["length_scale"] = 1.0 / rate
        return call(self.m.synthesize, text, **kw)


class Clarvia(Base):
    def __init__(self):
        d = snapshot("wite-tech/clarvia-tts-tiny")
        sys.path.insert(0, d)
        cwd = os.getcwd()
        os.chdir(d)  # speak.py reads config.json / onnx/model.onnx relative to its folder
        try:
            from speak import ClarviaTiny
            self.m = ClarviaTiny()
        finally:
            os.chdir(cwd)
        self.sr = int(self.m.config["sample_rate"])

    def voices(self):
        cfg = self.m.config
        names = list((cfg.get("voices") or cfg.get("speakers") or {}))
        names = names or [f"{g}_{i}" for g in ("female", "male") for i in (1, 2)]
        return [{"name": n, "gender": "female" if n.startswith("f") else "male" if n.startswith("m") else ""}
                for n in names]

    def say(self, text, voice, mood, rate, ref):
        return self.m.speak(text, voice=voice if voice and voice != "default" else self.voices()[0]["name"],
                            speed=rate or 1.0)


class Supertonic(Base):
    def __init__(self):
        from supertonic import TTS
        self.m = TTS(auto_download=True)
        self.sr = int(getattr(self.m, "sample_rate", 0) or getattr(self.m, "sr", 0) or 44100)
        self.style = {}

    def voices(self):
        names = list(getattr(self.m, "voice_names", None) or getattr(self.m, "voices", None) or [])
        names = [str(n) for n in names] or ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]
        return [{"name": n, "gender": "female" if n.upper().startswith("F") else "male"} for n in names]

    def say(self, text, voice, mood, rate, ref):
        v = voice if voice and voice != "default" else "F1"
        if v not in self.style:
            self.style[v] = self.m.get_voice_style(voice_name=v)
        out = call(self.m.synthesize, text, voice_style=self.style[v], lang="tr", speed=rate or 1.0)
        return out[0] if isinstance(out, tuple) else out


class Ema(Base):
    def __init__(self):
        from ema_lightning import EMA
        self.m = call(EMA, device=device())
        self.sr = 48000

    def voices(self):
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        sp = call(self.m.say, text, speed=rate or 1.0)
        self.sr = int(getattr(sp, "sample_rate", self.sr))
        return sp.audio


class AhenkCep(Base):
    def __init__(self):
        d = snapshot("ozgurguler/ahenk-cep-tr", allow_patterns=["*.pt", "*.py", "config.json"])
        sys.path.insert(0, d)
        from ahenk_cep import AhenkCep as A
        self.m = call(A, f"{d}/student.pt", f"{d}/decoder.pt", device=device())
        self.moods = list(getattr(self.m, "styles", None) or ["neutral", "happy", "sad", "angry", "calm"])
        self.sr = 48000

    def voices(self):
        return [{"name": "f022", "gender": "female"}]

    def say(self, text, voice, mood, rate, ref):
        kw = {"style": mood} if mood else {}
        audio, sr = call(self.m.say, text, **kw)
        self.sr = int(sr)
        return audio


class Pocket(Base):
    moods = ["mutlu", "üzgün", "kızgın", "şaşkın", "sakin"]

    def __init__(self):
        from pocket_tts_turkish import TurkishTTS
        self.m = TurkishTTS.from_pretrained()
        self.sr = int(self.m.sample_rate)
        self.refs = {}

    def voices(self):
        names = list(getattr(self.m, "voices", None) or getattr(self.m, "voice_names", None) or [])
        names = [str(n) for n in names] or ["female_1", "female_2", "female_3", "male_1", "male_2"]
        return [{"name": n, "gender": "female" if n.startswith("f") else "male"} for n in names]

    def say(self, text, voice, mood, rate, ref):
        if ref:
            if ref not in self.refs:
                self.refs[ref] = self.m.voice_from_file(ref)
            v = self.refs[ref]
        else:
            v = voice if voice and voice != "default" else "female_1"
        kw = {"emotion": mood} if mood else {}
        return call(self.m.generate, text, voice=v, **kw)


class Anka(Base):
    def __init__(self):
        from anka import AnkaTTS
        self.m = AnkaTTS.from_pretrained("anka-tts/v0.1", device=device())
        self.sr = int(getattr(self.m, "sample_rate", 24000))

    def voices(self):
        return [{"name": "male", "gender": "male"}, {"name": "female", "gender": "female"}]

    def say(self, text, voice, mood, rate, ref):
        if ref:  # the clip and its transcript go straight in: nothing is registered in the user's home folder
            return call(self.m.synthesize, text, ref_audio=ref, ref_text=getattr(self, "ref_text", "") or None,
                        speed=rate or 1.0, validate_reference=False)
        v = voice if voice in ("male", "female") else "male"
        return call(self.m.synthesize, text, voice=v, speed=rate or 1.0)


class Freya(Base):
    def __init__(self):
        sys.path.insert(0, github_src("freyavoiceai/FreyaTTS"))  # inference code is not on PyPI
        from freyatts import FreyaTTS
        self.m = FreyaTTS.from_pretrained("freyavoice/freya-tts", device=device())
        self.sr = int(getattr(self.m, "sample_rate", 48000))

    def voices(self):
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        return self.m.synthesize(text)


class Drifting(Base):
    def __init__(self):
        from huggingface_hub import hf_hub_download
        from drifting_tts.synthesize import Synthesizer
        repo = "Vyvo/drifting-tts-tr-dacvae"
        self.m = Synthesizer(hf_hub_download(repo, "drifting_tts_dacvae_10k.pt"), device(),
                             vocoder=hf_hub_download(repo, "dacvae_decoder_ft.pt"))
        self.sr = 24000

    def voices(self):
        return [{"name": "studio", "gender": ""}, {"name": "female", "gender": "female"},
                {"name": "male", "gender": "male"}]

    def say(self, text, voice, mood, rate, ref):
        wav, info = self.m(text, speaker=voice if voice in ("studio", "male", "female") else "studio", seed=0)
        if isinstance(info, dict) and info.get("sample_rate"):
            self.sr = int(info["sample_rate"])
        return wav


class Mms(Base):
    def __init__(self):
        from transformers import AutoTokenizer, VitsModel
        self.model = VitsModel.from_pretrained("facebook/mms-tts-tur")
        self.tok = AutoTokenizer.from_pretrained("facebook/mms-tts-tur")
        self.sr = int(self.model.config.sampling_rate)

    def voices(self):
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        import torch
        self.model.speaking_rate = float(rate or 1.0)
        with torch.no_grad():
            return self.model(**self.tok(text.lower(), return_tensors="pt")).waveform


class Coqui(Base):
    """Shared by the coqui-tts engines: XTTS v2, VITS OpenBible, Turkish VITS (Kur0Keri)."""

    def __init__(self):
        os.environ.setdefault("COQUI_TOS_AGREED", "1")  # the user agreed to the CPML when installing XTTS
        self.kind = ENGINE
        dev = device()
        if ENGINE == "xtts":
            from TTS.api import TTS
            self.m = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dev)
            self.sr = int(self.m.synthesizer.output_sample_rate)
        elif ENGINE == "openbible":
            from huggingface_hub import hf_hub_download
            from TTS.tts.utils.speakers import SpeakerManager
            from TTS.utils.synthesizer import Synthesizer
            repo = "multilingual-tts/VITS-OpenBible-Turkish"
            spk = hf_hub_download(repo, "speakers.pth")
            self.m = Synthesizer(tts_checkpoint=hf_hub_download(repo, "model_last.pth"),
                                 tts_config_path=hf_hub_download(repo, "config.json"), tts_speakers_file=spk,
                                 use_cuda=dev == "cuda")
            if self.m.tts_model.speaker_manager is None:
                self.m.tts_model.speaker_manager = SpeakerManager(speaker_id_file_path=spk)
            self.sr = int(self.m.output_sample_rate)
        else:  # turkvits
            d = snapshot("Kur0Keri/turkce-tts-vits")
            sys.path.insert(0, d)
            cwd = os.getcwd()
            os.chdir(d)
            try:
                import speak
                self.speak = speak
                self.m = call(speak.load, cuda=dev == "cuda")
            finally:
                os.chdir(cwd)
            self.sr = int(getattr(self.m, "output_sample_rate", 16000))

    def voices(self):
        if self.kind == "xtts":
            names = sorted(getattr(self.m, "speakers", None) or [])
            return [{"name": n, "gender": ""} for n in names] or [{"name": "Ana Florence", "gender": "female"}]
        if self.kind == "openbible":
            return [{"name": n, "gender": ""} for n in sorted(self.m.tts_model.speaker_manager.speaker_names)]
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        if self.kind == "xtts":
            kw = {"speaker_wav": ref} if ref else {"speaker": voice if voice and voice != "default" else
                                                   self.voices()[0]["name"]}
            return call(self.m.tts, text=text, language="tr", speed=rate or 1.0, **kw)
        if self.kind == "openbible":
            v = voice if voice and voice != "default" else self.voices()[0]["name"]
            return self.m.tts(text=text, speaker_name=v, split_sentences=False)
        import torch
        torch.manual_seed(0)
        return self.m.tts(self.speak.normalize(text), speaker_name=self.speak.VOICE)


class VoxCpm(Base):
    """VoxCPM2 family: Kizagan, Trendyol-TTS (merged models), Ahenk (LoRA on VoxCPM2)."""
    REPO = {"kizagan": "AlicanKiraz0/Kizagan-TTS-v1.0", "trendyol": "Trendyol/Trendyol-TTS"}
    moods = ["neutral", "happy", "sad", "angry", "calm", "excited", "whisper"]

    def __init__(self):
        from voxcpm import VoxCPM
        dev = device()
        if ENGINE == "ahenk":
            from voxcpm.model.voxcpm import LoRAConfig
            d = snapshot("ozgurguler/ahenk-tts-tr", allow_patterns=["lora_*", "*.py", "instructions_tr.json",
                                                                    "config.json"])
            sys.path.insert(0, d)
            cfg = json.loads(open(os.path.join(d, "lora_config.json"), encoding="utf-8").read())["lora_config"]
            self.m = call(VoxCPM.from_pretrained, "openbmb/VoxCPM2", load_denoiser=False, optimize=False,
                          lora_config=LoRAConfig(**cfg), lora_weights_path=d, device=dev)
            from instruction_pick import compose, pick
            self.pick, self.compose = pick, compose
        else:
            d = snapshot(self.REPO[ENGINE])
            self.m = call(VoxCPM.from_pretrained, d, device=dev, load_denoiser=False, optimize=False)
        self.sr = int(self.m.tts_model.sample_rate)

    def voices(self):
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        kw = dict(cfg_value=2.0, inference_timesteps=10 if device() == "cpu" else 16, normalize=ENGINE != "ahenk")
        if ENGINE == "ahenk":
            try:
                from trnorm import normalize
                text = normalize(text)
            except Exception:  # noqa: BLE001
                pass
            instruction, model_text, _ = self.pick(mood or "", text, "auto")
            text = self.compose(instruction, model_text)
        elif mood and mood != "neutral":
            text = f"({mood}){text}"
        if ref:
            kw["reference_wav_path"] = ref
        return call(self.m.generate, text=text, **kw)


class Nefes(Base):
    def __init__(self):
        import torch
        if device() != "cuda":  # its checkpoints were saved on a GPU and are loaded without map_location
            _load = torch.load
            torch.load = lambda *a, **k: _load(*a, **{"map_location": "cpu", **k})
        _voxcpm_compat()
        from nefes import Nefes as N
        self.m = call(N.from_pretrained, "alicangunduz/nefes-0.5", device=device())
        self.sr = 48000

    def voices(self):
        return [{"name": "default", "gender": ""}]

    def say(self, text, voice, mood, rate, ref):
        wav, sr = self.m.say(text)
        self.sr = int(sr)
        return wav


class Fish(Base):
    """Fish Audio S2 Pro through fish-speech's own API server (tools/api_server.py of its repository), started by
    this worker on a free local port and stopped with it. Runs best on a big NVIDIA GPU; the CPU works, slowly."""
    moods = ["(happy)", "(sad)", "(angry)", "(excited)", "(calm)", "(whispering)", "(laughing)"]

    def __init__(self):
        import atexit
        import socket
        import subprocess
        import time
        import urllib.request
        repo = github_src("fishaudio/fish-speech")
        ckpt = snapshot("fishaudio/s2-pro")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        argv = [sys.executable, "tools/api_server.py", "--listen", f"127.0.0.1:{port}", "--llama-checkpoint-path",
                ckpt, "--decoder-checkpoint-path", os.path.join(ckpt, "codec.pth"), "--decoder-config-name",
                "modded_dac_vq", "--device", device()]
        if device() == "cuda":
            argv.append("--half") if not _bf16() else None
        self.proc = subprocess.Popen(argv, cwd=repo, stdout=sys.stderr, stderr=sys.stderr)
        atexit.register(lambda: self.proc.poll() is None and self.proc.kill())
        for _ in range(1800):  # loading 9 GB of weights takes minutes on a CPU
            if self.proc.poll() is not None:
                raise RuntimeError(f"fish-speech server stopped (code {self.proc.returncode})")
            try:
                with urllib.request.urlopen(self.url + "/v1/health", timeout=5) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(2)
        self.sr = 44100

    def say(self, text, voice, mood, rate, ref):
        import io
        import urllib.request

        import ormsgpack
        body = {"text": f"{mood} {text}".strip() if mood else text, "format": "wav", "references": [],
                "reference_id": None, "streaming": False, "chunk_length": 200, "max_new_tokens": 1024}
        req = urllib.request.Request(self.url + "/v1/tts", data=ormsgpack.packb(body),
                                     headers={"Content-Type": "application/msgpack"})
        with urllib.request.urlopen(req, timeout=3600) as r:
            data = r.read()
        with wave.open(io.BytesIO(data), "rb") as w:
            import numpy as np
            self.sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32") / 32768
            return x.reshape(-1, w.getnchannels()).mean(axis=1) if w.getnchannels() > 1 else x


def _bf16() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_bf16_supported())
    except Exception:  # noqa: BLE001
        return False


ADAPTERS = {"seda": Seda, "clarvia": Clarvia, "supertonic": Supertonic, "ema": Ema, "ahenkcep": AhenkCep,
            "pocket": Pocket, "anka": Anka, "freya": Freya, "drifting": Drifting, "mms": Mms, "xtts": Coqui,
            "openbible": Coqui, "turkvits": Coqui, "kizagan": VoxCpm, "trendyol": VoxCpm, "ahenk": VoxCpm,
            "nefes": Nefes, "fish": Fish}


def main() -> None:
    for s in (sys.stdout, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    real_out = sys.stdout
    sys.stdout = sys.stderr  # packages print progress; only our JSON goes to the real stdout
    model = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            if model is None:
                model = ADAPTERS[ENGINE]()
            if req.get("cmd") == "voices":
                ans = {"ok": True, "voices": model.voices(), "moods": list(model.moods), "sr": model.sr,
                       "device": device()}
            else:
                model.ref_text = req.get("ref_text") or ""  # what the reference clip says (F5-style engines)
                x = model.say(req["text"], req.get("voice") or "", req.get("mood") or "",
                              float(req.get("rate") or 1.0), req.get("ref") or "")
                write_wav(req["out"], x, model.sr)
                ans = {"ok": True, "sr": model.sr}
        except Exception as e:  # noqa: BLE001
            ans = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"}
        real_out.write(json.dumps(ans, ensure_ascii=False) + "\n")
        real_out.flush()


if __name__ == "__main__":
    main()
