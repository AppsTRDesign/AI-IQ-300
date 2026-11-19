"""Picture -> short realistic video clip (image-to-video AI), free, through Hugging Face ZeroGPU Spaces.

Spaces are tried in order (Wan 2.2 image-to-video, then a backup Wan, then AnimateLCM-SVD). Anonymous calls share a
small daily GPU quota; with a Hugging Face token saved (Settings > Providers > Hugging Face, the free account's
token) the user's own quota is used. A Space that is out of quota or busy is skipped. Results are cached by the
picture, prompt and length, so a re-render never spends quota twice. Every clip is re-encoded to H.264 MP4.
"""
from __future__ import annotations

import asyncio
import hashlib
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
        job = client.submit(input_image=handle_file(str(image)), prompt=prompt, steps=6, negative_prompt=NEGATIVE,
                            duration_seconds=max(1.5, min(seconds, 5.0)), guidance_scale=1, guidance_scale_2=1,
                            seed=42, randomize_seed=True, api_name="/generate_video")
        out = job.result(timeout=TIMEOUT)
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


async def animate(image: Path, root: Path, prompt: str = "", seconds: float = 3.5) -> tuple[Path, str]:
    """(cached MP4 of the moving picture, the Space that made it). Raises AnimateError with each Space's reason."""
    if not image.is_file():
        raise AnimateError(f"picture not found: {image}")
    prompt = (prompt or "cinematic, smooth natural motion, subtle camera movement, realistic").strip()[:400]
    seconds = max(1.5, min(float(seconds or 3.5), 5.0))
    target = _cache_dir(root) / f"{image.stem[:40]}-{cache_key(image, prompt, seconds)}.mp4"
    if target.is_file():
        return target, "cache"
    reasons = []
    for space, kind in SPACES:
        try:
            src = await asyncio.wait_for(asyncio.to_thread(_call_space, space, kind, image, prompt, seconds), TIMEOUT + 30)
            await asyncio.to_thread(_reencode, src, target)
            return target, space
        except Exception as e:  # quota, busy, a Space that changed: the next one is tried
            reasons.append(f"{space.split('/')[-1]}: {_short_reason(e)}")
    hint = "" if get_secret("huggingface_api_key") else (" A free Hugging Face token (Settings > Providers > Hugging "
                                                        "Face) gives your own daily GPU quota.")
    raise AnimateError("no free image-to-video service could make the clip now (" + "; ".join(reasons) + ")." + hint)
