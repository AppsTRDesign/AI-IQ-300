"""Image generation through the keyed services (services.CATALOG order: Gemini, Cloudflare FLUX, Hugging Face FLUX,
Together FLUX, OpenAI gpt-image-1, Stability) and the system's own free service, Pollinations FLUX (no key).

A service whose key is missing, that is switched off, or that is out of quota (or rate limited) is skipped, and the
next one is used; when all of them are unavailable Pollinations makes the picture. Without a token Pollinations adds
its own small logo to the corner: that is the free tier's attribution and it is kept. With the free token of a
registered account (auth.pollinations.ai, Settings > Web research > Image generation) the picture comes without it."""
from __future__ import annotations

import base64
import io
from urllib.parse import quote

import httpx

from ..config import get_secret, load_settings
from . import services
from .services import ServiceError

BASE = "https://image.pollinations.ai/prompt/"
TIMEOUT = httpx.Timeout(120, connect=15)
UA = "AI-IQ-300/0.12 (local assistant; image generation)"
GEMINI_MODEL = "gemini-2.5-flash-image"
CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
TOGETHER_MODEL = "black-forest-labs/FLUX.1-schnell"
HF_MODEL = "black-forest-labs/FLUX.1-schnell"
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"
RATIOS = {"1:1": 1, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3,
          "5:4": 5 / 4, "4:5": 4 / 5, "21:9": 21 / 9, "9:21": 9 / 21}


def token() -> str:
    return get_secret("pollinations_token") or ""


def _size_openai(w: int, h: int) -> str:
    if w > h * 1.2:
        return "1536x1024"
    if h > w * 1.2:
        return "1024x1536"
    return "1024x1024"


def _ratio(w: int, h: int) -> str:
    want = w / max(h, 1)
    return min(RATIOS, key=lambda k: abs(RATIOS[k] - want))


def _image_bytes(sid: str, r: httpx.Response) -> bytes:
    """A raw picture answer (not JSON)."""
    services.check(sid, r)
    if not (r.headers.get("content-type", "").startswith("image/")):
        raise ServiceError(f"no picture in the answer: {r.text[:120]}")
    return r.content


def _b64_json(sid: str, r: httpx.Response, pick) -> bytes:
    """A JSON answer whose picture is base64; pick(json) returns the string (Cloudflare, OpenAI, Together)."""
    services.check(sid, r)
    try:
        b64 = pick(r.json())
    except (KeyError, IndexError, TypeError, ValueError):
        b64 = None
    if not b64:
        raise ServiceError(f"no picture in the answer: {r.text[:120]}")
    return base64.b64decode(b64)


async def _model(sid: str) -> str:
    from . import mediamodels
    return await mediamodels.current("image", sid)


