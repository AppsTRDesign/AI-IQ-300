"""Which model each image / video service uses, and the models the user may pick for it.

When a key is entered nothing has to be chosen: every service has a default (for Gemini / Veo the newest suitable
model of the live model list, since Google retires older names for new users - "gemini-2.5-flash is no longer
available to new users"). Settings > Web can change it, but only to a model of the right kind: image services list
image models, video services list video models. The choice lives in settings media.models / video.models."""
from __future__ import annotations

import re
import time

import httpx

from ..config import get_secret, load_settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# kind -> service -> {default, choices}; "live": the list comes from the provider (filtered to the kind)
MODELS: dict[str, dict[str, dict]] = {
    "image": {
        "gemini": {"default": "gemini-2.5-flash-image", "live": "gemini",
                   "choices": ["gemini-2.5-flash-image", "imagen-4.0-generate-001", "imagen-4.0-fast-generate-001",
                               "imagen-4.0-ultra-generate-001"]},
        "cloudflare": {"default": "@cf/black-forest-labs/flux-1-schnell", "live": "cloudflare",
                       "choices": ["@cf/black-forest-labs/flux-1-schnell", "@cf/leonardo/lucid-origin",
                                   "@cf/leonardo/phoenix-1.0"]},
        "huggingface": {"default": "black-forest-labs/FLUX.1-schnell",
                        "choices": ["black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-dev",
                                    "stabilityai/stable-diffusion-3.5-large", "stabilityai/stable-diffusion-xl-base-1.0"]},
        "together": {"default": "black-forest-labs/FLUX.1-schnell",
                     "choices": ["black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-schnell-Free",
                                 "black-forest-labs/FLUX.1-dev", "black-forest-labs/FLUX.1.1-pro",
                                 "black-forest-labs/FLUX.1-kontext-pro"]},
        "openai": {"default": "gpt-image-1", "choices": ["gpt-image-1", "gpt-image-1-mini", "dall-e-3"]},
        "stability": {"default": "core", "choices": ["core", "ultra", "sd3"]},
    },
    "video": {
        "veo": {"default": "veo-3.1-fast-generate-preview", "live": "gemini",
                "choices": ["veo-3.1-fast-generate-preview", "veo-3.1-generate-preview", "veo-3.0-fast-generate-001",
                            "veo-3.0-generate-001", "veo-2.0-generate-001"]},
        "fal": {"default": "fal-ai/wan/v2.2-a14b/image-to-video",
                "choices": ["fal-ai/wan/v2.2-a14b/image-to-video", "fal-ai/kling-video/v2.1/standard/image-to-video",
                            "fal-ai/kling-video/v2.1/pro/image-to-video", "fal-ai/minimax/hailuo-02/standard/image-to-video",
                            "fal-ai/bytedance/seedance/v1/lite/image-to-video", "fal-ai/veo3/fast/image-to-video"]},
        "replicate": {"default": "wan-video/wan-2.2-i2v-fast",
                      "choices": ["wan-video/wan-2.2-i2v-fast", "kwaivgi/kling-v2.1", "minimax/hailuo-02",
                                  "bytedance/seedance-1-lite", "google/veo-3-fast"]},
        "runway": {"default": "gen4_turbo", "choices": ["gen4_turbo", "gen3a_turbo"]},
    },
}
SECTION = {"image": "media", "video": "video"}
_LIVE: dict[str, tuple[float, list[str]]] = {}
LIVE_TTL = 6 * 3600


async def gemini_models() -> list[str]:
    """Every model name the Gemini key can use (cached 6 h): image and video models are picked from it."""
    key = get_secret("gemini_api_key") or ""
    if not key:
        return []
    hit = _LIVE.get("gemini")
    if hit and time.time() - hit[0] < LIVE_TTL:
        return hit[1]
    names: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            token = ""
            for _ in range(5):
                r = await c.get(f"{GEMINI}/models", params={"pageSize": 1000, **({"pageToken": token} if token else {})},
                                headers={"x-goog-api-key": key})
                if r.status_code != 200:
                    break
                d = r.json()
                names += [m["name"].removeprefix("models/") for m in d.get("models") or []]
                token = d.get("nextPageToken") or ""
                if not token:
                    break
    except httpx.HTTPError:
        return hit[1] if hit else []
    if names:
        _LIVE["gemini"] = (time.time(), names)
    return names


