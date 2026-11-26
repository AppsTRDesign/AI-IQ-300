"""Cloud voices with the user's own key: ElevenLabs, OpenAI, Google Cloud Text-to-Speech, Gemini and Azure Speech.

Each one is a card in Settings > Voices (key, test, model, on/off), like the chat providers. A keyed and switched-on
service adds its voices to every voice picker (ids "<service>:<voice>": elevenlabs:21m00Tcm4TlvDq8ikWAM, openai:nova,
google:tr-TR-Chirp3-HD-Achernar, gemini:Kore, azure:tr-TR-EmelNeural). Cloud voices are used only when chosen: the
automatic fallback order never spends the user's credits. Keys stay in secrets.json and travel only in headers."""
from __future__ import annotations

import asyncio
import base64
import re
import time
from html import escape

import numpy as np

from ..config import get_secret, load_settings

# langs: the languages a multilingual voice speaks (its voices are listed under each); a per-locale service has none
MULTI = ["tr", "en", "de", "fr", "es", "it", "pt", "ru", "ar", "nl", "pl", "sv", "da", "fi", "no", "cs", "ro", "el",
         "hu", "bg", "hr", "sk", "uk", "hi", "ja", "ko", "zh", "id", "ms", "vi", "az", "he", "fa"]
CLOUD: dict[str, dict] = {
    "elevenlabs": {"name": "ElevenLabs", "secret": "elevenlabs_api_key", "multi": True,
                   "models": ["eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v3"]},
    "openai": {"name": "OpenAI TTS", "secret": "openai_api_key", "multi": True,
               "models": ["gpt-4o-mini-tts", "tts-1-hd", "tts-1"]},
    "google": {"name": "Google Cloud TTS", "secret": "google_tts_api_key", "multi": False, "models": []},
    "gemini": {"name": "Gemini TTS", "secret": "gemini_api_key", "multi": True,
               "models": ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]},
    "azure": {"name": "Azure Speech", "secret": "azure_speech_key", "multi": False, "models": []},
}
OPENAI_VOICES = {"alloy": "female", "ash": "male", "ballad": "male", "coral": "female", "echo": "male",
                 "fable": "male", "nova": "female", "onyx": "male", "sage": "female", "shimmer": "female",
                 "verse": "male", "marin": "female", "cedar": "male"}
OPENAI_NEW = {"ballad", "verse", "marin", "cedar"}  # only gpt-4o-mini-tts speaks with these
GEMINI_VOICES = {"Zephyr": "female", "Puck": "male", "Charon": "male", "Kore": "female", "Fenrir": "male",
                 "Leda": "female", "Orus": "male", "Aoede": "female", "Callirrhoe": "female", "Autonoe": "female",
                 "Enceladus": "male", "Iapetus": "male", "Umbriel": "male", "Algieba": "male", "Despina": "female",
                 "Erinome": "female", "Algenib": "male", "Rasalgethi": "male", "Laomedeia": "female",
                 "Achernar": "female", "Alnilam": "male", "Schedar": "male", "Gacrux": "female",
                 "Pulcherrima": "female", "Achird": "male", "Zubenelgenubi": "male", "Vindemiatrix": "female",
                 "Sadachbia": "male", "Sadaltager": "male", "Sulafat": "female"}
TIMEOUT = 60
_LIST: dict[str, tuple[float, str, list[dict]]] = {}  # service -> (time, key fingerprint, raw voices)
ERRORS: dict[str, str] = {}


class CloudError(Exception):
    pass


def conf() -> dict:
    return {"disabled": [], "models": {}, "azure_region": "", **(load_settings().get("voice_cloud") or {})}


def key_of(sid: str) -> str:
    return get_secret(CLOUD[sid]["secret"]) or ""


def model_of(sid: str) -> str:
    models = CLOUD[sid]["models"]
    chosen = (conf().get("models") or {}).get(sid) or ""
    return chosen if chosen in models else (models[0] if models else "")


def region() -> str:
    r = str(conf().get("azure_region") or "").strip().lower()
    return r if re.fullmatch(r"[a-z0-9]{2,30}", r) else ""


def ready(sid: str) -> bool:
    return bool(key_of(sid)) and (sid != "azure" or bool(region()))


def active() -> list[str]:
    off = set(conf().get("disabled") or [])
    return [s for s in CLOUD if s not in off and ready(s)]


def voice_ok(vid: str) -> bool:
    sid, _, name = vid.partition(":")
    return sid in CLOUD and bool(re.fullmatch(r"[\w.@#' -]{1,100}", name)) and name.strip() == name


def _client():
    import httpx
    return httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=10))


