"""Video timeline planner, real ffmpeg render, and keyed-service fallback (quota, rate limit, system service).
Run: python -m pytest tests/test_media_services.py   (the render test needs ffmpeg on PATH)."""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DATA = tempfile.mkdtemp(prefix="aiiq-media-test-")
os.environ["AIIQ_DATA"] = DATA  # keys and usage counters go to a throw-away data dir
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402

from app.config import set_secret  # noqa: E402
from app.tools import services, video_edit  # noqa: E402
from app.tools.video_edit import TimelineError  # noqa: E402

PROBES = {"a.mp4": {"duration": 10.0, "video": True, "audio": True},
          "m.mp3": {"duration": 30.0, "video": False, "audio": True},
          "logo.png": {"duration": 0.0, "video": True, "audio": False},
          "silent.mp4": {"duration": 5.0, "video": True, "audio": False}}


def _plan(spec, tmp):
    return video_edit.plan(spec, PROBES, Path(tmp), Path(tmp), "C:/Windows/Fonts/arial.ttf")


def test_plan_builds_the_timeline(tmp_path):
    spec = {"width": 1280, "height": 720, "clips": [
        {"type": "video", "src": "a.mp4", "start": 0, "in": 2, "dur": 5, "fade_in": 0.5},
        {"type": "image", "src": "logo.png", "start": 1, "dur": 3, "scale": 0.3, "x": "right", "y": "top+20"},
        {"type": "audio", "src": "m.mp3", "start": 0, "in": 0, "dur": 6, "volume": 0.4, "fade_out": 1},
        {"type": "text", "text": "Merhaba", "start": 0.5, "dur": 3, "y": "bottom", "box": True}]}
    pl = _plan(spec, tmp_path)
    f = pl["filter"]
    assert pl["duration"] == pytest.approx(6.0)
    assert "trim=start=2.000:duration=5.000" in f
    assert "overlay=" in f and "eof_action=pass" in f
    assert "drawtext=" in f and "textfile=" in f and "boxcolor=black@0.5" in f
    assert "[aout]" in f and pl["audio"] is True
    assert (tmp_path / "clip3.txt").read_text(encoding="utf-8") == "Merhaba"


def test_video_without_sound_gets_no_audio_output(tmp_path):
    pl = _plan({"clips": [{"type": "video", "src": "silent.mp4", "dur": 4}]}, tmp_path)
    assert pl["audio"] is False
    assert "[aout]" not in pl["filter"]


@pytest.mark.parametrize("spec, message", [
    ({}, "no clips"),
    ({"clips": [{"type": "video", "src": "missing.mp4"}]}, "file not found"),
    ({"clips": [{"type": "video", "src": "a.mp4", "in": 12}]}, "past the end"),
    ({"clips": [{"type": "text", "text": "x", "x": "middle-ish"}]}, "position"),
    ({"clips": [{"type": "sound", "src": "a.mp4"}]}, "type must be"),
    ({"clips": [{"type": "audio", "src": "logo.png"}]}, "has no sound"),
])
def test_bad_timelines_say_what_to_fix(tmp_path, spec, message):
    with pytest.raises(TimelineError) as err:
        _plan(spec, tmp_path)
    assert message in str(err.value)


def test_keyed_services_fall_back_when_out_of_quota():
    set_secret("pexels_api_key", "test-pexels-key")
    set_secret("pixabay_api_key", "test-pixabay-key")
    services._STATE.clear()
    services._LOADED = True  # usage starts empty in this test
    asked = []

    async def pexels():
        asked.append("pexels")
        raise services.QuotaError("HTTP 429: too many requests", retry_after=600)

    async def pixabay():
        asked.append("pixabay")
        return ["photo"]

    async def system():
        asked.append("system")
        return ["free"]

    async def go():
        return await services.run("stock", lambda sid: {"pexels": pexels, "pixabay": pixabay}[sid](), system, "openverse")

    (result, used) = asyncio.run(go())
    assert (result, used) == (["photo"], "pixabay")
    assert asked == ["pexels", "pixabay"]
    assert "pexels" not in services.usable("stock")  # blocked for ten minutes
    assert next(s for s in services.status() if s["id"] == "pexels")["blocked"] is True

    # every keyed service blocked (pixabay now too): the system's own free service answers
    services._entry("pixabay")["blocked_until"] = time.time() + 600
    assert services.usable("stock") == []
    (result, used) = asyncio.run(go())
    assert (result, used) == (["free"], "openverse")


