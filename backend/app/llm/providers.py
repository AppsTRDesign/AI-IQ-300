"""Provider adapters. Each adapter normalizes its wire format into a common stream of events:
{"type": "text"|"thinking", "text"} | {"type": "tool_call", "id", "name", "arguments": dict} |
{"type": "usage", ...} | {"type": "done"}. Errors raise ProviderError.

Internal message format (adapters convert it):
  {"role": "system"|"user"|"assistant", "content": str, "images"?: [b64], "tool_calls"?: [{"id","name","arguments"}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
Tools are passed as opts["tools"] = [{"name", "description", "parameters": JSON schema}].
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from ..config import get_secret

TIMEOUT = httpx.Timeout(connect=10, read=1800, write=60, pool=10)  # long silent tool-call generation (router heartbeat)

_POOL: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None
_METHODS = {"get", "post", "put", "patch", "delete", "request", "stream"}


class _Bound:
    """The shared client with a per-call timeout (each call site keeps its own limit)."""
    def __init__(self, client: httpx.AsyncClient, timeout) -> None:
        self._c, self._t = client, timeout

    def __getattr__(self, name: str):
        fn = getattr(self._c, name)
        return (lambda *a, **k: fn(*a, **{"timeout": self._t, **k})) if name in _METHODS else fn


async def _observe(resp: httpx.Response) -> None:
    """Rate-limit headers of every provider response feed the quota view (llm/usage.py)."""
    from . import usage
    usage.observe(str(resp.request.url), resp.headers)


class pooled:
    """`async with pooled(timeout=...) as c:` like httpx.AsyncClient, but on one shared keep-alive pool:
    every model turn reuses the open HTTPS connection instead of a new TCP + TLS handshake."""
    def __init__(self, timeout=None) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> _Bound:
        global _POOL
        loop = asyncio.get_running_loop()
        if _POOL is None or _POOL[0] is not loop or _POOL[1].is_closed:
            _POOL = (loop, httpx.AsyncClient(limits=httpx.Limits(max_connections=50, max_keepalive_connections=20,
                                                                  keepalive_expiry=60),
                                             event_hooks={"response": [_observe]}))
        return _Bound(_POOL[1], self.timeout)

    async def __aexit__(self, *exc) -> bool:
        return False
CONTEXT_FIELDS = ("context_length", "context_window", "max_context_length", "max_model_len", "max_input_tokens",
                  "inputTokenLimit", "loaded_context_length")
KEEP_ALIVE = "10m"  # resident between turns (no reload), released after 10 idle minutes (RAM back to the system)


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retry_at: float | None = None):
        super().__init__(message)
        self.code = code
        self.retry_at = retry_at  # when the provider said to try again (Retry-After / rate-limit reset)


def _ctx_from(d: dict) -> int | None:
    for k in CONTEXT_FIELDS:
        v = d.get(k) or (d.get("top_provider") or {}).get(k)
        if isinstance(v, int) and v > 0:
            return v
    return None


def _tools_from(d: dict) -> bool | None:
    caps = d.get("capabilities")
    if isinstance(caps, dict) and "tools" in caps:
        return bool(caps["tools"])
    if isinstance(d.get("supported_parameters"), list):
        return "tools" in d["supported_parameters"]
    return None


def _caps_from(d: dict) -> dict:
    """Capabilities as reported by OpenAI-compatible model listings (OpenRouter, EVREN, gateways...)."""
    caps = d.get("capabilities") if isinstance(d.get("capabilities"), dict) else {}
    params = d.get("supported_parameters") if isinstance(d.get("supported_parameters"), list) else None
    mods = (d.get("architecture") or {}).get("input_modalities") or d.get("modalities") or d.get("input_modalities")
    vision = caps.get("vision")
    if vision is None and isinstance(mods, list):
        vision = "image" in mods
    if vision is None and d.get("task"):
        vision = d["task"] == "vision_chat"
    thinking = caps.get("thinking") if "thinking" in caps else (
        any(p in params for p in ("reasoning", "include_reasoning")) if params is not None else None)
    return {"tools": _tools_from(d), "vision": vision, "thinking": thinking}


def _args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {"_raw": raw}
    except (TypeError, json.JSONDecodeError):
        return {"_raw": raw}


@dataclass
class Capabilities:
    streaming: bool = True
    images: bool = False


@dataclass
class Provider:
    name: str
    cfg: dict[str, Any]
    caps: Capabilities = field(default_factory=Capabilities)
    native_tools = False

    @property
    def base_url(self) -> str:
        return (self.cfg.get("base_url") or "").rstrip("/")

    @property
    def local(self) -> bool:
        return bool(self.cfg.get("local"))

    def key(self, required: bool = True) -> str | None:
        k = get_secret(f"{self.name}_api_key")
        if required and not k and not self.local:
            raise ProviderError("missing_credentials", f"{self.name}: API key is not set (Settings > Providers)")
        return k

    def headers(self) -> dict:
        k = self.key(required=not self.local)
        if not k:
            return {}
        h = self.cfg.get("auth_header")
        return {h: k} if h else {"Authorization": f"Bearer {k}"}

    async def list_models(self) -> list[dict]:
        return [{"id": m, "context": None} for m in ([self.cfg["model"]] if self.cfg.get("model") else [])]

    async def model_info(self, model: str) -> dict:
        for m in await self.list_models():
            if m["id"] == model:
                return {k: m.get(k) for k in ("context", "tools", "vision", "thinking")}
        return {"context": None}

    async def test(self) -> dict:
        models = await self.list_models()
        return {"models": len(models)}

    def stream(self, model: str, messages: list[dict], opts: dict) -> AsyncIterator[dict]:
        raise NotImplementedError


async def _sse(resp: httpx.Response) -> AsyncIterator[dict]:
    """Server-sent events as dicts. A malformed or split line (a proxy cut a chunk, a keep-alive comment) is skipped
    instead of ending the whole task with an internal JSON error; a 'data:' payload split over several lines is
    joined until it parses."""
    buf = ""
    async for line in resp.aiter_lines():
        if line.startswith(":"):  # an SSE keep-alive comment: the server is alive (resets the stall timer)
            yield {"_ping": True}
            continue
        if not line.startswith("data:"):
            if buf and line.strip() and not line.startswith((":", "event:", "id:", "retry:")):
                buf += line  # continuation of a payload split by a proxy
            else:
                continue
        else:
            data = line[5:].strip()
            if not data or data == "[DONE]":
                buf = ""
                continue
            buf = data if not buf else buf + data
        try:
            d = json.loads(buf)
        except json.JSONDecodeError:
            if len(buf) > 200_000:  # never grows without bound on garbage
                buf = ""
            continue
        buf = ""
        if isinstance(d, dict):
            yield d


def stream_error(err: Any) -> ProviderError:
    """An error object sent inside a running stream (OpenRouter, EVREN, gateways: overloaded, rate limited,
    upstream timeout). Classified like an HTTP error, so busy/overloaded ones are retried instead of ending the task."""
    text = json.dumps(err, ensure_ascii=False)[:500] if not isinstance(err, str) else err[:500]
    if re.search(r"repeat limit|repetition|degenerat", text, re.I):
        # Ollama stopped a reply that repeated one token ("@@@@..."): the model or its runtime backend produced
        # garbage. Asking the same thing again gives the same garbage; the task loop handles it (see 'degenerate').
        return ProviderError("degenerate", text)
    status = 0
    if isinstance(err, dict):
        c = err.get("code") or err.get("status")
        status = c if isinstance(c, int) else int(c) if isinstance(c, str) and c.isdigit() else 0
    code = classify_error(status or 500, text)
    return ProviderError(code if code != "http" else "server", text)


# Status -> normalized code, following the providers' documented errors (OpenAI, Anthropic, OpenRouter, Gemini,
# Ollama, EVREN). The UI translates codes (err_<code> in languages/*.json); the raw message is kept as detail.
STATUS_CODES = {400: "bad_request", 401: "auth", 402: "payment", 403: "forbidden", 404: "not_found", 408: "timeout",
                413: "too_large", 422: "bad_request", 429: "rate_limit", 500: "server", 502: "bad_gateway",
                503: "overloaded", 504: "timeout", 529: "overloaded"}
# Cloudflare Workers AI error codes (developers.cloudflare.com/workers-ai/platform/errors/), read from the body.
CF_CODES = {3036: "quota", 3040: "overloaded", 5035: "plan_required", 5016: "terms", 3023: "forbidden",
            5018: "forbidden", 3041: "forbidden", 5007: "model_not_found", 3042: "model_not_found", 3006: "too_large",
            3007: "timeout", 3008: "timeout", 3003: "bad_request", 5004: "bad_request", 3039: "bad_request",
            5005: "bad_request", 5019: "bad_request", 10000: "auth"}
BODY_PATTERNS = [  # more specific causes hidden behind generic statuses
    (r"workers paid plan|not available on the workers free plan|requires? (a )?paid plan|upgrade to access|"
     r"paid tier|not available on your plan", "plan_required"),
    (r"terms|şart", "terms"),
    # "No user query found" (Qwen chat templates in Ollama/llama.cpp): the prompt was longer than num_ctx, the
    # server cut the oldest messages (the user's request with them) and the template refused the rest.
    (r"context_length_exceeded|maximum context length|prompt is too long|context window|too many tokens|"
     r"exceeds the context|input is too long|no user query found|truncating input|"
     # Ollama 0.3x / llama.cpp server: "request (9297 tokens) exceeds the available context size (8192 tokens)"
     r"exceeds the available context|available context size|context size has been exceeded|n_ctx", "context_length"),
    (r"insufficient_quota|exceeded your current quota|quota|credit|balance|kredi|RESOURCE_EXHAUSTED|neurons|"
     r"daily free allocation", "quota"),
    (r"does not support tools|tool(s)? (is|are) not supported|tool_choice|function calling", "no_tools"),
    (r"model .*not found|model_not_found|no such model|unknown model|does not exist|no longer available|has been deprecated|decommissioned", "model_not_found"),
    (r"invalid.api.key|incorrect api key|invalid x-api-key|authentication_error|authentication error|authorization failed|unauthorized|geçersiz api", "auth"),
    (r"moderation|flagged|content policy|safety", "moderation"),
    (r"overloaded|capacity|unavailable|no endpoints found|no providers", "overloaded"),
]


def _error_message(body: str) -> str:
    """Pull the human-readable message out of the common JSON error shapes."""
    try:
        d = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body.strip()[:400]
    err = d.get("error", d) if isinstance(d, dict) else d
    if isinstance(err, dict):
        return str(err.get("message") or err.get("detail") or err.get("status") or err)[:400]
    if isinstance(d, dict) and d.get("detail"):
        return str(d["detail"])[:400]
    return str(err)[:400]


def _cf_code(body: str) -> str | None:
    """Cloudflare puts its own numeric code in {"errors": [{"code": ...}]}."""
    try:
        errs = json.loads(body).get("errors") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    return next((CF_CODES[e["code"]] for e in errs if isinstance(e, dict) and e.get("code") in CF_CODES), None)


def classify_error(status: int, body: str) -> str:
    if code := _cf_code(body):
        return code
    code = STATUS_CODES.get(status, "server" if status >= 500 else "http")
    if status in (400, 402, 403, 404, 413, 422, 429, 500, 503):
        for pattern, specific in BODY_PATTERNS:
            if re.search(pattern, body, re.I):
                if specific == "auth" and status not in (400, 401, 403):
                    continue
                return specific
    return code


async def _raise_for(resp: httpx.Response, name: str) -> None:
    if resp.status_code >= 400:
        body = (await resp.aread()).decode(errors="replace")[:2000]
        code = classify_error(resp.status_code, body)
        from . import usage
        when = None
        if code in ("rate_limit", "overloaded", "quota"):
            when = usage.retry_delay(body) or usage.reset_hint(str(resp.request.url))
        raise ProviderError(code, f"{name} · HTTP {resp.status_code}: {_error_message(body)}", when)


def _connect_error(name: str, e: Exception) -> ProviderError:
    return ProviderError("unavailable", f"{name} is unreachable: {e}")


# ---------------------------------------------------------------- Ollama
class OllamaProvider(Provider):
    native_tools = True

    async def list_models(self) -> list[dict]:
        try:
            async with pooled(timeout=8) as c:
                r = await c.get(f"{self.base_url}/api/tags", headers=self.headers())
                await _raise_for(r, self.name)
                models = [{"id": m["name"], "context": None, "size": m.get("size")} for m in r.json().get("models", [])]
        except httpx.HTTPError as e:
            raise _connect_error(self.name, e)
        infos = await asyncio.gather(*(self.model_info(m["id"]) for m in models[:40]), return_exceptions=True)
        for m, info in zip(models, infos):
            if isinstance(info, dict):
                m.update({k: info.get(k) for k in ("context", "default_ctx", "tools", "vision", "thinking")})
        return models

    async def model_info(self, model: str) -> dict:
        try:
            async with pooled(timeout=10) as c:
                r = await c.post(f"{self.base_url}/api/show", json={"model": model}, headers=self.headers())
        except httpx.HTTPError:
            return {"context": None}
        if r.status_code >= 400:
            return {"context": None}
        d = r.json()
        ctx = next((v for k, v in (d.get("model_info") or {}).items() if k.endswith(".context_length")), None)
        m = re.search(r"num_ctx\s+(\d+)", d.get("parameters") or "")
        caps = d.get("capabilities")
        families = (d.get("details") or {}).get("families") or []
        from .memguard import kv_per_token
        return {"context": ctx, "default_ctx": int(m.group(1)) if m else None,
                "kv_per_token": kv_per_token(d.get("model_info") or {}),
                "tools": ("tools" in caps) if isinstance(caps, list) else None,
                "thinking": ("thinking" in caps) if isinstance(caps, list) else None,
                "vision": ("vision" in caps) if isinstance(caps, list) else ("clip" in families or None)}

    async def running(self) -> list[str]:
        async with pooled(timeout=5) as c:
            r = await c.get(f"{self.base_url}/api/ps")
            return [m["name"] for m in r.json().get("models", [])]

    async def unload(self, model: str) -> None:
        async with pooled(timeout=30) as c:
            await c.post(f"{self.base_url}/api/generate", json={"model": model, "keep_alive": 0})

    async def load(self, model: str, num_ctx: int | None) -> None:
        body: dict = {"model": model, "keep_alive": KEEP_ALIVE}
        if num_ctx:
            from .memguard import threads
            body["options"] = {"num_ctx": num_ctx, "num_thread": threads()}
        async with pooled(timeout=httpx.Timeout(600, connect=10)) as c:
            r = await c.post(f"{self.base_url}/api/generate", json=body)
            await _raise_for(r, self.name)

    @staticmethod
    def _messages(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name", "")})
                continue
            msg: dict = {"role": m["role"], "content": m.get("content") or ""}
            if m.get("images"):
                msg["images"] = m["images"]
            if m.get("tool_calls"):
                msg["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in m["tool_calls"]]
            out.append(msg)
        return out

    async def stream(self, model, messages, opts):
        options = {k: v for k, v in opts.items() if k in ("temperature", "num_ctx", "top_p", "repeat_penalty", "repeat_last_n")}
        from .memguard import threads
        options.setdefault("num_thread", threads())  # one core left free: no overheating, the PC stays usable
        if opts.get("max_tokens"):
            options["num_predict"] = opts["max_tokens"]
        body: dict = {"model": model, "messages": self._messages(messages), "stream": opts.get("stream", self.cfg.get("streaming", True)),
                      "options": options, "keep_alive": KEEP_ALIVE}
        if "think" in opts:  # model profile: thinking on / off
            body["think"] = opts["think"]
        if e := opts.get("effort"):  # effort: gpt-oss takes the level, other thinking models on / off
            body["think"] = False if e == "off" else True if e == "on" else e
        if opts.get("tools"):
            body["tools"] = [{"type": "function", "function": t} for t in opts["tools"]]
        try:
            async with pooled(timeout=TIMEOUT) as c, \
                    c.stream("POST", f"{self.base_url}/api/chat", json=body, headers=self.headers()) as r:
                await _raise_for(r, self.name)
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a cut line never ends the task with an internal error
                    if d.get("error"):
                        raise ProviderError(classify_error(400, d["error"]) if "tool" in d["error"] else stream_error(d["error"]).code, d["error"])
                    msg = d.get("message", {})
                    if t := msg.get("thinking"):
                        yield {"type": "thinking", "text": t}
                    if t := msg.get("content"):
                        yield {"type": "text", "text": t}
                    for call in msg.get("tool_calls") or []:
                        fn = call.get("function", {})
                        yield {"type": "tool_call", "id": call.get("id") or uuid.uuid4().hex[:12],
                               "name": fn.get("name", ""), "arguments": _args(fn.get("arguments"))}
                    if d.get("done"):
                        if d.get("done_reason") == "length":
                            # The output limit (num_predict) or the end of the window stopped the model mid-answer:
                            # reported like a cloud provider's finish_reason "length", so the task keeps what was
                            # written and continues it instead of taking a cut answer or a half file as finished.
                            yield {"type": "truncated", "name": None, "chars": 0, "reason": "length"}
                        # prompt_eval_count leaves out the prefix Ollama reused from its cache: "partial" tells the
                        # context meter it is a lower bound, not the prompt's size.
                        yield {"type": "usage", "input": d.get("prompt_eval_count"), "output": d.get("eval_count"),
                               "partial": True}
        except httpx.ConnectError as e:
            raise _connect_error(self.name, e)
        yield {"type": "done"}


# ---------------------------------------------------------------- OpenAI-compatible
class OpenAICompatProvider(Provider):
    """OpenAI and OpenAI-compatible servers (LM Studio, Groq, OpenRouter, EVREN, gateways...)."""
    native_tools = True

    async def list_models(self) -> list[dict]:
        try:
            async with pooled(timeout=15) as c:
                r = await c.get(f"{self.base_url}/models", headers=self.headers())
                await _raise_for(r, self.name)
                data = r.json()
        except httpx.HTTPError as e:
            raise _connect_error(self.name, e)
        items = data.get("data", data if isinstance(data, list) else [])
        out = []
        for m in items:
            if not (isinstance(m, dict) and m.get("id")):
                continue
            if m.get("task") and m["task"] not in ("chat", "vision_chat"):  # EVREN: skip embedding/ocr/tts models
                continue
            out.append({"id": m["id"], "context": _ctx_from(m), **_caps_from(m)})
        return out or await super().list_models()

    def _root(self) -> str:
        return re.sub(r"/v1$", "", self.base_url)

    async def model_info(self, model: str) -> dict:
        if self.local:  # LM Studio native REST exposes max/loaded context
            try:
                async with pooled(timeout=5) as c:
                    r = await c.get(f"{self._root()}/api/v0/models/{model}")
                    if r.status_code < 400:
                        d = r.json()
                        return {"context": d.get("max_context_length"), "default_ctx": d.get("loaded_context_length"),
                                "state": d.get("state")}
            except httpx.HTTPError:
                pass
        return await super().model_info(model)

    @property
    def is_evren(self) -> bool:
        return "evren" in self.name or "ssyz.org.tr" in self.base_url

    async def test(self) -> dict:
        out: dict = {}
        if self.is_evren:  # EVREN: terms must be accepted before models/chat work
            async with pooled(timeout=15) as c:
                r = await c.get(f"{self._root()}/v1/terms/status", headers=self.headers())
                await _raise_for(r, self.name)
                out["terms"] = r.json()
                if not out["terms"].get("accepted"):
                    return {**out, "models": 0}
                q = await c.get(f"{self._root()}/v1/quota", headers=self.headers())
                if q.status_code < 400:
                    out["quota"] = q.json()
        return {**out, **(await super().test())}

    async def terms(self) -> dict:
        async with pooled(timeout=15) as c:
            st = await c.get(f"{self._root()}/v1/terms/status", headers=self.headers())
            await _raise_for(st, self.name)
            tx = await c.get(f"{self._root()}/v1/terms/text", headers=self.headers())
            await _raise_for(tx, self.name)
        return {**st.json(), **tx.json()}

    async def accept_terms(self, version: int) -> dict:
        async with pooled(timeout=15) as c:
            r = await c.post(f"{self._root()}/v1/terms/accept", json={"version": version}, headers=self.headers())
            await _raise_for(r, self.name)
            return r.json()

    @staticmethod
    def _messages(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
                continue
            if m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)},
                     # Gemini: the call's thought signature must come back with it, or the next request fails (400)
                     **({"extra_content": c["extra"]} if c.get("extra") else {})}
                    for c in m["tool_calls"]]})
                continue
            if not m.get("images"):
                out.append({"role": m["role"], "content": m["content"]})
                continue
            parts = [{"type": "text", "text": m["content"]}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for b in m["images"]]
            out.append({"role": m["role"], "content": parts})
        return out

    async def stream(self, model, messages, opts):
        streaming = opts.get("stream", self.cfg.get("streaming", True))
        body: dict = {"model": model, "messages": self._messages(messages), "stream": streaming}
        if "temperature" in opts:
            body["temperature"] = opts["temperature"]
        if opts.get("max_tokens"):
            body["max_tokens"] = opts["max_tokens"]
        if e := opts.get("effort"):  # reasoning effort: OpenRouter's reasoning object, else OpenAI's field
            if "openrouter" in self.base_url:
                body["reasoning"] = {"enabled": False} if e == "off" else {"effort": e}
            elif e not in ("off", "on"):
                body["reasoning_effort"] = e
        elif "think" in opts:  # model profile: OpenRouter's reasoning switch, else the OpenAI reasoning_effort field
            if "openrouter" in self.base_url:
                body["reasoning"] = {"enabled": opts["think"]}
            elif opts["think"]:
                body["reasoning_effort"] = "medium"
        if opts.get("tools"):
            body["tools"] = [{"type": "function", "function": t} for t in opts["tools"]]
        if streaming:
            body["stream_options"] = {"include_usage": True}
        url = f"{self.base_url}/chat/completions"
        try:
            async with pooled(timeout=TIMEOUT) as c:
                if not streaming:
                    r = await c.post(url, json=body, headers=self.headers())
                    await _raise_for(r, self.name)
                    d = r.json()
                    for ch in d.get("choices", []):
                        msg = ch.get("message") or {}
                        if t := msg.get("reasoning_content") or msg.get("reasoning"):
                            yield {"type": "thinking", "text": t}
                        if t := msg.get("content"):
                            yield {"type": "text", "text": t}
                        for call in msg.get("tool_calls") or []:
                            fn = call.get("function", {})
                            yield {"type": "tool_call", "id": call.get("id") or uuid.uuid4().hex[:12],
                                   "name": fn.get("name", ""), "arguments": _args(fn.get("arguments")),
                                   **({"extra": call["extra_content"]} if call.get("extra_content") else {})}
                    if u := d.get("usage"):
                        yield {"type": "usage", "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                               "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens")}
                else:
                    calls: dict[int, dict] = {}
                    last_usage = None
                    finish = None
                    async with c.stream("POST", url, json=body, headers=self.headers()) as r:
                        await _raise_for(r, self.name)
                        async for d in _sse(r):
                            if d.get("_ping"):
                                yield {"type": "ping"}
                                continue
                            if d.get("error"):
                                raise stream_error(d["error"])
                            for ch in d.get("choices") or []:
                                finish = ch.get("finish_reason") or finish
                                if ch.get("error"):
                                    raise stream_error(ch["error"])
                                delta = ch.get("delta") or {}
                                if t := delta.get("reasoning_content") or delta.get("reasoning"):
                                    yield {"type": "thinking", "text": t}
                                if t := delta.get("content"):
                                    yield {"type": "text", "text": t}
                                for tc in delta.get("tool_calls") or []:  # arguments arrive in fragments
                                    idx = tc.get("index", len(calls))
                                    new = idx not in calls
                                    slot = calls.setdefault(idx, {"id": None, "name": "", "args": "", "extra": None})
                                    slot["id"] = tc.get("id") or slot["id"]
                                    slot["extra"] = tc.get("extra_content") or slot["extra"]
                                    fn = tc.get("function") or {}
                                    slot["name"] += fn.get("name") or ""
                                    slot["args"] += fn.get("arguments") or ""
                                    yield {"type": "tool_call_start" if new else "tool_call_progress",
                                           "name": slot["name"], "chars": len(slot["args"]), "index": idx,
                                           "delta": fn.get("arguments") or ""}
                            if u := d.get("usage"):
                                # Some providers (Cloudflare) put a per-chunk usage on every chunk (prompt 0,
                                # 1-2 output tokens): only the last one is the real total, sent once at the end.
                                last_usage = u
                    if last_usage:
                        u = last_usage
                        yield {"type": "usage", "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                               "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens")}
                    for slot in calls.values():
                        args = _args(slot["args"])
                        if "_raw" in args and slot["args"].strip():
                            # The arguments stop mid-JSON: the output limit cut the call (finish_reason "length") or
                            # the stream ended early. Running it would write a broken file: report it instead.
                            yield {"type": "truncated", "name": slot["name"], "chars": len(slot["args"]),
                                   "reason": finish or "cut"}
                            continue
                        yield {"type": "tool_call", "id": slot["id"] or uuid.uuid4().hex[:12], "name": slot["name"],
                               "arguments": args, **({"extra": slot["extra"]} if slot["extra"] else {})}
                    if finish == "length" and not calls:
                        yield {"type": "truncated", "name": None, "chars": 0, "reason": "length"}
        except httpx.ConnectError as e:
            raise _connect_error(self.name, e)
        yield {"type": "done"}


# ---------------------------------------------------------------- Anthropic
class AnthropicProvider(Provider):
    native_tools = True

    @property
    def root(self) -> str:
        return re.sub(r"/v1$", "", self.base_url)

    def headers(self) -> dict:
        return {"x-api-key": self.key(), "anthropic-version": "2023-06-01"}

    async def list_models(self) -> list[dict]:
        try:
            async with pooled(timeout=10) as c:
                r = await c.get(f"{self.root}/v1/models?limit=100", headers=self.headers())
                await _raise_for(r, self.name)
                return [{"id": m["id"], "context": _ctx_from(m), "tools": True, "vision": True,
                         "thinking": bool(re.search(r"claude-(3-7|sonnet-4|opus-4|haiku-4|[4-9])", m["id"])) or None}
                        for m in r.json().get("data", [])]
        except httpx.HTTPError as e:
            raise _connect_error(self.name, e)

    @staticmethod
    def _messages(messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                        and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                    out[-1]["content"].append(block)  # consecutive results share one user turn
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            content: Any = m.get("content") or ""
            if m.get("images"):
                content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}}
                           for b in m["images"]] + [{"type": "text", "text": m["content"]}]
            if m.get("tool_calls"):
                # Extended thinking with tools: the turn's thinking blocks (with their signatures) go back first.
                content = list(m.get("thinking_blocks") or []) + (
                    [{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                    {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]} for c in m["tool_calls"]]
            out.append({"role": m["role"], "content": content})
        return out

    async def stream(self, model, messages, opts):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        body: dict = {"model": model, "max_tokens": opts.get("max_tokens", 8192), "messages": self._messages(messages),
                      "stream": True}
        budget = {"low": 2048, "medium": 8192, "high": 24576}.get(opts.get("effort"))
        if (budget or opts.get("think")) and opts.get("effort") != "off":
            # Extended thinking, also with tools: the thinking blocks of a tool turn are returned with the
            # tool results (see _messages and the 'thinking_blocks' event below).
            budget = budget or max(1024, min(16_000, body["max_tokens"] // 2))
            body["max_tokens"] = max(body["max_tokens"], budget + 4096)
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
        elif "temperature" in opts:
            body["temperature"] = opts["temperature"]
        if system:
            # Prompt caching: tools + system prompt stay the same for a whole task (the orchestrator keeps
            # them stable), so every later turn reads them from cache: faster first token, lower cost.
            body["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if opts.get("tools"):
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                             for t in opts["tools"]]
        blocks: dict[int, dict] = {}
        thinking: dict[int, dict] = {}  # index -> thinking / redacted_thinking block being received
        try:
            async with pooled(timeout=TIMEOUT) as c, \
                    c.stream("POST", f"{self.root}/v1/messages", json=body, headers=self.headers()) as r:
                await _raise_for(r, self.name)
                async for d in _sse(r):
                    if d.get("_ping"):
                        yield {"type": "ping"}
                        continue
                    t = d.get("type")
                    if t == "content_block_start" and d["content_block"].get("type") in ("thinking", "redacted_thinking"):
                        cb = d["content_block"]
                        thinking[d["index"]] = ({"type": "thinking", "thinking": cb.get("thinking", ""), "signature": cb.get("signature", "")}
                                                if cb["type"] == "thinking" else {"type": "redacted_thinking", "data": cb.get("data", "")})
                    elif t == "content_block_start" and d["content_block"].get("type") == "tool_use":
                        cb = d["content_block"]
                        blocks[d["index"]] = {"id": cb["id"], "name": cb["name"], "json": ""}
                        yield {"type": "tool_call_start", "name": cb["name"], "chars": 0}
                    elif t == "content_block_delta":
                        delta = d["delta"]
                        if delta.get("type") == "text_delta":
                            yield {"type": "text", "text": delta["text"]}
                        elif delta.get("type") == "thinking_delta":
                            if d.get("index") in thinking:
                                thinking[d["index"]]["thinking"] += delta["thinking"]
                            yield {"type": "thinking", "text": delta["thinking"]}
                        elif delta.get("type") == "signature_delta" and d.get("index") in thinking:
                            thinking[d["index"]]["signature"] += delta.get("signature", "")
                        elif delta.get("type") == "input_json_delta" and d["index"] in blocks:
                            b = blocks[d["index"]]
                            b["json"] += delta.get("partial_json", "")
                            yield {"type": "tool_call_progress", "name": b["name"], "chars": len(b["json"])}
                    elif t == "content_block_stop" and d.get("index") in blocks:
                        b = blocks.pop(d["index"])
                        yield {"type": "tool_call", "id": b["id"], "name": b["name"], "arguments": _args(b["json"])}
                    elif t == "message_start" and (u := d.get("message", {}).get("usage")):
                        # cached prompt parts are counted separately; the context still holds them
                        yield {"type": "usage", "input": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                               + (u.get("cache_creation_input_tokens") or 0)}
                    elif t == "message_delta" and (u := d.get("usage")):
                        yield {"type": "usage", "output": u.get("output_tokens")}
                    elif t == "error":
                        raise stream_error(d.get("error"))
        except httpx.ConnectError as e:
            raise _connect_error(self.name, e)
        if thinking:  # kept by the caller for the next tool turn
            yield {"type": "thinking_blocks", "blocks": [thinking[i] for i in sorted(thinking)]}
        yield {"type": "done"}


# ---------------------------------------------------------------- Gemini (native API, tag-protocol tools)
class GeminiProvider(Provider):
    """Native Gemini API (protocol 'gemini'). Gemini's OpenAI-compatible endpoint uses 'openai' (native tools)."""

    async def list_models(self) -> list[dict]:
        async with pooled(timeout=10) as c:
            r = await c.get(f"{self.base_url}/models", headers={"x-goog-api-key": self.key()})
            await _raise_for(r, self.name)
        return [{"id": m["name"].removeprefix("models/"), "context": m.get("inputTokenLimit"), "tools": False,
                 "vision": True, "thinking": m.get("thinking")}
                for m in r.json().get("models", []) if "generateContent" in (m.get("supportedGenerationMethods") or ["generateContent"])]

    async def stream(self, model, messages, opts):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            text = m.get("content") or ""
            if m["role"] == "tool":
                text = f"Tool result ({m.get('name')}):\n{text}"
            parts = [{"text": text}] + [{"inline_data": {"mime_type": "image/png", "data": b}} for b in m.get("images", [])]
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
        body: dict = {"contents": contents}
        gen = {k: v for k, v in (("temperature", opts.get("temperature")), ("maxOutputTokens", opts.get("max_tokens")))
               if v is not None}
        if (e := opts.get("effort")) in ("off", "low", "medium", "high"):
            gen["thinkingConfig"] = {"thinkingBudget": {"off": 0, "low": 1024, "medium": 8192, "high": 24576}[e]}
        if gen:
            body["generationConfig"] = gen
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse"
        try:
            async with pooled(timeout=TIMEOUT) as c, \
                    c.stream("POST", url, json=body, headers={"x-goog-api-key": self.key()}) as r:
                await _raise_for(r, self.name)
                usage = None
                async for d in _sse(r):
                    if d.get("_ping"):
                        yield {"type": "ping"}
                        continue
                    for cand in d.get("candidates", []):
                        for p in cand.get("content", {}).get("parts", []):
                            if t := p.get("text"):
                                yield {"type": "text", "text": t}
                    usage = d.get("usageMetadata") or usage  # every chunk carries the running total; the last wins
                if usage:  # the real prompt size: context meter and compression follow it
                    yield {"type": "usage", "input": usage.get("promptTokenCount"),
                           "output": (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0),
                           "reasoning": usage.get("thoughtsTokenCount")}
        except httpx.ConnectError as e:
            raise _connect_error(self.name, e)
        yield {"type": "done"}


