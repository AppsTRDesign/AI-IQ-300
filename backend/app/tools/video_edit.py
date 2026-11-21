"""Timeline video editor (ffmpeg): one JSON description in, one finished, professional-looking video out.

Two ways to describe a video (both can be combined):

1. scenes - the main track, played one after another with real transitions between them (the easy, pro path):
     {"aspect": "16:9", "look": "warm", "music": "ambient",
      "scenes": [{"src": "images/a.jpg", "dur": 4, "motion": "zoom_in", "title": "Kahve Dükkanı",
                  "subtitle": "Her gün taze", "transition": "fade"},
                 {"src": "clips/b.mp4", "in": 2, "dur": 5, "caption": "Barista", "say": "Text read aloud"}]}
   - picture scenes move (Ken Burns): motion zoom_in | zoom_out | pan_left | pan_right | pan_up | pan_down | none | auto
   - transition to the next scene: fade, dissolve, fadeblack, fadewhite, slideleft, slideright, slideup, slidedown,
     wipeleft, wiperight, circleopen, circleclose, radial, smoothleft, smoothright, zoomin, pixelize, cut, auto
   - text on a scene (animated): title (+ subtitle), caption (bottom), lower_third (name bar), text + text_style
   - say: a voice-over line read at the start of that scene (neural TTS)
   - fit: cover (default) | blur (whole picture over a blurred copy of itself) | contain (black bars)

   Shortcut for weak models: {"photos": ["images/a.jpg", "images/b.jpg"], "title": "...", "duration": 10} builds the
   scenes (even timing, varied motions and transitions, title on the first scene, captions[i] on scene i).

2. clips - free layers above the scenes at exact times (logos, picture-in-picture, extra text, sound effects):
     type video | image | audio | text, start (timeline seconds), in, dur / out, x, y, scale, volume, fade_in, fade_out

Whole video: width/height or aspect (16:9, 9:16, 1:1, 4:5), fps, duration, look (warm | cinematic | vivid | bw |
vintage | cool | none), music ("ambient" | "upbeat" | "calm" generated, or a file; {"src", "volume"}), voiceover
({"text", "gender", "language", "voice", "start"} or {"src"}), fade (fade in from / out to black, default on with
scenes), quality (good | fast | small), output. A preview sheet of key frames is written next to the video.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

TYPES = ("video", "image", "audio", "text")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_CLIPS = 80
MAX_SECONDS = 1800
PRESETS = {"good": ("medium", "19"), "fast": ("veryfast", "23"), "small": ("slow", "27")}
ASPECTS = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1280, 960),
           "21:9": (1680, 720)}
FONTS = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"]
BOLD_FONTS = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
TRANSITIONS = {"fade", "dissolve", "fadeblack", "fadewhite", "slideleft", "slideright", "slideup", "slidedown",
               "wipeleft", "wiperight", "wipeup", "wipedown", "circleopen", "circleclose", "radial", "smoothleft",
               "smoothright", "smoothup", "smoothdown", "zoomin", "pixelize", "hblur", "distance", "fadegrays",
               "squeezeh", "squeezev", "diagtl", "diagbr", "horzopen", "vertopen"}
AUTO_TRANSITIONS = ["fade", "slideleft", "circleopen", "smoothleft", "dissolve", "wipeleft", "zoomin", "radial"]
MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "none")
AUTO_MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "zoom_in", "pan_down", "zoom_out"]
LOOKS = {
    "warm": "colorbalance=rs=0.06:gs=0.02:bs=-0.06:rm=0.04:bm=-0.04,eq=saturation=1.12:contrast=1.05",
    "cinematic": "eq=contrast=1.1:saturation=0.88:brightness=-0.02,colorbalance=rs=-0.04:bs=0.06:rh=0.06:bh=-0.05,"
                 "vignette=angle=PI/5",
    "vivid": "eq=saturation=1.35:contrast=1.08",
    "bw": "hue=s=0,eq=contrast=1.15",
    "vintage": "curves=preset=vintage,eq=saturation=0.85,vignette=angle=PI/4",
    "cool": "colorbalance=rs=-0.05:bs=0.07:bm=0.04,eq=saturation=1.05",
    "none": "",
}
TIMEOUT = 1500
SEPIA = "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
# Effects (free, offline: ffmpeg filters). Simple ones are one filter string; glow / light_leak build small graphs.
EFFECTS = {
    "grain": "noise=alls=14:allf=t+u",
    "old_film": SEPIA + ",noise=alls=22:allf=t+u,eq=brightness='0.025*sin(t*37)':eval=frame,vignette=angle=PI/4",
    "vhs": "rgbashift=rh=-3:bh=3,noise=alls=10:allf=t,eq=saturation=0.85:contrast=1.05,drawgrid=w=iw:h=4:t=1:c=black@0.18",
    "glitch": "rgbashift=rh=9:bv=-7:enable='lt(mod(t,2.6),0.13)',noise=alls=30:allf=t:enable='lt(mod(t,2.6),0.13)'",
    "shake": "crop=w=iw*0.96:h=ih*0.96:x='(iw-ow)/2+iw*0.012*sin(t*19)':y='(ih-oh)/2+ih*0.012*sin(t*27)',scale={W}:{H}",
    "letterbox": "drawbox=x=0:y=0:w=iw:h=ih*0.11:color=black:t=fill,drawbox=x=0:y=ih*0.89:w=iw:h=ih*0.11:color=black:t=fill",
    "sepia": SEPIA,
    "bw": "hue=s=0,eq=contrast=1.12",
    "sharpen": "unsharp=5:5:0.8",
    "dreamy": "gblur=sigma=1.4,eq=brightness=0.03:saturation=1.12",
    "vignette": "vignette=angle=PI/5",
    "flash_in": "fade=t=in:st=0:d=0.35:color=white",
    "glow": None,  # graph: soft bloom (screen blend of a blurred copy)
    "light_leak": None,  # graph: a warm moving gradient over the picture
}


def effect_chain(names, W: int, H: int, FPS: float, T: float, src: str, dst: str, tag: str) -> list[str]:
    """Filter graph lines taking [src] to [dst] through the named effects (unknown names raise TimelineError)."""
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    lines, cur = [], src
    for n, name in enumerate(names or []):
        name = str(name).lower().replace("-", "_").replace(" ", "_")
        if name not in EFFECTS:
            raise TimelineError(f"effect {name!r} is not known; use: {', '.join(EFFECTS)}")
        nxt = f"{dst}_{n}" if n + 1 < len(names) else dst
        if name == "glow":
            lines += [f"[{cur}]split[gw{tag}{n}a][gw{tag}{n}b]", f"[gw{tag}{n}b]gblur=sigma=16[gw{tag}{n}g]",
                      f"[gw{tag}{n}a][gw{tag}{n}g]blend=all_mode=screen:all_opacity=0.35[{nxt}]"]
        elif name == "light_leak":
            lines += [f"gradients=s={W}x{H}:c0=0xffa040:c1=0x000000:c2=0xff4f7a:speed=0.012:duration={T + 1:.2f}:"
                      f"rate={FPS:g},format=rgba,colorchannelmixer=aa=0.32[lk{tag}{n}]",
                      f"[{cur}][lk{tag}{n}]overlay=0:0:shortest=1[{nxt}]"]
        else:
            lines.append(f"[{cur}]{EFFECTS[name].format(W=W, H=H)}[{nxt}]")
        cur = nxt
    if cur != dst:
        lines.append(f"[{cur}]null[{dst}]")
    return lines


class TimelineError(ValueError):
    """The timeline is wrong; the message tells the model what to fix."""


def _num(v, name: str, lo: float, hi: float, default: float | None = None) -> float:
    if v is None or v == "":
        if default is None:
            raise TimelineError(f"{name} is required")
        v = default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise TimelineError(f"{name} must be a number, got {v!r}") from None
    if not lo <= x <= hi:
        raise TimelineError(f"{name} must be between {lo:g} and {hi:g}, got {x:g}")
    return x


def _pos(v, axis: str, text: bool = False) -> str:
    """An ffmpeg expression for a position: pixels, or a word with an optional +/-N offset."""
    if v is None:
        v = "left" if axis == "x" else "top"
    if (pm := re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*%\s*", str(v))):  # "35%": share of the frame (studio drag)
        frame = ("w" if axis == "x" else "h") if text else ("main_w" if axis == "x" else "main_h")
        return f"{frame}*{float(pm[1]) / 100:.4f}"
    if isinstance(v, (int, float)) or re.fullmatch(r"-?\d+(\.\d+)?", str(v).strip()):
        return str(int(float(v)))
    m = re.fullmatch(r"\s*(left|center|middle|right|top|bottom)\s*([+-]\s*\d+)?\s*", str(v).lower())
    if not m:
        raise TimelineError(f"position {v!r}: use pixels, or left|center|right (x) / top|middle|bottom (y), optionally +N/-N")
    word, off = m[1], (m[2] or "").replace(" ", "")
    if text:
        table = {"x": {"left": "40", "center": "(w-text_w)/2", "middle": "(w-text_w)/2", "right": "w-text_w-40"},
                 "y": {"top": "40", "middle": "(h-text_h)/2", "center": "(h-text_h)/2", "bottom": "h-text_h-40"}}
    else:
        table = {"x": {"left": "0", "center": "(main_w-overlay_w)/2", "middle": "(main_w-overlay_w)/2",
                       "right": "main_w-overlay_w"},
                 "y": {"top": "0", "middle": "(main_h-overlay_h)/2", "center": "(main_h-overlay_h)/2",
                       "bottom": "main_h-overlay_h"}}
    if word not in table[axis]:
        raise TimelineError(f"position {v!r} is not valid for {axis}")
    base = table[axis][word]
    return f"({base}){off}" if off else base


def _esc(path: str) -> str:
    """A path inside a filter argument: forward slashes, colons escaped, quoted."""
    return "'" + path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'") + "'"


def _first(paths: list[str]) -> str:
    return next((p for p in paths if Path(p).is_file()), "")


def _font_paths(spec: dict, root: Path) -> tuple[str, str]:
    """(regular, bold) font files. A font given in the timeline is used for both."""
    if spec.get("font"):
        p = Path(str(spec["font"]))
        p = p if p.is_absolute() else root / p
        if not p.is_file():
            raise TimelineError(f"font file not found: {spec['font']}")
        return str(p), str(p)
    regular = _first(FONTS)
    if not regular:
        raise TimelineError("no font found on this computer: set font to a .ttf file in the working folder")
    return regular, _first(BOLD_FONTS) or regular


_FF_MAJOR: list[int] = []


def _ffmpeg_major() -> int:
    """drawtext text_align (centred lines) needs ffmpeg 7+; older builds get left-aligned lines."""
    if not _FF_MAJOR:
        try:
            out = subprocess.run([_ffmpeg(), "-version"], capture_output=True, text=True, timeout=20).stdout
            m = re.search(r"ffmpeg version n?(\d+)", out)
            _FF_MAJOR.append(int(m[1]) if m else 0)
        except Exception:
            _FF_MAJOR.append(0)
    return _FF_MAJOR[0]


def _kind_of(src: str) -> str:
    ext = Path(src).suffix.lower()
    return "image" if ext in IMAGE_EXT else "audio" if ext in AUDIO_EXT else "video"


def _expand(root: Path, src: str) -> list[str]:
    """A folder given as a source stands for the pictures and videos in it (sorted by name)."""
    p = Path(src) if Path(src).is_absolute() else root / src
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXT | VIDEO_EXT
                       and not f.name.startswith("."))
        return [str(f.relative_to(root)).replace("\\", "/") if not Path(src).is_absolute() else str(f) for f in files]
    return [src]


TOP_KEYS = {"width", "height", "aspect", "fps", "duration", "look", "music", "voiceover", "fade", "quality", "output",
            "scenes", "clips", "transition", "transition_dur", "font", "fit", "photos", "images", "pictures", "files",
            "captions", "narration", "says", "title", "subtitle", "outro", "logo", "watermark", "base", "project",
            "add_clips", "remove_scenes", "voice", "effects", "animate", "add_scenes", "remove_clips", "subtitles"}
SCENE_KEYS = {"src", "dur", "in", "out", "motion", "transition", "transition_dur", "title", "subtitle", "caption",
              "lower_third", "text", "text_style", "say", "fit", "volume", "color", "voice", "effects", "animate",
              "motion_prompt", "animated_src", "stretch"}
CLIP_KEYS = {"type", "src", "start", "dur", "in", "out", "x", "y", "scale", "volume", "fade_in", "fade_out", "text",
             "style", "size", "size_pct", "color", "box", "bold", "animation", "opacity", "fit", "_logo", "font",
             "outline", "shadow", "align", "wrap", "delay", "name"}
LOGO_POS = {"top_right": ("{r}", "{m}"), "top_left": ("{m}", "{m}"), "bottom_right": ("{r}", "{b}"),
            "bottom_left": ("{m}", "{b}"), "center": ("center", "center")}


def ignored_keys(spec: dict) -> list[str]:
    """Fields the engine does not know (a model inventing "logo_position" etc.): reported, never silently dropped."""
    out = [k for k in spec if k not in TOP_KEYS]
    for i, sc in enumerate(spec.get("scenes") or []):
        if isinstance(sc, dict):
            out += [f"scenes[{i + 1}].{k}" for k in sc if k not in SCENE_KEYS]
    for i, c in enumerate(spec.get("clips") or []):
        if isinstance(c, dict):
            out += [f"clips[{i + 1}].{k}" for k in c if k not in CLIP_KEYS]
    return out


def _apply_patch(spec: dict, root: Path) -> dict:
    """{"base": "videos/x.timeline.json", "scenes": {"3": {"caption": "..."}}, "logo": {...}, "music": "upbeat"}:
    only what is given changes, everything else stays as in the project file (a weak model rewriting the whole JSON
    from memory dropped voice lines and titles). A field set to null is removed."""
    base_path = str(spec.get("base") or spec.get("project") or "")
    p = Path(base_path) if Path(base_path).is_absolute() else root / base_path
    if p.suffix.lower() in (".mp4", ".mov", ".mkv"):
        p = project_path(p)
    if not p.is_file():
        raise TimelineError(f"base project not found: {base_path} (use the .timeline.json path the last render reported)")
    try:
        base = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise TimelineError(f"base project is not valid JSON: {e}") from None
    return merge_patch(base, spec)


TEXT_KEYS = ("title", "subtitle", "caption", "lower_third", "text")


def _merge_item(item: dict, change: dict) -> dict:
    out = dict(item)
    for ck, cv in (change or {}).items():
        if ck == "#":  # the number a model saw in numbered_view, not a field
            continue
        if cv is None:
            out.pop(ck, None)
        elif ck in TEXT_KEYS and isinstance(cv, dict) and ck in out:
            # {"caption": {"color": "red"}} keeps the caption's text (and other styles)
            old = out[ck] if isinstance(out[ck], dict) else {"text": out[ck]}
            out[ck] = {**old, **cv}
        else:
            out[ck] = cv
    return out


def _numbered(items: list, change: dict, what: str) -> list:
    """{"3": {...}} merged into item 3 (1-based); null removes the item."""
    items = [dict(x) if isinstance(x, dict) else x for x in items]
    for key, ch in change.items():
        try:
            n = int(str(key).strip()) - 1
        except ValueError:
            raise TimelineError(f"{what} patch keys are numbers (1, 2, 3...), got {key!r}") from None
        if not 0 <= n < len(items):
            raise TimelineError(f"there is no {what[:-1]} {key}: the project has {len(items)} {what}")
        if what == "clips" and isinstance(ch, dict) and isinstance(items[n], dict) and "type" not in ch:
            kind = items[n].get("type") or "text"
            if kind != "text" and TEXT_ONLY & set(ch):
                texts = [str(i + 1) for i, x in enumerate(items) if isinstance(x, dict) and (x.get("type") or "text") == "text"]
                raise TimelineError(f"clip {key} is a {kind} layer, text fields ({', '.join(sorted(TEXT_ONLY & set(ch)))}) "
                                    f"go to a text clip: {', '.join(texts) or 'none (use add_clips)'}")
        items[n] = None if ch is None else _merge_item(items[n], ch)
    return [x for x in items if x is not None]


# Fields only a text layer has: sent to an image / video / audio layer they mean the wrong clip number was picked.
TEXT_ONLY = {"text", "color", "font", "size_pct", "bold", "box", "outline", "shadow", "align", "animation"}


def numbered_view(spec: dict) -> dict:
    """The project as a model should see it: every scene and clip carries its patch number ("#") and clip type."""
    out = dict(spec)
    if isinstance(spec.get("scenes"), list):
        out["scenes"] = [{"#": i + 1, **x} if isinstance(x, dict) else {"#": i + 1, "src": x}
                         for i, x in enumerate(spec["scenes"])]
    if isinstance(spec.get("clips"), list):
        out["clips"] = [{"#": i + 1, "type": "text", **x} if isinstance(x, dict) else x
                        for i, x in enumerate(spec["clips"])]
    return out


def merge_patch(base: dict, spec: dict) -> dict:
    """A patch over a project: scenes / clips as {"n": change}, add_clips, remove_scenes, remove_clips, any other
    field replaced (null removes it). A full list for scenes / clips replaces them."""
    out = dict(base)
    for k, v in spec.items():
        if k in ("base", "project"):
            continue
        if k == "scenes" and isinstance(v, dict):
            out["scenes"] = _numbered(out.get("scenes") or [], v, "scenes")
        elif k == "clips" and isinstance(v, dict):
            out["clips"] = _numbered(out.get("clips") or [], v, "clips")
        elif k == "add_clips":
            out["clips"] = list(out.get("clips") or []) + list(v or [])
        elif k == "add_scenes":
            out["scenes"] = list(out.get("scenes") or []) + list(v or [])
        elif k == "remove_scenes":
            drop = {int(x) - 1 for x in (v or [])}
            out["scenes"] = [x for i, x in enumerate(out.get("scenes") or []) if i not in drop]
        elif k == "remove_clips":
            drop = {int(x) - 1 for x in (v or [])}
            out["clips"] = [x for i, x in enumerate(out.get("clips") or []) if i not in drop]
        elif v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def _logo_clip(logo, W_hint: str = "") -> dict:
    """"logo": "images/logo.png" or {"src", "position": top_right|top_left|bottom_right|bottom_left|center,
    "size": 0.15 (share of the frame width), "opacity", "start", "dur"} -> an image layer over the whole video."""
    cfg = {"src": logo} if isinstance(logo, str) else dict(logo or {})
    if not cfg.get("src"):
        raise TimelineError("logo needs src (an image in the working folder)")
    size = float(cfg.get("size") or cfg.get("scale") or 0.15)
    pos = str(cfg.get("position") or "top_right").lower().replace("-", "_").replace(" ", "_")
    if pos not in LOGO_POS:
        raise TimelineError(f"logo position must be one of {', '.join(LOGO_POS)}")
    m, r, b = "3%", f"{97 - size * 100:.1f}%", "82%"
    x, y = (v.format(m=m, r=r, b=b) for v in LOGO_POS[pos])
    clip = {"type": "image", "src": cfg["src"], "x": x, "y": y, "scale": size, "start": float(cfg.get("start") or 0),
            "opacity": float(cfg.get("opacity") or 0.95), "fade_in": 0.4, "_logo": True}
    if cfg.get("dur"):
        clip["dur"] = float(cfg["dur"])
    return clip


def normalize(spec: dict, root: Path) -> dict:
    """Shortcuts and aliases become plain scenes: photos/images (+ title, captions, duration), folders as sources,
    a patch over a saved project (base), a logo."""
    if not isinstance(spec, dict):
        raise TimelineError("the timeline must be one JSON object")
    spec = dict(spec)
    if spec.get("base") or spec.get("project"):
        spec = _apply_patch(spec, root)
    # narration / says: a list = one spoken line per photo; anything else is ONE voice-over for the whole video -
    # a text, an audio file the model made with text_to_speech ("speech/x.mp3"), or {"src"} / {"text"}. An object
    # here crashed with KeyError 0, reported as "Missing required argument: 0", and the voice was silently dropped.
    for k in ("narration", "says"):
        v = spec.get(k)
        if v and not isinstance(v, list):
            spec.pop(k)
            if not spec.get("voiceover"):
                if isinstance(v, dict):
                    spec["voiceover"] = {x: v[x] for x in ("src", "text", "start", "volume") if v.get(x) is not None} \
                        or {"text": str(v.get("say") or "")}
                elif Path(str(v)).suffix.lower() in AUDIO_EXT:
                    spec["voiceover"] = {"src": str(v)}
                else:
                    spec["voiceover"] = {"text": str(v)}
    photos = spec.get("photos") or spec.get("images") or spec.get("pictures") or spec.get("files")
    if isinstance(photos, str):
        photos = [photos]
    if photos and not spec.get("scenes"):
        srcs = [s for p in photos for s in _expand(root, str(p.get("src") if isinstance(p, dict) else p))]
        if not srcs:
            raise TimelineError("photos is empty (or the folder has no pictures)")
        n = len(srcs)
        td = _num(spec.get("transition_dur", 0.8), "transition_dur", 0, 3, 0.8)
        total = _num(spec.get("duration") or 0, "duration", 0, MAX_SECONDS, 0) or n * 4.0
        each = max(1.0, (total + (n - 1) * td) / n)
        captions = spec.get("captions") or []
        scenes = []
        for i, s in enumerate(srcs):
            sc: dict = {"src": s, "dur": round(each, 3), "motion": "auto", "transition": spec.get("transition", "auto")}
            if i == 0 and spec.get("title"):
                sc["title"] = spec["title"]
                if spec.get("subtitle"):
                    sc["subtitle"] = spec["subtitle"]
            if i < len(captions) and captions[i]:
                sc["caption"] = captions[i]
            if i == n - 1 and spec.get("outro"):
                sc["title" if not sc.get("title") else "caption"] = spec["outro"]
            says = spec.get("narration") or spec.get("says") or []
            if i < len(says) and says[i]:
                sc["say"] = says[i]
            scenes.append(sc)
        spec["scenes"] = scenes
        spec.setdefault("music", "ambient")
        spec.setdefault("look", "warm")
    if spec.get("scenes"):
        out = []
        for sc in spec["scenes"]:
            if isinstance(sc, str):
                sc = {"src": sc}
            if not isinstance(sc, dict):
                raise TimelineError("each scene must be an object with src")
            srcs = _expand(root, str(sc.get("src") or ""))
            out += [{**sc, "src": s} for s in srcs] if len(srcs) > 1 else [{**sc, "src": srcs[0] if srcs else ""}]
        spec["scenes"] = out
        if len(out) > MAX_CLIPS:
            raise TimelineError(f"at most {MAX_CLIPS} scenes (got {len(out)})")
    for key in ("logo", "watermark"):
        if spec.get(key):
            clip = _logo_clip(spec.pop(key))  # no dur: it lasts to the end of the video (see plan)
            spec["clips"] = [c for c in spec.get("clips") or [] if not (isinstance(c, dict) and c.get("_logo"))] + [clip]
    return spec


def _alpha(A: float, B: float, fi: float, fo: float) -> str:
    return (f"if(lt(t,{A:.3f}),0,if(lt(t,{A + fi:.3f}),(t-{A:.3f})/{max(fi, 0.001):.3f},"
            f"if(gt(t,{B - fo:.3f}),max(0,({B:.3f}-t)/{max(fo, 0.001):.3f}),1)))")


def _ease(A: float, d: float) -> str:
    """0 -> 1 over d seconds from A, easing out (fast start, soft landing)."""
    return f"(1-pow(1-min(1,max(0,(t-{A:.3f})/{d:.3f})),3))"


def _wrap(text: str, width_chars: int) -> str:
    lines = []
    for para in str(text).split("\n"):
        lines += textwrap.wrap(para, max(8, width_chars)) or [""]
    return "\n".join(lines[:6])


FAMILIES: dict[str, tuple[list[str], list[str]]] = {
    "serif": (["C:/Windows/Fonts/georgia.ttf", "/System/Library/Fonts/Supplemental/Georgia.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
              ["C:/Windows/Fonts/georgiab.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]),
    "display": (["C:/Windows/Fonts/impact.ttf", "/System/Library/Fonts/Supplemental/Impact.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
                ["C:/Windows/Fonts/impact.ttf", "/System/Library/Fonts/Supplemental/Impact.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]),
    "mono": (["C:/Windows/Fonts/consola.ttf", "/System/Library/Fonts/Menlo.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
             ["C:/Windows/Fonts/consolab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]),
    "script": (["C:/Windows/Fonts/segoesc.ttf", "C:/Windows/Fonts/segoepr.ttf",
                "/System/Library/Fonts/Supplemental/Brush Script.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"],
               ["C:/Windows/Fonts/segoescb.ttf", "C:/Windows/Fonts/segoeprb.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf"]),
    "condensed": (["C:/Windows/Fonts/bahnschrift.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"],
                  ["C:/Windows/Fonts/bahnschrift.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"]),
}
COLOR_RE = re.compile(r"[#A-Za-z0-9@.]+")
# Scene texts given as objects get these defaults (the studio turns a scene text into an object when it is moved or
# styled); x / y are the text's top-left in % of the frame, or words (center...).
STYLE_DEFAULTS = {
    "title": {"x": "center", "y": "38%", "size_pct": 9.5, "bold": True, "animation": "slide_up", "align": "center"},
    "subtitle": {"x": "center", "y": "54%", "size_pct": 4.5, "animation": "slide_up", "align": "center", "delay": 0.35},
    "caption": {"x": "center", "y": "82%", "size_pct": 4.6, "box": "black@0.45", "animation": "slide_up", "align": "center"},
    "lower_third": {"x": "5%", "y": "76%", "size_pct": 5, "bold": True, "box": "0xE8A33D@0.92", "animation": "slide_left"},
    "text": {"x": "center", "y": "82%", "size_pct": 4.6, "box": "black@0.45", "animation": "fade", "align": "center"},
}


def pick_font(fonts: tuple, family: str | None, bold: bool) -> str:
    """The file of a font family (sans, serif, display, mono, script, condensed); a font given for the whole video
    (spec.font) wins; a family missing on this computer falls back to the default sans."""
    if len(fonts) > 2 and fonts[2]:
        return fonts[0]
    fam = FAMILIES.get(str(family or "sans").lower())
    if fam:
        found = _first(fam[1] if bold else fam[0]) or _first(fam[0])
        if found:
            return found
    return fonts[1] if bold else fonts[0]


def free_text(c: dict, where: str, start: float, dur: float, W: int, H: int, fonts: tuple, textdir: Path, key: str) -> str:
    """One text anywhere on the frame, styled: x/y (% top-left or words), size_pct (% of the short side), color,
    box (colour@alpha), outline (colour), shadow, bold, font family, align, animation (fade/slide_up/slide_left/
    pop/none), fade_in/fade_out."""
    text = str(c.get("text") or "")
    if not text.strip():
        raise TimelineError(f"{where}: the text is empty")
    color = str(c.get("color") or "white")
    if not COLOR_RE.fullmatch(color):
        raise TimelineError(f"{where}: color {color!r} is not valid (use a name like white or #ffcc00)")
    S = min(W, H)
    if c.get("size_pct"):
        size = max(8, int(S * _num(c["size_pct"], f"{where} size_pct", 1, 40) / 100))
    else:
        size = int(_num(c.get("size", 48), f"{where} size", 8, 400, 48))
    if c.get("wrap") or "\n" not in text:
        width = _num(c.get("wrap", 90), f"{where} wrap", 10, 100, 90) / 100
        text = _wrap(text, int(W * width / (size * 0.55)))
    tfile = textdir / f"{key}.txt"
    tfile.write_text(text, encoding="utf-8", newline="\n")
    x, y = _pos(c.get("x", "center"), "x", True), _pos(c.get("y", "bottom"), "y", True)
    A = start + float(c.get("delay") or 0)
    B = start + dur
    anim = str(c.get("animation") or "fade").lower()
    if anim not in ("fade", "slide_up", "slide_left", "pop", "none"):
        raise TimelineError(f"{where}: animation must be fade, slide_up, slide_left, pop or none")
    fi = _num(c.get("fade_in"), f"{where} fade_in", 0, 60, 0 if anim == "none" else min(0.45, dur / 3))
    fo = _num(c.get("fade_out"), f"{where} fade_out", 0, 60, 0 if anim == "none" else min(0.35, dur / 3))
    if anim == "slide_up":
        y = f"({y})+{int(H * 0.045)}*(1-{_ease(A, 0.6)})"
    elif anim == "slide_left":
        x = f"({x})-{int(W * 0.12)}*(1-{_ease(A, 0.6)})"
    elif anim == "pop":
        y = f"({y})-{int(H * 0.02)}*sin(min(1,max(0,(t-{A:.3f})/0.35))*PI)"
    parts = []
    box = c.get("box")
    if box and str(box).lower() not in ("false", "no", "none"):
        bc = box if isinstance(box, str) and box.lower() not in ("true", "yes") else "black@0.5"
        if not COLOR_RE.fullmatch(bc):
            raise TimelineError(f"{where}: box colour {bc!r} is not valid")
        parts.append(f"box=1:boxcolor={bc}:boxborderw={max(6, int(size * 0.35))}")
    if c.get("outline"):
        oc = str(c["outline"]) if str(c["outline"]).lower() not in ("true", "yes") else "black"
        if not COLOR_RE.fullmatch(oc):
            raise TimelineError(f"{where}: outline colour {oc!r} is not valid")
        parts.append(f"borderw={max(2, int(size * 0.07))}:bordercolor={oc}")
    if c.get("shadow", True) not in (False, "false", "no"):
        parts.append("shadowcolor=black@0.55:shadowx=2:shadowy=3")
    if str(c.get("align") or "").lower() == "center" and _ffmpeg_major() >= 7:
        parts.append("text_align=C")
    font = pick_font(fonts, c.get("font"), bool(c.get("bold")))
    extra = (":" + ":".join(parts)) if parts else ""
    return (f"drawtext=fontfile={_esc(font)}:textfile={_esc(str(tfile))}:fontsize={size}:fontcolor={color}:"
            f"line_spacing={int(size * 0.25)}:x='{x}':y='{y}'{extra}:alpha='{_alpha(A, B, fi, fo)}':"
            f"enable='between(t,{A:.3f},{B:.3f})'")


def text_filters(text: str, style: str, A: float, B: float, W: int, H: int, fonts: tuple[str, str], textdir: Path,
                 key: str, color: str = "white", accent: str = "0xE8A33D", size: float | None = None) -> list[str]:
    """Animated drawtext filters for one piece of text. Styles: title, subtitle, caption, lower_third, top, plain."""
    regular, bold = fonts[0], fonts[1]
    S = min(W, H)  # sizes follow the short side: a 9:16 frame got huge, wrapped text before
    centred = ":text_align=C" if _ffmpeg_major() >= 7 else ""
    shadow = ":shadowcolor=black@0.6:shadowx=2:shadowy=3:borderw=2:bordercolor=black@0.35"
    fi, fo = min(0.6, (B - A) / 3), min(0.5, (B - A) / 3)
    alpha = _alpha(A, B, fi, fo)
    style = (style or "caption").lower()
    if style == "title":
        fs = int(size or S * 0.095)
        body, font = _wrap(text, int(W / (fs * 0.56))), bold
        x, y = "(w-text_w)/2", f"(h-text_h)/2-{int(H * 0.04)}+{int(H * 0.05)}*(1-{_ease(A, 0.8)})"
        extra = shadow + centred
    elif style == "subtitle":
        fs = int(size or S * 0.045)
        body, font = _wrap(text, int(W / (fs * 0.55))), regular
        x, y = "(w-text_w)/2", f"h/2+{int(H * 0.06)}+{int(H * 0.03)}*(1-{_ease(A, 0.8)})"
        extra = shadow + centred
    elif style == "lower_third":
        fs = int(size or S * 0.05)
        body, font = _wrap(text, int(W * 0.8 / (fs * 0.56))), bold
        margin = int(W * 0.05)
        x = f"{margin}-(text_w+{margin * 2})*(1-{_ease(A, 0.7)})"
        y = f"h-text_h-{int(H * 0.12)}"
        extra = f":box=1:boxcolor={accent}@0.92:boxborderw={int(fs * 0.45)}"
    elif style == "top":
        fs = int(size or S * 0.055)
        body, font = _wrap(text, int(W / (fs * 0.56))), bold
        x, y = "(w-text_w)/2", f"{int(H * 0.07)}-{int(H * 0.04)}*(1-{_ease(A, 0.6)})"
        extra = shadow + centred
    else:  # caption (and plain): bottom centre on a soft dark band
        fs = int(size or S * 0.046)
        body, font = _wrap(text, int(W * 0.85 / (fs * 0.55))), regular
        x, y = "(w-text_w)/2", f"h-text_h-{int(H * 0.08)}+{int(H * 0.025)}*(1-{_ease(A, 0.6)})"
        extra = f":box=1:boxcolor=black@0.45:boxborderw={int(fs * 0.5)}" + centred
    tfile = textdir / f"{key}.txt"
    tfile.write_text(body, encoding="utf-8", newline="\n")  # Windows line ends drew an empty line
    return [f"drawtext=fontfile={_esc(font)}:textfile={_esc(str(tfile))}:fontsize={fs}:fontcolor={color}:"
            f"line_spacing={int(fs * 0.25)}:x='{x}':y='{y}'{extra}:alpha='{alpha}':"
            f"enable='between(t,{A:.3f},{B:.3f})'"]


def _zoompan(motion: str, frames: int, W: int, H: int, fps: float) -> str:
    N = max(frames, 1)
    p = f"on/{N}"
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = {
        "zoom_in": (f"1+0.16*{p}", centre_x, centre_y),
        "zoom_out": (f"1.16-0.16*{p}", centre_x, centre_y),
        "pan_right": ("1.14", f"(iw-iw/zoom)*{p}", centre_y),
        "pan_left": ("1.14", f"(iw-iw/zoom)*(1-{p})", centre_y),
        "pan_down": ("1.14", centre_x, f"(ih-ih/zoom)*{p}"),
        "pan_up": ("1.14", centre_x, f"(ih-ih/zoom)*(1-{p})"),
        "none": ("1", "0", "0"),
    }[motion]
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={N}:s={W}x{H}:fps={fps:g}"


def _fit_chain(fit: str, W: int, H: int, up: int, tag: str = "0") -> str:
    """Scale a picture/video to the frame (x up for smooth Ken Burns moves). tag keeps the labels of the blur
    composite unique per scene."""
    w, h = W * up, H * up
    if fit == "blur":
        return (f"split[fa{tag}][fb{tag}];[fa{tag}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur=24:3,eq=brightness=-0.08[bg{tag}];[fb{tag}]scale={w}:{h}:force_original_aspect_ratio=decrease"
                f"[fg{tag}];[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2")
    if fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def plan(spec: dict, probes: dict[str, dict], root: Path, textdir: Path, font: str | tuple = "",
         extra_audio: dict | None = None) -> dict:
    """The ffmpeg arguments for a (normalized) timeline. probes: source path (as written) -> {duration, video, audio}.
    extra_audio: generated files {"music": path, "voice": [(start, path, volume)]}. Pure apart from writing the text
    files into textdir, so it can be tested without rendering."""
    fonts = font if isinstance(font, tuple) else (font, font, False)
    extra_audio = extra_audio or {}
    if spec.get("aspect") and not (spec.get("width") and spec.get("height")):
        if str(spec["aspect"]) not in ASPECTS:
            raise TimelineError(f"aspect must be one of {', '.join(ASPECTS)}")
        dw, dh = ASPECTS[str(spec["aspect"])]
    else:
        dw, dh = 1280, 720
    W = int(_num(spec.get("width"), "width", 160, 3840, dw))
    H = int(_num(spec.get("height"), "height", 160, 3840, dh))
    W, H = W - W % 2, H - H % 2
    FPS = _num(spec.get("fps"), "fps", 10, 60, 30)
    scenes = spec.get("scenes") or []
    clips = spec.get("clips") or []
    if not isinstance(clips, list) or not isinstance(scenes, list):
        raise TimelineError("scenes and clips must be lists")
    if not scenes and not clips:
        raise TimelineError("the timeline has no clips: add \"scenes\" (or \"photos\") or a \"clips\" list")
    if len(clips) > MAX_CLIPS:
        raise TimelineError(f"at most {MAX_CLIPS} clips per timeline (got {len(clips)}): split the edit in two")
    look = str(spec.get("look") or "none").lower()
    if look not in LOOKS:
        raise TimelineError(f"look must be one of {', '.join(LOOKS)}")
    up = 3 if W * H <= 1920 * 1080 else 2

    inputs: list[list[str]] = []
    chains: list[str] = []
    post: list[tuple] = []  # drawn above the scene track, in order: ("text", filter) / ("pic", i, chain, xy)
    audio: list[tuple[int | str, str]] = []  # (label key, chain ending in [aKEY])
    voices: list[str] = []  # labels of voice-over streams (they duck the music)
    covers: list[tuple[float, float]] = []
    end = 0.0

    def src_probe(where: str, src: str) -> tuple[Path, dict]:
        if not src:
            raise TimelineError(f"{where} needs src (a file in the working folder)")
        if src not in probes:
            raise TimelineError(f"{where}: file not found: {src}")
        return (Path(src) if Path(src).is_absolute() else root / src), probes[src]

    # ---- scenes: the main track with transitions
    L = 0.0
    starts: list[float] = []
    if scenes:
        prev_label, prev_td, prev_t = "", 0.0, "fade"
        for k, sc in enumerate(scenes):
            where = f"scene {k + 1}"
            path, pr = src_probe(where, str(sc.get("src") or ""))
            kind = _kind_of(str(path))
            if kind == "audio":
                raise TimelineError(f"{where}: {path.name} is sound only; put music in \"music\" or a clip of type audio")
            fit = str(sc.get("fit") or spec.get("fit") or "cover").lower()
            if fit not in ("cover", "blur", "contain"):
                raise TimelineError(f"{where}: fit must be cover, blur or contain")
            if kind == "image":
                dur = _num(sc.get("dur", 4), f"{where} dur", 0.5, MAX_SECONDS, 4)
                in_ = 0.0
                motion = str(sc.get("motion") or "auto").lower()
                if motion == "auto":
                    motion = AUTO_MOTIONS[k % len(AUTO_MOTIONS)]
                if motion not in MOTIONS:
                    raise TimelineError(f"{where}: motion must be one of {', '.join(MOTIONS)} or auto")
                inputs.append(["-i", str(path)])
                i = len(inputs) - 1
                frames = int(round(dur * FPS))
                chains.append(f"[{i}:v]{_fit_chain(fit, W, H, up, str(k))},setsar=1,{_zoompan(motion, frames, W, H, FPS)},"
                              f"format=yuv420p,setsar=1,setpts=PTS-STARTPTS,settb=AVTB[{'r' if sc.get('effects') else 's'}{k}]")
            else:
                if not pr.get("video"):
                    raise TimelineError(f"{where}: {path.name} has no picture")
                in_ = _num(sc.get("in", 0), f"{where} in", 0, MAX_SECONDS, 0)
                total = float(pr.get("duration") or 0)
                avail = (_num(sc["out"], f"{where} out", 0, MAX_SECONDS) - in_) if sc.get("out") is not None else total - in_
                if avail <= 0.1:
                    raise TimelineError(f"{where}: 'in' is past the end of {path.name} ({total:.1f} s long)")
                want = _num(sc.get("dur", avail), f"{where} dur", 0.3, MAX_SECONDS, avail)
                # an AI-animated photo (a few seconds) fills a longer scene by playing slower; other clips are cut
                slow = min(2.5, want / avail) if sc.get("stretch") and want > avail else 1.0
                dur = min(want, avail * slow)
                inputs.append(["-i", str(path)])
                i = len(inputs) - 1
                fitc = _fit_chain(fit, W, H, 1, str(k))
                chains.append(f"[{i}:v]trim=start={in_:.3f}:duration={dur / slow:.3f},setpts=(PTS-STARTPTS)*{slow:.4f},"
                              f"{fitc},setsar=1,fps={FPS:g},format=yuv420p,settb=AVTB[{'r' if sc.get('effects') else 's'}{k}]")
            if sc.get("effects"):
                chains += effect_chain(sc["effects"], W, H, FPS, dur, f"r{k}", f"fx{k}", f"s{k}")
                chains.append(f"[fx{k}]format=yuv420p,settb=AVTB[s{k}]")
            # where this scene starts: after the previous ones, overlapping the previous transition
            if k == 0:
                start, label = 0.0, f"s{k}"
                L = dur
            else:
                start = L - prev_td
                label = f"x{k}"
                chains.append(f"[{prev_label}][s{k}]xfade=transition={prev_t}:duration={prev_td:.3f}:"
                              f"offset={start:.3f}[{label}]")
                L = start + dur
            starts.append(start)
            # the transition into the next scene
            t = str(sc.get("transition") or spec.get("transition") or "auto").lower()
            if t == "auto":
                t = AUTO_TRANSITIONS[k % len(AUTO_TRANSITIONS)]
            if t not in TRANSITIONS | {"cut", "none"}:
                raise TimelineError(f"{where}: transition {t!r} is not known; use one of: auto, cut, "
                                    + ", ".join(sorted(TRANSITIONS)))
            td = _num(sc.get("transition_dur", spec.get("transition_dur", 0.8)), f"{where} transition_dur", 0, 3, 0.8)
            if k + 1 < len(scenes):
                nxt = scenes[k + 1]
                nxt_dur = float(nxt.get("dur") or 4) if isinstance(nxt, dict) else 4.0
                td = min(td, dur / 2, max(nxt_dur, 0.2) / 2)
            prev_t, prev_td = ("fade", 0.04) if t in ("cut", "none") else (t, max(td, 0.05))
            prev_label = label
            covers.append((start, start + dur))
            # scene text (animated) and voice line
            B = start + dur - (prev_td / 2 if k + 1 < len(scenes) else 0.15)
            A = start + (0.35 if k else 0.25)
            n = 0
            for key, style in (("title", "title"), ("subtitle", "subtitle"), ("caption", "caption"),
                               ("lower_third", "lower_third"), ("text", sc.get("text_style") or "caption")):
                val = sc.get(key)
                if isinstance(val, dict):  # a moved / styled scene text (studio, or a model giving x/y/colour)
                    if not str(val.get("text") or "").strip():
                        continue
                    n += 1
                    merged = {**STYLE_DEFAULTS.get(key, STYLE_DEFAULTS["text"]), **val}
                    post.append(("text", free_text(merged, f"{where} {key}", A, B - A, W, H, fonts, textdir,
                                                   f"scene{k}_{key}")))
                elif val:
                    n += 1
                    a = A + (0.35 if key == "subtitle" else 0)
                    post += [("text", f) for f in text_filters(str(val), style, a, B, W, H, fonts, textdir,
                                                               f"scene{k}_{key}", str(sc.get("color") or "white"))]
            if pr.get("audio") and kind == "video":
                vol = _num(sc.get("volume", 0.0 if spec.get("music") or sc.get("say") else 1.0), f"{where} volume", 0, 4, 1)
                if vol > 0:
                    ms = int(round(start * 1000))
                    audio.append((f"sc{k}", f"[{i}:a]atrim=start={in_:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,"
                                            f"volume={vol:.3f},afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 0.4):.3f}:d=0.4,"
                                            f"adelay={ms}|{ms},aformat=sample_rates=48000:channel_layouts=stereo[asc{k}]"))
        chains.append(f"[{prev_label}]null[track]")
        end = L
        track_at = len(chains) - 1  # padded below when free layers run past the scenes

    # ---- free layers
    for idx, c in enumerate(clips):
        where = f"clip {idx + 1}"
        if not isinstance(c, dict):
            raise TimelineError(f"{where} must be an object")
        kind = str(c.get("type") or "").lower()
        src_ext = Path(str(c.get("src") or "")).suffix.lower()
        if kind in ("video", "") and src_ext in IMAGE_EXT:
            kind = "image"  # a picture given as "video" is taken as what it is (a common slip)
        elif kind in ("video", "") and src_ext in AUDIO_EXT:
            kind = "audio"
        elif not kind and c.get("text") is not None:
            kind = "text"
        if kind not in TYPES:
            raise TimelineError(f"{where}: type must be one of {', '.join(TYPES)}, got {kind or 'nothing'!r}")
        start = _num(c.get("start", 0), f"{where} start", 0, MAX_SECONDS, 0)
        fi = _num(c.get("fade_in", 0), f"{where} fade_in", 0, 60, 0)
        fo = _num(c.get("fade_out", 0), f"{where} fade_out", 0, 60, 0)
        if kind == "text":
            text = str(c.get("text") or "")
            if not text.strip():
                raise TimelineError(f"{where}: a text clip needs text")
            dur = _num(c.get("dur", 3), f"{where} dur", 0.1, MAX_SECONDS, 3)
            end = max(end, start + dur)
            color = str(c.get("color") or "white")
            if not re.fullmatch(r"[#A-Za-z0-9@.]+", color):
                raise TimelineError(f"{where}: color {color!r} is not valid (use a name like white or #ffcc00)")
            if c.get("style") and c.get("x") is None and c.get("y") is None and not c.get("box") and not c.get("font"):
                post += [("text", f) for f in text_filters(text, str(c["style"]), start, start + dur, W, H, fonts,
                                                           textdir, f"clip{idx}", color,
                                                           size=float(c["size"]) if c.get("size") else None)]
                continue
            if c.get("style") in STYLE_DEFAULTS:
                c = {**STYLE_DEFAULTS[c["style"]], **c}
            post.append(("text", free_text({**c, "fade_in": c.get("fade_in") if c.get("fade_in") else None,
                                            "fade_out": c.get("fade_out") if c.get("fade_out") else None},
                                           where, start, dur, W, H, fonts, textdir, f"clip{idx}")))
            continue

        path, pr = src_probe(where, str(c.get("src") or ""))
        if kind == "video" and not pr.get("video"):
            raise TimelineError(f"{where}: {path.name} has no picture (use type audio for sound only)")
        if kind == "audio" and not pr.get("audio"):
            raise TimelineError(f"{where}: {path.name} has no sound")
        if kind == "image":
            if c.get("_logo") and not c.get("dur"):  # a logo without a length lasts to the end of the video
                other = max([L] + [_num(o.get("start", 0), "start", 0, MAX_SECONDS, 0) + float(o.get("dur") or 3)
                                   for o in clips if isinstance(o, dict) and not o.get("_logo")])
                dur = max(0.5, (other or 5) - start)
            else:
                dur = _num(c.get("dur", 5), f"{where} dur", 0.1, MAX_SECONDS, 5)
            in_ = 0.0
            inputs.append(["-loop", "1", "-framerate", f"{FPS:g}", "-t", f"{dur + start:.3f}", "-i", str(path)])
        else:
            in_ = _num(c.get("in", 0), f"{where} in", 0, MAX_SECONDS, 0)
            total = float(pr.get("duration") or 0)
            if c.get("out") is not None:
                avail = _num(c.get("out"), f"{where} out", 0, MAX_SECONDS) - in_
            else:
                avail = total - in_
            if avail <= 0.05 or in_ >= total > 0:
                raise TimelineError(f"{where}: 'in' is past the end of {path.name} ({total:.1f} s long)")
            dur = min(_num(c.get("dur", avail), f"{where} dur", 0.05, MAX_SECONDS, avail), avail)
            inputs.append(["-i", str(path)])
        i = len(inputs) - 1
        end = max(end, start + dur)
        if kind in ("video", "image"):
            if not c.get("scale"):
                covers.append((start, start + dur))
            pre = (f"trim=start={in_:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS" if kind == "video"
                   else "setpts=PTS-STARTPTS")
            pre += f"+{start:.3f}/TB"
            if c.get("scale"):
                sw = max(2, int(round(W * _num(c["scale"], f"{where} scale", 0.02, 1) / 2)) * 2)
                fit = f"scale={sw}:-2"
                default_xy = ("center", "center")
            else:
                fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
                       if str(c.get("fit") or "contain").lower() == "cover"
                       else f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
                default_xy = ("left", "top")
            fades = []
            if fi > 0:
                fades.append(f"fade=t=in:st={start:.3f}:d={fi:.3f}:alpha=1")
            if fo > 0:
                fades.append(f"fade=t=out:st={max(start, start + dur - fo):.3f}:d={fo:.3f}:alpha=1")
            opacity = _num(c.get("opacity", 1), f"{where} opacity", 0, 1, 1)
            if opacity < 1:
                fades.append(f"colorchannelmixer=aa={opacity:.3f}")
            chain = ",".join([pre, fit, "format=rgba", *fades])
            x = _pos(c.get("x", default_xy[0]), "x")
            y = _pos(c.get("y", default_xy[1]), "y")
            post.append(("pic", i, f"[{i}:v]{chain}[p{i}]", f"x={x}:y={y}"))
        if kind in ("video", "audio") and pr.get("audio"):
            vol = _num(c.get("volume", 1), f"{where} volume", 0, 4, 1)
            if vol > 0:
                ms = int(round(start * 1000))
                af = [f"atrim=start={in_:.3f}:duration={dur:.3f}", "asetpts=PTS-STARTPTS", f"volume={vol:.3f}"]
                if fi > 0:
                    af.append(f"afade=t=in:st=0:d={fi:.3f}")
                if fo > 0:
                    af.append(f"afade=t=out:st={max(0, dur - fo):.3f}:d={fo:.3f}")
                af += [f"adelay={ms}|{ms}", "aformat=sample_rates=48000:channel_layouts=stereo"]
                audio.append((str(i), f"[{i}:a]{','.join(af)}[a{i}]"))

    T = _num(spec.get("duration"), "duration", 0, MAX_SECONDS, 0) if not spec.get("photos") else 0
    T = (T or end) if not scenes else min(T or max(end, L), max(end, L))
    if T <= 0:
        raise TimelineError("the timeline has nothing to show")
    T = min(T, MAX_SECONDS)

    if scenes and T > L + 0.05:  # layers run past the last scene: the track goes on in black
        chains[track_at] = f"[{prev_label}]tpad=stop_mode=add:stop_duration={T - L:.3f}:color=black[track]"

    # ---- voice-over and music
    for n, (at, vpath, vvol) in enumerate(extra_audio.get("voice") or []):
        inputs.append(["-i", str(vpath)])
        i = len(inputs) - 1
        ms = int(round(at * 1000))
        audio.append((f"v{n}", f"[{i}:a]volume={vvol:.3f},adelay={ms}|{ms},"
                               f"aformat=sample_rates=48000:channel_layouts=stereo[av{n}]"))
        voices.append(f"av{n}")
    if extra_audio.get("music"):
        mpath, mvol, m_in, m_at, m_fi, m_fo = (list(extra_audio["music"]) + [0, 0, None, None])[:6]
        inputs.append(["-stream_loop", "-1", "-i", str(mpath)])
        i = len(inputs) - 1
        span = max(0.5, T - m_at)
        fo_m = min(2.5, span / 3) if m_fo is None else min(m_fo, span)
        fi_m = min(1.2, span / 4) if m_fi is None else min(m_fi, span)
        ms = int(round(m_at * 1000))
        chains.append(f"[{i}:a]atrim=start={m_in:.3f}:duration={span:.3f},asetpts=PTS-STARTPTS,volume={mvol:.3f},"
                      f"afade=t=in:d={max(fi_m, 0.01):.3f},afade=t=out:st={max(0, span - fo_m):.3f}:d={max(fo_m, 0.01):.3f},"
                      f"adelay={ms}|{ms},aformat=sample_rates=48000:channel_layouts=stereo[mus]")

    # ---- gaps (black stretches) for the report
    gaps: list[tuple[float, float]] = []
    at = 0.0
    for a, b in sorted(covers):
        if a > at + 0.05:
            gaps.append((round(at, 2), round(min(a, T), 2)))
        at = max(at, b)
    if at < T - 0.05:
        gaps.append((round(at, 2), round(T, 2)))
    gaps = [g for g in gaps if g[0] < T and g[1] > g[0] + 0.05]

    # ---- picture: base (scene track or black canvas), look, layers, fades
    if scenes:
        cur = "track"
        if LOOKS[look]:
            chains.append(f"[track]{LOOKS[look]}[graded]")
            cur = "graded"
    else:
        chains.append(f"color=c=black:s={W}x{H}:r={FPS:g}:d={T:.3f}[c0]")
        cur = "c0"
        if LOOKS[look]:
            chains.append(f"[c0]{LOOKS[look]}[graded]")
            cur = "graded"
    if spec.get("effects"):
        chains += effect_chain(spec["effects"], W, H, FPS, T, cur, "gfx", "g")
        cur = "gfx"
    for n, item in enumerate(post, 1):
        nxt = f"l{n}"
        if item[0] == "text":
            chains.append(f"[{cur}]{item[1]}[{nxt}]")
        else:
            _, i, pic_chain, xy = item
            chains.append(pic_chain)
            chains.append(f"[{cur}][p{i}]overlay={xy}:eof_action=pass[{nxt}]")
        cur = nxt
    fade_on = spec.get("fade", bool(scenes))
    fades = ""
    if fade_on and str(fade_on).lower() not in ("false", "0", "no"):
        fades = f"fade=t=in:st=0:d={min(0.6, T / 6):.3f},fade=t=out:st={max(0, T - 0.8):.3f}:d={min(0.8, T / 6):.3f},"
    chains.append(f"[{cur}]{fades}format=yuv420p[vout]")

    # ---- sound: scene sound, clips, voices; music ducked under the voices; a limiter on the mix
    for _, ch in audio:
        chains.append(ch)
    labels = [ch.rsplit("[", 1)[1].rstrip("]") for _, ch in audio]
    others = [lb for lb in labels if lb not in voices]
    mix = list(others)
    if voices:
        if len(voices) == 1:
            chains.append(f"[{voices[0]}]asplit=2[vox][voxsc]")
        else:
            chains.append("".join(f"[{v}]" for v in voices)
                          + f"amix=inputs={len(voices)}:duration=longest:dropout_transition=0:normalize=0,asplit=2[vox][voxsc]")
        mix.append("vox")
    if extra_audio.get("music"):
        if voices:
            chains.append("[mus][voxsc]sidechaincompress=threshold=0.02:ratio=9:attack=20:release=450:makeup=1[musd]")
            mix.append("musd")
        else:
            mix.append("mus")
    elif voices:
        chains.append("[voxsc]anullsink")
    if mix:
        if len(mix) == 1:
            chains.append(f"[{mix[0]}]apad,atrim=0:{T:.3f},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            chains.append("".join(f"[{m}]" for m in mix)
                          + f"amix=inputs={len(mix)}:duration=longest:dropout_transition=0:normalize=0,"
                            f"apad,atrim=0:{T:.3f},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    return {"inputs": inputs, "filter": ";".join(chains), "duration": T, "width": W, "height": H, "fps": FPS,
            "audio": bool(mix), "gaps": gaps, "scenes": [round(s, 2) for s in starts], "look": look}


def _probe_sync(path: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe is not installed (ffmpeg package missing)")
    r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise TimelineError(f"{path.name} is not a media file ffprobe can read: {r.stderr.strip()[-160:]}")
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams") or []
    duration = float((data.get("format") or {}).get("duration") or 0)
    for s in streams:
        if s.get("codec_type") == "video" and s.get("duration") and s.get("duration") != "N/A":
            duration = max(duration, float(s["duration"]))
    return {"duration": duration,
            "video": any(s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1 for s in streams),
            "audio": any(s.get("codec_type") == "audio" for s in streams)}


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not installed (the toolchain installs it; or add it to PATH)")
    return exe


# Generated background music: soft chord pads (C - Am - F - G), with a beat for "upbeat". Simple, royalty-free.
CHORDS = [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)]


def _music_expr(kind: str) -> str:
    P = {"calm": 3.2, "ambient": 2.4, "upbeat": 2.0}.get(kind, 2.4)
    def chord(c):
        root = c[0] / 2
        notes = "+".join(f"0.11*sin(2*PI*{f}*t)+0.04*sin(4*PI*{f}*t)" for f in c)
        return f"({notes}+0.16*sin(2*PI*{root}*t))"
    m = f"mod(t,{4 * P})"
    pad = (f"if(lt({m},{P}),{chord(CHORDS[0])},if(lt({m},{2 * P}),{chord(CHORDS[1])},"
           f"if(lt({m},{3 * P}),{chord(CHORDS[2])},{chord(CHORDS[3])})))")
    env = f"min(1,mod(t,{P})/0.5)*min(1,({P}-mod(t,{P}))/0.7)"
    expr = f"({pad})*{env}*0.8"
    if kind == "upbeat":
        beat = 0.5
        expr += (f"+0.55*sin(2*PI*52*t)*exp(-22*mod(t,{beat}))"
                 f"+0.06*(2*random(0)-1)*exp(-70*mod(t+{beat / 2},{beat}))")
    return expr


GENERATED = {"corporate", "upbeat", "lofi", "cinematic", "acoustic", "electronic", "ambient", "calm", "auto", "true"}


async def make_music(kind: str, seconds: float, target: Path, seed: int = 0) -> Path:
    """Original background music of a style (tools/music.py: drums, bass, chords, arpeggios, reverb); the old ffmpeg
    pads only if numpy is missing."""
    try:
        from . import music
        style = "corporate" if kind in ("auto", "true") else kind
        return await asyncio.to_thread(music.generate, style, seconds, target.with_suffix(".wav"), seed)
    except ImportError:
        pass
    expr = _music_expr(kind if kind in ("ambient", "upbeat", "calm") else "ambient")
    args = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            f"aevalsrc=exprs='{expr}|{expr}':s=44100:d={seconds + 1:.2f}",
            "-af", "lowpass=f=5200,aecho=0.8:0.6:70|140:0.22|0.12,volume=0.9", "-c:a", "pcm_s16le", str(target)]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"music generation failed: {err.decode(errors='replace')[-200:]}")
    return target


async def _voice(text: str, target: Path, lang: str, cfg: dict) -> dict:
    from . import speech
    # the video's own mix sets the loudness, so the voice gets the "video" finish unless one is given
    tone = {k: cfg[k] for k in ("pitch", "emotion", "pause", "room") if cfg.get(k) is not None}
    return await speech.text_to_speech(text, target, (cfg.get("language") or lang or "tr")[:3],
                                       str(cfg.get("voice") or ""), str(cfg.get("gender") or ""),
                                       float(cfg["rate"]) if cfg.get("rate") else None,
                                       preset=str(cfg.get("studio") or "video"), speakers=cfg.get("speakers"), **tone)


def _subs_style(spec: dict) -> str:
    """libass style for burned subtitles: white text, dark outline, above the bottom edge (spec.subtitles may be a
    dict: size, color "#ffffff", position bottom|top)."""
    s = spec.get("subtitles") if isinstance(spec.get("subtitles"), dict) else {}
    size = int(s.get("size") or 15)
    col = str(s.get("color") or "#ffffff").lstrip("#")
    col = col if re.fullmatch(r"[0-9a-fA-F]{6}", col) else "ffffff"
    bgr = col[4:6] + col[2:4] + col[0:2]
    align = 8 if str(s.get("position") or "").lower() == "top" else 2
    return (f"FontName=Arial,FontSize={size},PrimaryColour=&H00{bgr},OutlineColour=&H00000000,BackColour=&H80000000,"
            f"BorderStyle=1,Outline=1.6,Shadow=0.6,Bold=1,Alignment={align},MarginV=22")


async def _burn_subs(target: Path, segs: list[tuple[float, float, str]], spec: dict, workdir: Path) -> Path:
    """Timed subtitles from the voice-over's real sentence timings, burned into the video; a .srt goes next to it."""
    from ..voice.render import srt_text
    segs = sorted(segs)
    srt = srt_text(segs)
    (workdir / "subs.srt").write_text(srt, encoding="utf-8")
    target.with_suffix(".srt").write_text(srt, encoding="utf-8")
    tmp = target.with_name(target.stem + ".subs" + target.suffix)
    args = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(target),
            "-vf", f"subtitles=subs.srt:force_style='{_subs_style(spec)}'", "-c:a", "copy", "-c:v", "libx264",
            "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    proc = await asyncio.create_subprocess_exec(*args, cwd=str(workdir), stdout=asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.PIPE)
    _, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
    if proc.returncode or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError("subtitles: " + err.decode("utf-8", "replace").strip()[-300:])
    tmp.replace(target)
    return target.with_suffix(".srt")


