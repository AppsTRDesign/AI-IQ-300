"""Routes 'provider:model' IDs to adapters. No silent cloud fallback: cloud is used only when selected,
or when settings.cloud_fallback is explicitly enabled (and the switch is reported as an event)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import AsyncIterator, Callable

import httpx

from ..config import DATA_DIR, get_secret, load_settings, save_settings
from ..events import bus
from . import modelstats, usage
from .providers import ADAPTERS, VISION_HINT, Capabilities, OllamaProvider, Provider, ProviderError

# Used only when a provider's API does not report a context window.
CONTEXT_FALLBACK = [
    (r"gemini", 1_048_576), (r"deepseek-v4|glm-5|gpt-4\.1", 1_000_000), (r"claude", 200_000),
    # NVIDIA NIM lists no window: Nemotron 3 / 3.5 (nano, super, ultra 550B) read up to 1M tokens (model cards).
    (r"nemotron-3(?!.*(embed|safety|parse|reward))", 1_000_000), (r"llama-3\.\d-nemotron", 128_000),
    (r"gpt-5", 400_000), (r"grok", 256_000), (r"qwen3\.8|gemma-4|qwen3-vl", 256_000),
    (r"gpt-4o|deepseek|mistral|llama-3|qwen", 128_000), (r"evren-llm-7b", 32_768),
]
DEFAULT_CONTEXT = 32_768
LOCAL_DEFAULT_CTX = 16_384  # local window when neither the user nor the model file sets one (fast on a CPU, light on RAM;
# grows only when a task really needs it, within what the free RAM allows)
_INFO_CACHE: dict[str, tuple[float, dict]] = {}
_NO_NATIVE_TOOLS: set[str] = set()  # models that rejected native tool calls (tag protocol is used)


def split_model_id(model_id: str) -> tuple[str, str]:
    provider, _, model = model_id.partition(":")
    if not model:
        raise ProviderError("bad_model", f"Model id must be 'provider:model', got {model_id!r}")
    return provider, model


def get_provider(name: str, require_enabled: bool = True) -> Provider:
    cfg = load_settings()["providers"].get(name)
    if not cfg:
        raise ProviderError("unknown_provider", f"Unknown provider: {name}")
    if require_enabled and not cfg.get("enabled"):
        raise ProviderError("disabled", f"Provider '{name}' is disabled in Settings")
    cls = ADAPTERS.get(cfg.get("kind", name))
    if not cls:
        raise ProviderError("unknown_kind", f"Unsupported protocol: {cfg.get('kind')}")
    return cls(name, cfg, Capabilities(streaming=cfg.get("streaming", True)))


def supports_images(model_id: str) -> bool:
    """The user's profile first, then what the provider's API reported for the model (Ollama capabilities,
    OpenRouter modalities...), and only then the name."""
    if (v := profile(model_id).get("vision")) in ("on", "off"):
        return v == "on"
    cached = _INFO_CACHE.get(model_id)
    if cached and cached[1].get("vision") is not None:
        return bool(cached[1]["vision"])
    for m in (_MODEL_CACHE.get(model_id.partition(":")[0]) or (0, {}))[1].get("models", []):
        if m.get("id") == model_id.partition(":")[2] and m.get("vision") is not None:
            return bool(m["vision"])
    return any(h in model_id.lower() for h in VISION_HINT)


# Model profiles: the user's per-model overrides. "auto" (or a missing key) keeps what the provider reports.
PROFILE_CHOICES = {"thinking": ("auto", "on", "off"), "vision": ("auto", "on", "off"),
                   "streaming": ("auto", "on", "off"), "tools": ("auto", "native", "tags")}


# Reasoning effort. Levels a model really supports come from what its API reports; "api" sends the provider's
# own parameter, "prompt" adds an instruction for models whose API offers no such control (e.g. most local ones).
EFFORT_LEVELS = ("off", "on", "minimal", "low", "medium", "high")
PROMPT_EFFORTS = ["low", "medium", "high"]
EFFORT_PROMPT = {
    "low": "Reasoning effort: LOW. Answer directly and keep internal deliberation to a minimum.",
    "medium": "Reasoning effort: MEDIUM. Think as much as the task needs, then answer.",
    "high": "Reasoning effort: HIGH. Think step by step and carefully before answering; double-check code, edge "
            "cases and assumptions before you act.",
}
ANTHROPIC_BUDGET = {"low": 2048, "medium": 8192, "high": 24576}
GEMINI_BUDGET = {"off": 0, "low": 1024, "medium": 8192, "high": 24576}


def effort_spec(model_id: str, m: dict, settings: dict | None = None) -> dict:
    """{"efforts": supported levels, "effort_via": "api" | "prompt" | None} for a model, from its provider kind,
    address and the capabilities its API reported (m: list entry or context info)."""
    try:
        pname, model = split_model_id(model_id)
    except ProviderError:
        return {"efforts": [], "effort_via": None}
    cfg = (settings or load_settings())["providers"].get(pname) or {}
    kind, url, name, thinking = cfg.get("kind", pname), (cfg.get("base_url") or "").lower(), model.lower(), m.get("thinking")
    api = lambda levels: {"efforts": levels, "effort_via": "api"}  # noqa: E731
    if kind == "ollama":
        if "gpt-oss" in name:
            return api(["low", "medium", "high"])  # Ollama: think="low"|"medium"|"high" for gpt-oss
        if thinking:
            return api(["off", "on"])  # other thinking models: think on / off only
    elif kind == "anthropic" and thinking:
        return api(["off", "low", "medium", "high"])  # extended thinking budget
    elif kind == "gemini" and (thinking or re.search(r"gemini-(2\.5|[3-9])", name)):
        return api((["off"] if "flash" in name else []) + ["low", "medium", "high"])  # thinkingBudget
    elif kind == "openai":
        if "generativelanguage.googleapis.com" in url and (thinking or re.search(r"gemini-(2\.5|[3-9])", name)):
            # Gemini's OpenAI-compatible reasoning_effort ("none" turns thinking off on Flash models)
            return api((["off"] if "flash" in name else []) + ["low", "medium", "high"])
        if "openrouter" in url and thinking:
            return api(["off", "minimal", "low", "medium", "high"])  # OpenRouter reasoning.effort
        if "api.openai.com" in url and re.search(r"(^|/)(o[134]|gpt-5)", name):
            return api((["minimal"] if "gpt-5" in name else []) + ["low", "medium", "high"])  # reasoning_effort
        if "gpt-oss" in name and thinking is not False:
            return api(["low", "medium", "high"])
    if thinking is False:
        return {"efforts": [], "effort_via": None}
    return {"efforts": list(PROMPT_EFFORTS), "effort_via": "prompt"}


def with_effort_prompt(messages: list[dict], effort: str, model_id: str) -> list[dict]:
    """Prompt-based effort: one line appended to the system prompt (qwen3-style models also get their switch)."""
    line = EFFORT_PROMPT.get(effort)
    if not line:
        return messages
    if re.search(r"qwen3|qwq", model_id, re.I) and effort in ("low", "high"):
        line += " /no_think" if effort == "low" else " /think"
    out = list(messages)
    if out and out[0]["role"] == "system":
        out[0] = {**out[0], "content": out[0]["content"] + "\n\n" + line}
    else:
        out.insert(0, {"role": "system", "content": line})
    return out


def profile(model_id: str) -> dict:
    return (load_settings().get("model_profiles") or {}).get(model_id) or {}


def with_profile(model_id: str, m: dict, profiles: dict | None = None) -> dict:
    """Model info (list entry or context info) with the profile's capability overrides applied."""
    p = (profiles.get(model_id) or {}) if profiles is not None else profile(model_id)
    m = {**m, "can_think": m.get("can_think", m.get("thinking"))}  # the API's own answer, before any override
    if not p:
        return m
    for k in ("vision", "thinking"):
        if p.get(k) in ("on", "off"):
            m[k] = p[k] == "on"
    if p.get("tools") in ("native", "tags"):
        m["native_tools"] = p["tools"] == "native"
    m["profile"] = p
    return m


