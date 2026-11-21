"""Studio pieces: patch numbering and its guard, original music, logo cut-out, effects and styled text.
Run: python -m pytest tests/test_studio.py"""
import io
import os
import sys
import tempfile
import wave
from pathlib import Path

os.environ.setdefault("AIIQ_DATA", tempfile.mkdtemp(prefix="aiiq-studio-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402

from app.tools import logo, music, video_edit  # noqa: E402
from app.tools.video_edit import TimelineError  # noqa: E402

PROJECT = {"scenes": [{"src": "a.mp4", "dur": 5}, {"src": "b.jpg", "dur": 4}],
           "clips": [{"type": "image", "src": "c.jpg", "start": 0, "dur": 9, "scale": 0.2},
                     {"type": "text", "text": "Hello", "start": 0, "dur": 3, "color": "white"}]}


def test_numbered_view_shows_patch_numbers_and_types():
    v = video_edit.numbered_view(PROJECT)
    assert [s["#"] for s in v["scenes"]] == [1, 2]
    assert [(c["#"], c["type"]) for c in v["clips"]] == [(1, "image"), (2, "text")]
    assert "#" not in PROJECT["clips"][0]  # the real project is untouched


def test_text_style_sent_to_an_image_layer_is_refused_with_the_right_number():
    with pytest.raises(TimelineError) as e:
        video_edit.merge_patch(PROJECT, {"clips": {"1": {"color": "yellow"}}})
    assert "image layer" in str(e.value) and "2" in str(e.value)


def test_patch_with_the_right_number_changes_only_that_clip_and_drops_the_number():
    new = video_edit.merge_patch(PROJECT, {"clips": {"2": {"#": 2, "color": "#ffd34d"}},
                                           "scenes": {"2": {"caption": "Hi"}}})
    assert new["clips"][1]["color"] == "#ffd34d" and "#" not in new["clips"][1]
    assert new["clips"][0] == PROJECT["clips"][0]
    assert new["scenes"][1]["caption"] == "Hi" and "caption" not in new["scenes"][0]


def test_restyling_a_scene_text_keeps_its_words():
    base = {"scenes": [{"src": "a.jpg", "caption": "Fresh coffee"}]}
    new = video_edit.merge_patch(base, {"scenes": {"1": {"caption": {"color": "red"}}}})
    assert new["scenes"][0]["caption"] == {"text": "Fresh coffee", "color": "red"}


def test_missing_numbers_say_how_many_there_are():
    with pytest.raises(TimelineError, match="has 2 scenes"):
        video_edit.merge_patch(PROJECT, {"scenes": {"5": {"dur": 2}}})


@pytest.mark.parametrize("style", music.STYLES)
def test_every_music_style_makes_a_clean_track(tmp_path, style):
    p = music.generate(style, 6, tmp_path / f"{style}.wav", seed=1)
    with wave.open(str(p)) as w:
        secs = w.getnframes() / w.getframerate()
        frames = w.readframes(w.getnframes())
    assert 6 <= secs <= 14  # at least the asked length: whole bars plus a fade-out tail (the render trims it)
    assert max(frames) > 0  # not silence


def test_music_seed_gives_a_new_variation(tmp_path):
    a = music.generate("lofi", 5, tmp_path / "a.wav", seed=1).read_bytes()
    b = music.generate("lofi", 5, tmp_path / "b.wav", seed=2).read_bytes()
    c = music.generate("lofi", 5, tmp_path / "c.wav", seed=1).read_bytes()
    assert a != b and a == c


def test_logo_cutout_removes_a_plain_background():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(im).ellipse((60, 60, 140, 140), fill=(200, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out = Image.open(io.BytesIO(logo.cutout(buf.getvalue()))).convert("RGBA")
    assert out.size[0] < 200 and out.size[1] < 200  # trimmed to the symbol
    assert out.getpixel((0, 0))[3] == 0  # the corner is transparent
    cx, cy = out.size[0] // 2, out.size[1] // 2
    assert out.getpixel((cx, cy))[3] == 255  # the symbol stays


def test_every_effect_builds_a_filter_chain():
    for name in video_edit.EFFECTS:
        chain = video_edit.effect_chain([name], 1280, 720, 30, 5, "v0", "v1", "t")
        assert chain and all(isinstance(x, str) for x in chain), name
        assert "[v1]" in chain[-1]


def test_styled_text_becomes_a_drawtext_with_its_place_and_colors(tmp_path):
    fonts = ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", {})
    f = video_edit.free_text({"text": "Sale 50%", "x": "10%", "y": "20%", "size_pct": 8, "color": "#ffd34d",
                              "box": "#C0392B@0.9", "animation": "fade"}, "v", 1, 3, 1280, 720, fonts, tmp_path, "t1")
    assert "drawtext" in f and "fontcolor" in f and "box=1" in f
    assert "0.1" in f or "128" in f  # x = 10 % of 1280
