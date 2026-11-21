"""Runs INSIDE the Chatterbox environment (data/tts/chatterbox/venv), not in the app's Python.
One JSON request per stdin line -> one JSON answer per stdout line. The model stays loaded between requests."""
import json
import sys
import wave

MODEL = None


def load():
    global MODEL
    if MODEL is None:
        import perth
        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            # resemble-perth leaves its watermarker None when its optional backend fails to import (seen on Windows):
            # Chatterbox then crashes with "'NoneType' object is not callable". Use its no-op watermarker instead.
            class _NoMark:
                def apply_watermark(self, wav, sample_rate=None, **kw):
                    return wav

                def get_watermark(self, *a, **kw):
                    return 0.0
            perth.PerthImplicitWatermarker = getattr(perth, "DummyWatermarker", None) or _NoMark
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        MODEL = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    return MODEL


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            m = load()
            kw = {"language_id": req.get("lang") or "en", "exaggeration": float(req.get("exaggeration", 0.5)),
                  "cfg_weight": float(req.get("cfg_weight", 0.5))}
            if req.get("ref"):
                kw["audio_prompt_path"] = req["ref"]
            wav = m.generate(req["text"], **kw)
            x = wav.squeeze().detach().cpu().numpy()
            pcm = (x.clip(-1, 1) * 32767).astype("int16").tobytes()
            with wave.open(req["out"], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(m.sr))
                w.writeframes(pcm)
            print(json.dumps({"ok": True, "sr": int(m.sr)}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"}), flush=True)


if __name__ == "__main__":
    main()
