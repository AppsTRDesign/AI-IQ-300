# Provider compatibility: research and plan (2026-11-22)

This document compares how the providers in Settings stream, send tool calls and handle reasoning with how AI IQ 300 handles them. Most "connection dropped" problems come from a mismatch here: the stream goes silent or is cut when a provider or server behaves differently from what we assumed.

## Real causes of the drops (logs + docs)

| Symptom (in the logs) | Cause | Status |
|---|---|---|
| "no data for 62/90/92 s" while the provider answers a new request in 1 s | The vLLM/NIM tool parser **holds a tool call's arguments until the call is complete**. Not a byte arrives meanwhile, so a proxy or gateway in between closes the idle connection. The NVIDIA forum reports the same: arguments are not streamed, and after 300 s of silence the stream closes with no finish_reason. | Existing: a provider that writes silently is moved to the text protocol, so the file streams as text. |
| "the provider ends a request after about 194 s" (evren) | Evren ends every request after a fixed time (measured: 194 s). DeepSeek **reasoned** for 120–190 s per turn, leaving no time to write. | **Fixed:** evren tool requests get a `thinking_token_budget` sized to the cap and the model's speed. |
| DeepSeek still reasons with thinking "off" | The code sent only `chat_template_kwargs.enable_thinking=false`, which is the Qwen/Nemotron/GLM key. Per the vLLM docs, the DeepSeek V3.1+ template reads `thinking`. | **Fixed:** both keys are sent (a template ignores the key it does not use), and NVIDIA NIM gets them too. |
| A file went from 80K to 0; 50K of game.js was lost | Our bug: when a plain rewrite of an existing file was written live, the restore base was `""`, so a break emptied the file. After a second break, the cut rewrite was written over the file. | **Fixed:** the file guard (below). |
| "Preparing tool_my_location", looping | (1) Some OpenAI-compatible servers repeat the tool name on every fragment, and joining them broke the name. (2) A tool with no arguments got stuck in an argument loop. (3) A missing translation key showed the raw name. | **Fixed:** repeated names are not joined; 3000+ characters into a tool with short arguments is treated as a loop and cut; 32 missing tool labels were added in TR and EN. |

## Per provider

- **Evren (vLLM, OpenAI-compatible)**
  - Streams over SSE and supports `stream_options.include_usage`.
  - Tool arguments may be held back, depending on the model and its parser.
  - Reasoning is switched through `chat_template_kwargs` (`enable_thinking` / `thinking`).
  - Every request has a fixed time cap, measured in `data/request_caps.json`.
  - Per the vLLM docs, DeepSeek supports tool calling in non-thinking mode.
- **NVIDIA NIM (integrate.api.nvidia.com)**
  - OpenAI-compatible.
  - Reasoning is switched with `chat_template_kwargs.enable_thinking`, and `thinking_token_budget` is also supported.
  - Tool arguments are not streamed, and the stream closes after 300 s of silence (forum report; seen here too).
  - The NIM release notes report a parser error when streaming with tool calls; their workaround is `stream:false` for tool requests.
- **Ollama (local / Cloud)**
  - Streams NDJSON from `/api/chat`.
  - Tool calls arrive whole, not in fragments.
  - On a CPU the first token can take minutes, so local silence is not cut.
- **Google Gemini (OpenAI compatibility layer)**
  - In a stream, `tool_calls` chunks may lack `index`, `id` may be empty, arguments arrive in one piece, and finish_reason may be `stop`.
  - Gemini 3 returns 400 if `thought_signature` is not sent back.
  - Handled here: a call without an index counts as a new call, an empty id is generated, and the signature goes back via `extra_content`.
- **Mistral**
  - A tool-call id must be **exactly 9 letters/digits**, otherwise the request fails with 422.
  - **Fixed:** ids from another provider are mapped to 9 characters, the same way in the call and in its result.
- **OpenRouter**
  - Sends SSE comment keep-alives (`: OPENROUTER PROCESSING`), which are counted here as `_ping`.
  - Reasoning is set through the `reasoning` object.
- **Anthropic (native API)**
  - Streams SSE events, including `ping`.
  - Tool arguments stream as `input_json_delta`, so the stream never goes silent.
- **Groq, Cerebras, SambaNova, Together, Fireworks, DeepSeek, xAI, Moonshot, Z.ai, MiniMax, HF router, Requesty, Vercel, Poe**
  - All are OpenAI-compatible, and most send tool arguments in one piece.
  - Limits (rpm, concurrency) are kept in Settings.
  - Reasoning keys differ per model: MiniMax uses `thinking_mode`, Kimi uses `thinking`.

## Plan (done ✓ / next)

1. ✓ **File guard.** A file written in this task cannot be shrunk by a forgotten rewrite.
   - The first attempt is refused, and the file's real end is shown to the model.
   - A deliberate repeat goes through, and the old version is kept as a backup.
   - A second break never overwrites the saved file; the cut rewrite is kept beside it as `.cut-rewrite.txt`.
   - A plain continuation is appended.
   - Live writing never touches an existing file that is being rewritten.