async def _animate_scenes(spec: dict, root: Path) -> tuple[dict, dict]:
    """Photo scenes with "animate": true (or the whole video's "animate": true) become short AI video clips that
    really move (free image-to-video, cached; ~40-60 s per new photo). Returns (spec for the render, report). A photo
    that cannot be animated now (quota) keeps its Ken Burns motion, and the report says why."""
    import copy
    out = copy.deepcopy(spec)
    report = {"done": 0, "cached": 0, "failed": []}
    if not any(isinstance(sc, dict) and (sc.get("animate") or (spec.get("animate") and sc.get("animate") is not False))
               for sc in out.get("scenes") or []):
        return out, report
    from . import animate as anim
    for k, sc in enumerate(out.get("scenes") or []):
        if not isinstance(sc, dict) or _kind_of(str(sc.get("src") or "")) != "image":
            continue
        if not (sc.get("animate") or (spec.get("animate") and sc.get("animate") is not False)):
            continue
        img = Path(str(sc["src"])) if Path(str(sc["src"])).is_absolute() else root / str(sc["src"])
        if not img.is_file():
            continue
        prompt = str(sc.get("motion_prompt") or "cinematic, smooth natural motion, gentle camera movement, realistic")
        try:
            clip, how = await anim.animate(img, root, prompt, min(5.0, float(sc.get("dur") or 4)))
        except Exception as e:  # quota / busy: this scene stays a moving still
            report["failed"].append(f"scene {k + 1}: {str(e)[:220]}")
            continue
        report["cached" if how == "cache" else "done"] += 1
        sc["animated_src"] = clip.relative_to(root).as_posix() if root in clip.parents else str(clip)
        spec["scenes"][k]["animated_src"] = sc["animated_src"]  # the studio previews the moving clip
        sc["src"], sc["stretch"] = sc["animated_src"], True
        sc.pop("motion", None)
    return out, report