def profile_opts(model_id: str, opts: dict) -> dict:
    """Request options from the profile; options set by the caller win."""
    p = profile(model_id)
    if p.get("temperature") is not None:
        opts.setdefault("temperature", p["temperature"])
    from . import families
    for k, v in families.sampling(split_model_id(model_id)[1]).items():
        # the model card's sampling when nothing else set one (provider rules still drop what a server rejects)
        opts.setdefault(k, v)
    if p.get("max_tokens"):
        opts.setdefault("max_tokens", p["max_tokens"])
    if p.get("thinking") in ("on", "off"):
        opts.setdefault("think", p["thinking"] == "on")
    if p.get("streaming") in ("on", "off"):
        opts.setdefault("stream", p["streaming"] == "on")
    if p.get("effort"):
        opts.setdefault("effort", p["effort"])
    return opts


def usable(name: str, cfg: dict) -> bool:
    return bool(cfg.get("enabled")) and (bool(cfg.get("local")) or bool(get_secret(f"{name}_api_key")))


HEARTBEAT = 2.0  # seconds of silence after which an 'idle' event is emitted
# A cloud API streams continuously (also while it writes a tool call); minutes of silence mean a stalled request:
# give up and let the task retry (or switch model) instead of waiting for the 30-minute read timeout.
# Local servers stay silent while they read a long prompt on CPU, so they have no such limit.
CLOUD_SILENCE = float(os.environ.get("AIIQ_CLOUD_SILENCE") or 300)  # default of Settings > Agent > stream_timeout


def silence_limits(local: bool) -> tuple[float | None, float | None]:
    """(first token, between chunks) silence limits in seconds from Settings > Agent; None = no limit."""
    a = load_settings().get("agent") or {}
    if local:
        v = float(a.get("local_stream_timeout") or 0)
        return (v or None), (v or None)
    mid = float(a.get("stream_timeout") or CLOUD_SILENCE)
    first = float(a.get("first_token_timeout") or max(mid, 300))
    return max(30.0, first), max(30.0, mid)


def stall_floor() -> float:
    """Settings > Agent > stall_floor: the lowest stall limit of a steady stream that suddenly stops (default 90 s)."""
    try:
        return max(30.0, float((load_settings().get("agent") or {}).get("stall_floor") or 90))
    except (TypeError, ValueError):
        return 90.0


async def _heartbeat(gen: AsyncIterator[dict], name: str, max_silence: float | None = None,
                     first_silence: float | None = None, adaptive: bool = False) -> AsyncIterator[dict]:
    """Pass provider events through, adding {'type': 'idle', 'seconds'} while the provider is silent.
    Local servers stream nothing while a model writes a native tool call (a whole file can take minutes), so the
    UI shows live progress and cancellation still works. Network failures become ProviderErrors.
    first_silence: the limit before the first event (the provider reads the prompt first), max_silence after it."""
    it = gen.__aiter__()
    pending: asyncio.Future | None = None
    last_data = time.monotonic()  # the last real content (text, thinking, tool-call parts, usage)
    started = False
    chunks, max_gap = 0, 0.0
    last_kind = None  # type of the latest event (text, thinking, tool_call_progress...)
    last_ping = 0.0  # the latest SSE keep-alive: the server still holds this request open
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT)
            if done and pending.exception() is None and (pending.result() or {}).get("type") == "ping":
                # A keep-alive (SSE comment) keeps the connection open but carries nothing: it must not reset the
                # silence clock, or a provider that pings while it writes a tool call never hits the stall limit.
                pending, done = None, set()
                last_ping = time.monotonic()
            if not done:
                idle = time.monotonic() - last_data
                limit = max_silence if started else (first_silence or max_silence)
                paced = False
                # Only while a tool call's arguments were streaming (a big file arriving chunk after chunk): after
                # reasoning or visible text the model may be composing a call the provider sends whole (EVREN), and
                # that normal silence was cut as a stall at 46-56 s.
                if adaptive and started and limit and chunks >= 30 and last_kind == "tool_call_progress":
                    # A steady cloud stream (a big file arriving chunk after chunk) that suddenly stops has stalled:
                    # waiting the full setting (300 s) after 10K characters made a fast model look frozen. The limit
                    # follows this stream's own pace: 10 x its longest gap so far, at least 45 s.
                    # Not after reasoning: a provider that sends a tool call only when it is complete (EVREN) is
                    # silent between the last thought and the call, and that silence was cut as a stall at 46 s.
                    # (EVREN sends file arguments in batches 5-12 s apart, more under load: at least 90 s.)
                    floor = stall_floor()
                    paced = max(floor, max_gap * 10) < limit
                    limit = min(limit, max(floor, max_gap * 10))
                if limit and idle >= limit:
                    # Mid-answer it is a stalled stream (what was written is kept and continued), not a busy provider
                    raise ProviderError("stalled" if started else "timeout", f"{name}: no data for {int(idle)} s "
                                        f"({'stalled mid-answer' if started else 'no first token'}; limit {int(limit)} s"
                                        + (", from this stream's own pace)" if paced else " in Settings > Agent)"))
                yield {"type": "idle", "seconds": int(idle),
                       "keepalive": int(time.monotonic() - last_ping) if last_ping else None}
                continue
            fut, pending = pending, None
            now = time.monotonic()
            if started:
                chunks += 1
                max_gap = max(max_gap, now - last_data)
            last_data = now
            started = True
            try:
                evt = fut.result()
            except StopAsyncIteration:
                return
            except httpx.TimeoutException as e:
                raise ProviderError("timeout", f"{name}: no response in time ({type(e).__name__})")
            except httpx.HTTPError as e:
                raise ProviderError("unavailable", f"{name}: connection lost ({type(e).__name__}: {e})")
            if isinstance(evt, dict):
                last_kind = evt.get("type")
            yield evt
    finally:
        if pending is not None:
            pending.cancel()
        try:
            await gen.aclose()
        except Exception:
            pass