2. ✓ After a break, the model sees the saved file's **real end on disk** (1200 characters), not the end it remembers.
3. ✓ Reasoning-off keys for vLLM/NIM, and a reasoning budget for evren.
4. ✓ An unclosed tool call no longer swallows the next one (the search leak), and search queries are cleaned of protocol pieces.
5. ✓ `run`: a command with no output for 120 s, or one that listens on a port, moves to the background so the task is not blocked.
6. ✓ NIM: a tool request whose tool parser fails while streaming is repeated with `stream:false`.
7. ✓ Kimi / Z.ai `thinking:{type}`, Cerebras `reasoning_effort:"none"`, Groq `reasoning_format`, no `frequency_penalty` for xAI reasoning / SambaNova / OpenAI o-series.

## Deep plan per provider (round 2, 2026-11-22)

Each provider was checked against its own current documentation. ✓ = in the code now.

### Anthropic (native Messages API)
- ✓ Thinking follows the model generation (`claude_gen`). Before 4.6 the request uses `budget_tokens`. From 4.6 on it uses `thinking:{type:"adaptive", display:"summarized"}` plus `output_config.effort`; from 4.7 on `budget_tokens` and `temperature` are a 400.
- ✓ Thinking off:
  - Opus 5.5, Fable and Mythos cannot turn it off, so they get the lowest effort instead.
  - Sonnet 5.5 uses `{type:"between_tools"}`.
  - Other models use `{type:"disabled"}`, at effort `high` or below.
- ✓ `eager_input_streaming:true` on every tool, so a file being written streams live instead of arriving as one block after minutes of silence.
- ✓ Stop reasons: `max_tokens` / `model_context_window_exceeded` → truncated (kept and continued, a half tool call salvaged). `refusal` → a clear error with its category.
- ✓ Already in place: `ping` keep-alives, `input_json_delta`, thinking blocks with signatures sent back on tool turns, prompt caching of the system prompt.

### Hugging Face (router.huggingface.co/v1)
- OpenAI-compatible chat completions with tools and streaming. The model id can carry a policy or provider suffix (`:fastest` default, `:cheapest`, `:preferred`, `:groq`, `:together`…). The suffix is passed through unchanged.
- Each backend provider has its own tool and reasoning behaviour. The general OpenAI-compatible path covers it: calls without `index`, `reasoning` / `reasoning_content`, repeated names.