def _err(sid: str, r) -> CloudError:
    """A short reason from the service's error body (never the key)."""
    msg = ""
    try:
        d = r.json()
        d = d[0] if isinstance(d, list) and d else d
        for k in ("detail", "error", "message"):
            v = d.get(k) if isinstance(d, dict) else None
            msg = (v.get("message") or v.get("status") or "") if isinstance(v, dict) else str(v or "")
            if msg:
                break
    except Exception:  # noqa: BLE001
        pass
    msg = msg or r.text
    return CloudError(f"{CLOUD[sid]['name']}: HTTP {r.status_code} {str(msg)[:240]}")


def _azure_base() -> str:
    return f"https://{region()}.tts.speech.microsoft.com/cognitiveservices"


# ------------------------------------------------------------------ voice lists
async def _raw(sid: str) -> list[dict]:
    """The service's own voices as {name, label, gender, locale, quality}."""
    key = key_of(sid)
    if sid == "openai":
        new = model_of("openai") == "gpt-4o-mini-tts"
        return [{"name": n, "label": n.capitalize(), "gender": g, "quality": "high"}
                for n, g in OPENAI_VOICES.items() if new or n not in OPENAI_NEW]
    if sid == "gemini":
        return [{"name": n, "label": n, "gender": g, "quality": "studio"} for n, g in GEMINI_VOICES.items()]
    async with _client() as c:
        if sid == "elevenlabs":
            r = await c.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
            if r.status_code != 200:
                raise _err(sid, r)
            out = []
            for v in r.json().get("voices") or []:
                g = str((v.get("labels") or {}).get("gender") or "").lower()
                out.append({"name": v["voice_id"], "label": v.get("name") or v["voice_id"],
                            "gender": g if g in ("female", "male") else "unknown", "quality": "studio",
                            "own": v.get("category") in ("cloned", "generated", "professional")})
            return out
        if sid == "google":
            r = await c.get("https://texttospeech.googleapis.com/v1/voices", headers={"X-Goog-Api-Key": key})
            if r.status_code != 200:
                raise _err(sid, r)
            out = []
            for v in r.json().get("voices") or []:
                n = v.get("name") or ""
                q = "studio" if re.search(r"Chirp|Studio", n) else "high" if re.search(r"Neural2|Wavenet|Journey", n) \
                    else "standard"
                out.append({"name": n, "label": re.sub(r"^[a-z]{2,3}-[A-Z]{2}-", "", n).replace("-", " "),
                            "gender": str(v.get("ssmlGender") or "").lower(), "locale": (v.get("languageCodes") or [""])[0],
                            "quality": q})
            return out
        if sid == "azure":
            r = await c.get(f"{_azure_base()}/voices/list", headers={"Ocp-Apim-Subscription-Key": key})
            if r.status_code != 200:
                raise _err(sid, r)
            return [{"name": v["ShortName"], "label": v.get("DisplayName") or v["ShortName"],
                     "gender": str(v.get("Gender") or "").lower(), "locale": v.get("Locale") or "",
                     "quality": "studio" if "HD" in v["ShortName"] else "high"} for v in r.json()]
    return []


async def _cached(sid: str) -> list[dict]:
    fp = f"{len(key_of(sid))}:{key_of(sid)[-4:]}:{region()}:{model_of(sid)}"
    hit = _LIST.get(sid)
    if hit and hit[1] == fp and time.time() - hit[0] < (3600 if hit[2] else 300):
        return hit[2]
    try:
        raw = await asyncio.wait_for(_raw(sid), 12)
        ERRORS.pop(sid, None)
    except Exception as e:  # noqa: BLE001 - offline, bad key: the other voices still list
        ERRORS[sid] = str(e)[:300] or type(e).__name__
        raw = []
    _LIST[sid] = (time.time(), fp, raw)
    return raw


async def voices(lang: str = "") -> list[dict]:
    """Picker entries of every keyed, switched-on cloud service."""
    sids = active()
    lists = await asyncio.gather(*(_cached(s) for s in sids))
    out: list[dict] = []
    for sid, raw in zip(sids, lists):
        multi = CLOUD[sid]["multi"]
        for v in raw:
            loc = v.get("locale") or ""
            code = loc.split("-")[0].lower() if loc else (lang or "tr")
            if lang and (lang not in MULTI if multi else code != lang):
                continue
            out.append({"id": f"{sid}:{v['name']}", "engine": sid, "name": v["label"], "lang": code,
                        "locale": loc or "multilingual", "country": loc.split("-")[-1] if loc else "",
                        "gender": v["gender"] if v["gender"] in ("female", "male") else "unknown",
                        "quality": v["quality"], "offline": False, "installed": True, "cloud": True, "speed": "fast",
                        **({"langs": MULTI} if multi else {}), **({"own": True} if v.get("own") else {})})
    return out


# ------------------------------------------------------------------ speech
def _pcm16(data: bytes, sr: int = 24000) -> tuple[np.ndarray, int]:
    return np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0, sr