class _Slots:
    """Requests in flight to one cloud provider. Providers limit parallel requests per key (evren answers a second
    one with HTTP 503 "model is busy"); the app itself sends several at once (title, summary, vision, team members,
    a second chat), so they wait here for a free slot instead of failing. After a busy/rate-limit answer the
    provider gets one request at a time for a while (adaptive), then the normal limit again."""

    def __init__(self, limit: int):
        self.limit, self.busy, self.low_until = max(1, limit), 0, 0.0
        self.cond = asyncio.Condition()

    def cap(self) -> int:
        return 1 if time.monotonic() < self.low_until else self.limit


_SLOTS: dict[str, _Slots] = {}
DEFAULT_CONCURRENCY = 3  # per cloud provider; Settings > provider "concurrency" overrides it
SERIAL_AFTER_BUSY = 300  # seconds of one-at-a-time after a busy / rate-limit answer


async def _take_slot(pname: str, cfg: dict, cancel: asyncio.Event | None) -> _Slots | None:
    if cfg.get("local"):
        return None  # local servers queue by themselves
    s = _SLOTS.get(pname)
    limit = max(1, int(cfg.get("concurrency") or DEFAULT_CONCURRENCY))
    if s is None:
        s = _SLOTS[pname] = _Slots(limit)
    s.limit = limit  # Settings > provider "parallel requests" applies at once (it was read only on first use)
    async with s.cond:
        while s.busy >= s.cap():
            if cancel and cancel.is_set():
                raise asyncio.CancelledError
            try:
                await asyncio.wait_for(s.cond.wait(), 1.0)
            except asyncio.TimeoutError:
                pass
        s.busy += 1
    return s


async def _free_slot(s: _Slots | None) -> None:
    if s is None:
        return
    async with s.cond:
        s.busy = max(0, s.busy - 1)
        s.cond.notify_all()


_MAIN_ACTIVE: dict[str, int] = {}  # provider -> task requests streaming now (side jobs wait for 0)


def provider_busy(pname: str) -> None:
    """A busy / rate-limit answer: one request at a time to this provider for a while."""
    if s := _SLOTS.get(pname):
        s.low_until = time.monotonic() + SERIAL_AFTER_BUSY


