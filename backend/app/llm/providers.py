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
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from ..config import DATA_DIR, get_secret

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
    raw = json.dumps(err, ensure_ascii=False)[:2000] if not isinstance(err, str) else err[:2000]
    text = message_of(err) or raw[:500]
    if re.search(r"repeat limit|repetition|degenerat", text, re.I):
        # Ollama stopped a reply that repeated one token ("@@@@..."): the model or its runtime backend produced
        # garbage. Asking the same thing again gives the same garbage; the task loop handles it (see 'degenerate').
        return ProviderError("degenerate", text)
    status = 0
    if isinstance(err, dict):
        c = err.get("code") or err.get("status")
        status = c if isinstance(c, int) else int(c) if isinstance(c, str) and c.isdigit() else 0
    code = classify_error(status or 500, raw)
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
    # A model the provider retired ("gemini-2.5-flash is no longer available to new users. Please use ..."): not a typo
    (r"no longer available|has been deprecated|decommissioned|been retired|is deprecated", "model_retired"),
    (r"model .*not found|model_not_found|no such model|unknown model|does not exist", "model_not_found"),
    (r"invalid.api.key|incorrect api key|invalid x-api-key|authentication_error|authentication error|authorization failed|unauthorized|geçersiz api", "auth"),
    (r"moderation|flagged|content policy|safety", "moderation"),
    (r"overloaded|capacity|unavailable|no endpoints found|no providers", "overloaded"),
]


