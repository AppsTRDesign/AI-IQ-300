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
    return any(h in model_id.lower() for h in VISION_HINT)


def usable(name: str, cfg: dict) -> bool:
    return bool(cfg.get("enabled")) and (bool(cfg.get("local")) or bool(get_secret(f"{name}_api_key")))


HEARTBEAT = 2.0  # seconds of silence after which an 'idle' event is emitted


async def _heartbeat(gen: AsyncIterator[dict], name: str) -> AsyncIterator[dict]:
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
    opts = dict(opts or {})
    pname, model = split_model_id(model_id)
    if "num_ctx" not in opts and (n := load_settings()["context"]["num_ctx"].get(model_id)):
        opts["num_ctx"] = n
    try:
        async for evt in _heartbeat(get_provider(pname).stream(model, messages, opts), pname):
            if cancel and cancel.is_set():
                raise asyncio.CancelledError
            yield evt
    except ProviderError as e:
        settings = load_settings()
        fb = settings.get("fallback_model")
        if e.code == "unavailable" and settings.get("cloud_fallback") and fb and fb != model_id:
            if on_fallback:
                on_fallback(fb)
            async for evt in stream_chat(fb, messages, opts, cancel):
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
        return cached[1]
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
    return out


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
    if cached and time.monotonic() - cached[0] < 300:
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
    return {"model": model_id, "max": max_ctx, "current": current, "local": local, "adjustable": local,
            "threshold": settings["context"]["compress_threshold"], "tools": info.get("tools"),
            "vision": info.get("vision"), "thinking": info.get("thinking"),
            "native_tools": native_tools(model_id, info)}


def native_tools(model_id: str, info: dict) -> bool:
    """Use the provider's function calling unless the model is known not to support it."""
    pname, _ = split_model_id(model_id)
    try:
        prov = get_provider(pname)
    except ProviderError:
        return False
    return prov.native_tools and info.get("tools") is not False and model_id not in _NO_NATIVE_TOOLS


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