async def stream_chat(model_id: str, messages: list[dict], opts: dict | None = None,
                      cancel: asyncio.Event | None = None,
                      on_fallback: Callable[[str], None] | None = None) -> AsyncIterator[dict]:
    caller = dict(opts or {})  # without this model's profile: a fallback model applies its own
    # lane "side": a background job (chat title) that must never overlap a task's own request on that provider.
    lane = caller.pop("lane", "main")
    retired_retry = caller.pop("_retired_retry", False)  # already the successor of a retired model: no second hop
    opts = dict(caller)
    pname, model = split_model_id(model_id)
    if "num_ctx" not in opts and (n := load_settings()["context"]["num_ctx"].get(model_id)):
        opts["num_ctx"] = n
    profile_opts(model_id, opts)
    if effort := opts.pop("effort", None):
        spec = await context_info(model_id)  # cached
        if effort not in (spec.get("efforts") or []):
            pass  # a level the model does not support (e.g. after switching models) is ignored
        elif spec.get("effort_via") == "api":
            opts["effort"] = effort
            if effort == "off":
                opts["think"] = False
        elif effort in EFFORT_PROMPT:  # no API control: say it in the system prompt
            messages = with_effort_prompt(messages, effort, model_id)
    hide_thinking = opts.get("think") is False  # profile: thinking off (also hides it if the API still sends some)
    prov = None
    tokens = {"input": 0, "output": 0}
    try:
        prov = get_provider(pname)
        if prov.cfg.get("local") and isinstance(prov, OllamaProvider) and "num_ctx" not in opts:
            # Every request to a local model carries the same window. A side call without one (a summary, a language
            # fix, a title, a probe) made Ollama fall back to its own default size: the model was reloaded for that
            # call and again for the next task turn - twice tens of seconds on a CPU, with a RAM spike each time.
            opts["num_ctx"] = (await context_info(model_id))["current"]
        # A provider with a known requests-per-minute cap (NVIDIA NIM free: 40) is paced instead of answering 429s.
        # free_rpm: a cap only the provider's free models have (OpenRouter ":free": 20 per minute).
        free = model.endswith(":free") and int(prov.cfg.get("free_rpm") or 0)
        if rpm := int(free or prov.cfg.get("rpm") or 0):
            await usage.pace(f"{pname}:free" if free else pname, rpm, cancel)
        first, mid = silence_limits(bool(prov.cfg.get("local")))
        if lane == "side":
            for _ in range(180):  # waits while a task streams on this provider (90 s at most)
                if not _MAIN_ACTIVE.get(pname):
                    break
                await asyncio.sleep(0.5)
        slot = await _take_slot(pname, prov.cfg, cancel)
        if lane != "side":
            _MAIN_ACTIVE[pname] = _MAIN_ACTIVE.get(pname, 0) + 1
        try:
            async for evt in _heartbeat(prov.stream(model, messages, opts), pname, mid, first,
                                         adaptive=not prov.cfg.get("local")):
                if cancel and cancel.is_set():
                    raise asyncio.CancelledError
                if evt["type"] == "thinking" and hide_thinking:
                    continue
                if evt["type"] == "usage":
                    tokens["input"] = evt.get("input") or tokens["input"]
                    tokens["output"] = evt.get("output") or tokens["output"]
                yield evt
        finally:
            await _free_slot(slot)
            if lane != "side":
                _MAIN_ACTIVE[pname] = max(0, _MAIN_ACTIVE.get(pname, 1) - 1)
        usage.record(model_id, tokens["input"], tokens["output"])  # quota windows (5 h / week)
    except ProviderError as e:
        if e.code == "model_retired" and prov is not None and not retired_retry:
            # The provider retired this model for new users and usually names the successor ("Please update your
            # code to use models/gemini-3.8-flash"): it is hidden from the lists, the request goes to the successor,
            # and an active-model choice of the old name is moved to it - the user never sees a dead model again.
            from .providers import mark_retired
            m = re.search(r"\buse\s+(?:models/)?([A-Za-z0-9][\w.\-]+[\w])", str(e))
            successor = m.group(1) if m and m.group(1) != model.removeprefix("models/") else ""
            mark_retired(prov.cfg, model, successor)
            invalidate_models(pname)
            if successor:
                new_id = f"{pname}:{successor}"
                if load_settings().get("active_model") == model_id:
                    save_settings({"active_model": new_id})
                if on_fallback:
                    on_fallback(new_id)
                async for evt in stream_chat(new_id, messages, {**caller, "lane": lane, "_retired_retry": True}, cancel,
                                             on_fallback):
                    yield evt
                return
        if (e.code == "bad_request" and re.search(r"reasoning is mandatory|cannot be disabled|thinking.*(required|cannot)", str(e), re.I)
                and (caller.get("think") is False or caller.get("effort") == "off" or caller.get("no_think"))):
            # A model whose reasoning cannot be switched off (OpenRouter: "Reasoning is mandatory for this endpoint"):
            # the same request again with its reasoning left on, instead of a failed turn.
            fixed = {k: v for k, v in caller.items() if k not in ("think", "no_think")}
            if fixed.get("effort") == "off":
                fixed.pop("effort")
            async for evt in stream_chat(model_id, messages, {**fixed, "lane": lane}, cancel, on_fallback):
                yield evt
            return
        if e.code in ("overloaded", "rate_limit"):
            provider_busy(pname)
        usage.fail(model_id, e.code, str(e), usage.reset_hint(prov.base_url) if prov else None)
        settings = load_settings()
        fb = settings.get("fallback_model")
        # The fallback model (Settings > Models) answers when the chosen provider cannot be reached or is
        # overloaded; quota, key and request errors are the user's to fix and are reported instead.
        if e.code in ("unavailable", "overloaded", "bad_gateway", "server") and settings.get("cloud_fallback") \
                and fb and fb != model_id:
            if on_fallback:
                on_fallback(fb)
            async for evt in stream_chat(fb, messages, caller, cancel):
                yield evt
            return
        raise


async def ping(model_id: str, timeout: float = 20.0) -> dict:
    """Liveness probe while a task's stream is silent: a separate, tiny request (1 token, no reasoning) to the same
    model on a NEW connection. It tells the cases apart that silence alone cannot:
      alive - the provider answers a new request at once (also with 429 / quota: it is there): our stream is stuck
              (a dropped connection a proxy / NAT never closed, or a generation the server lost);
      slow  - no answer within `timeout`: the provider is overloaded, the model may still be working - keep waiting;
      sick  - it answers with a server error (5xx): our stream will not come back either;
      down  - it cannot be reached (connection / DNS): this computer or the provider is offline.
    Returns {"state": ..., "ms": int, "error": str}. Bypasses the provider's slot limit on purpose (it must not wait
    for the very stream it checks)."""
    pname, model = split_model_id(model_id)
    t0 = time.monotonic()
    try:
        prov = get_provider(pname)
    except Exception as e:  # noqa: BLE001
        return {"state": "down", "ms": 0, "error": str(e)}

    async def one() -> None:
        async for evt in prov.stream(model, [{"role": "user", "content": "ping"}],
                                     {"max_tokens": 1, "think": False, "no_think": True, "effort": "off"}):
            if evt.get("type") in ("text", "thinking", "usage", "tool_call", "tool_call_start", "done"):
                return
    try:
        await asyncio.wait_for(one(), timeout)
        state, err = "alive", ""
    except asyncio.TimeoutError:
        state, err = "slow", f"no answer to a 1-token request in {int(timeout)} s"
    except ProviderError as e:
        err = str(e)
        state = ("alive" if e.code in ("rate_limit", "quota", "payment", "auth", "plan_required", "bad_request",
                                      "context", "invalid")
                 else "sick" if e.code in ("server", "bad_gateway", "overloaded")
                 else "slow" if e.code == "timeout" else "down")
    except httpx.TimeoutException as e:
        state, err = "slow", type(e).__name__
    except httpx.HTTPError as e:
        state, err = "down", f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 - a probe never breaks the task
        state, err = "slow", f"{type(e).__name__}: {e}"
    return {"state": state, "ms": int((time.monotonic() - t0) * 1000), "error": err[:300]}


async def complete(model_id: str, messages: list[dict], opts: dict | None = None,
                   cancel: asyncio.Event | None = None) -> str:
    """One-shot text (summaries, language fixes, delegated answers): reasoning the model wrote inline (<think>,
    harmony analysis channel, a lone </think>) is removed, so it never ends up in a summary or an answer."""
    from ..agents.stream_parser import StreamSplitter
    raw = "".join([e["text"] async for e in stream_chat(model_id, messages, opts, cancel) if e["type"] == "text"])
    sp = StreamSplitter()
    out: list[str] = []
    for kind, text in sp.feed(raw) + sp.flush():
        if kind == "retract":
            out.clear()
        elif kind == "visible":
            out.append(text)
    return "".join(out)


_MODEL_CACHE: dict[str, tuple[float, dict]] = {}
MODEL_CACHE_TTL = 300