# ---------------------------------------------------------------- Cloudflare Workers AI
class CloudflareProvider(OpenAICompatProvider):
    """Cloudflare Workers AI: OpenAI-compatible chat under the account's URL; the model list comes from the AI
    model search (there is no /models listing). Needs the Account ID (provider setting) and an API token."""
    API = "https://api.cloudflare.com/client/v4/accounts"

    @property
    def account(self) -> str:
        acc = str(self.cfg.get("account_id") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", acc):
            raise ProviderError("missing_credentials", f"{self.name}: Account ID is not set (Settings > Providers)")
        return acc

    @property
    def base_url(self) -> str:  # never raises (error paths read it too); requests check the account first
        return f"{self.API}/{str(self.cfg.get('account_id') or '').strip()}/ai/v1"

    async def stream(self, model, messages, opts):
        self.account  # a clear "Account ID is not set" instead of a routing error from Cloudflare
        async for evt in super().stream(model, messages, opts):
            yield evt

    async def list_models(self) -> list[dict]:
        out: list[dict] = []
        try:
            async with pooled(timeout=20) as c:
                for page in range(1, 6):
                    r = await c.get(f"{self.API}/{self.account}/ai/models/search", headers=self.headers(),
                                    params={"task": "Text Generation", "per_page": 100, "page": page})
                    await _raise_for(r, self.name)
                    found = r.json().get("result") or []
                    for m in found:
                        p = {x.get("property_id"): str(x.get("value")).lower() for x in m.get("properties") or []}
                        if not m.get("name") or p.get("lora") == "true" and m["name"].endswith("-lora"):
                            continue  # LoRA adapters are not chat models on their own
                        out.append({"id": m["name"], "context": int(p["context_window"]) if p.get("context_window", "").isdigit() else None,
                                    "tools": p.get("function_calling") == "true", "vision": None,
                                    "thinking": p.get("reasoning") == "true"})
                    if len(found) < 100:
                        break
        except httpx.HTTPError as e:
            raise _connect_error(self.name, e)
        return out


ADAPTERS: dict[str, type[Provider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatProvider,
    "cloudflare": CloudflareProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}
VISION_HINT = ("vl", "vision", "llava", "gpt-4o", "gpt-5", "claude", "gemini", "pixtral", "gemma-4", "qwen3.8")
