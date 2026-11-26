"""Media and device tools: stock_photo, inspect_media, generate_image, edit_video, animate_image, generate_video, mobile_env, speech_to_text, text_to_speech.

Split out of registry.py (round 2026-11-20). registry imports this module at its end and re-exports every name, so registry.X keeps working; import tools from registry, not from here."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from .. import approvals, policy
from ..config import LANG_DIR, load_settings
from ..process_manager import manager

from . import registry
from .registry import S, ToolResult, _network_gate, _path, _rel, clip, gate, tool  # noqa: F401
from .shell_tools import _did_you_mean


@tool("stock_photo", '<tool name="stock_photo" folder="images" count="3" wide="true">coffee shop interior</tool>',
      "Find real photos and download them into the working folder, web-sized. The photo services the user saved a key "
      "for (Pexels, Pixabay, Unsplash) are searched first, in order; one that is out of quota or rate limited is skipped "
      "and the next takes over; when none is usable the free Openverse / Wikimedia Commons photos are used (commercial-use "
      "licenses). Get ALL the photos a page needs in ONE call: list the subjects separated by commas "
      "(\"latte art cup, iced coffee, croissant, coffee shop interior\"); they are searched in parallel, one photo "
      "each (count = total). Short concrete English subjects work best. Use the returned relative paths (never hotlink "
      "a photo URL). Returns each file with its author and license for a credit line.",
      {"query": S("Subjects in English, comma separated: one call for every photo the page needs"), "folder": S("Folder in the working directory (default images)"),
       "count": {"type": "integer", "description": "How many photos (1-8, default 1)"},
       "wide": {"type": "boolean", "description": "Landscape photos only (hero/banner); default true"}},
      main="query", required=("query",))
async def stock_photo(ctx, args, body):
    from . import stock
    query = (args.get("query") or body).strip()
    if not query:
        return ToolResult(False, "Say what the photo should show.")
    if msg := await registry._network_gate(ctx, {"tool": "stock_photo", "url": "https://api.openverse.org"}):
        return ToolResult(False, msg)
    folder = _path(ctx, (args.get("folder") or "images").strip() or "images")
    if msg := await gate(ctx, {"tool": "stock_photo", "path": str(folder)}, policy.decide_file_write(folder / "x.jpg", ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    wide = str(args.get("wide", True)).lower() not in ("false", "0", "no")
    try:
        got = await stock.find(query, folder, int(re.sub(r"\D", "", str(args.get("count") or "")) or 1), wide)
    except Exception as e:  # network down, Pillow missing...
        return ToolResult(False, f"photo search failed: {str(e)[:200]}")
    if not got:
        return ToolResult(False, f"No usable photo found for {query!r}: try other, simpler English words, or use "
                                 "CSS/SVG art instead.")
    lines = []
    for g in got:
        rel = _rel(ctx, g["path"])
        ctx.files_changed.append(rel)
        lines.append(f"- {rel} ({g['width']}x{g['height']}) \"{g['title'][:70]}\" by {g['author']} · {g['license']} · {g['source']}")
    providers = list(dict.fromkeys(_provider_of(g.get("source") or g.get("url") or "") for g in got))
    return ToolResult(True, f"Downloaded {len(got)} photo(s) from {', '.join(providers)}; use these relative paths in the "
                            f"page (src=\"{_rel(ctx, got[0]['path'])}\") and add a small credit line (author, license, "
                            "source site) in the footer:\n" + "\n".join(lines),
                      {"files": [_rel(ctx, g["path"]) for g in got], "providers": providers,
                       # the step's photo grid: thumbnail, title, author, license, where it came from
                       "photos": [{"path": _rel(ctx, g["path"]), "title": str(g.get("title") or "")[:90],
                                   "author": str(g.get("author") or "")[:60], "license": str(g.get("license") or "")[:40],
                                   "provider": _provider_of(g.get("source") or g.get("url") or ""),
                                   "page": next((str(v) for v in (g.get("source"), g.get("url")) if str(v or "").startswith("http")), ""),
                                   "w": g.get("width"), "h": g.get("height")} for g in got]})


def _provider_of(url: str) -> str:
    """The photo service of a stock result, by its page's host (Pexels, Pixabay, Unsplash, Openverse, Wikimedia...)."""
    host = re.sub(r"^www\.", "", (re.match(r"https?://([^/]+)", url or "") or [None, ""])[1]).lower()
    for key, name in (("pexels", "Pexels"), ("pixabay", "Pixabay"), ("unsplash", "Unsplash"), ("wikimedia", "Wikimedia Commons"),
                      ("flickr", "Flickr (via Openverse)"), ("openverse", "Openverse"), ("rawpixel", "Rawpixel (via Openverse)")):
        if key in host:
            return name
    return f"{host} (via Openverse)" if host else "Openverse"


