"""Turkish TTS benchmark: every installed local voice reads the same sentences; the app measures each one.

    python eval/tts_bench.py                     # every installed voice pack + the installed Turkish Piper voices
    python eval/tts_bench.py seda pocket         # chosen packs only
    python eval/tts_bench.py --whisper small     # the recogniser used for accuracy (default: small)
    python eval/tts_bench.py --all-voices        # every voice of every pack (default: up to 3 a pack)
    python eval/tts_bench.py --redo              # measure again the voices already in results.json

Per voice: load time (first sentence, model loading included), RTF (synthesis time / audio length, lower is faster;
below 1 is faster than real time), median pitch (gender check) and accuracy: the audio is transcribed by
faster-whisper and compared with the text (CER, character error rate, lower is better; numbers and punctuation are
left out of the comparison so the score is about pronunciation, not about how a recogniser writes "14:30").
Measured on the machine it runs on: the device is written next to every result.

Writes eval/tts/results.json and eval/tts/samples/<voice>.wav (the first sentence)."""
from __future__ import annotations

import asyncio
import json
import platform
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.voice import catalog, engines, packs  # noqa: E402

OUT = ROOT / "eval" / "tts"
SENTENCES = [
    "Merhaba, bugün size yeni projemizin ilk sonuçlarını anlatacağım.",
    "Ağaçların arasından süzülen ışık, sabahın serinliğini ısıtıyordu.",
    "Lütfen kapıyı kapatmayı ve ışıkları söndürmeyi unutmayın.",
    "Öğrenciler sınavdan önce bütün konuları bir kez daha gözden geçirdi.",
    "Şirketin müşteri hizmetleri hafta içi her gün açık olacak.",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("I", "ı").replace("İ", "i").lower()
    s = re.sub(r"[^\wçğıöşü ]+|\d+", " ", s)
    return " ".join(s.split())


def cer(ref: str, hyp: str) -> float:
    a, b = norm(ref), norm(hyp)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)


_WHISPER = {}


def transcribe(samples, sr: int, size: str) -> str:
    import numpy as np
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly
    if size not in _WHISPER:
        _WHISPER[size] = WhisperModel(size, device="cpu", compute_type="int8")
    x = np.asarray(samples, dtype=np.float32)
    if sr != 16000:
        from math import gcd
        g = gcd(sr, 16000)
        x = resample_poly(x, 16000 // g, sr // g).astype(np.float32)
    segs, _ = _WHISPER[size].transcribe(x, language="tr", beam_size=5, vad_filter=False)
    return " ".join(s.text.strip() for s in segs)


def write_wav(path: Path, x, sr: int) -> None:
    import wave

    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("int16").tobytes())


async def bench(vid: str, size: str) -> dict:
    eng = engines.engine_of(vid)
    res = {"voice": vid, "engine": eng, "pack": eng in packs.PACKS}
    if eng in packs.PACKS:
        p = packs.PACKS[eng]
        res.update(name=p["name"], license=p["license"], commercial=p["commercial"], tier=p["tier"],
                   device=(packs.info(eng) or {}).get("device", "cpu"))
    else:
        res.update(name=vid.split(":", 1)[1], license="MIT (Piper)", commercial=True, tier="builtin", device="cpu")
    synth_s, audio_s, errs, pitches = 0.0, 0.0, [], []
    try:
        for i, text in enumerate(SENTENCES):
            t0 = time.perf_counter()
            x, sr = await engines.synth(vid, text, {})
            dt = time.perf_counter() - t0
            dur = len(x) / sr
            if i == 0:
                res["first_s"] = round(dt, 2)  # model loading included
                write_wav(OUT / "samples" / f"{vid.replace(':', '_')}.wav", x, sr)
            else:
                synth_s += dt
                audio_s += dur
            pitches.append(catalog.pitch_hz(x, sr))
            errs.append(cer(text, await asyncio.to_thread(transcribe, x, sr, size)))
        res["rtf"] = round(synth_s / audio_s, 3) if audio_s else None
        res["cer"] = round(sum(errs) / len(errs), 4)
        good = sorted(h for h in pitches if h)
        res["pitch_hz"] = round(good[len(good) // 2]) if good else 0
        res["gender"] = catalog.gender_of(res["pitch_hz"])
        res["sr"] = sr
        res["ok"] = True
    except Exception as e:  # noqa: BLE001
        res.update(ok=False, error=str(e)[:300])
    return res


async def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:]
    size = "small"
    if "--whisper" in args:
        size = args[args.index("--whisper") + 1]
        args = [a for a in args if a not in ("--whisper", size)]
    every = "--all-voices" in args  # default: up to 3 voices a pack (a female, a male, the first) - XTTS alone has 58
    redo = "--redo" in args  # default: voices already in results.json are kept, so a stopped run goes on from there
    want = {a for a in args if not a.startswith("--")}
    by_pack: dict[str, list[dict]] = {}
    for v in packs.voices("tr"):
        if v["installed"] and not v.get("own") and (not want or v["engine"] in want):
            by_pack.setdefault(v["engine"], []).append(v)
    vids = []
    for group in by_pack.values():
        if every or len(group) <= 3:
            vids += [v["id"] for v in group]
            continue
        pick = [group[0]] + [next((v for v in group if v.get("gender") == g), None) for g in ("female", "male")]
        vids += list(dict.fromkeys(v["id"] for v in pick if v))
    if not want or "piper" in want:
        vids += [f"piper:{n}" for n in catalog.PIPER_EXTRA if catalog.piper_installed(n)]
    OUT.mkdir(parents=True, exist_ok=True)
    prev = {}
    try:
        prev = {r["voice"]: r for r in json.loads((OUT / "results.json").read_text(encoding="utf-8"))["results"]}
    except (OSError, ValueError, KeyError):
        pass
    def save() -> None:
        data = {"machine": {"cpu": platform.processor() or platform.machine(), "os": platform.platform(),
                            "hardware": packs.hardware()}, "whisper": size, "sentences": SENTENCES,
                "at": time.strftime("%Y-%m-%d %H:%M"),
                "results": sorted(prev.values(), key=lambda r: (not r.get("ok"), r.get("cer", 9)))}
        (OUT / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    last = ""
    for vid in vids:
        if not redo and prev.get(vid, {}).get("ok"):
            print(f"== {vid} (kept)", flush=True)
            continue
        eng = engines.engine_of(vid)
        if last and eng != last and last in packs.PACKS:
            packs.worker(last).stop()  # one model in memory at a time
        last = eng
        print(f"== {vid}", flush=True)
        r = await bench(vid, size)
        prev[vid] = r
        print("  ", {k: r.get(k) for k in ("ok", "first_s", "rtf", "cer", "pitch_hz", "gender", "error")}, flush=True)
        save()  # after every voice: a stopped run loses nothing
    save()
    for w in packs.WORKERS.values():
        w.stop()
    print("written", OUT / "results.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
