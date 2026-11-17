"""Image generation (free FLUX through Pollinations).

Without a token Pollinations adds its own small logo to the corner: that is the free tier's attribution and it is
kept. With the free token of a registered account (auth.pollinations.ai, Settings > Web research > Image generation)
the picture comes without it (nologo)."""
from __future__ import annotations

import io
from urllib.parse import quote

import httpx

BASE = "https://image.pollinations.ai/prompt/"


def token() -> str:
    from ..config import get_secret
    return get_secret("pollinations_token") or ""


async def generate(prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None) -> tuple[bytes, bool]:
    """(image bytes, logo-free). Raises RuntimeError with the service's answer when it fails twice."""
    tok = token()
    params = {"width": width, "height": height, "model": "flux", "enhance": "true", "private": "true"}
    headers = {"User-Agent": "AI-IQ-300/0.10"}
    if tok:
        params["nologo"] = "true"
        headers["Authorization"] = f"Bearer {tok}"
    if seed is not None:
        params["seed"] = seed
    last = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), follow_redirects=True, headers=headers) as c:
        for _ in range(2):  # one retry: the free service is sometimes busy
            try:
                r = await c.get(BASE + quote(prompt[:1500], safe=""), params=params)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                    return r.content, bool(tok)
                last = f"HTTP {r.status_code}: {r.text[:150]}"
            except httpx.HTTPError as e:
                last = str(e)[:150]
    raise RuntimeError(last or "no image")


def save(data: bytes, target) -> tuple[int, int]:
    """Writes the picture (JPEG or PNG by the file name). Returns its size."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, "PNG" if target.suffix.lower() == ".png" else "JPEG", quality=92)
    return im.size