def invalidate_models(provider: str | None = None) -> None:
    """Called whenever a provider's URL, key or switch changes, so its model list is re-queried at once."""
    if provider:
        _MODEL_CACHE.pop(provider, None)
        for k in [k for k in _INFO_CACHE if k.startswith(provider + ":")]:
            _INFO_CACHE.pop(k, None)
    else:
        _MODEL_CACHE.clear()
        _INFO_CACHE.clear()


async def models_for(name: str, refresh: bool = False) -> dict:
    cfg = load_settings()["providers"].get(name) or {}
    cached = _MODEL_CACHE.get(name)
    if cached and not refresh and time.monotonic() - cached[0] < MODEL_CACHE_TTL:
        return _profiled(name, cached[1])
    out = {"name": cfg.get("name", name), "local": bool(cfg.get("local")), "models": [], "error": None, "code": None}
    try:
        out["models"] = await asyncio.wait_for(get_provider(name).list_models(), 12)
    except ProviderError as e:
        out["error"], out["code"] = str(e), e.code
    except asyncio.TimeoutError:
        out["error"], out["code"] = "timeout", "timeout"
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:  # unreachable, or an answer in another shape
        out["error"], out["code"] = f"{name}: {type(e).__name__}: {e}", "unavailable"
    for m in out["models"]:
        m["context"] = m.get("context") or fallback_context(m["id"]) if not out["local"] else m.get("context")
    if not out["error"]:  # failures are not cached: the next request retries immediately
        _MODEL_CACHE[name] = (time.monotonic(), out)
    return _profiled(name, out)


def _profiled(name: str, out: dict) -> dict:
    """A copy of a provider's model list with the user's model profiles and effort levels (the cache stays raw)."""
    settings = load_settings()  # read once for the whole list (OpenRouter lists hundreds of models)
    profiles = settings.get("model_profiles") or {}
    models = []
    for m in out["models"]:
        mid = f"{name}:{m['id']}"
        raw = m
        m = with_profile(mid, m, profiles)
        # Effort levels follow what the API offers, not the user's on/off choice (the buttons must not vanish).
        models.append({**m, **effort_spec(mid, raw, settings)})
    return {**out, "models": models}


def usable_providers() -> dict[str, dict]:
    return {k: {"name": v.get("name", k), "local": bool(v.get("local"))}
            for k, v in load_settings()["providers"].items() if usable(k, v)}


async def list_all_models() -> dict[str, dict]:
    providers = usable_providers()
    results = await asyncio.gather(*(models_for(k) for k in providers), return_exceptions=True)
    # One provider that fails in an unexpected way no longer takes the whole model list down with it.
    return {k: (r if isinstance(r, dict) else {"name": providers[k]["name"], "local": providers[k]["local"], "models": [],
                                               "error": f"{type(r).__name__}: {r}", "code": "error"})
            for k, r in zip(providers, results, strict=True)}


def fallback_context(model: str) -> int:
    return next((n for pat, n in CONTEXT_FALLBACK if re.search(pat, model, re.I)), DEFAULT_CONTEXT)


_INFO_REFRESH: set[str] = set()
_TASKS: set[asyncio.Task] = set()


async def _refresh_info(model_id: str) -> dict:
    pname, model = split_model_id(model_id)
    try:
        info = await asyncio.wait_for(get_provider(pname).model_info(model), 10)
        _INFO_CACHE[model_id] = (time.monotonic(), info)
        return info
    except Exception:
        return {"context": None}
    finally:
        _INFO_REFRESH.discard(model_id)


async def warm_info() -> None:
    """At start: the active model's and the pool models' details, fetched before the first task needs them."""
    s = load_settings()
    models = {s.get("active_model") or ""} | {e.get("model", "") for e in (s.get("multi_model") or {}).get("pool") or []}
    await asyncio.gather(*(_refresh_info(m) for m in models if ":" in m), return_exceptions=True)


async def context_info(model_id: str) -> dict:
    """max = what the model/API allows; current = the window actually used for requests."""
    pname, model = split_model_id(model_id)
    settings = load_settings()
    cached = _INFO_CACHE.get(model_id)
    if cached:
        # An older answer is still used at once and refreshed in the background: a task never waits for this
        # network call (it cost 0.3-0.5 s at the start of a task after every restart or every 30 minutes).
        info = cached[1]
        if time.monotonic() - cached[0] >= 1800 and model_id not in _INFO_REFRESH:
            _INFO_REFRESH.add(model_id)
            task = asyncio.create_task(_refresh_info(model_id))
            _TASKS.add(task)  # a reference until it ends (an unreferenced task can be collected mid-flight)
            task.add_done_callback(_TASKS.discard)
    else:
        info = await _refresh_info(model_id)
    p_cfg = settings["providers"].get(pname, {})
    max_ctx = info.get("context") or (p_cfg.get("context") or fallback_context(model))
    local = bool(p_cfg.get("local"))
    override = settings["context"]["num_ctx"].get(model_id)
    current = min(override or info.get("default_ctx") or (LOCAL_DEFAULT_CTX if local else max_ctx), max_ctx)
    ram = None
    if local:
        # RAM guard: the window (and any automatic growth) stays within what the free memory can hold, so a big
        # local model never pushes the computer into swapping or a crash.
        from . import memguard
        ram = await asyncio.to_thread(memguard.safe_window, get_provider(pname).base_url, model, info.get("kv_per_token"))
        if ram and not ram["short"]:
            binding = current > ram["max"]
            max_ctx = max(2048, min(max_ctx, ram["max"]))
            current = min(current, max_ctx)
            # The same window as the last request while it still fits: free RAM moving by a few megabytes must not
            # change num_ctx, because every other size makes the server reload the whole model.
            current = memguard.steady(model, current, ram["max"], binding)
            max_ctx = max(max_ctx, current)
        elif ram and memguard.load_check() == "warn":
            # The weights do not fit and the user chose "load with a warning": at least the KV cache stays small.
            max_ctx = min(max_ctx, 4096)
            current = min(current, max_ctx)
    if local:
        from . import memguard
        if (cap := memguard.cap(model)) and cap < max_ctx:
            # Memory ran low and the guard made this model's window smaller (the model stays loaded): nothing grows
            # past it until memory is comfortable again.
            max_ctx, current = cap, min(current, cap)
    out = with_profile(model_id, {
        "model": model_id, "max": max_ctx, "current": current, "local": local, "adjustable": local, "ram": ram,
        "threshold": settings["context"]["compress_threshold"], "tools": info.get("tools"),
        "vision": info.get("vision"), "thinking": info.get("thinking"), "native_tools": native_tools(model_id, info),
        "family": __import__("app.llm.families", fromlist=["family"]).family(model)[0]})
    return {**out, **effort_spec(model_id, {**out, "thinking": info.get("thinking")})}