def test_unkeyed_and_switched_off_services_are_skipped():
    services._STATE.clear()
    set_secret("pexels_api_key", None)
    set_secret("pixabay_api_key", "test-pixabay-key")
    assert "pexels" not in services.usable("stock")  # no key
    assert "pixabay" in services.usable("stock")
    set_secret("pixabay_api_key", None)


def test_black_gaps_are_reported(tmp_path):
    spec = {"clips": [{"type": "image", "src": "logo.png", "start": 0, "dur": 5},
                      {"type": "image", "src": "logo.png", "start": 0, "dur": 5},
                      {"type": "text", "text": "x", "start": 0, "dur": 10}]}
    pl = _plan(spec, tmp_path)
    assert pl["gaps"] == [(5.0, 10.0)]  # the second picture was placed at 0 too: 5-10 s is black
    ok = _plan({"clips": [{"type": "image", "src": "logo.png", "start": 0, "dur": 5},
                          {"type": "image", "src": "logo.png", "start": 5, "dur": 5}]}, tmp_path)
    assert ok["gaps"] == []


def test_scenes_get_motion_transitions_and_animated_text(tmp_path):
    spec = {"look": "warm", "scenes": [
        {"src": "logo.png", "dur": 4, "motion": "zoom_in", "title": "Kahve", "subtitle": "Taze"},
        {"src": "a.mp4", "in": 1, "dur": 4, "transition": "circleopen", "caption": "Barista"},
        {"src": "logo.png", "dur": 3, "lower_third": "Latte 85 TL", "transition": "cut"}]}
    pl = _plan(spec, tmp_path)
    f = pl["filter"]
    assert "zoompan=" in f and "xfade=transition=" in f
    assert pl["scenes"][0] == 0 and 3 < pl["scenes"][1] < 4 and pl["duration"] > 9
    assert f.count("drawtext=") == 4 and "colorbalance" in f  # title, subtitle, caption, lower third; warm look
    assert "fade=t=out" in f  # fade to black at the end


def test_photos_shortcut_builds_even_scenes(tmp_path):
    from app.tools.video_edit import normalize
    spec = normalize({"photos": ["logo.png", "logo.png"], "title": "T", "captions": ["", "c"], "duration": 10}, tmp_path)
    assert len(spec["scenes"]) == 2 and spec["scenes"][0]["title"] == "T" and spec["scenes"][1]["caption"] == "c"
    assert spec["music"] == "ambient"
    pl = _plan({**spec, "music": None}, tmp_path)
    assert abs(pl["duration"] - 10) < 0.05


def test_cli_tag_without_angle_bracket_in_a_fence_is_a_call():
    from app.agents.stream_parser import extract_inline_calls
    text = 'Başlıyorum.\n```tool name="stock_photo" folder="images" count="1">coffee shop interior</tool>\n```'
    calls, cleaned = extract_inline_calls(text, {"stock_photo"})
    assert [(c.name, c.args, c.body) for c in calls] == [("stock_photo", {"folder": "images", "count": "1"},
                                                         "coffee shop interior")]
    assert "tool" not in cleaned


def test_mcp_command_line_is_split_and_npx_gets_yes():
    from app.mcp_client import INSTALLER, split_command
    cmd, args = split_command("npx @modelcontextprotocol/server-filesystem C:/data", [])
    assert cmd == "npx" and args == ["-y", "@modelcontextprotocol/server-filesystem", "C:/data"]
    assert INSTALLER.search("npx skills add krea-ai/skills")


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed")
def test_render_photo_slideshow_with_music(tmp_path):
    root = tmp_path / "w"
    (root / "images").mkdir(parents=True)
    for i, c in enumerate(("red", "blue")):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size=800x600:duration=1,hue=h={i * 90}", "-frames:v", "1",
                        str(root / "images" / f"p{i}.jpg")], check=True)
    spec = {"photos": ["images"], "title": "Merhaba", "captions": ["", "İkinci"], "duration": 6, "music": "upbeat",
            "aspect": "9:16"}
    target = root / "videos" / "s.mp4"
    res = asyncio.run(video_edit.render(spec, root, target))
    assert res["duration"] == pytest.approx(6.0, abs=0.2) and res["audio"] and res["music"]
    assert (res["width"], res["height"]) == (720, 1280) and len(res["scenes"]) == 2
    assert res["preview"] and Path(res["preview"]).is_file()