@tool("inspect_media", '<tool name="inspect_media" path="photo.jpg" transcript="true">what to look for</tool>',
      "See and hear any image, video, audio or PDF file (a PDF: its first pages as one picture - use it to check how a "
      "document you made looks, never write render scripts for that), even if you cannot see images yourself: returns its facts (size, "
      "duration, codecs, EXIF, dominant colours, brightness, sharpness, faces), the text in it (OCR, also on video "
      "frames), a description by a vision model (a video as numbered key frames at scene changes; the frame sheet "
      "is saved and shown to the user) and the speech as text (offline transcription). Use it before you describe, "
      "edit or judge a media file.",
      {"path": S("Image, video, audio or PDF file in the working folder"),
       "question": S("Optional: what to look for"),
       "transcript": {"type": "boolean", "description": "Transcribe speech in video/audio (default true)"},
       "minutes": {"type": "integer", "description": "Transcribe at most this many minutes (default 10)"}},
      main="question", required=("path",))
async def inspect_media(ctx, args, body):
    from . import media_inspect
    target = _path(ctx, (args.get("path") or "").strip())
    if not target.is_file():
        return ToolResult(False, f"No such file in the working folder: {args.get('path')}")
    try:
        res = await media_inspect.inspect(
            target, ctx.root, ctx.model, (args.get("question") or body or ctx.goal or "")[:400], ctx.lang or "tr",
            transcript=str(args.get("transcript", True)).lower() not in ("false", "0", "no"),
            minutes=float(re.sub(r"[^\d.]", "", str(args.get("minutes") or "")) or 10))
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # a broken file, ffmpeg missing...
        return ToolResult(False, f"inspection failed: {type(e).__name__}: {str(e)[:200]}")
    data: dict = {"path": _rel(ctx, target)}
    if res.get("sheet"):
        data["screenshot"] = _rel(ctx, Path(res["sheet"]))  # a PDF gives its page sheet as text  # the key-frame sheet appears under the step like a screenshot
        ctx.files_changed.append(data["screenshot"])
    return ToolResult(True, clip(media_inspect.report(res), 16000), data)


DIAGRAM_PROMPT = re.compile(r"flow\s*-?\s*chart|flow\s*diagram|workflow\s+diagram|sequence\s+diagram|architecture\s+"
                            r"diagram|block\s+diagram|mind\s*map|org(anization(al)?)?\s*chart|akış\s*şema|diyagram|"
                            r"\bşema\b|uml\b|gantt", re.I)
PHOTO_WORDS = re.compile(r"photo|realistic|3d\s+render|illustration\s+of\s+a\s+person|whiteboard\s+photo", re.I)


@tool("generate_image",'<tool name="generate_image" path="images/hero.jpg" width="1280" height="768">detailed English prompt</tool>',
      "Create a new picture from a description. The services with a key the user saved (Gemini, Cloudflare FLUX, Hugging "
      "Face, Together, OpenAI, Stability) are used in order; a service that is out of quota or rate limited is skipped "
      "and the next one takes over; when none is available the free FLUX of Pollinations makes it (no key). The result "
      "says which service made the picture. Photo-realistic scenes, product shots, illustrations, 3D renders, a picture "
      "'like this one' (first describe the original with inspect_media, then write that description as the prompt). "
      "Write a detailed English prompt: subject, setting, lighting, camera/style (e.g. 'food photography, top view, soft "
      "daylight'). For flowcharts / process diagrams write a ```mermaid block in the answer (the chat draws it); for other exact or text-heavy graphics draw with code (skia/drawsvg).",
      {"prompt": S("Detailed English description of the picture"), "path": S("Output file (default images/generated.jpg)"),
       "width": {"type": "integer", "description": "Width in px (256-2048, default 1024)"},
       "height": {"type": "integer", "description": "Height in px (256-2048, default 1024)"},
       "seed": {"type": "integer", "description": "Optional seed: the same seed and prompt give the same picture"}},
      main="prompt", required=("prompt",))