def native_tools(model_id: str, info: dict) -> bool:
    """Use the provider's function calling unless the model is known not to support it."""
    pname, _ = split_model_id(model_id)
    try:
        prov = get_provider(pname)
    except ProviderError:
        return False
    forced = profile(model_id).get("tools")
    if forced == "tags":
        return False
    from . import families
    if forced != "native" and families.native_ok(split_model_id(model_id)[1]) is False:
        # The model family has no reliable function calling (R1, Gemma, small Llama, Phi) on any provider: the
        # text protocol, which every model can write and which streams live (model profile "native" overrides)
        return False
    if forced != "native" and is_local(model_id):
        # Local servers (Ollama) send a native tool call only when the whole call is generated: a page written by a
        # CPU model was 5-10 minutes of silence (nothing visible, everything lost on a drop). The text protocol streams
        # the file as it is written (live progress, resumable). Model profile "native" turns function calling back on.
        return False
    if forced != "native" and not streams_tool_args(model_id):
        # One rule for every provider and model, nothing learned per model: native function calling only where the
        # provider is known to stream a call's arguments live (EVREN). Anywhere else a long file written as a native
        # call is minutes of silence ("preparing... the provider sends it when complete"), invisible to the user and
        # lost whole on any break. The text protocol streams every file as it is written and can be continued.
        return False
    return (prov.native_tools and (forced == "native" or info.get("tools") is not False) and model_id not in _NO_NATIVE_TOOLS
            and f"{pname}:*" not in _NO_NATIVE_TOOLS)


def disable_native_tools(model_id: str, persist: bool = False) -> None:
    """persist: remembered across restarts (data/stream_tools.json) - for providers that send a native tool call
    only when it is complete, so every later task starts with the streamed text protocol instead of first losing
    a minute (or a whole file) to a silent call."""
    if persist and streams_tool_args(model_id):
        persist = False  # its provider streams tool calls: a silence was a pause, not a call sent only at the end
    _NO_NATIVE_TOOLS.add(model_id)
    if persist:
        # It is the provider's server that holds a tool call back until it is complete, so every model of it does the
        # same: all of them start with the streamed text protocol (NVIDIA: Nemotron Ultra was learned, Super then sat
        # silent for 60 s+ on its first file in the next task).
        _NO_NATIVE_TOOLS.add(f"{model_id.partition(':')[0]}:*")
        try:
            saved = set(json.loads(_STREAM_TOOLS.read_text(encoding="utf-8"))) if _STREAM_TOOLS.exists() else set()
            add = {model_id, f"{model_id.partition(':')[0]}:*"}
            if not add <= saved:
                _STREAM_TOOLS.write_text(json.dumps(sorted(saved | add)), encoding="utf-8")
        except (OSError, ValueError):
            pass


_STREAM_TOOLS = DATA_DIR / "stream_tools.json"
try:
    _NO_NATIVE_TOOLS.update(json.loads(_STREAM_TOOLS.read_text(encoding="utf-8")) if _STREAM_TOOLS.exists() else [])
except (OSError, ValueError):
    pass

# Providers seen streaming native tool-call arguments piece by piece (data/streams_args.json). Their silences are
# pauses on the provider's side (a queue, a preempted request), not a call that is sent only when complete: such a
# silence is never cut as "the provider sends tool calls at the end", and the protocol is never switched for it.
_STREAMS_ARGS_FILE = DATA_DIR / "streams_args.json"
try:
    _STREAMS_ARGS: set[str] = set(json.loads(_STREAMS_ARGS_FILE.read_text(encoding="utf-8"))) \
        if _STREAMS_ARGS_FILE.exists() else set()
except (OSError, ValueError):
    _STREAMS_ARGS = set()
# Measured, not learned: EVREN streams native tool arguments chunk by chunk (2,289 chunks in one file, longest gap
# 2.7 s). Known from the start, so a fresh install (or a cleaned data/ folder) never treats its pauses as "sends tool
# calls only at the end" and never moves its models to the text protocol for that.
_STREAMS_ARGS |= {"evren"}


# A provider that ends every request after a fixed time (NVIDIA's hosted API: ~300 s; a file streaming at 35 tok/s
# stopped at 35-60K characters again and again and the stream then sat silent until the stall cut). Learned from the
# requests that broke off after streaming for a long time: two such breaks close to each other are a limit, not chance.
_CAPS_FILE = DATA_DIR / "request_caps.json"
try:
    _CAPS: dict[str, dict] = json.loads(_CAPS_FILE.read_text(encoding="utf-8")) if _CAPS_FILE.exists() else {}
except (OSError, ValueError):
    _CAPS = {}


def note_request_break(model_id: str, secs: float) -> float | None:
    """A request that streamed for `secs` and then stopped sending. Returns the learned limit when there is one."""
    if secs < 120 or is_local(model_id):
        return request_cap(model_id)
    # Learned per provider (its gateway ends the request, whichever model streams): one rule for all of its models.
    d = _CAPS.setdefault(model_id.partition(":")[0], {"obs": []})
    d["obs"] = (d.get("obs", []) + [round(secs)])[-6:]
    obs = sorted(d["obs"])
    if round_cap := next((r for r in (120, 180, 240, 300, 360, 600, 900) if abs(secs - r) <= r * 0.025), None):
        # Gateways end requests at round numbers (NVIDIA: 300 s, measured directly: 44.6K characters, then silence
        # with the connection left open): a break right at one is that limit at once, not after a second lost file.
        d["cap"] = min(d.get("cap") or round_cap, round_cap)
    for a, b in zip(obs, obs[1:]):
        if b - a <= max(25, a * 0.12):  # two breaks at about the same elapsed time
            d["cap"] = min(d.get("cap") or a, a)
            break
    try:
        _CAPS_FILE.write_text(json.dumps(_CAPS), encoding="utf-8")
    except OSError:
        pass
    return request_cap(model_id)


