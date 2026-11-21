"""Fixes from a real run (shopping-site promo video): narration given as an object, file names written with other
Turkish letters than on disk, and the run tool's KeyError message."""
from pathlib import Path

from app.agents import checks
from app.tools import video_edit


def test_narration_object_or_text_becomes_one_voiceover(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.jpg").write_bytes(b"x")
    spec = video_edit.normalize({"photos": ["a.jpg", "b.jpg"], "narration": {"src": "speech/v.mp3"}}, tmp_path)
    assert spec["voiceover"] == {"src": "speech/v.mp3"} and "narration" not in spec
    assert all("say" not in sc for sc in spec["scenes"])
    spec = video_edit.normalize({"photos": ["a.jpg"], "narration": "speech/v.mp3"}, tmp_path)
    assert spec["voiceover"] == {"src": "speech/v.mp3"}
    spec = video_edit.normalize({"photos": ["a.jpg"], "narration": "Merhaba dünya."}, tmp_path)
    assert spec["voiceover"] == {"text": "Merhaba dünya."}
    spec = video_edit.normalize({"photos": ["a.jpg", "b.jpg"], "narration": ["bir", "iki"]}, tmp_path)
    assert [sc.get("say") for sc in spec["scenes"]] == ["bir", "iki"]


def test_turkish_letters_in_claimed_names(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "alısveris_tanitim.mp4").write_bytes(b"x")
    assert checks.real_path(tmp_path, "videos/alışveriş_tanitim.mp4") == "videos/alısveris_tanitim.mp4"
    assert checks._on_disk(tmp_path, "videos/alışveriş_tanitim.mp4")
    answer = "Video hazır: `videos/alışveriş_tanitim.mp4` (15 sn)."
    assert checks.fix_claimed_names(answer, tmp_path) == "Video hazır: `videos/alısveris_tanitim.mp4` (15 sn)."
    assert checks.real_path(tmp_path, "videos/baska.mp4") is None


def test_honest_failure_is_not_a_false_claim(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "sahne1_ai.mp4").write_bytes(b"x")
    answer = ("Oluşturulan: videos/sahne1_ai.mp4\n"
              "videos/sahne2_ai.mp4 ve videos/sahne3_ai.mp4 oluşturulamadı (ücretsiz GPU kotası doldu).")
    assert checks.missing_deliverables("Şu resimlerden gerçek hareketli AI video klip üret ve videos klasörüne kaydet", answer, tmp_path, 0) == []
    lie = "Hazır: videos/sahne1_ai.mp4 ve videos/sahne2_ai.mp4"
    assert "videos/sahne2_ai.mp4" in checks.missing_deliverables("Şu resimlerden gerçek hareketli AI video klip üret ve videos klasörüne kaydet", lie, tmp_path, 0)


def test_ambiguous_fold_is_not_guessed(tmp_path):
    for n in ("şekerli.png", "sekerli.png"):
        (tmp_path / n).write_bytes(b"x")
    # "sekerlı.png" (dotless ı) is neither file; it folds to both, so nothing is guessed
    assert checks.real_path(tmp_path, "sekerlı.png") is None
    assert Path(checks.fix_claimed_names("bak: sekerlı.png", tmp_path)) == Path("bak: sekerlı.png")
