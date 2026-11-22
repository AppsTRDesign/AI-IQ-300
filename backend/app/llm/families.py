"""Model families: how a model behaves, whichever provider serves it.

A provider decides the transport (URL, auth, streaming, its own request fields - providers.py). The model decides
how it reasons and calls tools: the same DeepSeek or Qwen behaves the same on EVREN, NVIDIA, OpenRouter, Ollama or
any provider that adds it later. Requests are built from both: provider rules + this family profile.

Fields of a profile (all optional):
  native     - function calling of this family through the provider's API:
               True = reliable, False = not supported / unreliable (the AI IQ 300 text protocol is used),
               None = no opinion (the provider rule decides).
  think_key  - the chat-template switch that turns reasoning off on template servers (vLLM, SGLang, NIM):
               "enable_thinking" (Qwen3, GLM, Nemotron, Hunyuan), "thinking" (DeepSeek V3.1+), None = no switch.
  always_thinks - reasons on every request and cannot be turned off (R1, QwQ, *-thinking, gpt-oss).
  text_format   - how the family writes a tool call as text when its server's parser misses it (for the notes;
                  stream_parser.py reads every one of them).
  sampling   - recommended sampling from the model card, used only when the user set none.
  no_system  - the chat template has no system role (the system prompt goes into the first user message).
  notes      - why (sources: model cards / vendor docs, 2026-11).
Order matters: the first pattern that matches wins (specific before general)."""
from __future__ import annotations

import re