### NVIDIA NIM (integrate.api.nvidia.com)
- ✓ `chat_template_kwargs.enable_thinking` / `thinking` turn reasoning off. `thinking_token_budget` is honoured.
- ✓ Tool arguments are not streamed, and a stream silent for 300 s is closed by NIM. The "Tool call sent whole" watchdog switches such a model to the streamed text protocol. A tool-parser error repeats the request with `stream:false`.
- ✓ Rate limit 40 RPM (the provider's `rpm` setting).

### EVREN (vLLM)
- ✓ vLLM now names the reasoning field `reasoning` (it used to be `reasoning_content`). Both are read.
- ✓ The reasoning-off key depends on the template: `enable_thinking` for Qwen / Nemotron / GLM, `thinking` for DeepSeek. Both are sent.
- ✓ The measured request cap (~194 s) limits `thinking_token_budget`, so writing time is left.
- ✓ Tool calls are parsed only from content (vLLM docs), and are sent whole. The silence watchdogs handle that case.

### Ollama (local) and Ollama Cloud (ollama.com)
- ✓ `/api/chat` with `think` (true/false, or low/medium/high for gpt-oss), native `tools`, and `done_reason:"length"` → truncated.
- ✓ A tool turn goes back with its `thinking` (Ollama docs: return thinking, content and tool_calls together).
- ✓ Ollama Cloud uses Bearer auth (API key). The local CPU options (`num_thread`, local `num_ctx`) are not sent there.
- ✓ Local: `keep_alive`, the memory guard, `prompt_eval_count` counted as a lower bound (cached prefix).

### LM Studio (local, /v1 OpenAI-compatible)
- ✓ Tools on `/v1/chat/completions`. Reasoning arrives in `reasoning` (gpt-oss, newer builds) or `reasoning_content`; both are read.
- The native `/api/v1/chat` has stateful chat and MCP, but custom tools are not documented there. The app stays on `/v1`.

### MCP for every model
- ✓ Every connected server is visible. Up to 40 tools are listed with their arguments, spread fairly over the servers; every other tool is listed by name. Before, a flat first-80 cut hid whole servers.
- ✓ `mcp` with `tool="list"` returns a server's tools with all their arguments.
- ✓ Plain questions keep the `mcp` tool too.
- ✓ With Playwright MCP connected, the model is told it is a second browser, for when a built-in `browser_*` tool keeps failing.

### Model families: provider + model (`backend/app/llm/families.py`)
The provider decides the transport. The **model family** decides how a model reasons and calls tools, whichever provider serves it, so a provider that later adds DeepSeek or Qwen gets the right behaviour without new code.
- **Tool calling.** Families without reliable function calling use the AI IQ 300 text protocol on every provider: DeepSeek-R1, Gemma, small Llama 3.x, Phi. The model profile "native" still overrides this.
- **Reasoning switch on template servers (vLLM, NIM).** Each family gets its own key: Qwen3, GLM, Nemotron and Seed-OSS use `enable_thinking`; DeepSeek V3.1+ uses `thinking`. Families that always reason get no switch: R1, QwQ, `*-thinking`, gpt-oss, MiniMax, Magistral.
- **Sampling.** The model card's sampling is used when nothing else set one: Qwen3 0.6/0.95, Kimi K2 0.6, R1 0.6, Gemma 1.0/0.95, MiniMax 1.0/0.95. Provider rules still drop what a server rejects (Claude 4.7+, OpenAI GPT-5/o, Kimi K2.5+ on Moonshot).
- **Text tool formats read by the parser.**

  | Format | Family |
  |---|---|
  | `<tool>` | AI IQ 300 |
  | `<function=…>` | Qwen3-Coder |
  | `<tool_call>{json}` | Hermes / Qwen |
  | `<tool_call>NAME<arg_key>` | GLM |
  | DSML | DeepSeek |
  | harmony | gpt-oss |
  | `[TOOL_CALLS]` | Mistral |
  | `<|tool_call_begin|>functions.NAME:0` | Kimi K2 (new) |
  | `<minimax:tool_call><invoke name=…>` | MiniMax (new) |
  | `<|python_tag|>{"name","parameters"}` | Llama 3 (new) |

  None of these reach the user as raw text.
- **Request fields of single models.**
  - OpenAI GPT-5/o-series use `max_completion_tokens` and get no `temperature`.
  - Kimi K2.5+ on Moonshot get no `temperature` / `top_p`.
  - Mistral thinking chunks in `content` are parsed.
  - Qwen on Alibaba Model Studio uses `enable_thinking` (a new "qwen" provider).

### Silence watchdogs: where they are
**Settings > Agent > "Model connection"**:
- `stream_timeout` (300 s)
- `first_token_timeout` (300 s: this is the "300-second watchdog")
- `local_stream_timeout` (∞)
- `provider_retries`

**Settings > Agent > "Silence watchdogs"** (new):

| Watchdog | Default |
|---|---|
| Connection check after the answer started | 30 s |
| Connection check before the first token | 45 s |
| Continue a lost stream | 90 s |
| Stopped file stream floor | 90 s |
| Tool call stopped mid-way | 150 s |
| Tool call sent whole | 75 s |

NVIDIA's own 300 s cut happens on the provider side; it is learned per provider (`data/request_caps.json`).

## Sources
- vLLM reasoning outputs: https://docs.vllm.ai/en/stable/features/reasoning_outputs/
- vLLM DeepSeek V3.1 tool parser: https://docs.vllm.ai/en/v0.14.0/api/vllm/tool_parsers/deepseekv31_tool_parser/
- NVIDIA NIM reasoning models: https://docs.nvidia.com/nim/large-language-models/latest/reasoning-model.html
- NVIDIA forum, arguments not streamed / 300 s: https://forums.developer.nvidia.com/t/tool-call-arguments-are-not-streamed-300-s-of-silence-closes-the-stream-with-no-finish-reason-integrate-api-nvidia-com/378789
- NIM 1.12 release notes: https://docs.nvidia.com/nim/large-language-models/1.12.0/release-notes.html
- Gemini OpenAI compatibility + streamed tool_call: https://discuss.ai.google.dev/t/gemini-openai-compatibility-issue-with-tool-call-streaming/59886
- Gemini 3 thought_signature: https://discuss.ai.google.dev/t/openai-api-compatibility-broken-due-to-thought-signature-on-gemini-3-pro-preview/109823
- Mistral 9-character ids: https://github.com/vercel/ai/issues/11802
- vLLM `reasoning` field: https://docs.vllm.ai/en/latest/features/reasoning_outputs/
- Ollama thinking / tool calling / streaming: https://docs.ollama.com/capabilities/thinking.md, https://docs.ollama.com/capabilities/tool-calling, https://docs.ollama.com/capabilities/streaming
- LM Studio REST + OpenAI compat: https://lmstudio.ai/docs/developer/rest, https://lmstudio.ai/docs/developer/openai-compat/tools, https://www.lmstudio.ai/docs/developer/api-changelog
- Hugging Face Inference Providers: https://huggingface.co/docs/inference-providers/index, https://huggingface.co/docs/inference-providers/guides/function-calling
- Anthropic Messages API (thinking, effort, stop reasons): Anthropic's current API reference
- Playwright Python (evaluate, locators, mouse.wheel): https://playwright.dev/python/docs/evaluating, https://playwright.dev/python/docs/api/class-locator, https://playwright.dev/python/docs/api/class-mouse
