"""Clone studio: cleaning really removes noise and clicks, keeps the voice, and work files are not voices."""
import numpy as np

from app.voice import catalog, clone as studio

SR = studio.SR


def _speech(secs=8.0, f0=140.0, seed=0):
    """Voiced bursts (harmonics of f0) with pauses: close enough to speech for the analysis."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * secs)) / SR
    tone = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    env = (np.sin(2 * np.pi * 1.3 * t) > -0.2).astype(np.float32)
    x = 0.25 * tone * env
    return x.astype(np.float32), rng


def test_denoise_raises_snr_and_keeps_pitch():
    x, rng = _speech()
    noisy = x + 0.03 * rng.standard_normal(len(x)).astype(np.float32)
    a = studio.analyse(noisy)
    y = studio.clean(noisy)
    b = studio.analyse(y)
    assert b["snr_db"] > a["snr_db"] + 6
    assert abs(b["pitch_hz"] - 140) < 15 and b["gender"] == "male"
    assert b["peak_db"] <= -0.9


def test_declick_removes_impulses():
    x, _ = _speech()
    clicked = x.copy()
    for i in range(2000, len(x), 9000):
        clicked[i] = 0.95
    y = studio.declick(clicked)
    assert np.abs(y).max() < 0.8


def test_trim_shortens_long_silence():
    x, _ = _speech(4)
    gap = np.zeros(SR * 3, dtype=np.float32)
    y = studio.trim(np.concatenate([gap, x, gap, x, gap]))
    assert len(y) < len(x) * 2 + SR * 2


def test_session_files_are_not_voices(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "REFS_DIR", tmp_path)
    x, rng = _speech()
    res = studio.start(x + 0.01 * rng.standard_normal(len(x)).astype(np.float32))
    assert studio.ok_id(res["id"]) and res["after"]["score"] >= res["before"]["score"] - 5
    assert studio.file_of(res["id"], "clean").exists()
    assert catalog.own_refs() == []
    monkeypatch.setattr(catalog, "META", tmp_path / "voices.json")
    saved = studio.save(res["id"], "benim-sesim")
    assert saved["gender"] == "male"
    assert [p.stem for p in catalog.own_refs()] == ["benim-sesim"]
    assert studio.voice_name(res["id"], "clean") == f"ref-_studio-{res['id']}-clean"