def test_patch_changes_only_what_is_given_and_logo_lasts_to_the_end(tmp_path):
    import json as _json

    from app.tools.video_edit import ignored_keys, normalize
    (tmp_path / "videos").mkdir()
    base = {"music": "ambient", "scenes": [{"src": "logo.png", "dur": 4, "title": "T", "say": "hello"},
                                           {"src": "logo.png", "dur": 4, "caption": "old"}]}
    (tmp_path / "videos" / "v.timeline.json").write_text(_json.dumps(base), encoding="utf-8")
    spec = normalize({"base": "videos/v.mp4", "scenes": {"2": {"caption": "new"}},
                      "logo": {"src": "logo.png", "position": "top_right", "size": 0.2}}, tmp_path)
    assert spec["scenes"][0]["say"] == "hello" and spec["scenes"][0]["title"] == "T"  # kept
    assert spec["scenes"][1]["caption"] == "new" and spec["music"] == "ambient"
    logo = spec["clips"][-1]
    assert logo["_logo"] and logo["x"] == "77.0%" and logo["y"] == "3%" and "dur" not in logo
    pl = _plan(spec, tmp_path)
    assert abs(pl["duration"] - 7.2) < 0.05  # the logo does not make the video longer
    assert "colorchannelmixer=aa=0.950" in pl["filter"]
    assert ignored_keys({"scenes": [{"src": "a.jpg", "logo_position": "x"}], "watermark_text": 1}) == \
        ["watermark_text", "scenes[1].logo_position"]
    with pytest.raises(TimelineError):
        normalize({"base": "videos/v.timeline.json", "scenes": {"5": {"caption": "x"}}}, tmp_path)


def test_timeline_in_a_bare_json_fence_becomes_an_edit_video_call():
    from app.agents.stream_parser import extract_inline_calls
    text = ('Videoyu hazırlıyorum:\n```json\n{"clips": [{"type": "image", "src": "images/a.jpg", "start": 0, "dur": 5}]}\n```\n'
            'Dosya videos/tanitim.mp4 olarak kaydedildi.')
    calls, cleaned = extract_inline_calls(text, {"edit_video"})
    assert [c.name for c in calls] == ["edit_video"]
    assert calls[0].args == {"output": "videos/tanitim.mp4"}
    assert '"clips"' in calls[0].body and "```" not in cleaned


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed")
def test_render_real_timeline(tmp_path):
    root = tmp_path / "work"
    (root / "clips").mkdir(parents=True)
    run = lambda *a: subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)  # noqa: E731
    run("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(root / "clips" / "a.mp4"))
    run("-f", "lavfi", "-i", "sine=frequency=220:duration=8", "-c:a", "libmp3lame", str(root / "clips" / "m.mp3"))
    run("-f", "lavfi", "-i", "color=c=red:s=200x200:d=1", "-frames:v", "1", str(root / "clips" / "logo.png"))
    spec = {"width": 640, "height": 360, "fps": 25, "output": "videos/out.mp4", "clips": [
        {"type": "video", "src": "clips/a.mp4", "start": 0, "in": 0.5, "dur": 3, "fit": "cover"},
        {"type": "image", "src": "clips/logo.png", "start": 0.5, "dur": 2, "scale": 0.3, "x": "right", "y": "top"},
        {"type": "audio", "src": "clips/m.mp3", "start": 0, "in": 1, "dur": 3, "volume": 0.5, "fade_out": 0.5},
        {"type": "text", "text": "Test", "start": 0.2, "dur": 2, "y": "bottom", "box": True}]}
    target = root / "videos" / "out.mp4"
    res = asyncio.run(video_edit.render(spec, root, target))
    assert target.is_file()
    assert res["duration"] == pytest.approx(3.0, abs=0.2)
    assert res["audio"] is True and res["width"] == 640 and res["height"] == 360
    info = video_edit._probe_sync(target)
    assert info["video"] and info["audio"]