def _scene_length(spec: dict, probes: dict) -> tuple[list[float], float]:
    """Start time and length of each scene before the full plan (voice lines are placed with them)."""
    starts, L, prev_td = [], 0.0, 0.0
    scenes = spec.get("scenes") or []
    for k, sc in enumerate(scenes):
        pr = probes.get(str(sc.get("src") or ""), {})
        if _kind_of(str(sc.get("src") or "")) == "image":
            dur = float(sc.get("dur") or 4)
        else:
            total = float(pr.get("duration") or 0) - float(sc.get("in") or 0)
            dur = min(float(sc.get("dur") or total), total) if total > 0 else float(sc.get("dur") or 4)
        start = 0.0 if k == 0 else L - prev_td
        L = start + dur
        starts.append(start)
        td = float(sc.get("transition_dur", spec.get("transition_dur", 0.8)) or 0.8)
        if k + 1 < len(scenes):
            nd = float((scenes[k + 1] or {}).get("dur") or 4) if isinstance(scenes[k + 1], dict) else 4
            td = min(td, dur / 2, nd / 2)
        prev_td = 0.04 if str(sc.get("transition") or "").lower() in ("cut", "none") else max(td, 0.05)
    return starts, L


async def render(spec: dict, root: Path, target: Path, lang: str = "tr") -> dict:
    """Renders the timeline to target, writes <name>_preview.jpg next to it. Raises TimelineError (fix the timeline)
    or RuntimeError (ffmpeg failed)."""
    spec = normalize(spec, root)
    ignored = ignored_keys(spec)
    save_project(spec, root, target)  # before the render: the studio picks the change up while ffmpeg works
    srcs = {str(c.get("src")) for c in (spec.get("clips") or []) + (spec.get("scenes") or [])
            if isinstance(c, dict) and c.get("src")}
    music = spec.get("music")
    music_cfg = music if isinstance(music, dict) else {"src": music} if music else {}
    if music_cfg.get("src") and str(music_cfg["src"]).lower() not in GENERATED:
        srcs.add(str(music_cfg["src"]))
    vo = spec.get("voiceover")
    vo_cfg = vo if isinstance(vo, dict) else {"text": vo} if isinstance(vo, str) else {}
    voice = spec.get("voice")  # {"voice": "tr-TR-EmelNeural", "rate": 1.0} or just the voice id
    voice_cfg = voice if isinstance(voice, dict) else {"voice": voice} if voice else {}
    if vo_cfg.get("src"):
        srcs.add(str(vo_cfg["src"]))
    animated, anim_notes = await _animate_scenes(spec, root)
    srcs |= {str(sc.get("src")) for sc in animated.get("scenes") or [] if isinstance(sc, dict) and sc.get("src")}
    spec_saved, spec = spec, animated  # the project keeps the photos (+ animate: true); the render uses the clips
    probes: dict[str, dict] = {}
    for src in sorted(srcs):
        p = Path(src) if Path(src).is_absolute() else root / src
        if p.is_file():
            probes[src] = await asyncio.to_thread(_probe_sync, p)
    has_text = any(isinstance(c, dict) and (c.get("type") == "text" or c.get("text")) for c in spec.get("clips") or []) \
        or any(isinstance(s, dict) and any(s.get(k) for k in ("title", "subtitle", "caption", "lower_third", "text"))
               for s in spec.get("scenes") or [])
    fonts = (*_font_paths(spec, root), bool(spec.get("font"))) if has_text else ("", "", False)
    textdir = Path(tempfile.mkdtemp(prefix="aiiq-video-"))
    try:
        extra: dict = {"voice": []}
        starts, L = _scene_length(spec, probes)
        # voice lines: per scene "say", and/or one voiceover for the whole video
        jobs = []
        ready: list[tuple[float, Path]] = []  # a recording given instead of text (a model made it with text_to_speech)

        def as_file(value: str) -> Path | None:
            v = str(value).strip()
            if Path(v).suffix.lower() in AUDIO_EXT:
                p = Path(v) if Path(v).is_absolute() else root / v
                if not p.is_file():
                    raise TimelineError(f"voice file not found: {v} (give the text to read, or an existing audio file)")
                return p
            return None

        for k, sc in enumerate(spec.get("scenes") or []):
            if isinstance(sc, dict) and sc.get("say"):
                at = starts[k] + (0.4 if k else 0.3)
                if (f := as_file(sc["say"])):
                    ready.append((at, f))
                else:
                    sv = sc.get("voice")
                    jobs.append((at, str(sc["say"]), textdir / f"say{k}.mp3",
                                 {**voice_cfg, **(sv if isinstance(sv, dict) else {"voice": sv} if sv else {})}))
        if vo_cfg.get("text"):
            at = float(vo_cfg.get("start") or 0.4)
            if (f := as_file(vo_cfg["text"])):
                ready.append((at, f))
            else:
                jobs.append((at, str(vo_cfg["text"]), textdir / "voiceover.mp3", {**voice_cfg, **vo_cfg}))
        subs: list[tuple[float, float, str]] = []
        if jobs:
            try:
                said = await asyncio.gather(*(_voice(t, p, lang, cfg) for _, t, p, cfg in jobs))
            except Exception as e:
                raise RuntimeError(f"voice-over (text to speech) failed: {str(e)[:200]}") from e
            vvol = float(vo_cfg.get("volume") or 1.0)
            extra["voice"] = [(at, p, vvol) for at, _, p, _ in jobs]
            # each sentence's real place in the video (voice start + its time in the recording)
            subs = [(at + s["start"], at + s["end"], s["text"]) for (at, *_), r in zip(jobs, said)
                    for s in (r.get("segments") or [])]
        extra["voice"] += [(at, p, float(vo_cfg.get("volume") or 1.0)) for at, p in ready]
        if vo_cfg.get("src"):
            if str(vo_cfg["src"]) not in probes:
                raise TimelineError(f"voiceover file not found: {vo_cfg['src']}")
            p = Path(vo_cfg["src"]) if Path(vo_cfg["src"]).is_absolute() else root / vo_cfg["src"]
            extra["voice"].append((float(vo_cfg.get("start") or 0), p, float(vo_cfg.get("volume") or 1.0)))
        # music: a file, or generated pads
        if music_cfg.get("src"):
            kind = str(music_cfg["src"]).lower()
            seconds = max(L, float(spec.get("duration") or 0), 5) + 2
            mvol = float(music_cfg.get("volume") or (0.22 if extra["voice"] else 0.45))
            if kind in GENERATED:
                mpath = await make_music(kind, seconds, textdir / "music.wav", int(music_cfg.get("seed") or 0))
            else:
                if str(music_cfg["src"]) not in probes:
                    raise TimelineError(f"music file not found: {music_cfg['src']}")
                mpath = Path(music_cfg["src"]) if Path(music_cfg["src"]).is_absolute() else root / music_cfg["src"]
            extra["music"] = (mpath, mvol, float(music_cfg.get("in") or 0), float(music_cfg.get("start") or 0),
                              None if music_cfg.get("fade_in") is None else float(music_cfg["fade_in"]),
                              None if music_cfg.get("fade_out") is None else float(music_cfg["fade_out"]))
        pl = plan(spec, probes, root, textdir, fonts, extra)
        preset, crf = PRESETS.get(str(spec.get("quality") or "good").lower(), PRESETS["good"])
        args = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
        for inp in pl["inputs"]:
            args += inp
        script = textdir / "graph.txt"  # long graphs go through a file (Windows limits a command line to 32K chars)
        script.write_text(pl["filter"], encoding="utf-8")
        # ffmpeg 7+ reads an option value from a file with "-/option"; older builds have -filter_complex_script
        args += (["-/filter_complex", str(script)] if _ffmpeg_major() >= 7 else ["-filter_complex_script", str(script)])
        args += ["-map", "[vout]"]
        args += (["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if pl["audio"] else ["-an"])
        args += ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-r", f"{pl['fps']:g}",
                 "-t", f"{pl['duration']:.3f}", "-movflags", "+faststart", str(target)]
        target.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"ffmpeg took longer than {TIMEOUT // 60} minutes; shorten the video") from None
        if proc.returncode != 0 or not target.is_file():
            tail = err.decode("utf-8", "replace").strip()[-600:]
            raise RuntimeError(tail or f"exit code {proc.returncode}")
        if spec.get("subtitles") and subs:
            subs = [(a, min(b, pl["duration"]), s) for a, b, s in subs if a < pl["duration"]]
            await _burn_subs(target, subs, spec, textdir)
    finally:
        shutil.rmtree(textdir, ignore_errors=True)
    info = await asyncio.to_thread(_probe_sync, target)
    preview = await _preview(target, info["duration"] or pl["duration"])
    project = save_project(spec_saved, root, target)
    return {"duration": info["duration"] or pl["duration"], "width": pl["width"], "height": pl["height"],
            "audio": pl["audio"], "size": target.stat().st_size, "gaps": pl["gaps"], "scenes": pl["scenes"],
            "preview": preview, "music": bool(extra.get("music")), "voice": len(extra.get("voice") or []),
            "subtitles": len(subs) if spec.get("subtitles") else 0,
            "look": pl["look"], "project": project, "ignored": ignored, "animated": anim_notes,
            "layers": {"logo": sum(1 for c in spec.get("clips") or [] if isinstance(c, dict) and c.get("_logo")),
                       "text": sum(1 for c in spec.get("clips") or [] if isinstance(c, dict) and c.get("type") == "text"),
                       "image": sum(1 for c in spec.get("clips") or [] if isinstance(c, dict) and c.get("type") == "image"
                                    and not c.get("_logo")),
                       "video": sum(1 for c in spec.get("clips") or [] if isinstance(c, dict) and c.get("type") == "video"),
                       "audio": sum(1 for c in spec.get("clips") or [] if isinstance(c, dict) and c.get("type") == "audio")},
            "texts": sum(1 for sc in spec.get("scenes") or [] if isinstance(sc, dict) for k in
                         ("title", "subtitle", "caption", "lower_third", "text") if sc.get(k))}


