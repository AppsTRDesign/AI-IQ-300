"""Routes 'provider:model' IDs to adapters. No silent cloud fallback: cloud is used only when selected,
or when settings.cloud_fallback is explicitly enabled (and the switch is reported as an event)."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from pathlib import Path
from typing import AsyncIterator, Callable

import httpx

from ..config import get_secret, load_settings
from ..events import bus
from . import usage
from .providers import ADAPTERS, VISION_HINT, Capabilities, OllamaProvider, Provider, ProviderError

# Used only when a provider's API does not report a context window.
CONTEXT_FALLBACK = [
    (r"gemini", 1_048_576), (r"deepseek-v4|glm-5|gpt-4\.1", 1_000_000), (r"claude", 200_000),
    (r"gpt-5", 400_000), (r"grok", 256_000), (r"qwen3\.8|gemma-4|qwen3-vl", 256_000),
    (r"gpt-4o|deepseek|mistral|llama-3|qwen", 128_000), (r"evren-llm-7b", 32_768),
]
DEFAULT_CONTEXT = 32_768
LOCAL_DEFAULT_CTX = 32_768  # local window when neither the user nor the model file sets one
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
    if (v := profile(model_id).get("vision")) in ("on", "off"):
        return v == "on"
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
    if not p:
        return m
    m = dict(m)
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
CLOUD_SILENCE = float(os.environ.get("AIIQ_CLOUD_SILENCE") or 180)


async def _heartbeat(gen: AsyncIterator[dict], name: str, max_silence: float | None = None) -> AsyncIterator[dict]:
    """Pass provider events through, adding {'type': 'idle', 'seconds'} while the provider is silent.
    Local servers stream nothing while a model writes a native tool call (a whole file can take minutes), so the
    UI shows live progress and cancellation still works. Network failures become ProviderErrors."""
    it = gen.__aiter__()
    pending: asyncio.Future | None = None
    idle = 0.0
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT)
            if not done:
                idle += HEARTBEAT
                if max_silence and idle >= max_silence:
                    raise ProviderError("timeout", f"{name}: no data for {int(idle)} s (stalled request)")
                yield {"type": "idle", "seconds": int(idle)}
                continue
            fut, pending, idle = pending, None, 0.0
            try:
                evt = fut.result()
            except StopAsyncIteration:
                return
            except httpx.TimeoutException as e:
                raise ProviderError("timeout", f"{name}: no response in time ({type(e).__name__})")
            except httpx.HTTPError as e:
                raise ProviderError("unavailable", f"{name}: connection lost ({type(e).__name__}: {e})")
            yield evt
    finally:
        if pending is not None:
            pending.cancel()
        try:
            await gen.aclose()
        except Exception:
            pass


async def stream_chat(model_id: str, messages: list[dict], opts: dict | None = None,
                      cancel: asyncio.Event | None = None,
                      on_fallback: Callable[[str], None] | None = None) -> AsyncIterator[dict]:
    caller = dict(opts or {})  # without this model's profile: a fallback model applies its own
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
        async for evt in _heartbeat(prov.stream(model, messages, opts), pname,
                                    None if prov.cfg.get("local") else CLOUD_SILENCE):
            if cancel and cancel.is_set():
                raise asyncio.CancelledError
            if evt["type"] == "thinking" and hide_thinking:
                continue
            if evt["type"] == "usage":
                tokens["input"] = evt.get("input") or tokens["input"]
                tokens["output"] = evt.get("output") or tokens["output"]
            yield evt
        usage.record(model_id, tokens["input"], tokens["output"])  # quota windows (5 h / week)
    except ProviderError as e:
        usage.fail(model_id, e.code, str(e), usage.reset_hint(prov.base_url) if prov else None)
        settings = load_settings()
        fb = settings.get("fallback_model")
        if e.code == "unavailable" and settings.get("cloud_fallback") and fb and fb != model_id:
            if on_fallback:
                on_fallback(fb)
            async for evt in stream_chat(fb, messages, caller, cancel):
                yield evt
            return
        raise


async def complete(model_id: str, messages: list[dict], opts: dict | None = None,
                   cancel: asyncio.Event | None = None) -> str:
    return "".join([e["text"] async for e in stream_chat(model_id, messages, opts, cancel) if e["type"] == "text"])


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
        m = with_profile(mid, m, profiles)
        models.append({**m, **effort_spec(mid, m, settings)})
    return {**out, "models": models}


def usable_providers() -> dict[str, dict]:
    return {k: {"name": v.get("name", k), "local": bool(v.get("local"))}
            for k, v in load_settings()["providers"].items() if usable(k, v)}


async def list_all_models() -> dict[str, dict]:
    providers = usable_providers()
    results = await asyncio.gather(*(models_for(k) for k in providers))
    return dict(zip(providers, results))


def fallback_context(model: str) -> int:
    return next((n for pat, n in CONTEXT_FALLBACK if re.search(pat, model, re.I)), DEFAULT_CONTEXT)


async def context_info(model_id: str) -> dict:
    """max = what the model/API allows; current = the window actually used for requests."""
    pname, model = split_model_id(model_id)
    settings = load_settings()
    cached = _INFO_CACHE.get(model_id)
    if cached and time.monotonic() - cached[0] < 1800:
        info = cached[1]
    else:
        try:
            info = await asyncio.wait_for(get_provider(pname).model_info(model), 10)
            _INFO_CACHE[model_id] = (time.monotonic(), info)
        except Exception:
            info = {"context": None}
    p_cfg = settings["providers"].get(pname, {})
    max_ctx = info.get("context") or (p_cfg.get("context") or fallback_context(model))
    local = bool(p_cfg.get("local"))
    override = settings["context"]["num_ctx"].get(model_id)
    current = min(override or info.get("default_ctx") or (LOCAL_DEFAULT_CTX if local else max_ctx), max_ctx)
    out = with_profile(model_id, {
        "model": model_id, "max": max_ctx, "current": current, "local": local, "adjustable": local,
        "threshold": settings["context"]["compress_threshold"], "tools": info.get("tools"),
        "vision": info.get("vision"), "thinking": info.get("thinking"), "native_tools": native_tools(model_id, info)})
    return {**out, **effort_spec(model_id, out)}


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
    return prov.native_tools and (forced == "native" or info.get("tools") is not False) and model_id not in _NO_NATIVE_TOOLS


def disable_native_tools(model_id: str) -> None:
    _NO_NATIVE_TOOLS.add(model_id)


def _lms() -> str | None:
    return shutil.which("lms") or next((str(p) for p in [Path.home() / ".lmstudio" / "bin" / "lms.exe",
                                                         Path.home() / ".lmstudio" / "bin" / "lms"] if p.exists()), None)


async def _run(*argv: str) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                             env={**os.environ, "NO_COLOR": "1"})
    out, _ = await p.communicate()
    return p.returncode or 0, out.decode(errors="replace")


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
    num_ctx = (await context_info(model_id))["current"]
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
        if isinstance(prov, OllamaProvider):
            await prov.load(model, num_ctx)
        elif lms := _lms():
            await _run(lms, "unload", "--all")
            args = [lms, "load", model, "--yes"] + (["--context-length", str(num_ctx)] if num_ctx else [])
            code, out = await _run(*args)
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
               tools: bool = False) -> tuple[str | None, str]:
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
        ranked.append((match, -usage.headroom(mid, limits), i, mid))
    if not ranked:
        return None, "no available model in the pool" + (f": {', '.join(skipped)}" if skipped else "")
    ranked.sort()
    return ranked[0][3], ""


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