async def _gemini(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("gemini_api_key") or ""
    model = await _model("gemini") or GEMINI_MODEL
    base = "https://generativelanguage.googleapis.com/v1beta/models/"
    if model.startswith("imagen"):  # Imagen: the predict API, aspect ratio instead of pixels
        r = await c.post(f"{base}{model}:predict", headers={"x-goog-api-key": key},
                         json={"instances": [{"prompt": prompt}],
                               "parameters": {"sampleCount": 1, "aspectRatio": _ratio(w, h) if _ratio(w, h) in
                                              ("1:1", "3:4", "4:3", "9:16", "16:9") else "1:1"}})
        services.check("gemini", r)
        preds = r.json().get("predictions") or []
        if preds and preds[0].get("bytesBase64Encoded"):
            return base64.b64decode(preds[0]["bytesBase64Encoded"])
        raise ServiceError("no picture in the answer (the prompt may have been filtered)")
    r = await c.post(f"{base}{model}:generateContent",
                     headers={"x-goog-api-key": key},
                     json={"contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"responseModalities": ["IMAGE"]}})
    services.check("gemini", r)
    for cand in r.json().get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if inline := part.get("inlineData") or part.get("inline_data"):
                return base64.b64decode(inline["data"])
    raise ServiceError("no picture in the answer (the model may have refused the prompt)")


async def _cloudflare(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("cloudflare_api_key") or ""
    account = (load_settings().get("media") or {}).get("cloudflare_account") or \
        ((load_settings().get("providers") or {}).get("cloudflare") or {}).get("account_id") or ""
    if not account:
        raise ServiceError("no Cloudflare account id (Settings > Web > Image services)")
    model = await _model("cloudflare") or CF_MODEL
    body = {"prompt": prompt}
    if "flux-1-schnell" in model:
        body["steps"] = 4
    else:
        body.update({"width": min(w, 1024), "height": min(h, 1024)})
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    if "flux-2" in model:  # FLUX.2 on Workers AI takes multipart form fields, not JSON
        r = await c.post(url, headers={"Authorization": f"Bearer {key}"},
                         files={"prompt": (None, prompt), "width": (None, str(min(w, 1024))),
                                "height": (None, str(min(h, 1024)))})
    else:
        r = await c.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code < 400 and r.headers.get("content-type", "").startswith("image/"):  # SDXL models answer a PNG
        services.note_headers("cloudflare", r.headers)
        return r.content
    return _b64_json("cloudflare", r, lambda d: d["result"]["image"])


async def _together(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("together_api_key") or ""
    body = {"model": await _model("together") or TOGETHER_MODEL, "prompt": prompt, "width": min(w, 1440), "height": min(h, 1440), "steps": 4,
            "n": 1, "response_format": "b64_json"}
    if seed is not None:
        body["seed"] = seed
    r = await c.post("https://api.together.xyz/v1/images/generations", headers={"Authorization": f"Bearer {key}"}, json=body)
    return _b64_json("together", r, lambda d: d["data"][0]["b64_json"])


async def _openai(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("openai_api_key") or ""
    model = await _model("openai") or "gpt-image-1"
    body = {"model": model, "prompt": prompt, "size": _size_openai(w, h), "n": 1}
    if model == "dall-e-3":  # DALL-E 3 sizes, and base64 must be asked for
        body.update(size={"1024x1536": "1024x1792", "1536x1024": "1792x1024"}.get(body["size"], "1024x1024"),
                    response_format="b64_json")
    r = await c.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {key}"},
                     json=body)
    return _b64_json("openai", r, lambda d: d["data"][0]["b64_json"])


async def _huggingface(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("huggingface_api_key") or ""
    params = {"width": min(w, 1440), "height": min(h, 1440)}
    if seed is not None:
        params["seed"] = seed
    r = await c.post(f"https://router.huggingface.co/hf-inference/models/{await _model('huggingface') or HF_MODEL}",
                     headers={"Authorization": f"Bearer {key}", "Accept": "image/png"},
                     json={"inputs": prompt, "parameters": params})
    return _image_bytes("huggingface", r)


async def _stability(c: httpx.AsyncClient, prompt: str, w: int, h: int, seed: int | None) -> bytes:
    key = get_secret("stability_api_key") or ""
    fields = {"prompt": (None, prompt), "output_format": (None, "png"), "aspect_ratio": (None, _ratio(w, h))}
    if seed is not None:
        fields["seed"] = (None, str(seed))
    model = await _model("stability") or "core"
    url = STABILITY_URL.rsplit("/", 1)[0] + "/" + (model if model in ("core", "ultra", "sd3") else "core")
    r = await c.post(url, headers={"Authorization": f"Bearer {key}", "Accept": "image/*"}, files=fields)
    return _image_bytes("stability", r)


ADAPTERS = {"gemini": _gemini, "cloudflare": _cloudflare, "together": _together, "openai": _openai,
            "huggingface": _huggingface, "stability": _stability}


async def _pollinations(c: httpx.AsyncClient, prompt: str, width: int, height: int, seed: int | None) -> bytes:
    """The system's own service (free FLUX). Two tries: the free service is sometimes busy."""
    tok = token()
    params = {"width": width, "height": height, "model": "flux", "enhance": "true", "private": "true"}
    headers = {}
    if tok:
        params["nologo"] = "true"
        headers["Authorization"] = f"Bearer {tok}"
    if seed is not None:
        params["seed"] = seed
    last = ""
    for _ in range(2):
        try:
            r = await c.get(BASE + quote(prompt[:1500], safe=""), params=params, headers=headers)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return r.content
            from ..llm.providers import message_of
            last = f"HTTP {r.status_code}: {(message_of(r.text[:4000]) or r.text)[:200]}"
        except httpx.HTTPError as e:
            last = str(e)[:150]
    raise RuntimeError(last or "no image")


async def generate(prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None) -> tuple[bytes, str, bool]:
    """(image bytes, service id, logo-free). Keyed services first (in order), then the system's own."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": UA}) as c:
        async def system():
            return await _pollinations(c, prompt, width, height, seed)
        data, sid = await services.run("image", lambda sid: ADAPTERS[sid](c, prompt, width, height, seed), system,
                                       "pollinations")
    return data, sid, sid != "pollinations" or bool(token())


async def generate_with(sid: str, prompt: str, width: int = 256, height: int = 256) -> bytes:
    """One named service alone (Settings > test button): its own error is raised, nothing falls back."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": UA}) as c:
        if sid == "pollinations":
            return await _pollinations(c, prompt, width, height, None)
        if sid not in ADAPTERS:
            raise RuntimeError(f"unknown image service: {sid}")
        return await services.call(sid, lambda: ADAPTERS[sid](c, prompt, width, height, None))


def save(data: bytes, target) -> tuple[int, int]:
    """Writes the picture (JPEG or PNG by the file name). Returns its size."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, "PNG" if target.suffix.lower() == ".png" else "JPEG", quality=92)
    return im.size
