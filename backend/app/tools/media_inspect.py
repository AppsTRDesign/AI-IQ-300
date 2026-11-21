"""Eyes and ears for every model: inspect an image, a video or an audio file with local libraries, so a model that
cannot see or hear still knows exactly what a file contains.

- image: size, format, EXIF (camera, date, GPS present), dominant colours, brightness/contrast, sharpness, faces
  (OpenCV), text (OCR: Windows OCR / Tesseract / RapidOCR), and a description by a vision model when one is set
- video: duration, resolution, fps, codecs, audio (ffprobe); key frames at scene changes (ffmpeg); a contact sheet
  of those frames (also saved for the user); text on the frames (OCR); a description of the contact sheet by a vision
  model; the speech as text (faster-whisper, on the CPU)
- audio: metadata and the speech as text

Everything except the optional vision-model description runs offline."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv"}
AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}


def _ffbin(name: str) -> str | None:
    return shutil.which(name)


def _vision(res: dict, seen) -> None:
    """A vision model's description, or why there is none (busy / no answer in time vs none set)."""
    if seen and not seen[1].startswith("(no vision"):
        res["description"] = f"{seen[0]}: {seen[1]}"
    elif seen:
        res["vision_note"] = f"the vision model {seen[0]} did not answer in time (busy)"


def _colour_name(rgb: tuple[int, int, int]) -> str:
    """#hex plus a plain name, so a text-only model can say "dark brown" instead of reading hex codes."""
    import colorsys
    r, g, b = rgb
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if l < 0.12:
        name = "black"
    elif l > 0.9 and s < 0.5:
        name = "white"
    elif s < 0.15:
        name = "grey" if 0.25 < l < 0.75 else ("dark grey" if l <= 0.25 else "light grey")
    else:
        hue = h * 360
        name = ("red" if hue < 15 or hue >= 345 else "orange" if hue < 40 else "yellow" if hue < 65 else
                "green" if hue < 165 else "cyan" if hue < 195 else "blue" if hue < 255 else "purple" if hue < 290 else
                "pink")
        if (name == "orange" and l < 0.45) or (name in ("yellow", "red") and l < 0.4 and s < 0.7):
            name = "brown"
        elif name in ("orange", "yellow") and l > 0.75:
            name = "cream" if s < 0.6 else "light " + name
        elif l < 0.3:
            name = "dark " + name
        elif l > 0.75:
            name = "light " + name
    return f"#{r:02x}{g:02x}{b:02x} {name}"


def _image_facts(img) -> dict:
    """Pixels -> facts (no model): colours, light, sharpness, faces."""
    from PIL import ImageStat
    rgb = img.convert("RGB")
    small = rgb.copy()
    small.thumbnail((256, 256))
    pal = small.quantize(colors=6, method=2)
    counts = sorted(pal.getcolors() or [], reverse=True)
    palette = pal.getpalette() or []
    total = sum(c for c, _ in counts) or 1
    colours = [f"{_colour_name(tuple(palette[i * 3:i * 3 + 3]))} {round(c * 100 / total)}%" for c, i in counts[:6]]
    stat = ImageStat.Stat(rgb.convert("L"))
    facts = {"colours": colours, "brightness": round(stat.mean[0] / 2.55), "contrast": round(stat.stddev[0] / 1.28)}
    try:
        import cv2
        import numpy as np
        gray = cv2.cvtColor(np.array(small.resize((min(1024, rgb.width), int(rgb.height * min(1024, rgb.width) / rgb.width)))),
                            cv2.COLOR_RGB2GRAY)
        facts["sharpness"] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        big = cv2.cvtColor(np.array(rgb.resize((min(1280, rgb.width), int(rgb.height * min(1280, rgb.width) / rgb.width)))),
                           cv2.COLOR_RGB2GRAY)
        facts["faces"] = len(casc.detectMultiScale(big, 1.1, 6, minSize=(40, 40)))
    except Exception:
        pass
    return facts