def request_cap(model_id: str) -> float | None:
    """Seconds after which this model's provider ends a request (learned per provider, shared by all its models)."""
    cap = (_CAPS.get(model_id.partition(":")[0]) or {}).get("cap")
    return float(cap) if cap else None


def streams_tool_args(model_id: str) -> bool:
    """This provider (any of its models: it is the server's tool parser) streams tool-call arguments."""
    return model_id.partition(":")[0] in _STREAMS_ARGS


def mark_streams_tool_args(model_id: str) -> None:
    pname = model_id.partition(":")[0]
    if pname in _STREAMS_ARGS:
        return
    _STREAMS_ARGS.add(pname)
    try:
        _STREAMS_ARGS_FILE.write_text(json.dumps(sorted(_STREAMS_ARGS)), encoding="utf-8")
        # Models of this provider that an earlier pause wrongly moved to the text protocol get native calls back.
        if _STREAM_TOOLS.exists():
            saved = [m for m in json.loads(_STREAM_TOOLS.read_text(encoding="utf-8")) if m.partition(":")[0] != pname]
            _STREAM_TOOLS.write_text(json.dumps(saved), encoding="utf-8")
    except (OSError, ValueError):
        pass


def _lms() -> str | None:
    return shutil.which("lms") or next((str(p) for p in [Path.home() / ".lmstudio" / "bin" / "lms.exe",
                                                         Path.home() / ".lmstudio" / "bin" / "lms"] if p.exists()), None)


async def _run(*argv: str) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                             env={**os.environ, "NO_COLOR": "1"})
    out, _ = await p.communicate()
    return p.returncode or 0, out.decode(errors="replace")


async def _lms_rest_load(prov, body: dict) -> bool:
    """LM Studio 0.4+: POST /api/v1/models/load with load options. False when the endpoint is missing (older app)."""
    import httpx
    root = prov.base_url.rstrip("/").removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5)) as c:
            r = await c.post(f"{root}/api/v1/models/load", json=body, headers=prov.headers())
    except httpx.HTTPError:
        return False
    if r.status_code in (404, 405):
        return False
    if r.status_code >= 400:
        raise ProviderError("load_failed", r.text[:400])
    return True


async def reload_local(model_id: str, num_ctx: int) -> bool:
    """LM Studio fixes the window when a model loads (Ollama takes num_ctx with each request): the memory guard's
    smaller window takes effect by loading the same model again at that size. Only this model is touched; the chat
    and the task go on (the next request waits for the load). False when it could not be done."""
    pname, model = split_model_id(model_id)
    cfg = load_settings()["providers"].get(pname, {})
    if not cfg.get("local"):
        return False
    prov = get_provider(pname)
    if isinstance(prov, OllamaProvider):
        return True  # the next request carries the new num_ctx
    from . import local_runtime
    try:
        rt = local_runtime.clean_lms(cfg.get("runtime") or {})
    except ValueError:
        rt = {}
    import httpx
    root = prov.base_url.rstrip("/").removesuffix("/v1")
    try:  # LM Studio 0.4+ REST: unload this instance, load it again at the new size
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{root}/api/v1/models/unload", json={"instance_id": model}, headers=prov.headers())
        if r.status_code < 400 and await _lms_rest_load(prov, local_runtime.lms_rest_body(model, num_ctx, rt)):
            _forget_ctx(model_id)
            return True
    except (httpx.HTTPError, ProviderError):
        pass
    if lms := _lms():
        await _run(lms, "unload", model)
        code, _out = await _run(lms, "load", model, "--yes", "--context-length", str(num_ctx), *local_runtime.lms_cli_args(rt))
        _forget_ctx(model_id)
        return code == 0
    return False


def _forget_ctx(model_id: str) -> None:
    """The cached window info of a model that was just loaded at another size."""
    _INFO_CACHE.pop(model_id, None)


NO_RAM_WARN = ("{model} needs about {need} GB of RAM for its weights, but only {free} GB is free (of {total} GB, after "
               "the reserve). It is loaded anyway because the memory guard is set to warn only: the computer may slow "
               "down a lot or freeze. The window is kept at 4K.")


async def activate(model_id: str) -> None:
    """Local models: unload every other local model (Ollama + LM Studio) and preload the selected one,
    so VRAM/RAM is not shared between idle models. Progress is published as 'model' events."""
    pname, model = split_model_id(model_id)
    settings = load_settings()
    cfg = settings["providers"].get(pname, {})
    if not cfg.get("local"):
        return
    emit = lambda state, msg="": bus.publish("model", state, {"model": model_id, "message": msg})
    emit("switching")
    info = await context_info(model_id)
    num_ctx = info["current"]
    from . import memguard
    if (ram := info.get("ram") or {}).get("short") and memguard.load_check() == "warn":
        # The user chose "load with a warning" (Settings > Providers > local model memory): say it, then load.
        from ..agents.checks import ui_text
        emit("memory", ui_text(settings.get("language") or "tr", "ai_warn_no_ram", NO_RAM_WARN, model=model,
                               need=ram["weights_gb"], free=ram["free_gb"], total=ram["total_gb"]))
    elif (ram := info.get("ram") or {}).get("short"):
        # The weights alone do not fit in the free RAM. Ollama reads a CPU model fully into memory (mmap off), so
        # loading it anyway pushed the computer into heavy paging and a blue screen (0xBE while a 21.8 GB model
        # loaded with 17.2 GB free). Selecting the model never loads it then; the task start says the same.
        from ..agents.checks import ui_text
        emit("memory", ui_text(
            settings.get("language") or "tr", "ai_err_no_ram", "{model} needs about {need} GB of RAM for its weights "
            "alone, but only {free} GB is free (of {total} GB, with a safety reserve). It was not loaded, to protect "
            "the computer. Close other programs, or pick a smaller local model or a cloud model.", model=model,
            need=ram["weights_gb"], free=ram["free_gb"], total=ram["total_gb"], parallel=ram["parallel"]))
        return
    try:
        for name, c in settings["providers"].items():
            if not (c.get("local") and c.get("enabled")):
                continue
            prov = get_provider(name)
            if isinstance(prov, OllamaProvider):
                try:
                    for running in await prov.running():
                        if not (name == pname and running == model):
                            await prov.unload(running)
                except Exception:
                    pass
            elif (lms := _lms()) and not (name == pname):
                await _run(lms, "unload", "--all")
        prov = get_provider(pname)
        rt = {}
        if not isinstance(prov, OllamaProvider):
            from . import local_runtime
            try:
                rt = local_runtime.clean_lms(cfg.get("runtime") or {})
            except ValueError:
                rt = {}
            body = local_runtime.lms_rest_body(model, num_ctx, rt)
        if isinstance(prov, OllamaProvider):
            await prov.load(model, num_ctx)
        elif body and await _lms_rest_load(prov, body):
            pass  # LM Studio's own REST load took the flash-attention / KV / batch options
        elif lms := _lms():
            await _run(lms, "unload", "--all")
            args = [lms, "load", model, "--yes"] + (["--context-length", str(num_ctx)] if num_ctx else [])
            code, out = await _run(*args, *local_runtime.lms_cli_args(rt))
            if code:
                raise ProviderError("load_failed", out[-400:])
        else:
            emit("ready", "lms_missing")
            return
        emit("ready")
    except Exception as e:
        emit("error", str(e))


