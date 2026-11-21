"""Picture -> short realistic video clip (image-to-video AI), free, through Hugging Face ZeroGPU Spaces.

Spaces are tried in order (Wan 2.2 image-to-video, then a backup Wan, then AnimateLCM-SVD). Anonymous calls share a
small daily GPU quota; with a Hugging Face token saved (Settings > Providers > Hugging Face, the free account's
token) the user's own quota is used. A Space that is out of quota or busy is skipped. Results are cached by the
picture, prompt and length, so a re-render never spends quota twice. Every clip is re-encoded to H.264 MP4.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from ..config import get_secret

# (space, kind): kind selects how the Space is called
SPACES = [("zerogpu-aoti/wan2-2-fp8da-aoti-faster", "wan"),
          ("Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom", "wan"),
          ("wangfuyun/AnimateLCM-SVD", "svd")]
NEGATIVE = "static, still image, blurry, distorted, deformed, extra fingers, watermark, text, subtitles, low quality"
TIMEOUT = 300


class AnimateError(RuntimeError):
    pass


def _cache_dir(root: Path) -> Path:
    d = root / ".cache" / "animated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(image: Path, prompt: str, seconds: float) -> str:
    h = hashlib.sha1()
    h.update(image.read_bytes())
    h.update(f"|{prompt}|{seconds:.2f}".encode())
    return h.hexdigest()[:16]


def _call_space(space: str, kind: str, image: Path, prompt: str, seconds: float) -> str:
    """Blocking: returns the path of the MP4 the Space produced (downloaded by gradio_client)."""
    from gradio_client import Client, handle_file
    token = get_secret("huggingface_api_key") or None
    client = Client(space, token=token, verbose=False) if token else Client(space, verbose=False)
    if kind == "wan":
        args = dict(input_image=handle_file(str(image)), prompt=prompt, steps=6, negative_prompt=NEGATIVE,
                    duration_seconds=max(1.5, min(seconds, 5.0)), guidance_scale=1, guidance_scale_2=1,
                    seed=42, randomize_seed=True)
        # Spaces change their API: a required argument added later ("No value provided for required argument:
        # last_image" - an optional end frame) is sent empty, up to three of them, instead of failing the Space.
        import re as _re
        for _ in range(4):
            try:
                out = client.submit(**args, api_name="/generate_video").result(timeout=TIMEOUT)
                break
            except TypeError as e:
                m = _re.search(r"required argument: (\w+)", str(e))
                if not m or m.group(1) in args:
                    raise
                args[m.group(1)] = None
        video = out[0] if isinstance(out, (list, tuple)) else out
    else:
        out = client.predict(handle_file(str(image)), 42, True, 80, 8, 1.2, 1, 1024, 576, 4, api_name="/video")
        video = out[0] if isinstance(out, (list, tuple)) else out
    if isinstance(video, dict):
        video = video.get("video") or video.get("path") or ""
    if not video or not Path(str(video)).is_file():
        raise AnimateError(f"{space}: no video in the answer")
    return str(video)


def _reencode(src: str, target: Path) -> None:
    exe = shutil.which("ffmpeg")
    if not exe:
        shutil.copyfile(src, target)
        return
    r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-an", "-c:v", "libx264", "-preset",
                        "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not target.is_file():
        raise AnimateError(f"re-encoding the clip failed: {r.stderr[-200:]}")


def _short_reason(e: Exception) -> str:
    text = f"{type(e).__name__}: {e}"
    low = text.lower()
    if "quota" in low or "runs limit" in low or "exceeded" in low:
        return "free GPU quota used up for now"
    if "queue" in low and "full" in low:
        return "queue full"
    return text[:160]


# ---------------------------------------------------------------- paid image-to-video APIs
POLL_LIMIT = 600  # seconds a paid job may take (Veo / Kling: 1-5 minutes)


def _data_uri(image: Path, max_side: int = 1280) -> tuple[str, str, str]:
    """(data URI, base64, mime) of the picture, downscaled to max_side as JPEG (APIs cap inline images ~5 MB)."""
    import base64
    import io
    from PIL import Image
    im = Image.open(image).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}", b64, "image/jpeg"


async def _download(c, url: str, headers: dict | None = None) -> bytes:
    r = await c.get(url, headers=headers or {}, follow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"download HTTP {r.status_code}")
    return r.content


async def _poll(fetch, done, interval: float = 6.0):
    """Calls fetch() until done(answer) gives a result (or raises), at most POLL_LIMIT seconds."""
    t0 = asyncio.get_running_loop().time()
    while True:
        ans = await fetch()
        res = done(ans)
        if res is not None:
            return res
        if asyncio.get_running_loop().time() - t0 > POLL_LIMIT:
            raise RuntimeError(f"no result after {POLL_LIMIT} s")
        await asyncio.sleep(interval)


async def _veo(c, model: str, image: Path, prompt: str, seconds: float, aspect: str) -> bytes:
    from . import services
    key = get_secret("gemini_api_key") or ""
    base = "https://generativelanguage.googleapis.com/v1beta"
    _, b64, mime = _data_uri(image)
    inst = {"prompt": prompt, "image": {"bytesBase64Encoded": b64, "mimeType": mime}}
    params = {"aspectRatio": aspect if aspect in ("16:9", "9:16") else "16:9"}
    if not model.startswith("veo-2"):
        params["durationSeconds"] = 4 if seconds <= 5 else 8
    h = {"x-goog-api-key": key}
    r = await c.post(f"{base}/models/{model}:predictLongRunning", headers=h, json={"instances": [inst], "parameters": params})
    if r.status_code == 400 and "duration" in r.text.lower():  # a model with other allowed lengths: its default
        params.pop("durationSeconds", None)
        r = await c.post(f"{base}/models/{model}:predictLongRunning", headers=h, json={"instances": [inst], "parameters": params})
    services.check("veo", r)
    op = r.json()["name"]

    async def fetch():
        x = await c.get(f"{base}/{op}", headers=h)
        services.check("veo", x)
        return x.json()

    def done(d):
        if not d.get("done"):
            return None
        if d.get("error"):
            raise services.ServiceError(str(d["error"].get("message") or d["error"])[:200])
        samples = ((d.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples") or []
        if not samples:
            raise services.ServiceError("no video in the answer (the prompt or picture may have been filtered)")
        return samples[0]["video"]["uri"]
    uri = await _poll(fetch, done, 8)
    return await _download(c, uri, h)


async def _fal(c, model: str, image: Path, prompt: str, seconds: float, aspect: str) -> bytes:
    from . import services
    h = {"Authorization": f"Key {get_secret('fal_api_key') or ''}"}
    uri, _, _ = _data_uri(image)
    r = await c.post(f"https://queue.fal.run/{model}", headers=h, json={"prompt": prompt, "image_url": uri})
    services.check("fal", r)
    job = r.json()
    status_url, response_url = job["status_url"], job["response_url"]

    async def fetch():
        x = await c.get(status_url, headers=h)
        services.check("fal", x)
        return x.json()

    def done(d):
        st = str(d.get("status") or "").upper()
        if st == "COMPLETED":
            return True
        if st in ("FAILED", "ERROR", "CANCELLED"):
            raise services.ServiceError(f"fal.ai job {st.lower()}: {str(d)[:160]}")
        return None
    await _poll(fetch, done, 4)
    out = await c.get(response_url, headers=h)
    services.check("fal", out)
    video = (out.json().get("video") or {}).get("url")
    if not video:
        raise services.ServiceError(f"no video in the answer: {out.text[:160]}")
    return await _download(c, video)


# Replicate models name their picture input differently
REPLICATE_IMAGE = {"kwaivgi/kling": "start_image", "minimax/": "first_frame_image"}


async def _replicate(c, model: str, image: Path, prompt: str, seconds: float, aspect: str) -> bytes:
    from . import services
    h = {"Authorization": f"Bearer {get_secret('replicate_api_key') or ''}", "Prefer": "wait=55"}
    uri, _, _ = _data_uri(image)
    field = next((v for k, v in REPLICATE_IMAGE.items() if model.startswith(k)), "image")
    r = await c.post(f"https://api.replicate.com/v1/models/{model}/predictions", headers=h,
                     json={"input": {field: uri, "prompt": prompt}})
    services.check("replicate", r)
    pred = r.json()
    get_url = (pred.get("urls") or {}).get("get")

    async def fetch():
        nonlocal pred
        if pred.get("status") in ("succeeded", "failed", "canceled"):
            return pred
        x = await c.get(get_url, headers={"Authorization": h["Authorization"]})
        services.check("replicate", x)
        pred = x.json()
        return pred

    def done(d):
        if d.get("status") == "succeeded":
            out = d.get("output")
            return out[0] if isinstance(out, list) else out
        if d.get("status") in ("failed", "canceled"):
            raise services.ServiceError(f"Replicate: {str(d.get('error') or d.get('status'))[:200]}")
        return None
    url = await _poll(fetch, done, 4)
    return await _download(c, url)


async def _runway(c, model: str, image: Path, prompt: str, seconds: float, aspect: str) -> bytes:
    from . import services
    h = {"Authorization": f"Bearer {get_secret('runway_api_key') or ''}", "X-Runway-Version": "2024-11-06"}
    uri, _, _ = _data_uri(image)
    ratio = {"9:16": "720:1280", "1:1": "960:960"}.get(aspect, "1280:720")
    if model.startswith("gen3"):
        ratio = "768:1280" if aspect == "9:16" else "1280:768"
    r = await c.post("https://api.dev.runwayml.com/v1/image_to_video", headers=h,
                     json={"model": model, "promptImage": uri, "promptText": prompt[:1000], "ratio": ratio,
                           "duration": 5 if seconds <= 5 else 10})
    services.check("runway", r)
    tid = r.json()["id"]

    async def fetch():
        x = await c.get(f"https://api.dev.runwayml.com/v1/tasks/{tid}", headers=h)
        services.check("runway", x)
        return x.json()

    def done(d):
        if d.get("status") == "SUCCEEDED":
            return (d.get("output") or [None])[0]
        if d.get("status") in ("FAILED", "CANCELLED"):
            raise services.ServiceError(f"Runway: {str(d.get('failure') or d.get('status'))[:200]}")
        return None
    url = await _poll(fetch, done, 5)
    return await _download(c, url)


PAID = {"veo": _veo, "fal": _fal, "replicate": _replicate, "runway": _runway}


async def _choices(sid: str) -> list[str]:
    from . import mediamodels
    try:
        c = mediamodels.choices("video", sid)
        c = await c if asyncio.iscoroutine(c) else c
        return [x if isinstance(x, str) else x.get("id", "") for x in (c or [])]
    except Exception:  # noqa: BLE001 - the chosen model alone
        return []


async def make_with(sid: str, image: Path, prompt: str, seconds: float, aspect: str = "16:9") -> str:
    """One video service alone (also the Settings test): the path of the clip it made (a temporary file)."""
    import tempfile
    import httpx
    from . import mediamodels, services
    spec = services.CATALOG[sid]
    if spec.get("free"):
        return await asyncio.wait_for(asyncio.to_thread(_call_space, spec["space"], spec["call"], image, prompt, seconds),
                                      TIMEOUT + 30)
    model = await mediamodels.current("video", sid)
    # The chosen model may be gone for this key ("veo-3.1-fast-generate-preview is not found for API version v1beta,
    # or is not supported"): the service's other video models are tried before the next service.
    tried, data, last = [], None, None
    candidates = [model] + [m for m in (await _choices(sid)) if m != model]
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20)) as c:
        for m in candidates[:4]:
            tried.append(m)
            try:
                data = await PAID[sid](c, m, image, prompt, seconds, aspect)
                break
            except services.ServiceError as e:
                last = e
                if not re.search(r"not found|not supported|no such model|unknown model|404|does not exist", str(e), re.I):
                    raise
    if data is None:
        raise last or services.ServiceError("no model of this service could make the clip")
    fd, path = tempfile.mkstemp(suffix=".mp4")
    with open(fd, "wb") as f:
        f.write(data)
    return path


async def animate(image: Path, root: Path, prompt: str = "", seconds: float = 3.5, aspect: str = "16:9") -> tuple[Path, str]:
    """(cached MP4 of the moving picture, the service that made it). The services of Settings > Web > AI video in
    order - paid ones with a key first, then the free Hugging Face Spaces - skipping switched-off ones; the first that
    succeeds is used (one at a time, never in parallel). Raises AnimateError with each service's reason."""
    from . import services
    if not image.is_file():
        raise AnimateError(f"picture not found: {image}")
    prompt = (prompt or "cinematic, smooth natural motion, subtle camera movement, realistic").strip()[:400]
    seconds = max(1.5, min(float(seconds or 3.5), 10.0))
    target = _cache_dir(root) / f"{image.stem[:40]}-{cache_key(image, prompt, seconds)}.mp4"
    if target.is_file():
        return target, "cache"
    async with _ONE_AT_A_TIME:  # a model sent three clips at once: they raced for the same free GPU quota
        if target.is_file():
            return target, "cache"
        return await _animate(image, target, prompt, seconds, aspect)


_ONE_AT_A_TIME = asyncio.Lock()


async def _animate(image: Path, target: Path, prompt: str, seconds: float, aspect: str) -> tuple[Path, str]:
    from . import services
    reasons = []
    order = services.usable("video")
    if not order:
        raise AnimateError("every AI video service is switched off (Settings > Web > AI video): switch one on")
    for sid in order:
        free = services.CATALOG[sid].get("free")
        try:
            src = await services.call(sid, lambda sid=sid: make_with(
                sid, image, prompt, min(seconds, 5.0) if free else seconds, aspect))
            await asyncio.to_thread(_reencode, src, target)
            if not free:
                Path(src).unlink(missing_ok=True)
            return target, services.CATALOG[sid]["name"]
        except Exception as e:  # quota, busy, a Space that changed: the next one is tried
            reasons.append(f"{services.CATALOG[sid]['name']}: {_short_reason(e)}")
    hint = "" if get_secret("huggingface_api_key") else (" A free Hugging Face token (Settings > Providers > Hugging "
                                                        "Face) gives your own daily GPU quota.")
    raise AnimateError("no image-to-video service could make the clip now (" + "; ".join(reasons) + ")." + hint)
