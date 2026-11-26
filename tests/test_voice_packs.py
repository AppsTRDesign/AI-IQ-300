"""Turkish voice packs: registry, hardware fit, catalog entries, the worker protocol and the installer question.
No real model is downloaded: the worker is run with a stub adapter, and data lives in the test's temp AIIQ_DATA."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from app.voice import catalog, engines, pack_worker, packs, render


def test_every_pack_has_an_adapter_and_a_complete_entry():
    for e, p in packs.PACKS.items():
        assert e in pack_worker.ADAPTERS, e
        for k in ("name", "tier", "env", "mb", "needs", "license", "commercial", "repo", "pip", "note"):
            assert k in p, (e, k)
        assert p["tier"] in packs.TIERS and p["needs"] in ("cpu", "gpu_better", "cuda")
        if p["needs"] == "cuda":
            assert p.get("vram"), e


def test_non_commercial_licences_are_marked():
    for e in ("mms", "xtts", "anka", "fish"):
        assert packs.PACKS[e]["commercial"] is False
    assert packs.PACKS["xtts"]["terms"]  # installing it means accepting the CPML: the UI asks first


def test_fit_follows_the_hardware(monkeypatch):
    monkeypatch.setattr(packs, "_HW", {"cuda": False, "vram_gb": 0.0, "mps": False})
    assert packs.fit("seda")["state"] == "ok"
    assert packs.fit("xtts")["state"] == "slow"
    assert packs.fit("nefes") == {"state": "no", "reason": "needs_cuda", "vram": 16}
    monkeypatch.setattr(packs, "_HW", {"cuda": True, "vram_gb": 8.0, "mps": False})
    assert packs.fit("kizagan")["state"] == "ok"
    assert packs.fit("nefes")["reason"] == "low_vram"
    assert packs.fit("xtts")["state"] == "ok"


def test_voice_ids_and_language():
    assert catalog.voice_id_ok("seda:default") and catalog.voice_id_ok("pocket:female_1")
    assert catalog.voice_id_ok("piper:tr_TR-dfki-medium")
    assert not catalog.voice_id_ok("nosuch:x") and not catalog.voice_id_ok("seda:../x")
    assert engines.engine_of("seda:default") == "seda" and engines.engine_of("tr-TR-EmelNeural") == "edge"
    assert render.lang_of("seda:default") == "tr" and render.lang_of("drifting:male") == "tr"


def test_catalog_lists_packs_before_and_after_install(monkeypatch):
    monkeypatch.setattr(packs, "_HW", {"cuda": False, "vram_gb": 0.0, "mps": False})
    before = {v["id"]: v for v in packs.voices("tr")}
    assert before["seda:default"]["installed"] is False and before["nefes:default"]["fit"]["state"] == "no"
    assert packs.voices("en") == []
    # an installed pack: its environment's python and the facts file written after a working install
    py = packs.py_of("pocket")
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("")
    packs.ready_file("pocket").write_text(json.dumps({"voices": [{"name": "female_1", "gender": "female"},
                                                                 {"name": "male_1", "gender": "male"},
                                                                 {"name": "bad", "error": "x"}],
                                                      "moods": ["sakin"], "sr": 24000}), encoding="utf-8")
    after = {v["id"]: v for v in packs.voices("tr")}
    assert after["pocket:female_1"]["installed"] and after["pocket:male_1"]["gender"] == "male"
    assert "pocket:bad" not in after and "pocket:default" not in after
    assert after["pocket:female_1"]["moods"] == ["sakin"]
    packs.remove("pocket")
    assert not packs.installed("pocket") and not packs.env_dir("pocket").exists()


def test_worker_protocol_with_a_stub_engine(tmp_path):
    """The real pack_worker main loop, with a stub adapter: JSON lines in, a WAV file and JSON lines out."""
    stub = tmp_path / "stub_worker.py"
    stub.write_text(
        "import sys, runpy\n"
        f"sys.path.insert(0, {str(Path(pack_worker.__file__).parent)!r})\n"
        "import pack_worker as w\n"
        "import numpy as np\n"
        "class S(w.Base):\n"
        "    sr = 16000\n"
        "    moods = ['calm']\n"
        "    def voices(self):\n"
        "        print('noise from a package')\n"  # must not break the JSON stream
        "        return [{'name': 'a', 'gender': 'female'}]\n"
        "    def say(self, text, voice, mood, rate, ref):\n"
        "        if text == 'boom':\n"
        "            raise ValueError('bad text')\n"
        "        return np.sin(np.arange(1600) / 5.0).astype('float32')[None, :]\n"
        "w.ADAPTERS['stub'] = S\n"
        "w.ENGINE = 'stub'\n"
        "w.main()\n", encoding="utf-8")
    out = tmp_path / "x.wav"
    reqs = [{"cmd": "voices"}, {"cmd": "say", "text": "Merhaba", "out": str(out)}, {"cmd": "say", "text": "boom",
                                                                                  "out": str(out)}]
    p = subprocess.run([sys.executable, str(stub)], input="\n".join(json.dumps(r) for r in reqs) + "\n",
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    lines = [json.loads(x) for x in p.stdout.splitlines()]
    assert lines[0]["ok"] and lines[0]["voices"][0]["name"] == "a" and lines[0]["moods"] == ["calm"]
    assert lines[1] == {"ok": True, "sr": 16000}
    assert not lines[2]["ok"] and "bad text" in lines[2]["error"]
    x, sr = engines.read_wav(out)
    assert sr == 16000 and len(x) == 1600 and np.abs(x).max() > 0.5


def test_to_np_flattens_shapes():
    assert pack_worker.to_np(np.zeros((1, 10))).shape == (10,)
    assert pack_worker.to_np(np.zeros((10, 1))).shape == (10,)
    assert pack_worker.to_np(np.zeros((2, 10))).shape == (10,)


def test_installer_question_answers_from_the_environment(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import installer
    for val, want in (("0", []), ("light", ["light"]), ("2", ["light", "medium"]), ("all", ["all"]),
                      ("seda xtts nosuch", ["seda", "xtts"])):
        monkeypatch.setenv("AIIQ_TTS", val)
        assert installer.ask_tts() == want
    # the installer's pack names are exactly the app's packs
    assert set(installer.tr("tts_names").split()) == set(packs.PACKS)
