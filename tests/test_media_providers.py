"""Round 2026-11-20b: provider listings, retired models, shared Cloudflare account, media models, video order."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.llm import providers  # noqa: E402
from app.tools import mediamodels, services  # noqa: E402


def test_non_chat_models_are_hidden():
    for name in ("nvidia/nv-embedqa-mistral-7b-v2", "snowflake/arctic-embed-l", "nvidia/nvclip", "gemini-3.5-transcribe",
                 "canopylabs/orpheus-v1-english", "@cf/meta/llama-guard-3-8b", "deep-research-pro-preview-12-2025",
                 "openai/gpt-audio-mini", "imagen-4.0-generate-001", "veo-3.1-generate-preview"):
        assert providers.NOT_CHAT.search(name), name
    for name in ("gemini-3.8-flash", "minimaxai/minimax-m3.1-flash", "qwen/qwen3.8-27b", "openai/gpt-oss-120b",
                 "@cf/openai/gpt-oss-120b", "deepseek-v4-pro"):
        assert not providers.NOT_CHAT.search(name), name


def test_capabilities_from_names_only_claim_what_matches():
    c = providers.infer_caps("google/gemma-4-31b-it")
    assert c["vision"] is True
    c = providers.infer_caps("meta/muse-glimmer-30b")
    assert c == {"vision": None, "thinking": None, "tools": None}  # unknown stays unknown, never "missing"
    assert providers.infer_caps("deepseek-v4-pro")["thinking"] is True
    assert providers.infer_caps("nvidia/llama-3.3-nemotron-super-49b")["tools"] is True


def test_retired_models_are_remembered_per_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_RETIRED_FILE", tmp_path / "retired.json")
    cfg = {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai"}
    assert providers.retired(cfg, "gemini-2.5-flash") is None
    providers.mark_retired(cfg, "models/gemini-2.5-flash", "gemini-3.8-flash")
    assert providers.retired(cfg, "gemini-2.5-flash") == "gemini-3.8-flash"
    assert providers.retired({"base_url": "https://openrouter.ai/api/v1"}, "gemini-2.5-flash") is None


def test_retired_answer_is_its_own_code():
    body = json.dumps({"error": {"code": 404, "message": "This model models/gemini-2.5-flash is no longer available to "
                                                         "new users. Please update your code to use models/gemini-3.8-flash"}})
    assert providers.classify_error(404, body) == "model_retired"
    assert providers.classify_error(404, '{"error": {"message": "model foo not found"}}') == "model_not_found"


def test_media_models_only_of_their_kind():
    names = ["gemini-3.8-flash", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image", "imagen-4.0-generate-001",
             "veo-3.1-fast-generate-preview", "veo-2.0-generate-001", "text-embedding-004"]
    img = mediamodels.of_kind("image", names)
    assert "gemini-3.8-flash" not in img and "veo-2.0-generate-001" not in img and "gemini-3.1-flash-image" in img
    vid = mediamodels.of_kind("video", names)
    assert vid == ["veo-3.1-fast-generate-preview", "veo-2.0-generate-001"]


def test_video_services_in_order_paid_first_and_switchable(monkeypatch):
    monkeypatch.setattr(services, "has_key", lambda sid: sid in ("veo", "hf_wan", "hf_wan2", "hf_svd"))
    monkeypatch.setattr(services, "_disabled", lambda kind: {"hf_wan2"} if kind == "video" else set())
    order = services.usable("video")
    assert order[0] == "veo" and "hf_wan2" not in order and order[-1] == "hf_svd"


def test_cloudflare_account_is_one_value():
    from app import main
    body = {"media": {"cloudflare_account": " ab03 "}}
    main._sync_shared(body)
    assert body["providers"]["cloudflare"]["account_id"] == "ab03"
    body = {"providers": {"cloudflare": {"account_id": "cd04"}}}
    main._sync_shared(body)
    assert body["media"]["cloudflare_account"] == "cd04"