def _parse_any(text: str):
    """JSON, or the Python repr of it ({'error': {...}} with single quotes, as some SDK messages print it)."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    s = (text or "").strip()
    if s[:1] in "[{" and len(s) < 20000:
        import ast
        try:
            return ast.literal_eval(s)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            pass
    return None


def message_of(obj, depth: int = 0) -> str:
    """The human sentence inside any error shape: {"error": {"message"}}, [{"error": ...}] (Gemini sends a list),
    {"errors": [{"message"}]} (Cloudflare), {"detail": ...}, nested strings that are JSON again. Never raw JSON."""
    if depth > 4:
        return ""
    if isinstance(obj, str):
        inner = _parse_any(obj)
        if inner is not None and not isinstance(inner, str):
            return message_of(inner, depth + 1) or obj.strip()[:400]
        # "prefix: {json}" (a provider name or "HTTP 503" before the body)
        m = re.search(r"[\[{].*[\]}]\s*$", obj, re.S)
        if m and (inner := _parse_any(m.group(0))) is not None:
            found = message_of(inner, depth + 1)
            if found:
                head = obj[:m.start()].strip().rstrip(":").strip()
                return f"{head}: {found}" if head else found
        return obj.strip()[:400]
    if isinstance(obj, list):
        for x in obj:
            if found := message_of(x, depth + 1):
                return found
        return ""
    if isinstance(obj, dict):
        for k in ("error", "errors"):
            if obj.get(k) and (found := message_of(obj[k], depth + 1)):
                return found
        for k in ("message", "detail", "msg", "error_description", "title", "status"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return message_of(v, depth + 1) if v.strip()[:1] in "[{" else v.strip()[:400]
            if isinstance(v, (dict, list)) and (found := message_of(v, depth + 1)):
                return found
        return ""
    return str(obj)[:400] if obj is not None else ""


def _error_message(body: str) -> str:
    """Pull the human-readable message out of the common JSON error shapes."""
    return message_of(body) or (body or "").strip()[:400]


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
                if m.get("reasoning"):
                    # Ollama docs: a tool turn goes back with its thinking (the model continues its own reasoning)
                    msg["thinking"] = m["reasoning"]
            out.append(msg)
        return out

    async def stream(self, model, messages, opts):
        options = {k: v for k, v in opts.items() if k in ("temperature", "num_ctx", "top_p", "repeat_penalty", "repeat_last_n")}
        if self.local or not self.base_url.startswith("https://ollama.com"):
            from .memguard import threads
            options.setdefault("num_thread", threads())  # one core left free: no overheating, the PC stays usable
        else:  # Ollama Cloud: its own hardware and window - no local CPU threads, no local num_ctx limit
            options.pop("num_ctx", None)
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
        if "generativelanguage.googleapis.com" in self.base_url:
            # Gemini's OpenAI-compatible listing has no capabilities and lists image / video / embedding / TTS models
            # as chat models: the native listing says what each one does (methods, window, thinking).
            native = await _gemini_native_models(self.cfg, self.headers())
            if native:
                return [m for m in native if not retired(self.cfg, m["id"])]
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
            if NOT_CHAT.search(m["id"]) or NOT_CHAT_EXTRA.search(m["id"].split("/")[-1]) or retired(self.cfg, m["id"]):  # embeddings, rerankers, speech, CLIP...
                continue
            outs = (m.get("architecture") or {}).get("output_modalities")
            if isinstance(outs, list) and outs and "text" not in outs:  # OpenRouter: image / audio-only output models
                continue
            if not _chat_by_meta(m):  # the listing's own type / capability fields say it is no chat model
                continue
            caps = _caps_from(m)
            # Listings without capabilities (NVIDIA NIM, Groq, Mistral, DeepSeek, Together...): from the model's name
            for k, v in infer_caps(m["id"]).items():
                if caps.get(k) is None:
                    caps[k] = v
            out.append({"id": m["id"], "context": _ctx_from(m), **caps})
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

    def _tool_stream_failed(self, model: str, opts: dict, err: ProviderError) -> ProviderError:
        """A streamed tool request that the server's tool parser broke: the next try of this model's tool requests
        goes without streaming (NIM's documented workaround), the error is retried as usual."""
        if opts.get("tools") and "nvidia" in self.base_url and TOOL_PARSER_ERROR.search(str(err)):
            NO_TOOL_STREAM.add(f"{self.name}:{model}")
        return err

    @staticmethod
    def _messages(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
                continue
            if m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or None,
                            **({"_reasoning": m["reasoning"]} if m.get("reasoning") else {}), "tool_calls": [
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
        if streaming and opts.get("tools") and f"{self.name}:{model}" in NO_TOOL_STREAM:
            streaming = False  # this model's tool parser broke while streaming (see _tool_stream_failed)
        body: dict = {"model": model, "messages": self._messages(messages), "stream": streaming}
        if "mistral.ai" in self.base_url:
            body["messages"] = _mistral_ids(body["messages"])
        for m in body["messages"]:
            # Only DeepSeek's own API takes the reasoning back (required with tools in thinking mode); any other
            # server gets the message without it.
            if (r := m.pop("_reasoning", None)) and "api.deepseek.com" in self.base_url:
                m["reasoning_content"] = r
        if "temperature" in opts:
            body["temperature"] = opts["temperature"]
        if opts.get("repeat_penalty") and not _no_penalty(self.base_url, model):
            # The OpenAI-style counterpart of a repeat penalty: after a generation loop the next try repeats less.
            body["frequency_penalty"] = round(min(1.0, (float(opts["repeat_penalty"]) - 1) * 2.5), 2)
        if opts.get("max_tokens"):
            body["max_tokens"] = opts["max_tokens"]
        if _openai_reasoning(self.base_url, model):
            # o-series / gpt-5: the limit counts reasoning + answer and has its own name; sampling is fixed
            if "max_tokens" in body:
                body["max_completion_tokens"] = body.pop("max_tokens")
            body.pop("temperature", None)
        if _fixed_sampling(self.base_url, model):
            body.pop("temperature", None)
            body.pop("top_p", None)
        if e := opts.get("effort"):  # reasoning effort: OpenRouter's reasoning object, else OpenAI's field
            if "openrouter" in self.base_url:
                body["reasoning"] = {"enabled": False} if e == "off" else {"effort": e}
            elif e == "off" and "generativelanguage.googleapis.com" in self.base_url:
                body["reasoning_effort"] = "none"  # Gemini: thinking off (Flash models)
            elif e not in ("off", "on"):
                body["reasoning_effort"] = e
        elif "think" in opts:  # model profile: OpenRouter's reasoning switch, else the OpenAI reasoning_effort field
            if "openrouter" in self.base_url:
                body["reasoning"] = {"enabled": opts["think"]}
            elif opts["think"]:
                body["reasoning_effort"] = "medium"
        if opts.get("tools"):
            body["tools"] = [{"type": "function", "function": t} for t in opts["tools"]]
        off = opts.get("no_think") or opts.get("think") is False or opts.get("effort") == "off"
        if off and "api.cerebras.ai" in self.base_url:
            body["reasoning_effort"] = "none"  # Cerebras: "none" turns reasoning off (disable_reasoning was removed)
        if opts.get("tools") and "api.groq.com" in self.base_url and re.search(r"qwen", model, re.I):
            # Groq: with tools a reasoning model's format must be parsed or hidden ("raw" is a 400). Only its Qwen
            # reasoning models take the field (gpt-oss uses include_reasoning, other models reject it).
            body["reasoning_format"] = "hidden" if off else "parsed"
        if (sw := _thinking_switch(self.base_url, model, opts)) is not None:
            body.update(sw)
            body.pop("reasoning_effort", None)  # Kimi K2.x / GLM take their own switch, not this field (Kimi docs)
        template_server = self.is_evren or "integrate.api.nvidia.com" in self.base_url
        if (opts.get("no_think") or opts.get("think") is False or opts.get("effort") == "off") and template_server:
            # vLLM / NIM ignore reasoning_effort; the chat template switch really turns reasoning off (checked on
            # EVREN: 0 reasoning tokens). The key depends on the model's template (vLLM docs): Qwen / Nemotron / GLM
            # read enable_thinking, DeepSeek V3.1+ reads thinking - a key the template does not use is ignored, so
            # both are sent (before, DeepSeek on EVREN kept reasoning for 190 s with "off").
            from . import families
            key = families.think_key(model)
            # the family's own key when known (models.families); both when not - a key the template does not use
            # is ignored. A model that always reasons gets nothing (its template has no switch).
            if not families.always_thinks(model):
                body["chat_template_kwargs"] = {key: False} if key else {"enable_thinking": False, "thinking": False}
        elif self.is_evren and opts.get("tools"):  # thinking on too: past the cap nothing is written; vLLM ignores unknown fields
            # A provider that ends every request after a fixed time (EVREN ~194 s, measured): reasoning that takes
            # most of it leaves no time to write (every turn of a game "broke off after thinking"). The reasoning is
            # given a budget that fits the cap at this model's speed (NIM / vLLM thinking_token_budget).
            from . import router as _router
            if cap := _router.request_cap(f"{self.name}:{model}"):
                tps = float(opts.get("tps") or 15)
                body["thinking_token_budget"] = int(max(1024, min(8192, cap * 0.45 * tps)))
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
                            yield {"type": "thinking", "text": t if isinstance(t, str) else split_content(t)[0] or split_content(t)[1]}
                        th, t = split_content(msg.get("content"))
                        if th:
                            yield {"type": "thinking", "text": th}
                        if t:
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
                                raise self._tool_stream_failed(model, opts, stream_error(d["error"]))
                            for ch in d.get("choices") or []:
                                finish = ch.get("finish_reason") or finish
                                if ch.get("error"):
                                    raise self._tool_stream_failed(model, opts, stream_error(ch["error"]))
                                delta = ch.get("delta") or {}
                                if t := delta.get("reasoning_content") or delta.get("reasoning"):
                                    yield {"type": "thinking", "text": t if isinstance(t, str) else split_content(t)[0] or split_content(t)[1]}
                                th, t = split_content(delta.get("content"))
                                if th:
                                    yield {"type": "thinking", "text": th}
                                if t:
                                    yield {"type": "text", "text": t}
                                for tc in delta.get("tool_calls") or []:  # arguments arrive in fragments
                                    if "index" in tc:
                                        idx = tc["index"]
                                    else:
                                        # No index (SambaNova, Gemini): a fragment without its own id/name belongs
                                        # to the call before it; one with a new id or a name starts the next call.
                                        last = max(calls) if calls else None
                                        tid, tname = tc.get("id"), (tc.get("function") or {}).get("name")
                                        fresh = (last is None or bool(tid and tid != calls[last]["id"])
                                                 or bool(tname and not tid))
                                        idx = len(calls) if fresh else last
                                    new = idx not in calls
                                    slot = calls.setdefault(idx, {"id": None, "name": "", "args": "", "extra": None})
                                    slot["id"] = tc.get("id") or slot["id"]
                                    slot["extra"] = tc.get("extra_content") or slot["extra"]
                                    fn = tc.get("function") or {}
                                    # Some OpenAI-compatible servers repeat the whole name on every fragment
                                    # (the spec sends it once): joined, my_location became my_locationmy_location...
                                    if (n := fn.get("name") or "") and n != slot["name"]:
                                        slot["name"] += n
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


# Models whose tool calls fail while streaming (NIM release notes: the tool parser errors intermittently with
# stream=true; their workaround is stream=false for tool requests). Filled at run time, per provider:model.
NO_TOOL_STREAM: set[str] = set()
TOOL_PARSER_ERROR = re.compile(r"pars(e|er|ing)|harmony|tool[_ ]?call|function[_ ]?call|invalid json", re.I)


def _thinking_switch(base_url: str, model: str, opts: dict) -> dict | None:
    """The request field that turns reasoning on/off where a provider has its own (None: no own switch or no
    choice made). Kimi K2.5/K2.6 and Z.ai GLM: thinking={"type": ...}. kimi-k2-thinking cannot turn it off, Kimi
    K3 uses reasoning_effort, GLM-5.3 rejects "disabled" - nothing is sent for those."""
    off = opts.get("no_think") or opts.get("think") is False or opts.get("effort") == "off"
    on = opts.get("think") is True or opts.get("effort") in ("low", "medium", "high")
    if not (off or on):
        return None
    m = model.lower()
    if "moonshot" in base_url or "kimi.com" in base_url:
        if re.search(r"k2[.-]?[56]", m) and "k2-thinking" not in m:
            return {"thinking": {"type": "disabled" if off else "enabled"}}
        return None
    if "api.z.ai" in base_url or "bigmodel.cn" in base_url:
        if off and re.search(r"glm-5\.3", m):
            return None
        return {"thinking": {"type": "disabled" if off else "enabled"}}
    if "dashscope" in base_url or "aliyuncs.com" in base_url:
        # Alibaba Model Studio: hybrid Qwen models switch per request with enable_thinking (top level in the JSON
        # body = the SDK's extra_body); thinking-only models (qwq, *-thinking) always reason - nothing is sent
        if re.search(r"qwq|thinking", m):
            return None
        return {"enable_thinking": not off}
    return None


def _openai_reasoning(base_url: str, model: str) -> bool:
    """OpenAI's own reasoning models (o-series, gpt-5 but -chat): max_completion_tokens instead of max_tokens (400),
    no temperature / top_p (400 'Unsupported parameter')."""
    m = model.lower().split("/")[-1]
    own = "api.openai.com" in base_url or "openai.azure.com" in base_url
    return own and bool(re.match(r"(o\d|gpt-5)", m)) and "chat" not in m


def _fixed_sampling(base_url: str, model: str) -> bool:
    """Moonshot's Kimi K2.5+ fix temperature and top_p: any value sent is an error (Kimi docs: 'cannot be
    modified', do not pass it)."""
    return ("moonshot" in base_url or "kimi.com" in base_url) and bool(
        re.search(r"k2[.-]?[5-9]|k[3-9]\b|k[3-9][.-]", model.lower()))


def split_content(c) -> tuple[str, str]:
    """(thinking, text) of a message / delta content: a plain string, or Mistral's list of chunks
    ({"type": "thinking", "thinking": [{"type": "text", "text": ...}]}, {"type": "text", "text": ...}) that Magistral
    and reasoning_effort="high" return - a list used to be passed on as the answer text and broke the stream."""
    if isinstance(c, str) or c is None:
        return "", c or ""
    if isinstance(c, dict):
        c = [c]
    think, text = [], []
    for ch in c if isinstance(c, list) else []:
        if not isinstance(ch, dict):
            text.append(str(ch))
            continue
        kind = ch.get("type")
        if kind == "thinking":
            inner = ch.get("thinking")
            if isinstance(inner, list):
                think += [x.get("text", "") for x in inner if isinstance(x, dict)]
            elif isinstance(inner, str):
                think.append(inner)
        elif kind in ("text", None) and isinstance(ch.get("text"), str):
            text.append(ch["text"])
    return "".join(think), "".join(text)


def _no_penalty(base_url: str, model: str) -> bool:
    """Servers that reject frequency_penalty (400): xAI reasoning models (every grok-4* but -non-reasoning, xAI docs),
    SambaNova, OpenAI reasoning models (o-series, gpt-5)."""
    m = model.lower()
    if "api.x.ai" in base_url:
        return "grok-4" in m and "non-reasoning" not in m or "grok-3-mini" in m
    if "sambanova" in base_url:
        return True
    return "api.openai.com" in base_url and bool(re.match(r"(o\d|gpt-5)", m))


def _mistral_id(cid: str) -> str:
    """Mistral accepts only tool-call ids of exactly 9 letters/digits (HTTP 422 otherwise): ids made by the app or by
    another provider before a model switch are mapped, the same way in the call and in its result."""
    if re.fullmatch(r"[A-Za-z0-9]{9}", cid or ""):
        return cid
    return hashlib.sha1((cid or "").encode()).hexdigest()[:9]


def _mistral_ids(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        if m.get("role") == "tool":
            m = {**m, "tool_call_id": _mistral_id(m.get("tool_call_id", ""))}
        elif m.get("tool_calls"):
            m = {**m, "tool_calls": [{**c, "id": _mistral_id(c.get("id", ""))} for c in m["tool_calls"]]}
        out.append(m)
    return out


# ---------------------------------------------------------------- Anthropic
def claude_gen(model: str) -> str:
    """Which thinking / sampling rules a Claude model follows:
    legacy (before 4.6: budget_tokens, temperature), 4.6 (adaptive, temperature still allowed), new (4.7+: adaptive,
    no sampling params), between_tools (Sonnet 5.5: off = between_tools), always_on (Opus 5.5, Fable, Mythos: thinking
    cannot be turned off)."""
    m = (model or "").lower().split("/")[-1]
    if re.search(r"fable|mythos|opus-5-5", m):
        return "always_on"
    if "sonnet-5-5" in m:
        return "between_tools"
    if re.search(r"claude-[23]\b|claude-[23]-|claude-instant", m):
        return "legacy"
    v = re.search(r"(?:opus|sonnet|haiku)-(\d+)(?:-(\d{1,2})(?!\d))?", m)
    if not v:
        return "new"
    major, minor = int(v.group(1)), int(v.group(2) or 0)
    if major < 4 or (major == 4 and minor < 6):
        return "legacy"
    if major == 4 and minor == 6:
        return "4.6"
    return "new"


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
        gen = claude_gen(model)
        effort = opts.get("effort")
        want = (bool(effort) or bool(opts.get("think"))) and effort != "off" and opts.get("think") is not False
        level = effort if effort in ("low", "medium", "high", "xhigh", "max") else None
        if gen == "legacy":
            # Claude before 4.6: a fixed thinking budget (min 1024, below max_tokens)
            if want:
                budget = {"low": 2048, "medium": 8192, "high": 24576, "xhigh": 32000, "max": 32000}.get(
                    level or "", max(1024, min(16_000, body["max_tokens"] // 2)))
                body["max_tokens"] = max(body["max_tokens"], budget + 4096)
                body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            elif "temperature" in opts:
                body["temperature"] = opts["temperature"]
        else:
            # 4.6+: adaptive thinking and output_config.effort (budget_tokens is a 400 from 4.7 on; temperature is
            # a 400 from 4.7 on). Opus 5.5 / Fable / Mythos cannot turn thinking off (lowest effort instead);
            # Sonnet 5.5 turns it off with between_tools.
            if want:
                body["thinking"] = {"type": "adaptive", "display": "summarized"}
            elif gen == "always_on":
                level = "low"
            elif gen == "between_tools":
                body["thinking"] = {"type": "between_tools"}
                level = level if level in ("low", "medium", "high") else None
            else:
                body["thinking"] = {"type": "disabled"}
                if level in ("xhigh", "max"):  # disabled thinking is accepted only at effort high or below
                    level = "high"
                if gen == "4.6" and "temperature" in opts:
                    body["temperature"] = opts["temperature"]
            if level and not (gen == "4.6" and level == "xhigh"):
                body["output_config"] = {"effort": level}
        if system:
            # Prompt caching: tools + system prompt stay the same for a whole task (the orchestrator keeps
            # them stable), so every later turn reads them from cache: faster first token, lower cost.
            body["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if opts.get("tools"):
            # eager_input_streaming: a tool's arguments (a whole file) stream as they are written instead of arriving
            # in one burst at the end - live progress, and no long silence the watchdog takes for a stall
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"],
                              "eager_input_streaming": True} for t in opts["tools"]]
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
                    elif t == "message_delta":
                        stop = (d.get("delta") or {}).get("stop_reason")
                        if u := d.get("usage"):
                            yield {"type": "usage", "output": u.get("output_tokens")}
                        if stop in ("max_tokens", "model_context_window_exceeded"):
                            # cut by the output limit / the window: kept and continued, never taken as finished
                            for b in blocks.values():  # a tool call cut mid-way: its partial arguments are salvaged
                                yield {"type": "truncated", "name": b["name"], "chars": len(b["json"]), "reason": "length"}
                            if not blocks:
                                yield {"type": "truncated", "name": None, "chars": 0, "reason": "length"}
                        elif stop == "refusal":
                            det = (d.get("delta") or {}).get("stop_details") or {}
                            raise ProviderError("refused", "The model declined this request"
                                                + (f" ({det.get('category')})" if det.get("category") else "")
                                                + (f": {det.get('explanation')}" if det.get("explanation") else ""))
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

    def _acc(self) -> str:
        """One account id for chat and image generation: the provider's own, else the one typed in the image card."""
        from ..config import load_settings
        return (str(self.cfg.get("account_id") or "").strip()
                or str((load_settings().get("media") or {}).get("cloudflare_account") or "").strip())

    @property
    def account(self) -> str:
        acc = self._acc()
        if not re.fullmatch(r"[0-9a-f]{32}", acc):
            raise ProviderError("missing_account", f"{self.name}: Account ID is not set (Settings > Providers)")
        return acc

    @property
    def base_url(self) -> str:  # never raises (error paths read it too); requests check the account first
        return f"{self.API}/{self._acc()}/ai/v1"

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
                        if NOT_CHAT.search(m["name"]) or (m.get("description") or "").lower().startswith("deprecated"):
                            continue  # classifiers (llama-guard) and models Cloudflare marks deprecated
                        guess = infer_caps(m["name"])
                        out.append({"id": m["name"], "context": int(p["context_window"]) if p.get("context_window", "").isdigit() else None,
                                    "tools": p.get("function_calling") == "true" or None,
                                    "vision": p.get("vision") == "true" or guess["vision"],
                                    "thinking": p.get("reasoning") == "true" or guess["thinking"]})
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

# Models that are not chat models (an OpenAI-compatible /models lists them too): never offered in the model picker
NOT_CHAT = re.compile(r"embed|rerank|nvclip|(^|/)clip|parakeet|whisper|canary|(^|[/-])tts|text-to-speech|bge-|e5-|"
                      r"retriever|nv-embed|arctic-embed|-ocr|paddleocr|cosmos-|imagen|veo-|flux|stable-diffusion|sdxl|"
                      r"-image-generation|dall-e|gpt-image|aqa$|nemoretriever|gliner|ai-detector|deplot|kosmos|"
                      # classifiers and agent products: not chat models a task can run on
                      r"guard|safety|detector|calibration|reward|starcoder2|deep-research|antigravity|"
                      # speech / music models some listings mix in (Gemini transcribe, Lyria, Groq Orpheus / PlayAI)
                      r"transcribe|lyria|orpheus|playai|-audio\b|gpt-audio|realtime", re.I)
_VISION_RE = re.compile(r"(\bvl\b|-vl|vl-|vision|llava|pixtral|multimodal|omni|gpt-4o|gpt-4\.1|gpt-5|(^|/)o[34]\b|"
                        r"gemini|gemma-?3n?|gemma-?4|llama-4|qwen2\.5-vl|qwen3-vl|qwen3\.[5-9]|kimi-k2\.5|glm-4\.[5-9]v|"
                        r"phi-4-multimodal|phi-3\.5-vision|mistral-medium|mistral-small-3|nemotron.*vl|claude)", re.I)
_THINK_RE = re.compile(r"(r1\b|-r1|reason|thinking|qwq|qwen3|gpt-oss|(^|/)o[134]\b|gpt-5|deepseek-v3\.[1-9]|"
                       r"deepseek-v4|magistral|nemotron|gemini-(2\.5|[3-9])|kimi-k2-thinking|glm-4\.[5-9]|glm-5|"
                       r"step-[3-9]|grok-[34]|minimax-m\d|seed-oss|hermes-4|phi-4-reasoning|kimi-k[3-9])", re.I)
_TOOLS_RE = re.compile(r"(llama-3\.[1-3]|llama-4|qwen|mistral|mixtral|nemotron|deepseek|gpt|gemini|glm|kimi|minimax|"
                       r"granite|command|hermes|devstral|codestral|phi-4|grok|seed-oss|step-|jamba|ling-|ernie)", re.I)


def _chat_by_meta(m: dict) -> bool:
    """What a provider's /models entry itself says about the model (documented fields, checked per provider):
    Together "type" (chat / language vs image, embedding, rerank, audio, moderation, transcribe), Mistral
    "capabilities.completion_chat", Fireworks "kind", DeepInfra / some gateways "task" or "model_type", Groq "active".
    Unknown fields leave the decision to the name filters."""
    t = str(m.get("type") or m.get("model_type") or m.get("task") or "").lower()
    if t and t not in ("chat", "language", "llm", "text-generation", "text_generation", "model", "code", "vlm", "multimodal"):
        if re.search(r"image|embed|rerank|audio|speech|tts|transcri|moderation|video|classif|detect|ocr", t):
            return False
    caps = m.get("capabilities")
    if isinstance(caps, dict) and caps.get("completion_chat") is False:
        return False
    if m.get("active") is False:  # Groq: a model taken out of service
        return False
    kind = str(m.get("kind") or "").upper()
    if kind and re.search(r"EMBED|IMAGE|AUDIO|RERANK", kind):
        return False
    return True


# Old completion-only and non-chat families some OpenAI-compatible listings still return
NOT_CHAT_EXTRA = re.compile(r"^(babbage|davinci|ada|curie)(-|$)|text-moderation|omni-moderation|-moderation|sora|"
                            r"dall-e|gpt-image|tts-|whisper|codex-mini|computer-use|-search-preview$|-transcribe", re.I)


def infer_caps(model_id: str) -> dict:
    """Vision / thinking / tool calling from the model's name, for listings that report none. Only True values are
    inferred from a match; no match leaves the capability unknown (None) instead of claiming it is missing."""
    n = model_id.lower()
    return {"vision": True if _VISION_RE.search(n) else None, "thinking": True if _THINK_RE.search(n) else None,
            "tools": True if _TOOLS_RE.search(n) else None}


# Models a provider retired (an answer "no longer available to new users"): hidden from the lists, and requests for
# them go to the replacement the provider named (see router.stream_chat). Kept in data/retired_models.json.
_RETIRED_FILE = DATA_DIR / "retired_models.json"


def _retired_all() -> dict:
    try:
        return json.loads(_RETIRED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def retired(cfg: dict, model: str) -> str | None:
    """The replacement of a retired model of this provider ('' if none was named), else None."""
    key = (cfg.get("base_url") or cfg.get("kind") or "") + "|" + model.removeprefix("models/")
    return _retired_all().get(key)


def mark_retired(cfg: dict, model: str, replacement: str) -> None:
    data = _retired_all()
    data[(cfg.get("base_url") or cfg.get("kind") or "") + "|" + model.removeprefix("models/")] = replacement
    try:
        _RETIRED_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


# Gemini chat models follow one naming: gemini-<version>-<pro|flash|flash-lite>[-preview[-date]|-latest|-001], the
# -latest aliases, and Gemma. Code-named entries the listing also returns (gemini-4-hydrogen, -argon, -neon: early
# access / experiments) answered after minutes or not at all ("provider slow - model still working" for 4 minutes),
# so they are not offered as chat models.
GEMINI_CHAT = re.compile(r"^(gemini-\d+(\.\d+)?-(pro|flash|flash-lite|flash-8b)(-preview(-[\w-]+)?|-latest|-exp(-[\w-]+)?|-\d{3}"
                         r"|-thinking(-[\w-]+)?)?|gemini-(pro|flash|flash-lite)-latest|gemma-[\w.-]+)$")


async def _gemini_native_models(cfg: dict, headers: dict) -> list[dict]:
    """Gemini models from the native API: only text-generating chat models, with window, thinking, vision, tools."""
    key = (headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not key:
        return []
    out, token = [], ""
    try:
        async with pooled(timeout=15) as c:
            for _ in range(5):
                r = await c.get("https://generativelanguage.googleapis.com/v1beta/models",
                                params={"pageSize": 1000, **({"pageToken": token} if token else {})},
                                headers={"x-goog-api-key": key})
                if r.status_code != 200:
                    return []
                d = r.json()
                for m in d.get("models") or []:
                    mid = m["name"].removeprefix("models/")
                    if "generateContent" not in (m.get("supportedGenerationMethods") or []) or NOT_CHAT.search(mid) \
                            or re.search(r"-image|tts|native-audio|live|computer-use|robotics|learnlm", mid) \
                            or not GEMINI_CHAT.match(mid):
                        continue
                    gemma = mid.startswith("gemma")
                    out.append({"id": mid, "context": m.get("inputTokenLimit"), "name": m.get("displayName"),
                                "thinking": bool(m.get("thinking")) or bool(re.search(r"gemini-(2\.5|[3-9])", mid)),
                                "vision": not gemma or bool(re.search(r"gemma-?3(?!-1b)|gemma-?3n|gemma-?4", mid)),
                                "tools": not gemma, "max_output": m.get("outputTokenLimit")})
                token = d.get("nextPageToken") or ""
                if not token:
                    break
    except httpx.HTTPError:
        return []
    # newest first: version, then pro > flash > lite
    def rank(m):
        v = re.findall(r"(\d+(?:\.\d+)?)", m["id"])
        return (m["id"].startswith("gemini"), float(v[0]) if v else 0.0, "pro" in m["id"], "lite" not in m["id"],
                "preview" not in m["id"])
    return sorted(out, key=rank, reverse=True)