async def cloudflare_image_models() -> list[str]:
    """Cloudflare Workers AI text-to-image models of the account (cached 6 h), without the deprecated ones (a
    deprecated model answers HTTP 410: "@cf/bytedance/stable-diffusion-xl-lightning was deprecated")."""
    key = get_secret("cloudflare_api_key") or ""
    s = load_settings()
    acc = ((s.get("media") or {}).get("cloudflare_account") or (s.get("providers", {}).get("cloudflare") or {}).get("account_id") or "").strip()
    if not key or not acc:
        return []
    hit = _LIVE.get("cloudflare")
    if hit and time.time() - hit[0] < LIVE_TTL:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/models/search",
                            params={"task": "Text-to-Image", "per_page": 100}, headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return hit[1] if hit else []
            names = []
            for m in r.json().get("result") or []:
                props = {p.get("property_id"): str(p.get("value")).lower() for p in m.get("properties") or []}
                desc = (m.get("description") or "").lower()
                if m.get("name") and not (props.get("deprecated") == "true" or desc.startswith("deprecated")
                                          or props.get("planned_deprecation_date")):
                    names.append(m["name"])
    except httpx.HTTPError:
        return hit[1] if hit else []
    if names:
        _LIVE["cloudflare"] = (time.time(), names)
    return names


def _version(name: str) -> tuple:
    return tuple(float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", name)[:2]) or (0.0,)


def of_kind(kind: str, names: list[str]) -> list[str]:
    """Only models that make this kind of output (a chat model is never offered as an image / video model)."""
    if kind == "image":
        keep = [n for n in names if re.search(r"(^imagen-|-image(-preview)?$|flash-image)", n)]
    else:
        keep = [n for n in names if n.startswith("veo-")]
    return sorted(keep, key=lambda n: (_version(n), "fast" in n, "preview" not in n), reverse=True)


async def choices(kind: str, sid: str) -> list[str]:
    spec = MODELS.get(kind, {}).get(sid) or {}
    out = list(spec.get("choices") or [])
    if spec.get("live") == "gemini":
        live = of_kind(kind, await gemini_models())
        if live:  # the live list is the truth: retired names drop out, new ones come in
            out = live
    elif spec.get("live") == "cloudflare":
        live = await cloudflare_image_models()
        if live:
            out = sorted(live, key=lambda n: (n != spec["default"], n))
    return out


async def default(kind: str, sid: str) -> str:
    spec = MODELS.get(kind, {}).get(sid) or {}
    if spec.get("live") == "gemini":
        live = of_kind(kind, await gemini_models())
        if live:  # the newest suitable model (older names get retired for new users)
            prefer = [n for n in live if ("flash-image" in n and "lite" not in n if kind == "image" else "fast" in n)]
            return (prefer or live)[0]
    return spec.get("default", "")


async def current(kind: str, sid: str) -> str:
    """The user's choice for this service, else its default."""
    chosen = ((load_settings().get(SECTION[kind]) or {}).get("models") or {}).get(sid)
    return chosen or await default(kind, sid)


def current_sync(kind: str, sid: str) -> str:
    chosen = ((load_settings().get(SECTION[kind]) or {}).get("models") or {}).get(sid)
    if chosen:
        return chosen
    spec = MODELS.get(kind, {}).get(sid) or {}
    if spec.get("live") == "gemini" and (hit := _LIVE.get("gemini")):
        live = of_kind(kind, hit[1])
        if live:
            prefer = [n for n in live if ("flash-image" in n and "lite" not in n if kind == "image" else "fast" in n)]
            return (prefer or live)[0]
    return spec.get("default", "")
