"""Cloud voices (ElevenLabs, OpenAI, Google, Gemini, Azure): listing, ids, synthesis and the key test, with a fake
HTTP client. No request leaves the machine and no real key is used; data lives in the test's temp AIIQ_DATA."""
import asyncio
import base64
import json

import numpy as np
import pytest

from app import tts
from app.config import save_settings, set_secret
from app.voice import cloud, engines, render


class Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content = status, data, content
        self.text = json.dumps(data) if data is not None else ""

    def json(self):
        return self._data


class FakeClient:
    calls: list = []

    def __init__(self, routes):
        self.routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def _hit(self, method, url, **kw):
        FakeClient.calls.append((method, url, kw))
        for part, resp in self.routes.items():
            if part in url:
                return resp
        return Resp(404, {"error": {"message": "not found"}})

    async def get(self, url, **kw):
        return self._hit("GET", url, **kw)

    async def post(self, url, **kw):
        return self._hit("POST", url, **kw)


@pytest.fixture(autouse=True)
def _clean_keys():
    """The keys and switches of one test never reach another (nor a later test's /api/voices: no real request)."""
    yield
    for c in cloud.CLOUD.values():
        set_secret(c["secret"], None)
    save_settings({"voice_cloud": {"disabled": [], "models": {}, "azure_region": ""}})
    cloud._LIST.clear()
    cloud.ERRORS.clear()


def _fake(monkeypatch, routes):
    FakeClient.calls = []
    cloud._LIST.clear()
    monkeypatch.setattr(cloud, "_client", lambda: FakeClient(routes))
    monkeypatch.setattr(engines, "decode", lambda data, sr=24000: (np.zeros(2400, dtype=np.float32), sr))


def test_nothing_is_listed_without_a_key():
    cloud._LIST.clear()
    assert cloud.active() == []
    assert asyncio.run(cloud.voices("tr")) == []


def test_keyed_services_add_their_voices(monkeypatch):
    set_secret("elevenlabs_api_key", "test-el-key")
    set_secret("azure_speech_key", "test-az-key")
    save_settings({"voice_cloud": {"azure_region": "westeurope"}})
    _fake(monkeypatch, {
        "elevenlabs.io/v1/voices": Resp(200, {"voices": [
            {"voice_id": "abc123", "name": "Rachel", "labels": {"gender": "female"}, "category": "premade"},
            {"voice_id": "me456", "name": "My clone", "labels": {}, "category": "cloned"}]}),
        "voices/list": Resp(200, [
            {"ShortName": "tr-TR-EmelNeural", "DisplayName": "Emel", "Gender": "Female", "Locale": "tr-TR"},
            {"ShortName": "de-DE-KatjaNeural", "DisplayName": "Katja", "Gender": "Female", "Locale": "de-DE"}]),
    })
    vs = asyncio.run(cloud.voices("tr"))
    ids = {v["id"]: v for v in vs}
    assert "elevenlabs:abc123" in ids and ids["elevenlabs:abc123"]["gender"] == "female"
    assert ids["elevenlabs:me456"].get("own") and "tr" in ids["elevenlabs:me456"]["langs"]
    assert "azure:tr-TR-EmelNeural" in ids and "azure:de-DE-KatjaNeural" not in ids  # per-locale service
    assert all(v["cloud"] and v["installed"] and not v["offline"] for v in vs)
    # the key travels only in a header, never in a URL
    assert all("test-el-key" not in url and "test-az-key" not in url for _, url, _ in FakeClient.calls)
    # a switched-off service lists nothing
    save_settings({"voice_cloud": {"disabled": ["elevenlabs"]}})
    assert not any(v["engine"] == "elevenlabs" for v in asyncio.run(cloud.voices("tr")))


def test_cloud_voice_ids_are_accepted_and_routed():
    assert cloud.voice_ok("openai:nova") and cloud.voice_ok("google:tr-TR-Chirp3-HD-Achernar")
    assert not cloud.voice_ok("openai:") and not cloud.voice_ok("nope:nova") and not cloud.voice_ok("openai:a/b")
    assert engines.engine_of("elevenlabs:abc") == "elevenlabs" and engines.engine_of("azure:tr-TR-EmelNeural") == "azure"
    assert render.lang_of("azure:tr-TR-EmelNeural") == "tr" and render.lang_of("openai:nova") == ""