def _exif(img) -> dict:
    try:
        from PIL import ExifTags
        raw = img.getexif() or {}
        named = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw.items()}
        out = {k: str(named[k])[:60] for k in ("Make", "Model", "DateTime", "Software") if k in named}
        if 34853 in raw:
            out["GPS"] = "present (location data inside)"
        return out
    except Exception:
        return {}


def _ocr(images: list, lang: str) -> list[str]:
    try:
        from .docread import ocr_images
        texts, _ = ocr_images(images, lang)
        return [(t or "").strip() for t in texts]
    except Exception:
        return ["" for _ in images]


def _probe(path: Path) -> dict:
    exe = _ffbin("ffprobe")
    if not exe:
        return {}
    r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        return {}
    fmt = d.get("format") or {}
    out = {"duration_s": round(float(fmt.get("duration") or 0), 1), "size_mb": round(int(fmt.get("size") or 0) / 1048576, 1)}
    for s in d.get("streams") or []:
        if s.get("codec_type") == "video" and "video" not in out:
            fps = s.get("avg_frame_rate") or "0/1"
            n, _, m = fps.partition("/")
            out["video"] = (f"{s.get('width')}x{s.get('height')} {s.get('codec_name')} "
                            f"{round(float(n) / float(m or 1), 2) if float(m or 1) else 0} fps")
        elif s.get("codec_type") == "audio" and "audio" not in out:
            out["audio"] = f"{s.get('codec_name')} {s.get('sample_rate')} Hz {s.get('channels')} ch"
    return out


def _keyframes(path: Path, out_dir: Path, duration: float, n: int = 8) -> list[Path]:
    """Frames at scene changes (what changes in the video), topped up with evenly spaced ones."""
    exe = _ffbin("ffmpeg")
    if not exe:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("kf-*.jpg"):
        old.unlink(missing_ok=True)
    subprocess.run([exe, "-y", "-v", "error", "-i", str(path), "-vf", "select='gt(scene,0.35)',scale=640:-2",
                    "-vsync", "vfr", "-frames:v", str(n), str(out_dir / "kf-s%02d.jpg")], capture_output=True, timeout=300)
    frames = sorted(out_dir.glob("kf-s*.jpg"))
    if len(frames) < 4 and duration > 0:
        for i in range(n - len(frames)):
            t = duration * (i + 0.5) / (n - len(frames))
            target = out_dir / f"kf-e{i:02d}.jpg"
            subprocess.run([exe, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                            "-vf", "scale=640:-2", str(target)], capture_output=True, timeout=60)
        frames = sorted(out_dir.glob("kf-*.jpg"))
    return frames[:n]


def _sheet(frames: list[Path], target: Path) -> Path | None:
    from PIL import Image, ImageDraw
    if not frames:
        return None
    ims = [Image.open(f).convert("RGB") for f in frames]
    w = 640
    h = max(int(i.height * w / i.width) for i in ims)
    cols = 2 if len(ims) <= 4 else 3
    rows = -(-len(ims) // cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for k, im in enumerate(ims):
        im = im.resize((w, int(im.height * w / im.width)))
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im, (x, y))
        ImageDraw.Draw(sheet).text((x + 8, y + 6), str(k + 1), fill="yellow")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, "JPEG", quality=82)
    return target


def _transcribe(path: Path, minutes: float, lang: str | None) -> str:
    """Speech -> a timestamped table, with the same whisper model as speech_to_text (one copy in RAM)."""
    from .speech import _transcribe as run, table
    segs, _ = run(path, "base", lang, minutes)
    return table(segs)