FAMILIES: list[tuple[str, str, dict]] = [
    # --- DeepSeek ---------------------------------------------------------------------------------------------
    ("deepseek-r1", r"deepseek[-_.]?r1|r1-distill", {
        "native": False, "always_thinks": True, "text_format": "<think> + JSON",
        "sampling": {"temperature": 0.6, "top_p": 0.95},
        "notes": "R1 has no function calling (DeepSeek docs); reasoning always on, temperature 0.5-0.7."}),
    ("deepseek-v3", r"deepseek[-_.]?(v3|v4|chat|reasoner|coder-v2)", {
        "native": True, "think_key": "thinking", "text_format": "DSML / <｜tool▁calls▁begin｜>",
        "notes": "V3.1+ hybrid: chat_template_kwargs.thinking on vLLM/NIM; reasoning_content must go back with tools "
                 "on DeepSeek's API (done by the provider)."}),
    # --- Qwen ---------------------------------------------------------------------------------------------------
    ("qwq", r"\bqwq", {"native": True, "always_thinks": True, "sampling": {"temperature": 0.6, "top_p": 0.95},
                       "notes": "QwQ always reasons."}),
    ("qwen-thinking", r"qwen3[\w.-]*-thinking", {
        "native": True, "always_thinks": True, "text_format": "<tool_call>{json} (Hermes)",
        "sampling": {"temperature": 0.6, "top_p": 0.95}, "notes": "Thinking-only Qwen3 variants."}),
    ("qwen-coder", r"qwen[\d.]*-?coder", {
        "native": True, "text_format": "<function=NAME><parameter=k>v</parameter></function> (Qwen3-Coder XML)",
        "sampling": {"temperature": 0.7, "top_p": 0.8}, "notes": "Qwen3-Coder: non-thinking, XML tool format."}),
    ("qwen3", r"qwen3|qwen-(plus|max|turbo|flash)", {
        "native": True, "think_key": "enable_thinking", "text_format": "<tool_call>{json} (Hermes)",
        "sampling": {"temperature": 0.6, "top_p": 0.95},
        "notes": "Hybrid: enable_thinking (template servers, DashScope); thinking 0.6/0.95, non-thinking 0.7/0.8."}),
    ("qwen2", r"qwen2", {"native": True, "text_format": "<tool_call>{json} (Hermes)"}),
    # --- GLM (Z.ai) ---------------------------------------------------------------------------------------------
    ("glm", r"glm-?[45]", {
        "native": True, "think_key": "enable_thinking", "text_format": "<tool_call>NAME<arg_key>..</arg_key>",
        "notes": "GLM-4.5+ hybrid: enable_thinking on vLLM/SGLang, thinking={type} on Z.ai (provider rule)."}),
    # --- Kimi (Moonshot) ----------------------------------------------------------------------------------------
    ("kimi-thinking", r"kimi-k2-thinking", {"native": True, "always_thinks": True,
                                            "text_format": "<|tool_call_begin|>functions.NAME:0 ..."}),
    ("kimi", r"kimi|moonshot", {
        "native": True, "text_format": "<|tool_call_begin|>functions.NAME:0<|tool_call_argument_begin|>{json}",
        "sampling": {"temperature": 0.6},
        "notes": "K2: temperature 0.6 recommended; K2.5+ on Moonshot fix temperature/top_p (provider rule)."}),
    # --- MiniMax ------------------------------------------------------------------------------------------------
    ("minimax", r"minimax", {
        "native": True, "always_thinks": True, "text_format": "<minimax:tool_call><invoke name=..>",
        "sampling": {"temperature": 1.0, "top_p": 0.95},
        "notes": "M2 keeps <think> in content (interleaved thinking): it must stay in the history; M3 sends "
                 "reasoning_content."}),
    # --- OpenAI open weights / GPT ------------------------------------------------------------------------------
    ("gpt-oss", r"gpt-oss", {
        "native": True, "always_thinks": True, "text_format": "harmony <|channel|>commentary to=functions.NAME",
        "notes": "Reasoning levels low/medium/high (reasoning_effort, Ollama think level), cannot be turned off."}),
    ("gpt", r"(^|/)(gpt-[45]|o[134]\b|o[134]-|chatgpt)", {"native": True}),
    # --- Google ---------------------------------------------------------------------------------------------------
    ("gemma", r"gemma", {
        "native": False, "no_system": False, "text_format": "```tool_code fn(a=1)``` / JSON",
        "sampling": {"temperature": 1.0, "top_p": 0.95},
        "notes": "Gemma has no function-calling tokens: tools are prompt-based (Google's Gemma docs); the text "
                 "protocol is the reliable path. Sampling 1.0 / 0.95 / top_k 64."}),
    ("gemini", r"gemini", {"native": True, "notes": "Gemini 3: thought_signature in extra_content goes back with "
                                                    "every tool call (provider)."}),
    # --- Meta ---------------------------------------------------------------------------------------------------
    ("llama-small", r"llama-?3\.[123][\w.-]*?[-:](1b|3b|8b)|llama3\.[123]:(1b|3b|8b)|llama-?3\.2", {
        "native": False, "text_format": '<|python_tag|>{"name", "parameters"}',
        "notes": "Small Llama 3.x call tools unreliably (Meta: 8B and below not recommended for tool chains)."}),
    ("llama", r"llama", {"native": True, "text_format": '{"name": .., "parameters": ..} / <|python_tag|>'}),
    # --- Mistral ------------------------------------------------------------------------------------------------
    ("magistral", r"magistral", {"native": True, "always_thinks": True,
                                 "notes": "Reasoning as thinking chunks in content (provider parses them)."}),
    ("mistral", r"mistral|mixtral|devstral|codestral|ministral|pixtral", {
        "native": True, "text_format": "[TOOL_CALLS][{json}]",
        "notes": "Tool ids must be 9 alphanumerics on Mistral's API (provider rule). Mistral 7B v0.1/0.2: no tools."}),
    # --- NVIDIA ---------------------------------------------------------------------------------------------------
    ("nemotron", r"nemotron", {"native": True, "think_key": "enable_thinking",
                               "notes": "Nemotron reasoning switch: enable_thinking / 'detailed thinking off'."}),
    # --- others -------------------------------------------------------------------------------------------------
    ("phi", r"\bphi-?[234]", {"native": False, "notes": "Phi models call tools unreliably; text protocol."}),
    ("grok", r"grok", {"native": True}),
    ("claude", r"claude", {"native": True}),
    ("command", r"command-?(r|a)", {"native": True}),
    ("hermes", r"hermes", {"native": True, "text_format": "<tool_call>{json}"}),
    ("granite", r"granite", {"native": True}),
    ("seed-oss", r"seed-oss", {"native": True, "think_key": "enable_thinking"}),
]

_COMPILED = [(name, re.compile(pat, re.I), prof) for name, pat, prof in FAMILIES]


def family(model: str) -> tuple[str, dict]:
    """(family name, profile) of a model id ('' and {} when unknown). The provider prefix and a vendor path
    ('ollama:qwen3:8b', 'deepseek-ai/DeepSeek-V3.2', 'openrouter:moonshotai/kimi-k2') are ignored."""
    m = (model or "").lower()
    m = m.split(":", 1)[1] if re.match(r"^[a-z_]+:", m) and "/" not in m.split(":", 1)[0] else m
    for name, rx, prof in _COMPILED:
        if rx.search(m):
            return name, prof
    return "", {}


def native_ok(model: str) -> bool | None:
    """True / False when the family says whether its function calling works, None when it has no opinion."""
    return family(model)[1].get("native")


def think_key(model: str) -> str | None:
    """The chat-template key that switches this family's reasoning off (template servers), or None."""
    return family(model)[1].get("think_key")


def always_thinks(model: str) -> bool:
    return bool(family(model)[1].get("always_thinks"))


def sampling(model: str) -> dict:
    """Recommended sampling of the model card (only used when the user set none)."""
    return dict(family(model)[1].get("sampling") or {})