async def synth(sid: str, name: str, text: str, opts: dict) -> tuple[np.ndarray, int]:
    """One piece of text -> mono float32 samples."""
    if sid not in CLOUD:
        raise CloudError(f"unknown cloud voice service {sid}")
    key = key_of(sid)
    if not ready(sid):
        raise CloudError(f"{CLOUD[sid]['name']}: no API key (Settings > Voices > Cloud voices)")
    rate = max(0.5, min(2.0, float(opts.get("rate") or 1.0)))
    emo = max(0.0, min(1.0, float(opts.get("emotion", 0.5))))
    model = model_of(sid)
    from .engines import decode
    async with _client() as c:
        if sid == "elevenlabs":
            body = {"text": text, "model_id": model,
                    "voice_settings": {"stability": round(0.75 - emo * 0.5, 2), "similarity_boost": 0.8,
                                       "style": round(max(0.0, emo - 0.4), 2), "speed": round(max(0.7, min(1.2, rate)), 2)}}
            r = await c.post(f"https://api.elevenlabs.io/v1/text-to-speech/{name}",
                             params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": key}, json=body)
        elif sid == "openai":
            body = {"model": model, "input": text, "voice": name, "response_format": "mp3", "speed": rate}
            if model == "gpt-4o-mini-tts" and abs(emo - 0.5) > 0.15:
                body["instructions"] = ("Speak expressively, with lively emotion." if emo > 0.5
                                        else "Speak calmly and evenly.")
            r = await c.post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {key}"},
                             json=body)
        elif sid == "google":
            loc = "-".join(name.split("-")[:2])
            cfg = {"audioEncoding": "MP3", **({"speakingRate": rate} if abs(rate - 1) > 0.01 else {})}
            r = await c.post("https://texttospeech.googleapis.com/v1/text:synthesize", headers={"X-Goog-Api-Key": key},
                             json={"input": {"text": text}, "voice": {"languageCode": loc, "name": name},
                                   "audioConfig": cfg})
            if r.status_code == 200:
                return await asyncio.to_thread(decode, base64.b64decode(r.json()["audioContent"]))
        elif sid == "gemini":
            body = {"contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": name}}}}}
            r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                             headers={"x-goog-api-key": key}, json=body)
            if r.status_code == 200:
                parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                blob = next((p["inlineData"] for p in parts if p.get("inlineData")), None)
                if not blob:
                    raise CloudError("Gemini TTS: no audio in the answer")
                m = re.search(r"rate=(\d+)", blob.get("mimeType") or "")
                return _pcm16(base64.b64decode(blob["data"]), int(m.group(1)) if m else 24000)
        else:  # azure
            loc = "-".join(name.split("-")[:2])
            pct = f"{round((rate - 1) * 100):+d}%"
            ssml = (f"<speak version='1.0' xml:lang='{escape(loc)}'><voice name='{escape(name)}'>"
                    f"<prosody rate='{pct}'>{escape(text)}</prosody></voice></speak>")
            r = await c.post(f"{_azure_base()}/v1", content=ssml.encode("utf-8"),
                             headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                      "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                                      "User-Agent": "ai-iq-300"})
        if r.status_code != 200:
            raise _err(sid, r)
        return await asyncio.to_thread(decode, r.content)


async def test(sid: str) -> dict:
    """The key works: the voice list (free) or the model (OpenAI, Gemini) is fetched. Nothing is spoken (no credits)."""
    if sid not in CLOUD:
        raise CloudError("unknown service")
    if not ready(sid):
        return {"ok": False, "error": "azure region missing" if sid == "azure" and key_of(sid) else "API key missing"}
    t0 = time.time()
    key = key_of(sid)
    try:
        async with _client() as c:
            if sid == "openai":
                r = await c.get(f"https://api.openai.com/v1/models/{model_of(sid)}",
                                headers={"Authorization": f"Bearer {key}"})
                if r.status_code != 200:
                    raise _err(sid, r)
            elif sid == "gemini":
                r = await c.get(f"https://generativelanguage.googleapis.com/v1beta/models/{model_of(sid)}",
                                headers={"x-goog-api-key": key})
                if r.status_code != 200:
                    raise _err(sid, r)
        _LIST.pop(sid, None)
        raw = await asyncio.wait_for(_raw(sid), 20)
        ERRORS.pop(sid, None)
    except Exception as e:  # noqa: BLE001
        ERRORS[sid] = str(e)[:300] or type(e).__name__
        return {"ok": False, "error": ERRORS[sid], "ms": int((time.time() - t0) * 1000)}
    tr = sum(1 for v in raw if (v.get("locale") or "tr-").lower().startswith("tr"))
    return {"ok": True, "count": len(raw), "tr": tr, "ms": int((time.time() - t0) * 1000)}


def status() -> list[dict]:
    off = set(conf().get("disabled") or [])
    return [{"id": s, "name": c["name"], "keyed": bool(key_of(s)), "ready": ready(s), "on": s not in off,
             "model": model_of(s), "models": c["models"], "error": ERRORS.get(s, "")} for s, c in CLOUD.items()]