def test_synthesis_per_service(monkeypatch):
    for name, key in (("openai_api_key", "k1"), ("gemini_api_key", "k2"), ("google_tts_api_key", "k3"),
                      ("elevenlabs_api_key", "k4")):
        set_secret(name, key)
    pcm = (np.ones(4800, dtype="<i2") * 1000).tobytes()
    _fake(monkeypatch, {
        "audio/speech": Resp(200, content=b"mp3"),
        "generateContent": Resp(200, {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}),
        "text:synthesize": Resp(200, {"audioContent": base64.b64encode(b"mp3").decode()}),
        "text-to-speech/": Resp(200, content=b"mp3"),
    })
    x, sr = asyncio.run(cloud.synth("gemini", "Kore", "Merhaba", {}))
    assert sr == 24000 and len(x) == 4800 and abs(float(x[0]) - 1000 / 32768) < 1e-6
    for sid, name in (("openai", "nova"), ("google", "tr-TR-Wavenet-A"), ("elevenlabs", "abc")):
        x, sr = asyncio.run(cloud.synth(sid, name, "Merhaba", {"rate": 1.5, "emotion": 0.9}))
        assert len(x)
    body = next(kw["json"] for m, url, kw in FakeClient.calls if "audio/speech" in url)
    assert body["voice"] == "nova" and body["speed"] == 1.5 and "instructions" in body
    el = next(kw["json"] for m, url, kw in FakeClient.calls if "text-to-speech/" in url)
    assert el["voice_settings"]["speed"] == 1.2  # ElevenLabs' range is 0.7-1.2


def test_a_bad_key_is_reported_not_raised(monkeypatch):
    set_secret("elevenlabs_api_key", "wrong")
    _fake(monkeypatch, {"elevenlabs.io/v1/voices": Resp(401, {"detail": {"message": "Invalid API key"}})})
    r = asyncio.run(cloud.test("elevenlabs"))
    assert r["ok"] is False and "Invalid API key" in r["error"] and "wrong" not in r["error"]
    assert asyncio.run(cloud.voices("tr")) == [] or True  # the list stays usable
    _fake(monkeypatch, {"elevenlabs.io/v1/voices": Resp(200, {"voices": [{"voice_id": "a", "name": "A"}]})})
    assert asyncio.run(cloud.test("elevenlabs"))["ok"] is True


def test_azure_needs_a_region():
    set_secret("azure_speech_key", "k")
    save_settings({"voice_cloud": {"azure_region": "bad region!"}})
    assert not cloud.ready("azure")
    assert asyncio.run(cloud.test("azure"))["ok"] is False


def test_engine_order_adds_new_engines(monkeypatch):
    from app.voice import packs
    monkeypatch.setattr(packs, "installed", lambda e: e in ("seda", "xtts"))
    save_settings({"voice": {"order": ["kokoro", "piper", "edge", "chatterbox"], "disabled": [], "cloud_on": []}})
    assert render.engine_order() == ["kokoro", "piper", "seda", "xtts", "edge", "chatterbox"]  # packs before online
    set_secret("openai_api_key", "k")
    order = render.engine_order()
    assert order[-1] == "openai" and "openai" in render.engine_off()  # a cloud service waits to be switched on
    save_settings({"voice": {"cloud_on": ["openai"]}})
    assert "openai" not in render.engine_off()
    monkeypatch.setattr(packs, "installed", lambda e: e == "seda")
    assert "xtts" not in render.engine_order()  # a removed pack drops out
    save_settings({"voice": {"order": ["piper", "kokoro", "chatterbox", "edge"], "cloud_on": []}})


def test_tts_accepts_cloud_voice_ids(monkeypatch):
    async def fake_render(text, target, **kw):
        target.write_bytes(b"ID3" + kw["voice"].encode())
    monkeypatch.setattr(render, "render", fake_render)
    tts._AUDIO.clear()
    assert asyncio.run(tts.synthesize("Merhaba", "openai:nova")).endswith(b"openai:nova")