# --- multi-model ------------------------------------------------------------------------------------------
# A pool of cloud models the user enabled (Settings > Multi-model). Local models never take part: running a second
# local model next to the first can freeze the computer, so a local model may call cloud models but never another
# local one, and the system is only active when cloud models are in the pool.

CAPS = ("code", "reasoning", "fast", "vision", "long_context", "writing")


def multi_settings() -> dict:
    return load_settings().get("multi_model") or {}


def side_model() -> str:
    """A cloud model for small side jobs (chat titles) while a local model works: the vision model, the fallback
    model or the first pool model the user set up, if it is usable now. Empty when there is none."""
    s = load_settings()
    for mid in [s.get("vision_model"), s.get("fallback_model"), *[e["model"] for e in pool()]]:
        if not mid or ":" not in mid or is_local(mid):
            continue
        pid = mid.partition(":")[0]
        if usable(pid, s["providers"].get(pid) or {}) and availability(mid)[0]:
            return mid
    return ""


def is_local(model_id: str) -> bool:
    cfg = load_settings()["providers"].get(model_id.partition(":")[0]) or {}
    return bool(cfg.get("local"))


def pool() -> list[dict]:
    """Enabled cloud pool entries: {model, tags}."""
    ms = multi_settings()
    if not ms.get("enabled"):
        return []
    providers = load_settings()["providers"]
    out = []
    for e in ms.get("pool") or []:
        mid = e.get("model") if isinstance(e, dict) else e
        if not mid or ":" not in mid:
            continue
        name = mid.partition(":")[0]
        cfg = providers.get(name)
        if cfg and not cfg.get("local") and usable(name, cfg):
            out.append({"model": mid, "tags": list(e.get("tags") or []) if isinstance(e, dict) else []})
    return out


def availability(model_id: str) -> tuple[bool, str]:
    """(usable now, reason) from cooldowns and the user's own 5 h / weekly limits."""
    if cd := usage.cooldown(model_id):
        return False, f"{cd['code']} until {time.strftime('%H:%M', time.localtime(cd['until']))}"
    if win := usage.over_limit(model_id, multi_settings().get("limits") or {}):
        return False, f"{win} limit reached"
    return True, ""


async def pick(need: str | None = None, need_ctx: int = 0, exclude: set[str] | None = None,
               tools: bool = False, avoid: set[str] | None = None) -> tuple[str | None, str]:
    """The most available pool model for a capability: not cooling down, within limits, with room for the
    context, tagged for the capability when possible; ties go to the most headroom left, then pool order.
    Returns (model_id or None, explanation)."""
    exclude = exclude or set()
    limits = multi_settings().get("limits") or {}
    ranked = []
    skipped = []
    for i, e in enumerate(pool()):
        mid = e["model"]
        if mid in exclude:
            continue
        ok, why = availability(mid)
        if not ok:
            skipped.append(f"{mid} ({why})")
            continue
        info = await context_info(mid)
        if need_ctx and info["max"] and need_ctx > info["max"] * 0.9:
            skipped.append(f"{mid} (context {info['max']})")
            continue
        if tools and info.get("tools") is False:
            continue
        if need == "vision" and not (info.get("vision") or "vision" in e["tags"]):
            continue
        match = 0 if not need or need in e["tags"] else 1
        # The provider's own per-minute token cap (reported in its headers, e.g. Groq free: 8000): a request that
        # can never fit is skipped; one that would have to wait for the window ranks after models that are free
        # now. Members of a team also spread over providers (avoid), so they do not queue on one rate limit.
        pcfg = load_settings()["providers"].get(mid.partition(":")[0]) or {}
        tok = (usage.reported(pcfg.get("base_url") or "") or {}).get("tokens") or {}
        if tok.get("limit") and need_ctx and need_ctx > tok["limit"]:
            skipped.append(f"{mid} (per-minute cap {tok['limit']} tokens)")
            continue
        waiting = 1 if (tok.get("remaining") is not None and (tok.get("reset_at") or 0) > time.time()
                        and tok["remaining"] < max(need_ctx, 3000)) else 0
        crowded = 1 if avoid and mid.partition(":")[0] in avoid else 0
        # Proven fast, reliable models first (measured first-token time and failure rate, Settings > Models);
        # with prefer_fast off the pool order decides, as before.
        rel, speed = modelstats.rank_key(mid) if multi_settings().get("prefer_fast", True) else (0, 0)
        ranked.append((waiting, crowded, match, rel, speed, -usage.headroom(mid, limits), i, mid))
    if not ranked:
        return None, "no available model in the pool" + (f": {', '.join(skipped)}" if skipped else "")
    ranked.sort()
    return ranked[0][-1], ""


def agent_model(role: str, main: str) -> str:
    """The model assigned to an agent role, when it may be used next to the main model."""
    ms = multi_settings()
    mid = (ms.get("agents") or {}).get(role) if ms.get("enabled") else None
    if not mid or mid == main:
        return main
    if is_local(mid):  # local models never run next to another model
        return main
    if not any(e["model"] == mid for e in pool()) and not usable(mid.partition(":")[0], load_settings()["providers"].get(mid.partition(":")[0]) or {}):
        return main
    return mid if availability(mid)[0] else main
