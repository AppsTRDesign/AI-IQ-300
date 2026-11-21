"""Provider errors read as sentences (never JSON), chat-model filters, and the step kinds of made vs found media."""
from app.agents import runstate
from app.llm import providers


def test_error_message_from_every_shape():
    gemini = "[{'error': {'code': 503, 'message': 'This model is currently experiencing high demand.', 'status': 'UNAVAILABLE'}}]"
    assert providers.message_of(gemini) == "This model is currently experiencing high demand."
    assert providers.message_of('[{"error": {"code": 429, "message": "Quota exceeded"}}]') == "Quota exceeded"
    assert providers.message_of('{"errors":[{"code":3036,"message":"daily free allocation used"}]}') == "daily free allocation used"
    assert providers.message_of('{"detail": "Not found"}') == "Not found"
    assert providers.message_of("gemini · HTTP 503: " + gemini) == "gemini · HTTP 503: This model is currently experiencing high demand."
    assert providers.message_of("plain text") == "plain text"
    assert "{" not in providers._error_message(gemini)


def test_stream_error_is_classified_and_clean():
    e = providers.stream_error([{"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}])
    assert e.code == "overloaded" and str(e).strip().endswith("high demand") and "{" not in str(e)


def test_gemini_chat_names_only():
    ok = ["gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-3-pro-preview", "gemini-3.1-flash-preview-09-2026",
          "gemma-3-27b-it", "gemini-flash-latest", "gemini-2.0-flash-001"]
    bad = ["gemini-4-hydrogen", "gemini-4-argon", "gemini-4-carbon", "gemini-exp-1206-codename"]
    assert all(providers.GEMINI_CHAT.match(x) for x in ok)
    assert not any(providers.GEMINI_CHAT.match(x) for x in bad)


def test_listing_metadata_filters():
    assert providers._chat_by_meta({"id": "x", "type": "chat"})
    assert not providers._chat_by_meta({"id": "x", "type": "image"})
    assert not providers._chat_by_meta({"id": "x", "type": "embedding"})
    assert not providers._chat_by_meta({"id": "m", "capabilities": {"completion_chat": False}})
    assert not providers._chat_by_meta({"id": "g", "active": False})
    assert providers.NOT_CHAT_EXTRA.search("davinci-002") and providers.NOT_CHAT_EXTRA.search("omni-moderation-latest")
    assert not providers.NOT_CHAT_EXTRA.search("gpt-5.4-mini")


def test_made_media_is_not_a_photo_search():
    k = runstate.TOOL_TITLES
    assert k["generate_image"] == "image_gen" and k["stock_photo"] == "photo"
    assert k["generate_video"] == k["animate_image"] == "video_gen" and k["edit_video"] == "video_edit"
    assert k["text_to_speech"] == "speech" and k["inspect_media"] == "inspect"