async def generate_image(ctx, args, body):
    prompt = (args.get("prompt") or body or "").strip()
    if not prompt:
        return ToolResult(False, "Describe the picture to create.")
    if DIAGRAM_PROMPT.search(prompt) and not PHOTO_WORDS.search(prompt):
        # An image model draws boxes with unreadable fake text; a real flowchart is Mermaid code the chat draws.
        return ToolResult(False, "Not generated: an image model cannot draw a readable flowchart or diagram. Write it "
                                 "as a ```mermaid block in your answer instead (the chat draws it; use_skill flowchart "
                                 "for a polished one); for a picture file use render_diagram with that Mermaid code.")
    if msg := await registry._network_gate(ctx, {"tool": "generate_image", "url": "https://image.pollinations.ai"}):
        return ToolResult(False, msg)
    rel = (args.get("path") or "images/generated.jpg").strip()
    target = _path(ctx, rel if Path(rel).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else rel + ".jpg")
    if msg := await gate(ctx, {"tool": "generate_image", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    from . import imagegen
    num = lambda k, d: max(256, min(2048, int(re.sub(r"\D", "", str(args.get(k) or "")) or d)))  # noqa: E731
    seed = int(args["seed"]) if str(args.get("seed") or "").strip().isdigit() else None
    try:
        data, service, clean = await imagegen.generate(prompt, num("width", 1024), num("height", 1024), seed)
    except RuntimeError as e:
        return ToolResult(False, f"image generation failed ({e}); try again or draw it with code.")
    w, h = await asyncio.to_thread(imagegen.save, data, target)
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    note = ("" if clean else " (the free service puts its small pollinations.ai logo in a corner; a free Pollinations "
            "token in Settings > Web > Image services removes it)")
    return ToolResult(True, f"created {out} ({w}x{h}px) with {service}{note}. It is shown to the user; look at it with "
                            "inspect_media if you need to check.", {"path": out, "files": [out], "service": service})


@tool("edit_video", '<tool name="edit_video">{"photos": ["images/a.jpg", "images/b.jpg"], "title": "Kahve Dükkanı", "captions": ["", "Dostlarla bir fincan"], "duration": 10, "music": "ambient", "output": "videos/tanitim.mp4"}</tool>',
      "Make a professional video with ffmpeg: moving pictures (Ken Burns zoom/pan), real transitions, animated titles, "
      "captions and name bars, colour looks, background music, neural voice-over, 16:9 / 9:16 / 1:1. The body is ONE "
      "JSON object. EASIEST (use it for photo videos): {\"photos\": [files or a folder], \"title\", \"subtitle\", "
      "\"captions\": [one per photo], \"narration\": [one spoken line per photo] (or one text / an .mp3 you made with "
      "text_to_speech for the whole video), \"duration\": seconds, \"music\": "
      "\"corporate\"|\"upbeat\"|\"lofi\"|\"cinematic\"|\"acoustic\"|\"electronic\"|\"ambient\"|\"calm\" (original music "
      "generated for this video) or an audio file, \"look\":\"warm\"|\"cinematic\"|\"vivid\"|\"bw\"|\"vintage\"|\"cool\", "
      "\"aspect\": \"16:9\"|\"9:16\"|\"1:1\", \"output\"} - timing, motion and transitions are done for you. FULL "
      "CONTROL: \"scenes\": [{\"src\", \"dur\", \"in\" (video start), \"motion\": zoom_in|zoom_out|pan_left|pan_right|"
      "pan_up|pan_down|none, \"transition\" (to the next): fade|dissolve|slideleft|slideup|circleopen|wipeleft|"
      "smoothleft|zoomin|radial|fadeblack|cut, \"title\", \"subtitle\", \"caption\", \"lower_third\", \"say\" (voice "
      "line), \"fit\": cover|blur|contain}] played in order; plus \"clips\": free layers at exact times ({\"type\": "
      "image|video|audio|text, \"src\", \"start\", \"dur\", \"x\", \"y\", \"scale\", \"style\": title|caption|"
      "lower_third|top}) for logos, picture-in-picture, extra text or sound; \"voiceover\": {\"text\"} or {\"src\"}. "
      "REAL MOTION: \"animate\": true (whole video or one scene) turns photos into AI video clips that move (free, ~1 min "
      "per photo, cached; without quota they keep Ken Burns). EFFECTS (free): \"effects\": [\"grain\", \"old_film\", "
      "\"vhs\", \"glitch\", \"shake\", \"letterbox\", \"glow\", \"light_leak\", \"sepia\", \"bw\", \"dreamy\", \"vignette\", "
      "\"sharpen\", \"flash_in\"] for the whole video or a scene. STYLED TEXT: any scene text may be an object "
      "{\"text\", \"x\": \"6%\", \"y\": \"74%\", \"size_pct\", \"color\", \"box\": \"#E8A33D@0.9\", \"outline\", \"bold\", "
      "\"font\": sans|serif|display|mono|script|condensed, \"animation\": fade|slide_up|slide_left|pop|none}. VOICE: "
      "\"voice\": {\"voice\": \"piper:tr_TR-fettah-medium\" (empty: the user's default voice; or \"gender\": female|male), "
      "\"rate\": 1, \"pitch\": 0, \"emotion\": 0.5, \"studio\": \"video\"}; the music is ducked under the voice by itself. "
      "SUBTITLES: \"subtitles\": true (or {\"size\", \"color\", \"position\": bottom|top}) burns the voice-over's "
      "sentences in with their real timings and writes a .srt next to the video. "
      "LOGO: \"logo\": {\"src\": \"images/logo.png\", \"position\": \"top_right\"|\"top_left\"|\"bottom_right\"|"
      "\"bottom_left\", \"size\": 0.15}. CHANGE A VIDEO YOU MADE: send only the changes on top of its project file: "
      "{\"base\": \"videos/x.timeline.json\", \"scenes\": {\"3\": {\"caption\": \"new text\"}}, \"logo\": {...}, "
      "\"music\": \"upbeat\", \"add_clips\": [...]} - everything else stays as it was (null removes a field). "
      "Sources are files in the working folder (download photos first with stock_photo). The result says exactly what "
      "the video contains (scenes, layers, texts, voice, music) and shows a preview sheet of key frames to the user.",
      {"timeline": S("ONE JSON object as described (photos + title is enough for a slideshow)"),
       "output": S("Output file, default videos/video.mp4")},
      main="timeline", required=("timeline",))
async def edit_video(ctx, args, body):
    from . import video_edit
    raw = (args.get("timeline") or body or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        spec = json.loads(raw) if raw else None
    except ValueError as e:
        return ToolResult(False, f"the timeline is not valid JSON ({str(e)[:120]}). Send ONE JSON object, e.g. "
                                 "{\"photos\": [\"images/a.jpg\", \"images/b.jpg\"], \"title\": \"...\", \"duration\": 10}")
    if isinstance(spec, list):  # a bare list of files or scenes
        spec = {"scenes": spec} if spec and isinstance(spec[0], dict) else {"photos": spec}
    if not isinstance(spec, dict):
        return ToolResult(False, "the timeline must be one JSON object (e.g. {\"photos\": [...], \"title\": \"...\"}).")
    out_rel = str(args.get("output") or spec.get("output") or "videos/video.mp4").strip()
    if Path(out_rel).suffix.lower() not in (".mp4", ".mov", ".mkv"):
        out_rel += ".mp4"
    target = _path(ctx, out_rel)
    if msg := await gate(ctx, {"tool": "edit_video", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    from .video_edit import TimelineError
    try:
        res = await video_edit.render(spec, ctx.root, target, ctx.lang or "tr")
    except TimelineError as e:
        return ToolResult(False, f"timeline error: {e}. Fix it and call edit_video again (or use the simple form: "
                                 "{\"photos\": [...], \"title\": \"...\", \"duration\": 10}).")
    except RuntimeError as e:
        return ToolResult(False, f"ffmpeg failed: {str(e)[:500]}")
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    data: dict = {"path": rel, "files": [rel]}
    if res.get("preview"):
        data["screenshot"] = _rel(ctx, res["preview"])  # the key-frame sheet appears under the step
        ctx.files_changed.append(data["screenshot"])
    warn = ""
    if res.get("gaps"):
        spans = ", ".join(f"{a:g}-{b:g} s" for a, b in res["gaps"])
        warn = (f" WARNING: the picture is black from {spans}: nothing covers that time. Fix the timing and render "
                "again, unless black is intended.")
    proj = ""
    if res.get("project"):
        pj = _rel(ctx, res["project"])
        proj = (f" Project file: {pj} - the user can open it in the Video Studio; to change this video later, read "
                "that file, edit its JSON and call edit_video with it (same output).")
    starts = res.get("scenes") or []
    scenes = (f" {len(starts)} scene(s) starting at " + ", ".join(f"{s:g}s" for s in starts) + ".") if starts else ""
    lay = res.get("layers") or {}
    layers = ", ".join(f"{v} {k} layer(s)" for k, v in lay.items() if v) or "no layers above the scenes"
    if res.get("ignored"):
        warn += (" NOT APPLIED - unknown fields were ignored: " + ", ".join(res["ignored"][:12]) + ". Use only the "
                 "documented fields (a logo is \"logo\": {\"src\", \"position\"}); do not say they are in the video.")
    extras = ", ".join(x for x in (layers, f"{res.get('texts', 0)} scene text(s)",
                                   f"look {res['look']}" if res.get("look") not in (None, "none") else "",
                                   "music" if res.get("music") else "",
                                   f"{res['voice']} voice line(s)" if res.get("voice") else
                                   "NO voice-over (no narration / voiceover / say was given)",
                                   f"subtitles burned in ({res['subtitles']} lines)" if res.get("subtitles") else "") if x)
    if not res.get("voice"):
        warn += (" The video has NO spoken voice: the sound is music only. If a voice-over was wanted, call "
                 "edit_video again with \"narration\": [one line per photo] or \"voiceover\": {\"src\": "
                 "\"<your .mp3>\"} / {\"text\": \"...\"}; never say it has a voice-over.")
    return ToolResult(True, f"rendered {rel}: {res['duration']:.1f} s, {res['width']}x{res['height']}, "
                            f"{'with' if res['audio'] else 'without'} sound, {res['size'] // 1024} KB"
                            f"{'; ' + extras if extras else ''}.{scenes}{warn}{proj} A preview sheet of key frames "
                            f"({data.get('screenshot', 'none')}) is shown to the user; check it (inspect_media on the "
                            "video for more) before you say it is done, and report only what this result says.",
                      data)


@tool("animate_image", '<tool name="animate_image" path="images/cafe.jpg" seconds="4" output="videos/cafe_moving.mp4">steam rising from the cup, people chatting, gentle camera push in</tool>',
      "Turn a photo into a short REAL video clip where things move (image-to-video AI: the paid services the user "
      "keyed in Settings first - Google Veo, fal.ai, Replicate, Runway - then free Wan 2.2 on Hugging Face GPUs, about "
      "40-60 s per photo with a daily free quota). The prompt says what "
      "should move, in English. In edit_video the same happens for photo scenes with \"animate\": true (or the whole "
      "video's \"animate\": true), so a photo video looks like footage instead of a slideshow; results are cached.",
      {"path": S("Photo in the working folder"), "prompt": S("What should move, in English"),
       "seconds": {"type": "number", "description": "Clip length 1.5-5 s (default 4)"},
       "output": S("Output .mp4 (default videos/<name>_moving.mp4)")},
      main="prompt", required=("path",))
async def animate_image(ctx, args, body):
    from . import animate
    src = _path(ctx, (args.get("path") or "").strip())
    if not src.is_file():
        return ToolResult(False, f"No such picture in the working folder: {args.get('path')}")
    out_rel = (args.get("output") or f"videos/{src.stem}_moving.mp4").strip()
    target = _path(ctx, out_rel if out_rel.lower().endswith(".mp4") else out_rel + ".mp4")
    if msg := await registry._network_gate(ctx, {"tool": "animate_image", "url": "https://huggingface.co"}):
        return ToolResult(False, msg)
    if msg := await gate(ctx, {"tool": "animate_image", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        secs = float(args.get("seconds") or 4)
    except ValueError:
        secs = 4.0
    try:
        clip, how = await animate.animate(src, ctx.root, (args.get("prompt") or body or "").strip(), secs)
    except animate.AnimateError as e:
        return ToolResult(False, f"animation failed: {e} The picture can still move with Ken Burns in edit_video.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, target)
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    return ToolResult(True, f"made {rel} from {_rel(ctx, src)} ({'cached' if how == 'cache' else how}). Use it as a "
                            "video scene in edit_video (or set \"animate\": true on the photo scene).",
                      {"path": rel, "files": [rel]})


@tool("generate_video", '<tool name="generate_video" output="videos/coffee.mp4" seconds="4" aspect="16:9">a barista pours '
      'latte art in a cozy cafe, steam rising, slow camera push in, cinematic</tool>',
      "Text-to-video and image-to-video with AI: makes a short REAL video clip (things move) from a description. "
      "Without image, the first frame is generated from the prompt (keyed image services first, else free FLUX), then "
      "it is animated by the AI video services of Settings in order (paid ones with a key: Google Veo, fal.ai, "
      "Replicate, Runway; then free Wan 2.2 on Hugging Face GPUs, 40-90 s per clip). With image=<photo path> that "
      "photo moves. "
      "Prompt in English: subject, action, camera move, mood. For a longer video make several clips and join them "
      "(with music, voice, titles) in edit_video.",
      {"prompt": S("What happens in the clip, in English"), "image": S("Optional: a photo in the working folder to animate"),
       "seconds": {"type": "number", "description": "Clip length 1.5-10 s (default 4; the free services make at most 5)"},
       "aspect": S("16:9 (default), 9:16 or 1:1", enum=["16:9", "9:16", "1:1"]),
       "output": S("Output .mp4 (default videos/<slug>.mp4)")},
      main="prompt", required=())
async def generate_video(ctx, args, body):
    from . import animate, imagegen
    prompt = (args.get("prompt") or body or "").strip()
    if not prompt and not args.get("image"):
        return ToolResult(False, "Describe the clip (prompt) or give image=<photo>.")
    from .stock import _slug
    slug = _slug(prompt)[:40] or "clip"
    out_rel = (args.get("output") or f"videos/{slug}.mp4").strip()
    target = _path(ctx, out_rel if out_rel.lower().endswith(".mp4") else out_rel + ".mp4")
    if msg := await registry._network_gate(ctx, {"tool": "generate_video", "url": "https://huggingface.co"}):
        return ToolResult(False, msg)
    if msg := await gate(ctx, {"tool": "generate_video", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    made = []
    if args.get("image"):
        frame = _path(ctx, str(args["image"]).strip())
        if not frame.is_file():
            return ToolResult(False, f"No such picture in the working folder: {args['image']}" + _did_you_mean(ctx, frame.name))
        service = "your photo"
    else:
        w, h = {"9:16": (768, 1344), "1:1": (1024, 1024)}.get(str(args.get("aspect") or ""), (1344, 768))
        try:
            data, service, _clean = await imagegen.generate(prompt + ", photorealistic, cinematic still, sharp focus", w, h)
        except Exception as e:  # noqa: BLE001 - every image service down
            return ToolResult(False, f"the first frame could not be generated: {str(e)[:200]}")
        frame = _path(ctx, f"images/{slug}-frame.jpg")
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(data)
        made.append(_rel(ctx, frame))
    try:
        secs = max(1.5, min(10.0, float(args.get("seconds") or 4)))
    except ValueError:
        secs = 4.0
    try:
        clip, how = await animate.animate(frame, ctx.root, prompt, secs, str(args.get("aspect") or "16:9"))
    except animate.AnimateError as e:
        return ToolResult(False, f"animation failed: {e} The frame {made[0] if made else _rel(ctx, frame)} can still be "
                                 "used as a photo scene (Ken Burns motion) in edit_video.", {"files": made})
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, target)
    rel = _rel(ctx, target)
    made.append(rel)
    ctx.files_changed.extend(made)
    return ToolResult(True, f"made {rel} ({secs:.1f} s, first frame: {service}, motion: {how}). Join several clips with "
                            "music / voice / titles in edit_video (scenes: [{\"src\": \"" + rel + "\"}, ...]).",
                      {"path": rel, "files": made, "providers": [service, how]})


@tool("mobile_env", '<tool name="mobile_env" action="status"></tool>',
      "Mobile app testing: Android emulator (Windows/macOS/Linux) and Maestro UI flows; iOS simulator only on macOS "
      "with Xcode. action=status (what is installed and running) | setup (installs the Android SDK, emulator, a Pixel "
      "AVD and Maestro into the app's data folder, no admin; several GB, once; installs Java 17 itself) | java (a portable JDK 17 into the app's data folder: no installer, no admin, works while winget / MSI is locked) | start (boots the "
      "emulator and waits for it) | install (path=app.apk) | launch (package=com.x.y) | screenshot (path=shots/x.png, "
      "you can look at it) | flow (path=flow.yaml: a Maestro test; launchApp, tapOn, inputText, assertVisible...) | "
      "adb (args=\"shell pm list packages\") | gradle (installs Gradle 8.13 once for all projects; args=version) | "
      "sdk (args=\"platforms;android-36 build-tools;36.0.0\" installs SDK packages; args=\"--list\" shows the names). "
      "status returns every path (ANDROID_HOME, JAVA_HOME, gradle, adb, emulator, sdkmanager), the installed "
      "platforms / build-tools / system images, verified version sets for compileSdk 36 and 37, and the rules - read it "
      "first instead of searching the disk. Web-based apps (Expo web, Flutter web, Capacitor, PWA) are tested "
      "faster in the browser tools at phone size.",
      {"action": S("Action", enum=["status", "setup", "java", "start", "install", "launch", "screenshot", "flow", "adb",
                                   "gradle", "sdk"]),
       "path": S("APK, flow .yaml or screenshot path"), "package": S("Android package id for launch"),
       "args": S("adb arguments for action=adb"),
       "headless": {"type": "boolean", "description": "start: no emulator window"}},
      main="action", required=("action",))
async def mobile_env(ctx, args, body):
    from . import mobile
    action = (args.get("action") or body or "status").strip().lower()
    try:
        if action == "status":
            return ToolResult(True, json.dumps(await mobile.status(), ensure_ascii=False))
        if action == "setup":
            if msg := await gate(ctx, {"tool": "mobile_env", "path": str(mobile.ROOT)}, policy.decide_file_write(
                    mobile.ROOT / "x", ctx.root, ctx.mode)):
                return ToolResult(False, msg)
            st = await mobile.setup()
            return ToolResult(True, "Android test environment ready: " + json.dumps(st, ensure_ascii=False))
        if action == "java":
            if msg := await gate(ctx, {"tool": "mobile_env", "path": str(mobile.JDK_DIR)}, policy.decide_file_write(
                    mobile.JDK_DIR / "x", ctx.root, ctx.mode)):
                return ToolResult(False, msg)
            home = await mobile.install_java()
            return ToolResult(True, f"Java 17 ready (portable): JAVA_HOME={home}; mobile_env commands use it "
                                    "automatically. For a shell command set $env:JAVA_HOME and PATH to it.")
        if action == "start":
            st = await mobile.start(headless=str(args.get("headless", "")).lower() in ("true", "1", "yes"))
            return ToolResult(True, f"emulator running: {st['devices']}")
        if action == "install":
            apk = _path(ctx, args.get("path") or "")
            if not apk.is_file():
                return ToolResult(False, f"no such APK: {args.get('path')}" + _did_you_mean(ctx, apk.name))
            code, out = await mobile.adb("install", "-r", "-t", str(apk), timeout=600)
            return ToolResult(code == 0 and "Success" in out, out[-1500:])
        if action == "launch":
            pkg = (args.get("package") or "").strip()
            code, out = await mobile.adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
            return ToolResult(code == 0 and "No activities" not in out, out[-800:])
        if action == "screenshot":
            target = _path(ctx, args.get("path") or "shots/device.png")
            await mobile.screenshot(target)
            rel = _rel(ctx, target)
            ctx.files_changed.append(rel)
            return ToolResult(True, f"saved {rel} (look at it with inspect_media)", {"path": rel, "files": [rel]})
        if action == "flow":
            flow = _path(ctx, args.get("path") or "")
            if not flow.is_file():
                return ToolResult(False, f"no such flow file: {args.get('path')} (write a Maestro .yaml first)")
            maestro = shutil.which("maestro", path=mobile.env()["PATH"])
            if not maestro:
                return ToolResult(False, "Maestro is not installed: call mobile_env action=setup")
            # run in the working folder: '- takeScreenshot: shots/x' lands in the project (it went to the app's own
            # folder / ~/.maestro before, and the model searched for the pictures)
            t_flow = time.time()
            code, out = await mobile._run(maestro, "test", str(flow), timeout=900, cwd=str(ctx.root))
            dirs = {ctx.root, ctx.root / "shots", ctx.root / "screenshots", flow.parent, flow.parent / "shots"}
            shots = sorted({p for d in dirs if d.is_dir() for p in d.glob("*.png") if p.stat().st_mtime >= t_flow - 1})[:12]
            rels = [_rel(ctx, p) for p in shots]
            ctx.files_changed += rels
            return ToolResult(code == 0, out[-3000:] + (f"\nScreenshots: {', '.join(rels)}" if rels else ""),
                              {"files": rels} if rels else {})
        if action == "gradle":
            if msg := await gate(ctx, {"tool": "mobile_env", "path": str(mobile.GRADLE_DIR)}, policy.decide_file_write(
                    mobile.GRADLE_DIR / "x", ctx.root, ctx.mode)):
                return ToolResult(False, msg)
            ver = (args.get("args") or mobile.GRADLE_VERSION).strip()
            path = await mobile.install_gradle(ver)
            return ToolResult(True, f"Gradle {ver} ready: {path} (shared by all projects; use this path, or make a "
                                    f"wrapper in the project with: \"{path}\" wrapper --gradle-version {ver})")
        if action == "sdk":
            pkgs = shlex.split(args.get("args") or body or "--list")
            if pkgs != ["--list"]:
                if msg := await gate(ctx, {"tool": "mobile_env", "path": str(mobile.sdk_root())},
                                     policy.decide_file_write(mobile.sdk_root() / "x", ctx.root, ctx.mode)):
                    return ToolResult(False, msg)
            code, out = await mobile.sdk_install(pkgs)
            return ToolResult(code == 0, out[-4000:] + ("" if pkgs == ["--list"] else
                              "\nInstalled now: " + json.dumps(mobile.sdk_inventory(mobile.sdk_root()), ensure_ascii=False)))
        if action == "adb":
            code, out = await mobile.adb(*shlex.split(args.get("args") or "devices"))
            return ToolResult(code == 0, out[-3000:])
    except Exception as e:  # noqa: BLE001 - every failure is reported with its reason
        return ToolResult(False, f"{action} failed: {str(e)[:500]}")
    return ToolResult(False, f"unknown action {action}")


@tool("speech_to_text", '<tool name="speech_to_text" path="interview.mp4" language="tr" model="base"></tool>',
      "Turn the speech in an audio or video file into text, offline (faster-whisper on the CPU): returns the "
      "transcript with timestamps and writes <name>.srt (subtitles) and <name>.txt into the working folder. "
      "language: optional (auto-detected); model: tiny (fastest), base (default), small or medium (more accurate, "
      "slower); minutes: only the first N minutes.",
      {"path": S("Audio or video file in the working folder"), "language": S("Optional language code: tr, en..."),
       "model": S("tiny | base | small | medium"),
       "minutes": {"type": "integer", "description": "Only the first N minutes (default: all)"}},
      required=("path",))
async def speech_to_text(ctx, args, body):
    from . import speech
    target = _path(ctx, (args.get("path") or body or "").strip())
    if not target.is_file():
        return ToolResult(False, f"No such file in the working folder: {args.get('path') or body}")
    from .media_inspect import AUDIO, VIDEO
    if target.suffix.lower() not in AUDIO | VIDEO:
        return ToolResult(False, f"{target.name} is not an audio or video file. For a picture use inspect_media "
                                 "(it reads the text in it with OCR).")
    out_dir = target.parent
    if msg := await gate(ctx, {"tool": "speech_to_text", "path": str(out_dir / (target.stem + ".srt"))},
                         policy.decide_file_write(out_dir / (target.stem + ".srt"), ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        res = await speech.speech_to_text(target, out_dir, (args.get("language") or "").strip() or None,
                                          (args.get("model") or "base").strip(),
                                          float(re.sub(r"[^\d.]", "", str(args.get("minutes") or "")) or 0))
    except ImportError:
        return ToolResult(False, "faster-whisper is not installed (run install.bat / install.sh).")
    except Exception as e:
        return ToolResult(False, f"speech to text failed: {type(e).__name__}: {str(e)[:200]}")
    srt, txt = _rel(ctx, res["srt"]), _rel(ctx, res["txt"])
    ctx.files_changed += [srt, txt]
    if not res["segments"]:
        return ToolResult(True, f"No speech was found in {target.name} (silence or music only).", {"path": txt})
    return ToolResult(True, clip(
        f"Transcribed {res['segments']} segments, {int(res['duration'])} s of speech, language {res['language']}; "
        f"saved {srt} (subtitles) and {txt} (plain text).\nShow the transcript to the user as this table (translate "
        f"the header to the user's language, keep the times), then name the two files:\n\n{res['text']}", 16000),
        {"path": txt, "files": [srt, txt]})


@tool("text_to_speech", '<tool name="text_to_speech" path="audio/intro.mp3" language="tr" gender="female" srt="true">text to read</tool>',
      "Turn text into natural speech with a studio finish: writes an .mp3 (or .wav/.m4a) into the working folder, any "
      "length. Voices (Settings > Voices): local and offline first (piper:tr_TR-fettah-medium, kokoro:af_heart, "
      "chatterbox:default@tr for the most natural / emotional; installed Turkish voice packs such as seda:v03, "
      "pocket:female_1, supertonic:M1, xtts:<speaker> - only ids the user installed; the user's own cloned voices are "
      "<engine>:ref-<name>, e.g. xtts:ref-onur), then Microsoft's online voices "
      "(tr-TR-EmelNeural). "
      "Leave voice empty: the user's default voice for the language (gender female/male picks one). Tone: rate "
      "0.5-2.0, pitch -6..+6 semitones, emotion 0-1, pause (seconds between sentences), studio natural|podcast|"
      "broadcast|video|warm|none. Dialogs: lines 'Name: text' with speakers {\"Ayşe\": \"female\", \"Can\": "
      "\"male\"} (or voice ids) are read by different voices. srt=true also writes subtitles with real timings.",
      {"text": S("The text to read"), "path": S("Output path (default speech.mp3)"),
       "language": S("Language code: tr, en, de..."), "gender": S("female | male"),
       "voice": S("Optional exact voice id"),
       "rate": {"type": "number", "description": "Speed 0.5-2.0 (default from settings)"},
       "pitch": {"type": "number", "description": "Semitones -6..+6"},
       "emotion": {"type": "number", "description": "0 calm .. 1 expressive"},
       "pause": {"type": "number", "description": "Seconds between sentences"},
       "studio": S("Finish", enum=["natural", "podcast", "broadcast", "video", "warm", "none"]),
       "speakers": {"type": "object", "description": "Dialog: {speaker name: voice id | female | male}"},
       "srt": {"type": "boolean", "description": "Also write a .srt subtitle file with the real timings"}},
      main="text", required=("text",))
async def text_to_speech(ctx, args, body):
    from . import speech
    text = (args.get("text") or body or "").strip()
    if not text:
        return ToolResult(False, "Give the text to read.")
    rel = (args.get("path") or "speech.mp3").strip()
    target = _path(ctx, rel if rel.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac")) else rel + ".mp3")
    if msg := await gate(ctx, {"tool": "text_to_speech", "path": str(target)},
                         policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)

    def num(k):
        try:
            return float(args[k]) if args.get(k) not in (None, "") else None
        except (TypeError, ValueError):
            return None
    speakers = args.get("speakers")
    if isinstance(speakers, str):
        try:
            speakers = json.loads(speakers)
        except ValueError:
            speakers = None
    try:
        res = await speech.text_to_speech(
            text, target, (args.get("language") or ctx.lang or "tr").strip().lower()[:3],
            (args.get("voice") or "").strip(), (args.get("gender") or "").strip(), num("rate"),
            pitch=num("pitch"), emotion=num("emotion"), pause=num("pause"),
            preset=(args.get("studio") or None), speakers=speakers if isinstance(speakers, dict) else None,
            srt=str(args.get("srt", "")).lower() in ("true", "1", "yes"))
    except Exception as e:  # offline, unknown voice...
        return ToolResult(False, f"text to speech failed: {str(e)[:200]}")
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    extra = ""
    if res.get("srt"):
        ctx.files_changed.append(_rel(ctx, res["srt"]))
        extra += f", subtitles {_rel(ctx, res['srt'])}"
    if len(res.get("voices") or []) > 1:
        extra += f", voices {', '.join(res['voices'])}"
    if res.get("fallback_from"):
        extra += f" ({res['fallback_from']} failed, so {res['voice']} read it)"
    return ToolResult(True, f"saved {out} ({res['bytes'] // 1024} KB, {res['duration']} s, voice {res['voice']}"
                            f"{extra}, {res['chars']} characters). The user plays it in the chat and can pick another "
                            "voice there (with previews).",
                      {"path": out, "tts": {"text": text[:20000], "voice": res["voice"], "lang": res["lang"],
                                            "rate": num("rate") or 1.0}})
