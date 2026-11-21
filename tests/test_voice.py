"""The voice system (backend/app/voice): sentence split, dialogs, gender from pitch, the fallback order, the studio
finish and subtitle timings. Engines are faked with tones (no download, no network); ffmpeg does the real finish."""
import asyncio
import shutil

import numpy as np
import pytest

from app.voice import catalog, engines, render, studio


def tone(hz: float, secs: float = 1.0, sr: int = 22050) -> np.ndarray:
    t = np.arange(int(sr * secs)) / sr
    # a voiced sound: the fundamental plus harmonics, like speech
    return (0.3 * np.sin(2 * np.pi * hz * t) + 0.15 * np.sin(4 * np.pi * hz * t) + 0.08 * np.sin(6 * np.pi * hz * t)).astype(np.float32)


def test_split_sentences_and_paragraphs():
    parts = render.split("Merhaba! Nasılsın? İyiyim.\n\nYeni paragraf burada.")
    assert [p for p, _ in parts] == ["Merhaba!", "Nasılsın?", "İyiyim.", "Yeni paragraf burada."]
    assert [end for _, end in parts] == [False, False, True, True]
    long = "kelime " * 120 + "son."
    assert all(len(p) <= 400 for p, _ in render.split(long))


def test_dialog_lines():
    d = render.parse_dialog("Ayşe: Merhaba!\nCan: Selam.\nAyşe: Nasılsın?", {})
    assert d == [("Ayşe", "Merhaba!"), ("Can", "Selam."), ("Ayşe", "Nasılsın?")]
    assert render.parse_dialog("Not: bu bir dialog değil, tek satır.", {}) is None


def test_lang_of_every_id():
    assert render.lang_of("tr-TR-EmelNeural") == "tr"
    assert render.lang_of("piper:tr_TR-fettah-medium") == "tr"
    assert render.lang_of("kokoro:bf_emma") == "en"
    assert render.lang_of("chatterbox:ref-me@de") == "de"


def test_gender_from_pitch():
    assert 110 < catalog.pitch_hz(tone(120), 22050) < 130
    assert catalog.gender_of(catalog.pitch_hz(tone(120), 22050)) == "male"
    assert catalog.gender_of(catalog.pitch_hz(tone(215), 22050)) == "female"
    assert catalog.pitch_hz(np.zeros(22050, dtype=np.float32), 22050) == 0.0


def test_studio_chain_keeps_length_and_presets():
    for p in studio.PRESETS:
        c = studio.chain(p, 0, 22050, False)
        assert "alimiter" in c
    c = studio.chain("broadcast", 2, 22050, True)
    assert "loudnorm=I=-23" in c and "asetrate" in c and "atempo" in c and "aecho" in c


@pytest.fixture
def fake_engines(monkeypatch):
    calls = []

    async def synth(vid, text, opts):
        calls.append(vid)
        if vid.startswith("piper:bad"):
            raise engines.VoiceError("broken voice")
        return tone(210 if "female" in vid else 115, 0.4 + len(text) / 200), 22050

    async def local(lang=""):
        return [{"id": "piper:female-a", "engine": "piper", "gender": "female", "quality": "standard", "installed": True, "lang": "tr"},
                {"id": "piper:male-b", "engine": "piper", "gender": "male", "quality": "high", "installed": True, "lang": "tr"},
                {"id": "piper:off", "engine": "piper", "gender": "male", "quality": "high", "installed": False, "lang": "tr"}]

    async def edge(lang=""):
        return [{"id": "tr-TR-EmelNeural", "name": "Emel", "gender": "female", "locale": "tr-TR"}]
    monkeypatch.setattr(engines, "synth", synth)
    monkeypatch.setattr(catalog, "local_voices", local)
    monkeypatch.setattr("app.tts.voices", edge)
    return calls


def test_fallback_order_prefers_gender_then_local(fake_engines):
    female = asyncio.run(render.chain_for("", "tr", "female"))
    # the same gender comes first (an online female voice before a local male one); not-installed voices never
    assert female == ["piper:female-a", "tr-TR-EmelNeural", "piper:male-b"]
    male = asyncio.run(render.chain_for("", "tr", "male"))
    assert male[0] == "piper:male-b"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_render_falls_back_writes_srt_and_dialog(fake_engines, tmp_path):
    res = asyncio.run(render.render("Bir cümle. İkinci cümle burada.", tmp_path / "a.mp3", voice="piper:bad", lang="tr", srt=True))
    assert res["voice"] != "piper:bad" and res["fallback_from"] == "piper:bad"
    assert (tmp_path / "a.mp3").stat().st_size > 1000 and (tmp_path / "a.srt").exists()
    s = res["segments"]
    assert len(s) == 2 and s[0]["end"] < s[1]["start"]  # the pause sits between the sentences
    d = asyncio.run(render.render("Ayşe: Merhaba!\nCan: Selam, nasılsın?", tmp_path / "d.mp3", lang="tr"))
    assert d["voices"] == ["piper:female-a", "piper:male-b"]  # one female, one male speaker
    assert [x["speaker"] for x in d["segments"]] == ["Ayşe", "Can"]
