"""Round 2026-11-22 (b): Claude's current request rules (adaptive thinking, no sampling params on 4.7+, thinking that
cannot be turned off, stop reasons, streamed tool input), Ollama's thinking on tool turns and Ollama Cloud options,
and the silence watchdogs read from Settings. Run: python -m pytest tests/test_round_1122b.py"""
import asyncio

import pytest

from app.agents import streaming
from app.llm import providers as pv


def _capture(mp, events):
    sent = {}

    class R:
        status_code = 200

    async def fake_sse(r):
        for e in events:
            yield e

    class FakeClient:
        def stream(self, method, url, json=None, headers=None):
            sent.update(json or {})

            class C:
                async def __aenter__(s):
                    return R()

                async def __aexit__(s, *e):
                    return False
            return C()

    class Pool:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, *e):
            return False

    async def ok(*a, **k):
        return None
    mp.setattr(pv, "_sse", fake_sse)
    mp.setattr(pv, "pooled", Pool)
    mp.setattr(pv, "_raise_for", ok)
    return sent


def _claude(mp, model, opts, events=()):
    sent = _capture(mp, list(events))
    p = pv.AnthropicProvider("anthropic", {"base_url": "https://api.anthropic.com/v1"}, pv.Capabilities())
    p.key = lambda **k: "k"

    async def go():
        return [e async for e in p.stream(model, [{"role": "user", "content": "x"}], opts)]
    out = asyncio.run(go())
    return sent, out


def test_claude_generations():
    assert pv.claude_gen("claude-3-7-sonnet-20250219") == "legacy"
    assert pv.claude_gen("claude-sonnet-4-20250514") == "legacy"
    assert pv.claude_gen("claude-haiku-4-5-20251001") == "legacy"
    assert pv.claude_gen("claude-opus-4-6") == "4.6"
    assert pv.claude_gen("claude-opus-4-8") == "new"
    assert pv.claude_gen("claude-haiku-5-5") == "new"
    assert pv.claude_gen("claude-opus-5-5") == "always_on"
    assert pv.claude_gen("claude-fable-5-2") == "always_on"
    assert pv.claude_gen("claude-sonnet-5-5") == "between_tools"


def test_claude_request_shapes(monkeypatch):
    # 4.7+: adaptive thinking + effort, never budget_tokens or temperature
    sent, _ = _claude(monkeypatch, "claude-opus-4-8", {"effort": "high", "temperature": 0.3, "tools": [
        {"name": "t", "description": "d", "parameters": {"type": "object"}}]})
    assert sent["thinking"]["type"] == "adaptive" and sent["output_config"] == {"effort": "high"}
    assert "temperature" not in sent and sent["tools"][0]["eager_input_streaming"] is True
    # thinking off on a model that cannot turn it off: lowest effort, no 'disabled'
    sent, _ = _claude(monkeypatch, "claude-opus-5-5", {"effort": "off", "temperature": 0.3})
    assert "thinking" not in sent and sent["output_config"] == {"effort": "low"} and "temperature" not in sent
    sent, _ = _claude(monkeypatch, "claude-sonnet-5-5", {"think": False})
    assert sent["thinking"] == {"type": "between_tools"}
    # an older model keeps its budget and its temperature
    sent, _ = _claude(monkeypatch, "claude-haiku-4-5", {"think": True})
    assert sent["thinking"]["type"] == "enabled" and sent["thinking"]["budget_tokens"] >= 1024
    sent, _ = _claude(monkeypatch, "claude-haiku-4-5", {"temperature": 0.2})
    assert sent["temperature"] == 0.2 and "thinking" not in sent


def test_claude_stop_reasons(monkeypatch):
    _, out = _claude(monkeypatch, "claude-opus-4-8", {}, [
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hal"}},
        {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}, "usage": {"output_tokens": 5}}])
    assert any(e["type"] == "truncated" for e in out)
    with pytest.raises(pv.ProviderError) as e:
        _claude(monkeypatch, "claude-opus-5-5", {}, [
            {"type": "message_delta", "delta": {"stop_reason": "refusal", "stop_details": {"category": "cyber"}}}])
    assert e.value.code == "refused" and "cyber" in str(e.value)


def _compat(mp, base, model, opts, events=()):
    sent = _capture(mp, list(events))
    p = pv.OpenAICompatProvider("x", {"base_url": base}, pv.Capabilities())
    p.key = lambda **k: "k"

    async def go():
        return [e async for e in p.stream(model, [{"role": "user", "content": "x"}], opts)]
    return sent, asyncio.run(go())


def test_model_family_rules(monkeypatch):
    sent, _ = _compat(monkeypatch, "https://api.openai.com/v1", "gpt-5.1", {"max_tokens": 900, "temperature": 0.4})
    assert sent["max_completion_tokens"] == 900 and "max_tokens" not in sent and "temperature" not in sent
    sent, _ = _compat(monkeypatch, "https://api.openai.com/v1", "gpt-4.1", {"max_tokens": 900, "temperature": 0.4})
    assert sent["max_tokens"] == 900 and sent["temperature"] == 0.4
    sent, _ = _compat(monkeypatch, "https://api.moonshot.ai/v1", "kimi-k2.5", {"temperature": 0.4, "think": False})
    assert "temperature" not in sent and sent["thinking"] == {"type": "disabled"}
    sent, _ = _compat(monkeypatch, "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus", {"think": False})
    assert sent["enable_thinking"] is False and "reasoning_effort" not in sent


def test_mistral_thinking_chunks(monkeypatch):
    events = [{"choices": [{"delta": {"content": [{"type": "thinking", "thinking": [{"type": "text", "text": "hmm"}]}]}}]},
              {"choices": [{"delta": {"content": "Yanıt"}}]}]
    _, out = _compat(monkeypatch, "https://api.mistral.ai/v1", "magistral-medium-latest", {}, events)
    assert [(e["type"], e["text"]) for e in out if e["type"] in ("thinking", "text")] == [("thinking", "hmm"), ("text", "Yanıt")]


def test_ollama_tool_turn_keeps_its_thinking():
    out = pv.OllamaProvider._messages([{"role": "assistant", "content": "", "reasoning": "plan",
                                        "tool_calls": [{"id": "1", "name": "t", "arguments": {}}]}])
    assert out[0]["thinking"] == "plan"


def test_watchdogs_follow_settings(monkeypatch):
    from app import config
    real = config.load_settings
    monkeypatch.delenv("AIIQ_PROBE_AFTER", raising=False)
    monkeypatch.setattr(config, "load_settings", lambda: {**real(), "agent": {"midcall_stall": 240, "probe_after": 1}})
    assert streaming.wd("midcall_stall") == 240
    assert streaming.wd("probe_after") == 5  # floor: a too small value never cuts healthy streams
    assert streaming.wd("silent_tool_limit") == streaming.SILENT_TOOL_LIMIT
    from app.llm import router
    monkeypatch.setattr(router, "load_settings", lambda: {"agent": {"stall_floor": 200}})
    assert router.stall_floor() == 200