async def inspect(path: Path, work: Path, model: str, question: str = "", lang: str = "tr",
                  transcript: bool = True, minutes: float = 10) -> dict:
    """{kind, facts..., text, description, transcript, sheet} for the file at `path`."""
    from PIL import Image
    from .visual import describe_for
    ext = path.suffix.lower()
    res: dict = {"file": path.name}
    if ext in IMAGE:
        img = Image.open(path)
        res.update(kind="image", size=f"{img.width}x{img.height}", format=img.format or ext[1:].upper())
        res["exif"] = _exif(img)
        res.update(await asyncio.to_thread(_image_facts, img))
        res["text"] = (await asyncio.to_thread(_ocr, [img.convert("RGB")], lang))[0][:3000]
        seen = await describe_for("", path, question, budget=60)
        _vision(res, seen)
        return res
    if ext in VIDEO or ext in AUDIO:
        res["kind"] = "video" if ext in VIDEO else "audio"
        res.update(await asyncio.to_thread(_probe, path))
        if ext in VIDEO and "video" in res:
            frames = await asyncio.to_thread(_keyframes, path, work / ".frames" / path.stem, res.get("duration_s", 0))
            sheet = await asyncio.to_thread(_sheet, frames, work / "screenshots" / f"{path.stem}-frames.jpg")
            if sheet:
                res["sheet"] = sheet
                texts = await asyncio.to_thread(_ocr, [Image.open(f).convert("RGB") for f in frames], lang)
                res["frame_text"] = [f"frame {i + 1}: {t[:300]}" for i, t in enumerate(texts) if t]
                seen = await describe_for("", sheet, (question + " (numbered key frames of a video, in order)").strip(),
                                          budget=70)
                _vision(res, seen)
                res["frames"] = len(frames)
        if transcript and "audio" in res:
            try:
                res["transcript"] = (await asyncio.wait_for(asyncio.to_thread(_transcribe, path, minutes, None), 900))[:12000]
            except Exception as e:  # no model download possible, a broken stream...
                res["transcript"] = f"(speech to text failed: {str(e)[:150]})"
        return res
    if ext == ".pdf":
        # How a generated document looks (models wrote PyMuPDF scripts to render a page and look at it): the first
        # pages side by side in one picture, inspected like any image (colours, OCR text, the vision description).
        def sheet() -> tuple[Path, int]:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(path))
            pages = [doc[i].render(scale=1.4).to_pil().convert("RGB") for i in range(min(3, len(doc)))]
            w = sum(p.width for p in pages) + 12 * (len(pages) - 1)
            out = Image.new("RGB", (w, max(p.height for p in pages)), "#d9d9d9")
            x = 0
            for p in pages:
                out.paste(p, (x, 0))
                x += p.width + 12
            target = work / "screenshots" / f"{path.stem}-pages.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            out.save(target)
            return target, len(doc)
        pic, n = await asyncio.to_thread(sheet)
        img = Image.open(pic)
        res.update(kind="pdf", pages=n, sheet=str(pic), size=f"{img.width}x{img.height}")
        res.update(await asyncio.to_thread(_image_facts, img))
        seen = await describe_for("", pic, (question + " (the first pages of a PDF document, side by side)").strip(),
                                  budget=60)
        _vision(res, seen)
        return res
    raise ValueError(f"not an image, video, audio or PDF file: {path.name}")


def report(res: dict) -> str:
    """The inspection as text for the model."""
    lines = [f"{res['kind']} {res['file']}"]
    for k in ("size", "format", "duration_s", "size_mb", "video", "audio", "frames", "brightness", "contrast",
              "sharpness", "faces"):
        if res.get(k) not in (None, "", {}):
            lines.append(f"{k}: {res[k]}")
    if res.get("colours"):
        lines.append("dominant colours: " + ", ".join(res["colours"]))
    if res.get("exif"):
        lines.append("EXIF: " + ", ".join(f"{k}={v}" for k, v in res["exif"].items()))
    if res.get("description"):
        lines.append("What it shows (vision model " + res["description"])
        lines[-1] = lines[-1].replace(": ", "): ", 1)
    elif res["kind"] != "audio":
        lines.append("What it shows: " + (res.get("vision_note") or "no vision model is set (Settings > Models; free offline option: `ollama pull moondream`, 1.7 GB)")
                     + ". Rely only on the text, colours and facts here; never guess the content.")
    if res.get("text"):
        lines.append("Text in the image (OCR):\n" + res["text"])
    if res.get("frame_text"):
        lines.append("Text on key frames (OCR):\n" + "\n".join(res["frame_text"]))
    if res.get("transcript"):
        lines.append("Speech (transcript):\n" + res["transcript"])
    return "\n".join(lines)