SHORTCUT_KEYS = ("photos", "images", "pictures", "files", "captions", "narration", "says", "title", "subtitle", "outro")


def project_path(target: Path) -> Path:
    return target.with_name(target.stem + ".timeline.json")


def save_project(spec: dict, root: Path, target: Path) -> Path | None:
    """<name>.timeline.json beside <name>.mp4: the explicit scenes and layers (shortcuts already expanded), so the
    studio opens exactly this video and a model can change one field and render again."""
    try:
        rel = target.relative_to(root).as_posix()
    except ValueError:
        rel = target.name
    data = {k: v for k, v in spec.items() if k not in SHORTCUT_KEYS and k in TOP_KEYS}
    data["output"] = rel
    p = project_path(target)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return None
    return p


async def _preview(video: Path, seconds: float) -> Path | None:
    """Six evenly spaced frames in one sheet (3x2), shown in the chat right after the render."""
    target = video.with_name(video.stem + "_preview.jpg")
    n = 6
    times = [seconds * (i + 0.5) / n for i in range(n)]
    args = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for t in times:
        args += ["-ss", f"{t:.2f}", "-i", str(video)]
    graph = ";".join(f"[{i}:v]trim=end_frame=1,scale=480:-2,setsar=1[f{i}]" for i in range(n))
    graph += ";" + "".join(f"[f{i}]" for i in range(n)) + f"xstack=inputs={n}:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0[v]"
    args += ["-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "3", str(target)]
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.wait(), 120)
    except Exception:
        return None
    return target if target.is_file() else None
