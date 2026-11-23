# AI IQ 300 - PROJECT_STATE.md

[Türkçe](PROJECT_STATE.tr.md) · **English**

## Project Vision
A full-scale software development and command center: autonomous, multi-agent, working with local and cloud LLMs.

## Current State
- **Date:** 2026-11-21
- **Active task:** v0.16.0 done (connection check of silent streams, paid + free AI video, media model pickers, live model lists without embeddings / retired models, MCP tabs, installer progress). v0.15.1 done (internet drops: detected, shown, tasks wait and resume on the same model; installer offline / proxy handling). v0.15.0 done (step-log fixes, modular orchestrator / registry, pro installer). v0.12.0 done (weak models: plain-text tool calls run, requested files checked on disk, system_info, chat search, model record, LM Studio memory relief, test suite, orchestrator split). v0.11.0 done (full audit: lean prompt, continuity after drops and model switches, RAM / VRAM guard that keeps the model loaded, exact WebSocket reconnects, race fixes). v0.10.7 done (bulk select/delete, abilities from the first message, tool detection in 14 languages, no-split writing). v0.10.6 done (web design + stock_photo, page JS/broken-image testing, context anchored on real counts, local window growth, Markdown live answers). v0.10.5 done (real token data, vision model, settings audit). v0.10.4 done (settings, local GPU, MCP, toolchain, skills). v0.10.3 done (live tests: Evren auto, NVIDIA Nemotron 3 Ultra 550B, Groq).
- **Last major release:** v0.10.0, which added:
  - a professional document engine (Chromium PDF/HTML + KaTeX, designed DOCX/PPTX/XLSX)
  - adjustable stream timeouts and chunked writing
  - resume after interruption with run_state.json
  - parallel tool execution and live todos
  - a multilingual intent table
  - a rich message box with message paging, copy, delete and quote
  - right-click menus and a grouped changes card
  - media players, service cards and a quota/balance screen
- **Earlier:** v0.6, which added:
  - uninterrupted orchestration: resume, heartbeat during silent tool writing, in-task context trimming and summarizing, live context counting, cleanup of stuck steps, guards against repeated calls and unfounded file claims
  - the todo tool with a live to-do list
  - automatic skill detection (use_skill)
  - read-only tools for knowledge questions
  - a search relevance filter and Bing URL resolution
  - live grouped steps
  - context editing from the model picker (synced with settings)
  - toggle popovers, a drawing pad, folder upload and goal mode
  - document cards and preview (xlsx/docx/pdf/pptx)
  - removal of the unneeded docs/ folder from the project root

## v0.18.7 (2026-11-23): Mermaid diagrams, flowchart skill, split system tools, log fixes
pytest 318. Chat diagram checked in the browser (inline, expand, edit code, dark theme, no console errors).
- **Diagrams:** `frontend/src/components/Diagram.jsx` (inline diagram, hover menu, full-screen viewer with zoom / pan /
  fit, Monaco edit mode with live preview, PNG / SVG export); `lib/mermaidText.js` detects pasted Mermaid;
  `lib/diagramTheme.js` is the one theme source, also used by the backend.
- **`render_diagram`** (`backend/app/tools/diagram.py`): headless Chromium + the app's Mermaid build and theme, PNG or
  SVG, through the file-write gate. `generate_image` refuses diagram prompts.
- **Flowchart skill** (`skills/flowchart.md`): type choice, shapes, quoting, subgraphs, semantic classes, checks.
- **WORKFLOW.md / WORKFLOW.tr.md** with diagrams; `screenshots/workflow-*.png` in the READMEs.
- **System tools:** `system_info` (summary / now / all), `hardware_info`, `software_info`, `mobile_info`; date first;
  cached (hardware 30 min, software 10 min) and warmed at startup; drive letter -> physical disk type.
- **Log fixes:** only-todo final turn ends the run (no triple answer); todo merge keeps only finished old items;
  structure-aware babble cut ("Ak" truncation); `<|close|>message` template tokens hidden; near-duplicate search
  brake; MCP tools by their own name; `file_path` / `filename` aliases; glued search results split; identity knows
  the repo and version.

## v0.18.6 (2026-11-22): Google / GitHub integration, skills from other tools' commands
Real-model tested (NVIDIA Nemotron, temp AIIQ_DATA instance). pytest 284.
- **Google:** built-in `google` tool (Google REST APIs with the connected account: Gmail incl. drafts, Drive, Sheets,
  Docs, Calendar, Contacts); google-* MCP servers used when they answer, Developer Preview refusals fall back to it;
  the "enable the APIs" warning comes from a real probe.
- **GitHub MCP:** issue / PR / commit / repo words point at the connected github server; wrong owner -> get_me hint;
  "Did you mean" for missing tool names; an enum value sent to the wrong key is moved to its key.
- **Weak-model guards:** `<arguments>{...}</arguments>` / `<argument name="body">` wrappers unwrapped for every tool;
  unquoted `argv=[...]` / `arguments={...}` attributes read; a nested tool tag in an mcp body reported; google / mcp
  calls over 24K characters cut as a generation loop; account answers without the account tool nudged once; to-do
  no-op loop closed.
- **Skills from commands** (`catalog.skill_source`): `npx skills add owner/repo`, owner/repo, a GitHub URL,
  `hf skills add [name]` (Hugging Face marketplace bucket), `gradio skills add [user/space]` (gradio's skill or one
  generated from a Space's API) open a picker (RepoSkillsModal) on the Skills page or in the MCP form instead of
  failing as an MCP server. `source:` frontmatter makes re-imports update; built-ins never overwritten; files next
  to a skill become fetch_url links; at most 60 at once (each costs ~40 prompt tokens). YAML block descriptions
  (`description: >-`) are parsed.
- **Hardware report -> Drive run (fixed for every model):** `google file=` really uploads a local file (multipart up
  to 5 MB, resumable 8 MB chunks above; plain Drive URL turned into the upload one; /files/<id> = PATCH; the size
  Drive reports is checked). `save=` is download-only and a JSON answer never overwrites a .pdf (the earlier run
  replaced a good PDF with 128 bytes of JSON). fetch_url save= refuses a web page under a .pdf / .zip / image name.
  Skill `tools:` lists no longer block the basic tools (run, list_dir, read/write/edit_file, system_info...).
  Parser: an unclosed opening tag ends at the first `<`, `<parameter name=…>` / `<parameter=…>` / `<path>` /
  `<arguments>` blocks become arguments (the step label leaked "…Raporu</h1>"). Appended markup: an orphan closing
  fragment at the seam is dropped and an open table / list is closed. make_doc without a path names the file from
  its title. use_skill takes the name from any argument. Live: NVIDIA Nemotron did it in 4 turns / 24 s, a valid
  3-page PDF uploaded with a matching size; evren:auto too (446 s, one provider stall recovered by continuing the
  saved part). pytest 291.
- **No more thrown-away answers on questions about past work:** "…test ettin?" / "çalıştırdın mı" / "did you run
  it" matched the run-request words, so a finished answer that reported earlier commands in code blocks was erased
  with "a command was written but not run". `checks.asks_for` ignores past-tense / perfect forms (also Turkish
  "test et-" tenses) in every answer-rewriting guard (printed code, command not run, change claims, missing
  deliverables, code not written); the "printed only" guard needs real code (a source block or a command line), not
  pasted output. pytest 294.
- **Final answers no longer stopped by a status poll:** the loop guard turns the 3rd identical result into a failure
  so the model changes course; a poll that exited 0 (`ruflo task status`, 6 times) then counted as "the last command
  failed", the finished answer was erased ("…model bitti diyordu; önce düzeltmesi isteniyor") and the debugger role
  started. Such results carry `repeat_ok`: still a loop note for the model, never an unresolved failure or a debug
  turn. An answer that itself says a step failed / did not finish (`admits_failure`) is kept by the unresolved,
  not-delivered (after one retry) and open-to-do (after one reminder) guards.
- **Commands that leave a background child return at once:** `ruflo daemon start` (a daemon holding the inherited
  pipes) waited the full 10 s after exit each time; the pipes are now read only while output still comes (1.2 s
  quiet). pytest 297.
- **Removing a tool is no longer a string of "errors":** `Remove-Item … -ErrorAction SilentlyContinue` / `2>$null`
  as the last statement exits 0 (PowerShell still set `$?` false); lookups that find nothing (`Get-Command x`,
  `where`, `npm ls -g x`, `pip show`, `Test-Path`, `grep` …) are a result, not a failure; another state-changing
  call between two polls resets the loop count; an app tool typed as a command (`run list_dir`) runs the tool. The
  error playbook covers paths with spaces split into two arguments and npm EUSAGE from `@latest`. Opening a file
  outside the work folder shows a toast instead of an uncaught 403 in the console.
- **From the 8300 history scan:** MCP arguments with raw line breaks / a sentence after the object (long Linear /
  Notion bodies) are parsed; `head` / `tail` work in PowerShell; browser js code with a top-level `return` or an
  IIFE runs. A vendor call wrapper split between two stream chunks (`</minimax:` + `tool_call>`, nemotron on NVIDIA)
  showed as a note: every short tag-shaped tail is now held until whole and `<x:tool_call>` wrappers are dropped.
  pytest 305.

## Project Status: v0.18.5
Huge files and what comes after them (2026-11-21), for every provider, not per model. Live: NVIDIA Nemotron 3 Ultra
wrote a 152,690-character game in one call (660 s, no break, one doctype), tested it in the browser, fixed its one bug
with edit_file. pytest 199.
- **Live disk write:** a streaming write_file is written into the real file every 2 s (whole lines); after a break
  the written part stays, the model continues from it (append) and a restart is never appended (starts_over /
  trim_overlap: one document, never two doctypes). Salvage undoes todo items ticked without work.
- **Request time limit:** some providers stop sending at ~300 s from the request start without closing the
  connection. Measured on NVIDIA Nemotron 3 Ultra with direct streams (no app logic): with max_tokens=32000 the data
  stopped at 302 s and 308 s (2/2); without it a plain stream ran past 360 s, one with native tools finished normally
  at 697 s, the app's own run streamed 660 s (0/3). The app sends max_tokens only to local models; the user's earlier
  cuts happened without it, so the limit is treated as a provider behaviour, not a model's: learned per provider
  (request_caps.json: one break at a round gateway limit, or two close breaks), the stream is cut 12 s after it (not
  90), files are then written in parts that fit it.
- **Native tool calls only where the provider streams their arguments** (otherwise silent "preparing" phases); text
  protocol elsewhere. Notes to the user follow the UI language (_ui).
- **Self-kill guard:** a model freed a port with `taskkill /f /im python.exe` and killed the app itself mid-task.
  Killing python / node / the app's interpreter by name (taskkill /im, Stop-Process -Name, pkill, killall, wmic,
  Get-Process | Stop-Process) or the app's own PID is refused in every mode; one PID or the stop tool stays possible.
- **Ports:** `python -m http.server 8080` (bare port) is now seen: our old server is replaced, a foreign one gets a
  free port (a second server had bound the same port on Windows and every request went to the broken old one).
- **Browser tools (full audit):**
  - clicks look first (elementFromPoint + getAnimations): a pulsing button is clicked at once, a covered one names
    the layer over it (`covered by <div#cover>`) - 0.2-0.3 s instead of 6 s per click;
  - hold (`hold=800`), drag (`drag="120,0"`, `to:x,y`, onto a ref, in small pointer moves) for click and batch
    (drag / swipe / longpress), key hold (`hold=1500`);
  - js runs several statements, returns `undefined` as such (was null), elements / NodeLists as HTML (were {}),
    Maps / Sets / functions / errors / cyclic objects readably;
  - uncaught errors carry their type and place (`ReferenceError: ... (at index.html:3106:21)`), also in the
    write-time JS check, browser_check and web_screenshot;
  - favicon / apple-touch-icon / source maps / .well-known are no page errors; a failed earlier navigation is not
    reported on the next page; console listing filters them too;
  - browser_batch accepts fences, raw newlines in js code and trailing commas, and says where the JSON broke;
  - numbers as models send them ("3s", "200px", "1.5s" = 1500 ms) never stop a step;
  - opacity-0 screens (a game HUD under its title) are not read as visible;
  - back / forward with no history keeps the page (went to about:blank);
  - ERR_EMPTY_RESPONSE / connection reset / certificate errors explained; scroll / screenshot by a stale ref found
    again; wait text matches the visible copy;
  - browser_check no longer fails on pages that never go network-idle and always closes its Chromium; the window
    closed by the user no longer leaks the Playwright driver; closed tabs free their logs; downloads never overwrite
    each other and failed ones are reported.
- **Todo:** a started server no longer ticks "test in the browser and fix the errors"; items that ask to fix / debug
  or check in the browser are closed only by the model.
- **Playbook:** `timeout /t` (no console) -> Start-Sleep; ERR_EMPTY_RESPONSE / connection closed -> an old broken
  server holds the port, use another one.
- Earlier fixes in this round: system_info clean_text import fallback, MCP _read_stderr crash, MCP search inputs
  touching the divider, /fs/exists instead of a 404 HEAD.

## Project Status: v0.18.4
MCP: backend catalog (mcp_catalog.py, 16 servers, auth "" / oauth / header), /api/mcp-catalog, /api/mcp-registry
(search_servers), /api/mcp/{sid}/call (user runs a tool), tool input_schema in status; Settings MCP catalog with
category + search, registry search, Try modal, Use in chat; composer # trigger (CatalogPicker "#", RichInput
#server/tool chips recognised by shape, paste chipify, mode "mcp" chip, paste of a mode instruction restores chips);
prompt_section(request) puts picked tools first and reports missing ones; orchestrator ensures the picked server.
Search cards (SearchCards.jsx: favicon via icons.duckduckgo.com, lazy) from web_search / research data.results;
stock_photo data.photos grid. SpeedMeter in the trace header (live "speed" event 1/s, avg timing.tps 2 decimals);
steps get t0 / ms, export shows ms + tps. Todo status aliases ("done" -> completed), ticking a missing list ends.
Openverse license_type / mature filter restored (was inside a comment).

## Project Status: v0.18.3
LaTeX in ThinkText (katex on math markers only) + composer MathPreview; tokens/s per turn (streaming gen counter,
usage output when sent) in timing.tps and live step data.tps; stall cut: text max(PROBE_CUT, 6 x tgap, <=150),
thinking max(min(60, PROBE_CUT), ...), re-probe before cutting when the alive answer is >15 s old; finished thinking
keeps 30K characters; uvicorn ws_ping_timeout 60 s. Measured browser load / stress (see README).

## Project Status: v0.18.2
Reasoning view, template designs, gallery (2026-11-21). Raw reasoning measured (deepseek / gpt-oss one block, Nemotron
lines + lists, qwen3.8 paragraphs): ThinkText.paragraphize splits plain blocks; HTML / Markdown / code rendered, no
other decoration. xlsx_design.py (dashboard, budget, pipeline, tracker + Gantt, calendar sheet, scorecard, inventory)
applied in docs_gen._xlsx; template_thumbs.py draws xlsx / pptx thumbnails per layout; doc_templates._sample_html per
document layout. Gallery: STRIP 8 + View all modal (IntersectionObserver, 12 per page), arrows disabled at the ends.
make_doc: refuses the built-in template's name as title; header= / footer= per document (doc_templates.with_lines);
official_letter keeps only sample_header / sample_footer for its thumbnail.

## Project Status: v0.18.1
Streams, templates as real designs, weak-model guards (2026-11-21). pytest 173, mock e2e passed; live: evren qwen3-vl /
auto / deepseek-v4.1-flash / qwen3.8-flash, NVIDIA Nemotron 3.5 Super, Gemini, Groq, Cloudflare.
- **Stall cuts (streaming.py, router._heartbeat):** measured EVREN sends file arguments in 5-12 s batches; the probe
  cut healthy streams at 4 x gap (48 s). Now: PROBE_CUT 90, cut = max(90, 8 x gap), never while SSE keep-alives
  arrive (heartbeat idle events carry `keepalive`), MIDCALL_STALL 150; a thought stopped mid-sentence (token pace
  `tgap`) is continued after max(45, 6 x tgap); phase `think_stalled`; "no data" / end of live reasoning only after
  max(15, 2 x gap) s.
- **Reasoning view (ThinkText.jsx, thinkfmt.thinkParts):** a light parser (line breaks, basic HTML -> Markdown,
  headings, bold/italic, lists, tables, quotes, links) + code in CodeBlock (Monaco); open fences stay plain text;
  thinking steps 10/s. Live box, note and saved "Thought" all use it.
- **Templates (doc_templates.py):** 35 built-ins, 8 layouts (report, letter, memo, academic, magazine, invoice,
  resume, minimal) with font_family, margins (@page + pdf), header / footer lines (`**bold**`), logo (data/
  doc_templates/assets), own CSS (clean_css). docs_gen.TEMPLATE_SPEC drives PDF (`layout_body`, footer template),
  DOCX (plain_cover, h2 / table styles, footer lines, logo), PPTX (look: dark / hero / split / minimal / corner /
  band) and XLSX (header look solid / dark / band / soft / lines). Gallery thumbnails = `_real_page` (the engine).
  doc_template: inspect (palette, fonts, `_page_facts` lines with zone / align / mm, `save_reference_images`: page
  PNG + logo crops without guide lines), create (layout, margins, header, footer, logo, css, font_family), preview
  (PNG). Template instruction = design only; make_doc refuses repeated filler and the sample outline as headings.
- **Broken PDF font maps (docread):** `broken_chars` (U+FFFD, private use, a lone other-script letter in words) +
  OCR of the page + `repair_glyphs` voting per code; language guessed from the text.
- **Weak models:** skill tool lists bring companions (SKILL_COMPANIONS; /docs gets doc_template); delivery / promise
  checks run in skill-limited tasks (`work_mode`); `_same_as_before` sends a word-for-word repeated answer back;
  `_list_cut` ends comma-list loops; `request_core` keeps app instructions out of auto to-dos; old tool outputs keep
  up to 16K characters on large windows.
- **UI:** sent / copied mode messages show chips (meta.chips, chipsFromText); file chips only for files that exist
  (HEAD); reload returns to the same chat and viewer (sessionStorage aiiq_tab); all viewers preloaded; model pickers
  open on the selected model; landscape PDFs, KPI fit, short tables kept whole.
- **Other:** system_info `now` (date, time, weekday, zone) and the time in the prompt; MiniMax / Moonshot / Z.ai /
  Requesty / Vercel / Poe / Baseten direct URLs (DIRECT_NOW migration).

## Project Status: v0.18.0
Document templates, mode chips, made-vs-found steps, readable errors (2026-11-20). pytest 158, e2e 54/54.
- **Document templates** (tools/doc_templates.py): 14 built-in (PDF / DOCX: design report, experiment analysis,
  investment memo, project proposal, meeting notes, résumé; XLSX: analytics dashboard, financial budget, operating
  calendar, project tracker; PPTX: business review, market trends, operating review, pitch deck) + the user's own in
  data/doc_templates. A template id is a make_doc theme (colours in docs_gen.THEMES, type / cover CSS in
  TEMPLATE_CSS) and an outline. make_doc `template=`, tool `doc_template` (list / create / delete; Template Creator).
  API: GET /api/doc-templates, GET /api/doc-templates/{id}/preview (real HTML thumbnail), DELETE.
- **Composer modes** (ComposerModes.jsx): the (+) entries (image, promo video, AI clip, image to video, web shot,
  Word / PDF / Excel / PowerPoint) are coloured chips; the instruction goes with the message. Document modes open the
  template gallery (iframe thumbnails, Create template = Template Creator chip + brief). Image to video opens a picker
  of the chat folder's pictures, attachments and uploads.
- **Step kinds**: generate_image = image_gen, generate_video / animate_image = video_gen, edit_video = video_edit,
  inspect_media = inspect, text_to_speech = speech, speech_to_text = transcribe (was "Photo searched" / "Visual
  test"); a finished reasoning step says "Thought".
- **Reasoning rendering**: single line breaks kept (hard breaks), <br> and escaped \n become breaks.
- **Errors**: `providers.message_of` reads every error shape (Gemini's JSON list, Python repr, Cloudflare errors,
  nested) - no JSON in the UI; services use it too. UI: a translated hint per cause (high demand, per-minute, daily
  quota, GPU quota, payment, missing / retired model, timeout, safety, auth); the raw text under "technical detail".
- **Model lists**: Gemini only by its chat naming (code-named gemini-4-hydrogen etc. hidden: minutes without an
  answer); `_chat_by_meta` uses the listings' own fields (Together type, Mistral capabilities.completion_chat, Groq
  active, kind); NOT_CHAT_EXTRA (davinci / babbage, moderation, sora, dall-e, tts, whisper, ...).
- **AI video fallback**: a paid service's model that is not found is replaced by its other models; Spaces that added
  a required argument (last_image) get it empty; clips are made one at a time (a lock: parallel calls raced for the
  free GPU quota).
- **Media in chat**: the cards use the full video player and the waveform audio player (inline: no autoplay,
  keys only when hovered); the viewers' chunks are preloaded (an update no longer reloads the page on open); the
  studio's render result kept restarting every few seconds (Date.now() in the src) - fixed.
- **Voice of a file**: after "use this voice" the tone panel opens (speed, pitch, emotion, studio) and writes again.
- **Delivery check**: lines that say a file was NOT made are not counted as claims.

## Project Status: v0.17.1
Fixes from real runs (2026-11-20). pytest 147, e2e 54/54.
- **Drafts per chat** (lib/drafts.js, Composer): text + attachments of each chat's composer kept in localStorage,
  restored when the chat opens again, after a reload or a power cut; images get their base64 back from
  GET /api/sessions/{sid}/upload/raw. A new chat created by its first upload keeps its draft.
- **Reasoning rendering** (lib/thinkfmt.js): unfenced HTML / code in reasoning becomes fenced blocks with a language,
  pipe tables get their |---| line; the live box and the saved "Thinking" step render Markdown (the step was a <pre>).
- **edit_video**: `narration` as an object / text / .mp3 becomes one voiceover (an object crashed with KeyError 0 =
  "Missing required argument: 0" and the voice was dropped); the result says "NO voice-over" when there is none.
  The run's KeyError message now says a value may have the wrong shape.
- **speech_to_text**: audio decoded with ffmpeg (faster-whisper's PyAV reader broke on PyAV 19: metadata_errors).
- **Delivery check**: claimed file names are matched without Turkish letters / case (`checks.real_path`,
  `fold_name`); the final answer gets the real path (`fix_claimed_names`) instead of a false "not created" note.
- **Voices**: preview buttons pause when pressed again; Chatterbox install progress follows the package and model
  folder sizes (it stood at 60 % during the 3 GB model download).

## Project Status: v0.17.0
Local studio voices and pro selects (2026-11-20). pytest 144; real tests: 4 Turkish Piper voices + Kokoro installed
and measured, every engine through the API (Piper 0.7 s, Kokoro 1.2 s, Edge 6.7 s per preview), a narrated video
with burned subtitles (-15.3 LUFS). Chatterbox (3 GB model) real test: Turkish 10 s of speech in 33-45 s on the CPU;
own-voice reference followed (output 97 Hz vs reference 103 Hz; the default voice is female). resemble-perth left
PerthImplicitWatermarker None on Windows ("'NoneType' object is not callable"): the worker falls back to a no-op one.
- **backend/app/voice/** (new): `catalog.py` (Piper index + extra Turkish voices fahrettin / fettah / 99eren99,
  Kokoro v1.0 int8, Chatterbox languages, install / remove with progress, gender from pitch: autocorrelation F0,
  < 160 Hz male; measured dfki 97, fahrettin 108, 99eren99 83 = male, fettah 182 = female), `engines.py` (Piper
  SynthesisConfig, Kokoro, Chatterbox through one long-lived worker in its OWN uv venv data/tts/chatterbox/venv
  because chatterbox-tts pins numpy<2 / torch 2.6 / transformers, Edge decoded through ffmpeg), `studio.py`
  (one ffmpeg pass: presets none/natural/podcast/broadcast/video/warm, pitch with tempo kept, room echo, loudnorm),
  `render.py` (sentence split, trimmed pauses, timings -> .srt, "Name: line" dialogs, fallback chain by language +
  gender + engine order; settings `voice`).
- **Wiring:** `tts.synthesize` (spoken replies / previews) and `speech.text_to_speech` go through render; tool
  text_to_speech gained pitch / emotion / pause / studio / speakers / srt; edit_video voice gets the "video" finish,
  `subtitles: true` burns the voice-over sentences in (`_burn_subs`, libass, .srt next to the video).
- **API:** GET /api/voices, POST /api/voices/install (background, progress), DELETE /api/voices/{id},
  POST /api/voices/preview (tone), POST /api/voices/reference (own voice, consent required); /api/tts/voices merged.
- **Installer:** step "voices" (backend/voice_setup.py: fettah + 99eren99 + Kokoro, PROGRESS lines);
  requirements: piper-tts, kokoro-onnx (Chatterbox is installed from Settings, never into .venv).
- **UI:** Settings > Voices tab (VoicesPane.jsx), new VoicePicker (filters, download, engine / quality badges,
  tone sliders), lib/voices.js; `Select` gained a phone bottom sheet, size="sm", dot / icon options; every native
  <select> replaced (media/video model, Video Studio, Logo maker, STT); global CSS for range / checkbox / radio /
  color / file inputs, 16 px fields on phones.

## Project Status: v0.16.1
Shared-settings sync and the Android toolchain in commands (2026-11-20). pytest 137.
- **Cloudflare sync (UI):** an Account ID typed in the image card re-reads the provider's models at once (the
  provider card kept an old "Account ID is not set" error); service badges reload when a key or switch changes
  anywhere; the image card's field shows the stored value after saving. New error code `missing_account` (TR/EN).
- **Android / Kotlin in commands:** `mobile.add_to_run_env` puts data/mobile's Gradle, adb, emulator, sdkmanager,
  Maestro and the JDK on every `run` command's PATH (after the user's own PATH; ANDROID_HOME/JAVA_HOME if unset);
  `system_info` lists the toolchain (`android_kotlin_toolchain`). A model had reported "no Gradle, no Kotlin".
- **PowerShell 5.1 noise:** `tidy_ps_errors` removes the error-record lines (At ...ps1, + CategoryInfo,
  NativeCommandError) that `2>&1` wraps around a program's stderr; `java -version` no longer looks like a failure.

## Project Status: v0.16.0
Media services, live model lists, connection check (2026-11-20). pytest 133, mock e2e 54/54; real tests with the
user's keys in an isolated temp folder (8 cloud providers, 6 Cloudflare image models, stock, a free Wan 2.2 clip).
- **Connection check (streaming.py `_liveness`, router.ping):** a cloud stream silent for 20 s gets a 1-token probe on
  a new connection: alive -> the stream is continued after 30 s (90 s for providers that send tool calls whole), slow ->
  wait, sick -> server error, down -> netwatch / unreachable. UI: `probe_*` texts in the preparing step.
- **Video services (animate.py, services.CATALOG kind video):** Veo (Gemini key), fal.ai, Replicate, Runway, then the
  free HF Spaces as switchable services, one at a time. `/api/video/test/{sid}` (free key check, `?real=true` makes a
  clip). (+) > Image to video. Settings > Web > AI video replaces the old engines card.
- **Media models (tools/mediamodels.py):** per service default + only-that-kind choices (Gemini / Cloudflare live);
  settings media.models / video.models; `/api/media/models/{kind}/{sid}`; Cloudflare FLUX.2 multipart; Imagen predict.
- **Shared keys:** a key typed in a media card turns on the provider and the reverse; one Cloudflare account id
  (`_sync_shared`, startup migration).
- **Model lists:** Gemini native listing (window, thinking, vision, tools); `NOT_CHAT` hides embeddings / speech /
  guards / image-only models everywhere (also OpenRouter output modalities, Cloudflare); `infer_caps` from names;
  retired models (`model_retired`) hidden and requests moved to the named successor (router.stream_chat); OpenRouter
  "reasoning is mandatory" retried with reasoning on; Gemini reasoning_effort incl. "none".
- **MCP:** presets one-click add with on/off and remove; own servers in a separate tab.
- **Installer:** console-safe glyphs, Android setup live progress (`Meter`, `PROGRESS` lines), ETA from real pace.

## Project Status: v0.15.1
Internet drops and the installer (2026-11-20).
- **Net watcher (`backend/app/netwatch.py`):** probes DNS + TCP (or the system proxy) every 10 s, every 3 s while
  offline; offline after two failed probes, online after one good one. Changes go to the UI (`system`/`net` event,
  also in `hello`): a "connection lost" notice that stays, then "back (down N s)".
- **Tasks:** a network error on a cloud model is checked with `check_now()`; when this computer is offline the task
  waits with no time limit (stoppable), uses no retries against the quota, does not switch models and gets no
  "write in parts" hint, then continues on the same model and conversation (`ai_note_back_online`). A stream that
  goes silent while the watcher says offline is cut after 6 s instead of hanging to the stall limit.
- **Tools:** web tools (search, fetch of non-local URLs, image/video generation, TTS...) wait for the connection
  instead of failing; the repeat guard does not refuse the same call after the drop (`tooling._run_tool`).
- **UI:** an "No internet — waiting" box with the time offline in the chat; TR/EN texts; guide section.
- **Installer:** checks the connection first (3 tries), passes the Windows proxy to pip/npm/playwright, continues
  offline with what is installed (`pip --no-index`) and names the missing package; the log has no blank lines.
- **Clean zip:** no `chat/`, `data/`, `workspace/`, cache or dot folders.
- Tests: `tests/test_netwatch.py`; e2e scenario `NETCUT` (simulated drop with `AIIQ_NET_SIM`).

## Project Status: v0.15.0
Round of 2026-11-20: every error in the step logs of long real runs (PHP shop, Kotlin calculator, Android SDK
update; `hatalar/`) traced to its root and fixed, plus the user's requests of the round. pytest 120, mock e2e 43/43.
- **Tag protocol:** a whole file sent as an attribute (`content="..."`, also `old=`/`new=`) is read to its real end
  (`stream_parser.big_attr_call`); before, every app.js write stopped at `cart: '<svg viewBox=` (the first quote).
  DeepSeek's `<｜DSML｜invoke>` calls are parsed; stray `</parameter>`, `</tool>`, DSML pieces never reach notes (held
  across chunks). `todo` takes trailing commas, single quotes, fenced JSON and plain lines (`loose_json`).
- **edit_file:** SEARCH/REPLACE markers must stand on their own line - JS `===` was taken for the divider and wrote
  `=======` into files. An edit or write that would leave markers is refused.
- **write_file:** empty new files, garbled paths (`b u i l d . g r a d l e`), app bookkeeping lines (`[To-do ...]`)
  are refused / removed; broken characters (U+FFFD) and temporary names are reported.
- **No forced 8K splitting:** the "~8,000 characters, this provider drops long calls" notes follow Settings > Agent >
  split writing (off = one call). The 75 s "sends tool calls only at the end" cut is gone (it threw the call away);
  EVREN is known to stream tool arguments.
- **Loops:** a repetition, word salad (`_salad_cut`) or 48K characters of reasoning without an action is cut and the
  turn redone from the sound part (carried reasoning, no-think, repeat penalty) instead of ending the answer.
- **Memory of the task:** files read and not changed since stay whole in the history (a quarter of the window,
  `_kept_reads`); the to-do list (`todo_board`) goes with every model handover, resume and open-items note; an item
  naming several files is ticked only when all are written; a server start ticks its item; a failed command that
  names `file:line` gets those lines from disk (`error_context`).
- **Steering:** messages sent while a task runs arrive together, fenced as the user's words, with the to-do list and
  a short rule (correction / new direction / question); the old carried plan is dropped.
- **Choice, not keywords:** skills are no longer loaded by trigger words; the model sees every skill and agent with
  its purpose and picks (team members can take an agent role). The read-only limit for "questions" is soft: the model
  lifts it with need_tools.
- **Android:** `mobile_env status` returns every path, the installed platforms / build-tools / images, verified
  version sets (compileSdk 36 = AGP 8.11.1 + Kotlin 2.1.21 + Gradle 8.13 + JDK 17/21) and rules; new actions `gradle`
  and `sdk`; Maestro runs in the working folder; an SDK / JDK already on the machine (Android Studio) is used and only
  updated.
- **Shell UTF-8:** PowerShell output, `Get-Content` and Java tools (Maestro) read and print UTF-8.
- **UI:** live reasoning in a fixed-height box that follows the end and closes when thinking ends; long user and
  steering messages fold (Show more / less) with Markdown and code; no Vite chunk warnings.
- **Install / run:** `installer.py` (called by install.bat): steps, progress bar, elapsed / remaining time, log,
  Turkish on a Turkish Windows else English, mobile setup that reuses what exists. `run.bat` / launcher: banner and a
  readable coloured log (polling hidden, `--verbose` shows all).
- **Code layout:** `orchestrator.py` 4,288 -> 1,988 lines (learning, runstate, guards, history, continuity,
  prompting, streaming, tooling); `registry.py` 2,924 -> 459 lines (shell_tools, file_tools, web_tools, media_tools,
  doc_tools, agent_tools). Every name is re-exported; TOOLS keeps its order.

## Project Status: v0.14.3
Continuity round, proven by a 4 h 16 min real run on `evren:qwen3.8-flash-next` (the BakkalX Expo + Express +
admin + iyzico/PayTR task: 301 model turns, 9/9 to-dos, API smoke test 24/24, `tsc --noEmit` 0 errors on both sides,
one dropped connection recovered in 1 s). pytest 102, mock e2e 43/43.
- **Reasoning survives a break:** `_carry_thinking` puts the reasoning of a turn that broke off (pause, timeout, drop,
  model switch) into the next request (`THINK_CARRY`, at most 14K characters, one message, before a continued answer)
  and that request goes without reasoning (`run.no_think`; EVREN: `chat_template_kwargs.enable_thinking=false`, measured
  0 reasoning tokens; `reasoning_effort` is ignored there). Before, every retry thought the whole task through again
  (18 minutes in "thinking" after a few drops). Timeouts / stalls retry the same model twice before a switch.
- **Streaming providers are not "silent writers":** probes showed EVREN streams native tool arguments chunk by chunk
  (2,289 chunks, longest gap 2.7 s). `router.mark_streams_tool_args` learns this per provider (data/streams_args.json);
  such a provider is never cut at 75 s as "sends tool calls only at the end", never switched to the text protocol, and
  wrongly learned entries in stream_tools.json are dropped. The "after thinking" wait text no longer says the provider
  sends at the end.
- **Instant deletes:** chats disappear at once (optimistic list, busy / done toasts); the server stops their tasks in
  parallel, stops their dev servers, deletes rows, publishes `session.deleted` and removes the folder in a worker thread
  (node_modules used to block the whole app). Deleting messages of a working chat stops the task instead of a 409.
  `db.add_message` writes nothing for a deleted chat.
- **No request flood:** `/api/models/health` is pushed by `_health_watch` over the WebSocket only on a change (the page
  asks at start, on focus at most every 30 s, and once a minute); the context panel refetches every 30 s during a task
  instead of every 4 s.
- **system_info part=software:** working folder and its dependency files, shells, CLI tools, app Python packages,
  global npm packages, MCP servers and tools, active search engines, usable stock / image services, GitHub find and
  download routes, skills, agents, commands, providers.
- **Steps as Markdown:** copy or download (.md) buttons on every task's step list (`stepsMarkdown`).
- **Fixes from the live run:** old file bodies in the history become one line (`_gone_body`) - the model copied the
  "first 300 characters + shortened note" shape into new files and four writes were refused; write_file append without
  path goes to the file being written; search_code takes a pattern sent in `regex=`; browser_wait (max 60 s) ends at
  once on a page that stays blank with errors; browser_navigate waits up to 20 s for a local SPA to render; console
  entries carry their URL and the failed requests; the HTML JS check skips server-only references under file://; the
  preparing step names the file (or says the name has not arrived yet).

## Project Status: v0.14.2
Code scan (ruff, pyflakes, ESLint on the front end, pytest 87, mock e2e 43/43) plus a big real-model test: an Expo +
TypeScript "market super app" built end to end on evren glm-5.3 (503 -> evren auto) and gemma-4-31b.
- **Finishing honestly:** `missing_deliverables` also checks source files the request names (`REQUESTED_SOURCE`,
  e.g. `data/mockProducts.ts`); `_on_disk` walks without node_modules / build folders. Correction notes say they come
  from the app and that the next answer must be the complete final answer (the report was replaced by "fixed it").
- **Syntax check on write:** `syntax.syntax_errors` (Python `compile`, other languages tree-sitter) after
  `write_file` / `edit_file` (`_syntax_note`); a broken file stays `unresolved` (`track_syntax`) until it parses.
- **Debug cap per problem:** `max_debug_attempts` restarts after a command that worked or fewer error lines
  (`ran_ok`, `last_err_count`); a converging tsc loop was cut at 5.
- **Shell argv:** `argv` plus `shell=powershell|bash|cmd` whose program is not on PATH (`Move-Item`, `mv`) runs in
  that shell (`_shell_join`) instead of "not installed".
- **Stall limit:** the adaptive 45 s limit of `_heartbeat` no longer applies right after reasoning (EVREN sends a
  tool call only when complete) and its message says when the limit came from the stream's pace.
- **No circuit breaker (user request):** a count of failures never closes the tools any more (`max_debug_attempts`
  is now the same-error threshold, default 3; `STUCK_STOP` removed, `fail_streak` warns every 4). The same error
  again makes the model research it and take an untried route; only identical repeated calls (`round_sigs`) stop.
- **Install anything:** `mobile.install_java` / `mobile_env action=java` (portable Temurin 17 from the Adoptium API
  into data/mobile/jdk, no MSI, no admin; `setup` calls it); `ERROR_PLAYBOOK` for MSI 1618 (portable / wait route).
- **Per-page check:** `BrowserAgent.news()` reports failed requests (4xx/5xx, failed loads) with console errors after
  every page action and asks to fix them first; `browser_check` lists network errors too.
- **Long tasks:** the progress summary lists every file written in the task (exists on disk; edit, never rewrite);
  work rules: plan a step's files and write them all in one reply, then check once.
- **Waiting:** prep phase `after_think` ("finished thinking, writing its answer") instead of "provider may be busy".
- **UI:** jump-to-latest button and video ping no longer drift sideways (keyframes stacked a second -50% on
  Tailwind 4's `translate`).
- **Real-browser final test:** `_verified` no longer counts a started server; only opening the page (browser tools,
  web_screenshot, mobile_env) does. Work rules / SYSTEM_CONTRACT / mobile skill: web and Expo web apps are opened with
  browser_navigate, every console / network error fixed. `PAGE_ERR` holds `HTTP 5xx`, `JS error`, 404 js/css, refused
  bundles and the page-check note. Failed requests are noted at the response event (`BrowserAgent.bad`); request
  log entries for 404 / 500 had no status before.
- **edit_file:** blocks that match are saved, failed ones are reported with the current file (whole when < 7K).
- **todo:** short updates `advance` / `done` / `start` / `add` (`todo_patch`); the per-result reminder no longer asks
  to resend the whole list (26 full-list rewrites in one Expo task).
- **Late round-6 fixes:** `todo_patch` reads numbers in any shape ("4,5,6", "4-8"); `_babble_cut` stops runs of tiny mixed-language lines ("BOOM.", "LFG.", "火.") with a repeat penalty next; edit_file takes any key spelling (`oldText`, `old_str`, nested `changes` / `replacements`); a missing file lists what its folder really has; local pages load with the browser cache off; the live slot shows the latest note only while nothing newer happened; round signatures skip bookkeeping calls (`BOOKKEEPING`) and only 6 identical rounds close the tools.
- **Chat media:** local-file links in answers (`[x](screenshots/a.png)`) open in the app (as plain links they navigated to the app's own page and the chat looked reloaded); answer images are capped at 460×256; task screenshots are a compact scroll row (phone shots in a phone frame, desktop shots in a browser frame). `wrong_language` also catches other Latin languages (a French answer in a Turkish chat); `ERROR_PLAYBOOK` for Windows long-path errors.
- **Promo video:** tanitim/video (TR/EN, 16:9 and 9:16), real panel scenes, Gemini narration, CC BY trailer music.
- **Misc:** `stop` on a process that already ended is not an error; the front end reloads once when a rebuilt
  bundle's hashed files are gone (`vite:preloadError`, 404 stylesheet).
- **Expo:** `ERROR_PLAYBOOK` for `create-expo-app --template typescript` (scaffolds the TypeScript package) and
  `@types/*` 404s; the `mobile-app-test` skill has a scaffold section (`blank-typescript` / `tabs`, `npx expo install`).
- **Other fixes:** fork copies a project-less chat's folder; `messages.jsonl` cleanup skips half-written lines;
  `process_manager` flushes `\r` progress bars over 64 KB and never waits forever on a killed process; `mobile.py`
  (AVD list without log lines, adb missing, timeouts kill); PROJECT_STATE / summary.md headings in English;
  launcher and e2e runner print UTF-8 on Windows consoles.

## Project Status: v0.14.1
- **Mobile testing:** `tools/mobile.py` (status / setup / start / adb / screenshot / Maestro; Android SDK, emulator, Pixel AVD in data/mobile; `java_home()` finds a JDK 17+ outside PATH), `mobile_env` tool (group `mobile`), `backend/mobile_setup.py` called by install.bat / install.sh on request (`AIIQ_MOBILE`), skill `mobile-app-test`.
- **AI video:** `generate_video` (first frame via `imagegen.generate`, then `animate.animate`), `/api/video/engines` (HF Space runtime stage), Settings `VideoEnginesCard`, (+) > Create > AI clip.
- **Tools:** `venv_pip` / `PIP_CALL` rewrite every pip call to the app Python (argv too); `_unquote_arg`; `INSTALL_HINT` for a program not on PATH; `fetch_url save=` + `_download`; `_github_repo` (4th file-by-file read -> ZIP); `cd` from the task folder; `_port_of` / `_port_busy` in `start`; `ERROR_PLAYBOOK` (+ gh auth, wrong flags); `placeholder_marks` in make_doc; `_provider_of` for stock photos.
- **Orchestrator:** `_auto_todo` only ticks the item in progress; todo merge never reopens finished items and keeps one in progress; title only while `title_auto == 1`; `_step` strips `ACTION_ECHO` lines (whole line); connection-lost retry after 1 s; skills auto-load by `triggers:` (docs, video-studio, localhost-project, mobile-app-test).
- **Front end:** `RangeField` ∞ / Off / Auto buttons; `Markdown` img resolver (chat folder); `stripActionEcho`; `RichInput` deferred execCommand; `DocPreview` slide layout (`tools/slides_view.py`: positioned text / pictures / tables / charts, placeholder defaults) and Excel grid (formula bar, merges, widths, fills); guide sections create / testing / settings-buttons.
- **Late fixes (live suite 9/9 on evren auto and gemma-4-31b):** `editing.parse_blocks` accepts block variants, JSON edit lists and unified diffs, `edit_file` takes old/new aliases or the whole new text; `stream_parser.attrs` reads single-quoted tag attributes; the `mcp` tool takes `arguments` as a JSON string plus top-level extras and names missing required ones; `PLACEHOLDER` no longer matches HTML tags; `meta.docs` lists documents made by scripts (preview cards); `_make_title` retries reasoning models with a bigger budget, then the side model; `request_steps` opens the to-do list from numbered requests; sourced-answer agents are told once to research.
- **Big-task fixes (15-20 min real runs on evren auto / gemma-4-31b / glm-5.3):**
  - Model switching and handover: mid-write stalls need `retries >= 2` before `_busy_alternative`; `_heartbeat(adaptive=True)` for cloud providers; quota / payment / plan_required switch without a pool; `HANDOVER` note at every switch point.
  - Loop and overwrite protection: `editing.collapse_repeats` at write / append / salvage plus `_file_loop_check` while streaming (ProviderError `looping`, `run.file_loops` -> `frequency_penalty`); a salvaged path's plain write appends; unread overwrites of files over 1,500 characters are backed up to `.session/backups`.
  - To-do list and testing: `todos_auto` + merge of the model's list; `plan_steps` from a written plan; a one-time to-do nudge at `tool_turns == 4`; `VERIFY_ASK` / `VERIFY_TOOLS` send untested run-and-test answers back once (`ai_note_not_verified`).
  - Tools: `read_file` returns whole lines up to `ctx.read_limit` (15% of the window, 12K-40K) with the next range, and same-range rereads are answered from `read_seen`; `SERVER_CMD` covers `npm run web/preview`, `expo start`, `flutter run`, `artisan serve`; the failed write step's detail is the tool output; `JAVA_HINT` and the `mobile-app-test` skill use the browser first and the package manager only.
  - Front end: `ProviderIssue` and `toolErrorLine` (`te_*`, incl. `te_binary`).
  - Browser: `BrowserAgent.target()` (stale ref -> role + name from `remember_refs`, label / placeholder / exact-text priority, first visible match, hidden reported at once), script click when covered, `dismiss_popups(cookie_only)` for local sites and after the model acted (`acted`), `_batch_step` / `BATCH_ALIASES`; `start` reads the script file of the chat's own server for its port; `stop` takes a port or the only server; repeated no-op `edit_file` fails.
  - `fail_streak` counts one per model turn (`turn_idx` / `fail_turn`); `_summarize_progress` caps the summary at a quarter of what it replaces; the image refusal in `verify.MAKERS` names `stock_photo` / `generate_image`; `CD_ONLY` stops at the line end; `FIELD_NEAR_JS` (a label without for= -> its field); `_target_keys` (element / target / locator).
  - `SCRIPT_ONLY` runs a lone script name with its interpreter; `read_file` describes SQLite files (tables, rows) and refuses other binaries; `Run.outcomes` turns the third identical result of the same call into a failure; `request_parts` opens the to-do list at tool round 3 when the model has none; select options matched by text/value, `browser_form` takes `{label: value}`.
  - `local_page_instead` (web_screenshot, browser_check, browser_navigate): a dead localhost port opens the page's HTML file; `_verified` / `TEST_CMD` (installs are not tests); `files_nudged` (code printed instead of written); `todo` asks for the user's language; `shell=php|python|node` with a file name runs the file.

  - Final round: `SYSTEM_CONTRACT` (prompts) in every work prompt; `PLAN_GATED` + `plan_refusals` (plan gate, request_parts fallback); `_photo_for` removed (image writes refused with the stock_photo call); `round_sigs` loop detector, `counted` (number-only loops), `MEDIA_CAP`, `tools_off`; `failure_signature`; `shrink_old_steps` (older tool traffic shortened, KEEP_RECENT=6); `ctx_peak` -> `context_stats._peak` (ContextPanel `ctx_peak`); `_anchor_images` in make_doc, file: URIs in `docs_gen._image_bytes`; interpreter flags (`shell=php -S ...`) run as `php -S ...`; `PYTHONUTF8` for child processes; `_wait_online`; `test_every_tool_runs_its_own_function`.
  - Then: `APP_MARKS` / `app_placeholder` refuse the app's shortening notes as file content; `page_state` / `PAGE_ERR` hold a task whose page shows an error; `<option>` clicks select in the parent select; confirm() accepted on local sites; `OLD_STEP_MARK` (it collided with `SHRUNK`).

## Project Status: v0.13.0
Media and tooling round, tested live with EVREN `auto` and GLM 5.3; 49 unit tests (`tests/test_checks.py`, `test_media_services.py`, `test_studio.py`, `test_tools.py`) + 43 end-to-end checks.
- **Services (`tools/services.py`):** `CATALOG` of keyed image (HF, Together, OpenAI, Gemini, Stability, Cloudflare) and stock (Pexels, Pixabay, Unsplash) services plus system ones (Pollinations, Openverse, Commons); `run()` tries usable ones in order, `QuotaError` blocks a service until its reset, the system service answers last; usage in `data/service_usage.json`; `/api/services`, `/api/media/test/{id}`, `/api/stock/test/{id}`.
- **Video engine (`tools/video_edit.py`):** timeline JSON (scenes, clips, music, voice, logo, effects, look, aspect), patch format (`scenes{"n":…}`, `clips{"n":…}`, `add_*`, `remove_*`), `numbered_view` (what models see: `#` + clip type), a guard that refuses text styles sent to a non-text clip, free styled text (`free_text`: x/y %, `size_pct`, color, box, outline, shadow, align, animation), `EFFECTS` + `effect_chain`, zoompan/xfade, loudnorm + sidechain ducking, filter graph via `-/filter_complex`; projects saved as `<name>.timeline.json`.
- **Studio API (`main.py`):** `/video/media`, `/video/project` GET/PUT, `/video/render`, `/video/ai` (model patch with one error-fed retry), `/video/voice`, `/api/video/music` (`tools/music.py`, 8 offline styles), `/api/music/library` (Openverse with retry/fallback queries), `/music/download` (+ CREDITS.txt), `/api/stt`, logo endpoints (`tools/logo.py` cut-out). `tools/animate.py`: image-to-video on HF ZeroGPU Spaces via `gradio_client`.
- **Front end:** `VideoStudio.jsx` (stage with draggable/resizable texts and layers, inspector, timeline, `focus()` = click anything to open its settings and jump to it, music library, voice-over, effects preview, live AI log; phone layout: fixed stage / toolbar / timeline + scrolling panel, `pointer:coarse` touch handles), `VoiceLibrary.jsx` (VoicePicker, TTS, STT dialogs), `LogoMaker.jsx`, colorful Create section in the (+) menu, `lib/errors.js` service-error translation; every backend `fail()` code has `err_<code>` in TR/EN.
- **MCP (`mcp_client.py`):** OAuth 2.1 (metadata discovery, DCR, PKCE, `/api/mcp/{id}/oauth`, callback), `split_command` (npx `-y`), `search_servers` (registry, npm, GitHub, official first) behind the `mcp_search` tool.
- **Skills:** `video-studio`, `localhost-project` (any stack on localhost: detect, install runtimes/packages/DB on Win/macOS/Linux, start, test, report). New optional `triggers:` regex in a skill's frontmatter (`catalog.matching_skills`): a matching request gets a "use_skill X first" line in the system prompt.
- **Loops and debugging (real EVREN run on a PHP project):** `checks.ERROR_PLAYBOOK` / `error_playbook()` (routes for common failures); the debug branch counts `same_rounds` and, instead of giving up on the second identical failure, lists the commands already tried and demands a different route (gives up after 3, or 6 with unlimited debugging); `Run.fail_streak` (`STUCK_WARN`=4 note, `STUCK_STOP`=10 tools paused, answer required); `Run.fs_epoch` refuses a repeated `list_dir` / `read_file` / `search_code` when nothing changed; read tools are never added to `run.blocked`. `fetch_url` `save=` + automatic download of archives/installers (`_download`, `DOWNLOAD_EXT`), `_github_repo` turns the 4th file-by-file read of a repository into the ZIP instruction, GitHub API 403/429 explained; `list_dir` paths from the working folder, `_did_you_mean` for missing paths. Skills auto-load by `triggers:` (without narrowing the tools), `ai_note_skill_auto`.
- **Tests:** `tests/conftest.py` points `AIIQ_DATA` at a temp folder before any test module loads and stops the run if the real `data/` would be used (an earlier ordering let a test clear a real key; it was restored). `run_e2e.py` keeps its temp folder with `AIIQ_E2E_KEEP=1`.

## Project Status: v0.12.0
Weak-model round: real tests on EVREN `auto` (cloud) and Ollama Qwen2.5-Coder 7B (local CPU); 43 end-to-end mock checks + 6 unit checks in the repo.
- **Honesty checks (`agents/checks.py`):**
  - `stream_parser.cli_calls`: tool calls written as command lines or function calls (`write_file path="a" content="..."`, `run(shell=..., command=...)`, in or out of a fence) become real calls (`ai_note_cli_calls`). Never in chat-only turns.
  - `missing_deliverables(request, answer, root, since)`: a requested PDF/DOCX/XLSX/PPTX (`DELIVERABLES`, `DELIVER_VERB`) with no such file written in the task, or an output file named in the answer (`CLAIMED_FILE`) that is not on disk -> the model is told twice (`deliver_retries`), then `ai_note_not_delivered_final` leads the answer (`flag_unresolved`).
  - `NOT_FOUND`: a failed command naming a file that no tool wrote -> "create it first with write_file" instead of the web-search hint.
  - `tool_hint(request)`: one line naming `system_info` / `make_doc` for the request (not stored). `TAG_PROTOCOL` shows a right and a wrong call.
- **Degenerate output:** `providers.stream_error` maps "token repeat limit" to `degenerate`; the task loop drops the visible text, retries once with `repeat_penalty=1.18, repeat_last_n=256, temperature=0.4` (passed to Ollama options), then raises `err_degenerate_detail`. A final reply that is one repeated character counts as empty.
- **New tool `system_info` (`tools/sysinfo.py`, group `system`):** CPU, GPU + VRAM, RAM modules, board, BIOS, disks, network, monitors, OS; Windows CIM via PowerShell JSON, Linux lscpu/lspci/lsblk/DMI, macOS system_profiler; serial numbers dropped.
- **Model record (`llm/modelstats.py`, `data/model_stats.json`):** tasks, ok, failed (incl. `fallback` steps = switched away), EMA first-token wait and turn time; `GET/DELETE /api/models/stats` (with `SPEED` read speed); Settings > Multi-model > Model performance; `router.pick` ranks by `rank_key` when `multi_model.prefer_fast` (default on).
- **Search:** `messages_fts` (FTS5, `unicode61 remove_diacritics 2`, triggers, one-time rebuild; LIKE fallback), `GET /api/search`, sidebar `ChatSearch` with highlighted snippets.
- **Light chat pages:** `_light_steps` cuts step details over 2000 chars in paged message responses (`lazy: {mid, i, chars}`); `GET /api/messages/{mid}/steps/{i}`; `ActivityTrace.Step` loads the full step on open. Attachments are read/copied in a thread (`_with_attachments`).
- **LM Studio memory relief:** `router.reload_local(model_id, num_ctx)` (REST unload + load, else `lms` CLI); used by the task's memory branch and by `memguard.watchdog(..., other_local)` at critical memory.
- **Refactor and tests:** `orchestrator.py` split into `prompts.py` (prompt texts) and `checks.py` (language, intents, checks); names re-exported. `tests/e2e/run_e2e.py` + `mock_llm.py` (isolated data dir, `AIIQ_TEST_PORT`), `tests/test_checks.py`.
- **Real results:** EVREN `auto`: chat, file write+run, edit, hardware PDF (`system_info` + `make_doc`, 22 s) all passed. Qwen2.5 7B: chat and the hardware PDF passed (≈7 min on the CPU); its file task first failed by running a script it never wrote (now answered by the `NOT_FOUND` hint). After Ollama was restarted it ran on the GPU (first token 2.8 s instead of 40 s) and produced only "@@@@"; the new `degenerate` handling stopped that in 14 s with a clear error instead of five retries and a stored garbage answer. The file task on a healthy Qwen run was not repeated.

## Project Status: v0.11.0
Full audit (backend and frontend, line by line); tested on a scripted model (27 checks) and on EVREN `auto`, EVREN `glm-5.3`, NVIDIA `nemotron-3-ultra-550b-a55b`.
- **Lean prompt:**
  - `WORK_RULES_LEAN`, `CAPABILITIES_LEAN`, `RULE_TOPICS_LEAN`, `BROWSER_GUIDE_LEAN`, `CHAT_NOTE`; `language_rule(code, lean)`; `hostinfo.prompt_section(short=)`; `tools_prompt(.., lean)` / `tool_schemas(.., lean)`.
  - `lean_for(model, info, mode)`: `agent.prompt_mode` (auto | lean | full); auto = local, window ≤ 32K, or `is_slow` (`data/model_speed.json`: ms to the first token per 1K prompt tokens, learned in `_stream_turn`).
  - Prompt order: static part first (rules, index, core tools); tools of opened groups, environment and state at the end. A lean prompt opens a group only for the request's own words; browser tools need `STRONG_BROWSER`.
  - Chat abilities memory: `.session/abilities.json` (`_abilities_load/_open/_save`): groups used in the last 6 tasks start open; "Already open in this chat" section.
  - Measured (tokens): greeting 1333 → 587; local file task 3361 → 1885; local big task 4825 → 2910; cloud native 4732 → 3129 and 9809 → 6133.
- **Continuity:**
  - `broke()`: at a transient error, a model switch or memory relief the written part of an answer is kept (`CONTINUE_TAG`) and continued; `need_record` adds `_ledger(run)` (`RECORD_TAG`: files written/read, commands, lookups, to-dos, carried calls) once.
  - `_for_model(messages, model, native)`: native tool calls as tags for a text-protocol model; `thinking_blocks` / `extra` only for the model that wrote them (`by`).
  - `_history`: `DIGEST_TAG` digest of messages older than the window; `_overflow` + `compress(keep_recent=window)` fold them into the summary. A failed start compression no longer ends the task.
  - Teams: `_team_board` in the checkpoint, `ctx.team_prior`; `run_team` skips finished parts; `_member` keeps a `log` across model switches.
  - New guard: a file change was asked and no file changed (`FILE_EDIT_ASK`, `ai_note_no_edit`).
- **Memory guard (`llm/memguard.py`):**
  - `reserve(total)`, `limits(total)`, `vram_limits(total)`: scaled to the machine. `vram()`: nvidia-smi, Windows registry + PDH counter (any GPU, any language), Linux sysfs.
  - `watchdog(state, busy, notify, relief)`: app caches (`release_app_memory`) → unused models → smaller window (`shrink`, floor 8K; `_CAPS`) → unload only with `local_guard.emergency_unload`.
  - A running task sees `pressure(model)` in `_stream_turn` (ProviderError `memory`), salvages, shrinks and continues. `steady()` keeps num_ctx stable between requests.
  - `router.stream_chat` gives every local request the same `num_ctx`; local turns get `max_tokens` = room left; Ollama `done_reason: length` → `truncated`.
- **Events:** `EventBus` never raises on a full queue (backlog dropped + `gap`), `boot` id, `last_seq`. `/ws/events`: `hello` (reset), `snapshot` per run (with pending approvals), `process` replay, 15 s pings, `_coalesce`. Client: `socket.js` watchdog, `store.resync`, `boot`.
- **Races:** finalization of `execute` wrapped (`run.finishing`, RUNS always popped); `cancel_run` idempotent; `cancel_session` waits; `orchestrator.shutdown`; `ProcessManager.stop` timeout.
- **Other:** message index (`idx_messages_session`), `db.checkpoint`, settings file cache (`config._read`), `changes` text cache limits, `_Slots.limit` live, `_busy_alternative` respects `cloud_fallback`, `list_all_models` tolerant, `_make_title` call fixed.

## Project Status: v0.10.7
- **Bulk delete:**
  - `POST /api/sessions/delete` reuses the `delete_session` logic for each chat.
  - `POST /api/sessions/{sid}/messages/delete` ({ids} or {all}) clears the messages.jsonl lines, the summary (when summary_upto covers them) and run_state/partial; when the chat is emptied, its `.session` folder.
  - store: `chatSel`/`msgSel`, `toggleSel`, `deleteChats`, `deleteMessages`, `startSelect`, `syncIds` (live id → stored id).
  - A replayed "done" event is not added when the same stored answer is among the last 3 messages.
  - UI: Sidebar "Select", ChatView `Selectable` / `SelectBar`.
- **Abilities:**
  - `CAP_HEAD`; a "What you can do" section, the skills and an `# Agents` list in tool-less turns (and agents in task prompts).
  - intents.json `media` and `design` (14 languages); GROUP_WORDS and RULE_TOPICS extended.
- **Writing:**
  - The `write_file` description no longer asks for splitting; `agent.split_write_chars` (0 = off) adds a split rule to the end of the prompt.
  - An output-limit cut continues with `_salvage` and append; the cut call's partial arguments are kept.
- **Fixes:** `NO_CONF` stable selector (React #185); a `media` settings section; no repeats in the preparing label.

## Project Status: v0.10.6
- **Design:** `RULE_TOPICS["design"]` (a build verb plus a page word) and the `design` tool group (`stock_photo`, `web_screenshot`); `skills/web-design.md`; the `design` group in CAPABILITIES and need_tools.
- **stock_photo:** `tools/stock.py`: Openverse (commercial/modification licenses), then Wikimedia Commons. Pillow re-encodes to a 1600 px JPEG in `images/`; returns author, license and source.
- **Page testing:** `shot.capture` collects pageerror, console errors, requestfailed, HTTP ≥400 and broken `<img>` (naturalWidth 0); `web_screenshot` adds a "Problems found" list.
- **Context:** Ollama usage carries `partial: True` (the cached prefix is not counted); its ratio only grows, and a lower count is a cache hit. `Run.anchor` (model, estimate, real) drives `real_of(est)`; limits use the effective ratio (eff). Reasoning is left out of the live meter and the output count. If a local request still does not fit after trims and summaries: `_grow_local_window(need=...)` with `ai_note_ctx_grown_conv`.
- **Live answer:** `closeMarkdown` (open fence, `**`, `*`, `` ` ``, `~~`, half link); `LiveNote thought` (Brain icon, `.note-thought` two lines); `lastSentence` strips wrappers.
- **RAM guard:** `llm/memguard.py`:
  - `kv_per_token` (GGUF model_info) and `safe_window` = (psutil free RAM + loaded models − 3 GB reserve − weights) / (KV × parallel × KV type).
  - `router.context_info` caps the local max/current and returns `ram`.
  - `execute` raises `no_memory` when the weights do not fit, and adds a note when parallel > 1.
  - `watchdog` (`_ram_guard` in the main lifespan) unloads idle Ollama models below 8% free RAM and the running one below 4%, publishing `model/memory`.
  - `OLLAMA_NUM_PARALLEL` defaults to 1; the UI confirms and warns (TR/EN).
- **Faster stock photos:**
  - `stock.find` searches comma-separated subjects in parallel (`_find_one`).
  - `_english` translates the query; `_score` ranks by title and tags; `_simpler` tries shorter fallback queries.
  - A 30 s `wait_for` limit per subject.
  - `data/stock_cache` (`_from_cache` / `_to_cache`).
- **Loop guard:** `_loop_cut`: when the same sentence appears 4 or more times in the last 4000 characters, the stream is cut with `break` and closed with `stream.aclose()`; an `ai_note_loop` note is added.
- **Leaks:** the web_screenshot label shows the file name instead of a file:// path; shot reports `missing file: <relative>`.
- **Changes card:** `lib/changes.js` (`opsByFile`, `fileCounts`, `liveFiles`); write_file now carries diff, added and removed; ChangesCard reviews in place (no modal: accordions, groups, search, total/by-operation); LiveChanges reuses the card with `live`; new `photo` step kind; `MIDCALL_STALL=120` (salvage and continue when a stream stalls mid-file); `_run_jobs` makes a look at a just-written file wait for the write.
- **Vision:** `describe_for` also works when the vision model is the chat model.
- **Media:**
  - `tools/media_inspect.py` and the `inspect_media` tool.
    - Image: EXIF, palette, brightness, Laplacian sharpness, Haar faces, `docread.ocr_images`.
    - Video: ffprobe, scene key frames, `_sheet`, frame OCR, `describe_for("")`, whisper.
  - Attached images get a local inspection when there is no vision model.
  - `tools/speech.py`: `speech_to_text` (faster-whisper, .srt/.txt) and `text_to_speech` (edge-tts, chunked mp3).
  - New `media` group; RULE_TOPICS media extended.
- **Local lean mode:**
  - `router.native_tools` is False for local models (profile "native" turns it on).
  - `LOCAL_DEFAULT_CTX` is 16K.
  - `_budget` is at most 65% for local models.
  - `LOCAL_HISTORY=12`.
  - On overflow, `_summarize_progress` runs before the window grows.
- **Circuit breaker:**
  - `BUSY_CODES` and `_busy_alternative` (order: fallback_model → pool → `<provider>:auto`, never a local model).
  - The switch happens on the second busy answer or when `run.stalls >= 2`; the first retry waits 5 s.
  - The task start checks `usage_cooldown`; the busy cooldown is 90 s.
  - `MIDCALL_STALL=75`.
- **Voice studio and media cards:**
  - `/api/sessions/{sid}/tts-file` regenerates the file and updates `tts.voice` in the message meta.
  - `OutputGallery`: `MediaCard` (audio/video player) and `VoicePicker` (live previews via `/api/tts`).
  - `workspace.OUTPUT_EXTS` includes audio and video extensions.
- **Transcript:** `speech.table` (Time | Text); `media_inspect` shares the same whisper model.
- **Vision:** small local Ollama vision models that fit in RAM are the last candidate; colour names; OpenCV `<5`.
- **RAM guard 2:**
  - `memguard.commit_free` (GetPerformanceInfo) and `free_memory`; the guard runs every 2 s with 12%/6% thresholds and releases whisper.
  - `threads()` = physical cores − 1, sent to Ollama as `num_thread`.
  - `KEEP_ALIVE` is 10 minutes.
- **Streaming performance:**
  - The reasoning step is sent at most 4 times a second (`think_at`).
  - `StreamSplitter` resumes the search for the closing tag with `_scan`.
  - `PREP_NAME` is searched in the first 600 characters only.
- **One call and stalls:**
  - The salvage note asks for the rest in one call; the `write_file` description sets the split limit at 40K; SPLIT_HINT allows at most two parts (25K).
  - `stalled` code: a model using native tools switches to the text protocol (`silent_writer`); `run.stalls` is counted.
  - Labels: `step_retry_stalled` / `cd_stalled`.
  - Append and salvage steps carry added/diff.
  - `stock._photo_name`: the first photo has no suffix.
  - shot suggests the closest match for a missing file (difflib).
- **Diff view:** `OpDiff`; with several operations the default view is "ops"; "Open in code editor" calls `openFile(path, true)`; VoicePicker uses the current voice.
- **Image generation and abilities:**
  - `generate_image` (Pollinations FLUX) is in the media and design groups; `tools/imagegen.py`: logo-free with a token, `save` writes the picture; test endpoint `/api/media/test`.
  - The media words were widened, and a media request is no longer treated as a read-only knowledge question.
  - `_run_tool` runs a tool of a closed group by opening the group (unless `run.restricted`).
  - Attachments are copied to `attachments/`.
  - `lastSentence` shows about 160 characters plus the sentence being written; the reasoning line has at most 3 lines.
  - The permission button is icon-only below `md`.
- **Atomic writes:** `config.atomic_write` (settings/secrets). VERSION had turned into NUL bytes in a blue screen; fixed.
- **Scan:** pyflakes clean (dead `target` and a needless `global` removed); vite build passes.

## Project Status: v0.10.5
- **Real token data:** `usage` (Ollama prompt_eval_count, OpenAI include_usage, Anthropic input_tokens, Gemini usageMetadata). The per-model ratio is written to `data/ctx_ratio.json` by `_learn_ratio`. Trim/summary limits are converted to real tokens with it. Start-of-task compression uses `LAST_REAL` (the chat's last real prompt size).
- **Overflow:** "exceeds the available context size" was added to the provider BODY_PATTERNS. NATIVE_REJECT switches to the text protocol only on tool-related 400s. OVERFLOW_SIZES reads the real size. `_grow_local_window` raises the window to at least 16K and updates the UI through a model event.
- **Vision model:** `visual.describe_for` (web_screenshot / browser_screenshot description for models that cannot see). `router.supports_images` checks the profile first, then the API cache, then the name.
- **Settings audit:** Ollama `streaming`, Anthropic/Gemini "always streamed", compression threshold 40-95%, cloud_fallback description.

- **Speed and layered prompt:**
  - SYSTEM_CORE (identity + behaviour) and CAPABILITIES (capability map) are the static part.
  - RULE_TOPICS (install, media, markdown) are chosen once per task with `rule_topics`; SCREENSHOT_RULE is added separately.
  - ENV_SECTION + hostinfo moved to the end of the prompt. Skills are listed by name and title.
  - The URL and "take a screenshot" triggers were removed from BROWSER_WORDS.
  - Measured: 9.1K → 4.5K tokens; local task 433 → 180 s.
- **Stalls:** `_heartbeat` does not reset the silence clock on keep-alive pings (the 6-minute evren stall is fixed).
- **Vision:** `visual.describe_for` orders candidates by measured speed and tries them in turn with adaptive time limits; one request at a time (no racing requests); speeds are kept in vision_speed.json, VISION_NAMES come first, and a 180-word description takes 3.5-4 s.
- **Coordination:** `whole_calls` (a big call that arrives in one piece at the end → text protocol for good), `_call_open` (a completed call does not switch the guard off), batching rule + todo together with the first actions, `lane="side"` + `_MAIN_ACTIVE` (side jobs never overlap a task request).
- **Side jobs:** `router.side_model`; on a local model the title goes to a cloud model or no model is called. `browser_screenshot` errors on about:blank.

## Project Status: v0.10.4
- **Settings:**
  - Capability icons in every model selector.
  - A capability card for the fallback and profile models.
  - Every numeric field is a slider plus a number box (RangeField, log scale, reset to automatic).
- **Sync:**
  - /api/models/health runs every 5 s and pauses in hidden tabs.
  - Local servers that start or stop update the model list and error state.
  - A changed settings file is re-read.
  - A successful Test clears the model cache.
- **Local runtime** (llm/local_runtime.py):
  - Ollama environment variables are stored per OS:
    - Windows: HKCU\Environment plus WM_SETTINGCHANGE.
    - macOS: launchctl.
    - Linux: data/ollama_env.json.
  - Ollama can be restarted from the card.
  - LM Studio load options go through REST /api/v1/models/load, or `lms --gpu/--ttl`.
- **MCP:**
  - The mcp_add tool, in the mcp_setup group.
  - A fix for Windows .cmd paths that contain spaces.
  - End-to-end tests with npm, GitHub and PyPI servers.
- **Toolchain:**
  - toolchain.py:
    - static-ffmpeg fallback
    - composer.phar with a SHA-256 check
    - php.ini/PHPRC
    - data/bin and NODE_PATH
  - Installers: install.bat uses winget; install.sh uses brew/apt/dnf/pacman.
- **Skills:** site-test, remote-server, social-media, ads-manager, graphics, mcp-servers, packages, code-review.
- **Next:** timeline video editor, image generation, stock services, optional Docker (WSL2) sandbox.

## Architecture and Folder Layout
- `/backend`: FastAPI, Process Manager, LLM Router, Agents.
- `/frontend`: React, Vite, Monaco, i18n.
- `/agents`: Planner, Coder, Debugger, Tester.
- `/skills`: Markdown skill definitions.
- `/languages`: tr.json, en.json.
- `/chat/<chat id>/`: the working folder of every chat without a project. It holds files, downloads, and the documents made under docs/.
- `/chat/<chat id>/.session/`: the hidden session record. It holds session.json, messages.jsonl, summary.md, PROJECT_STATE.md, uploads/ and scripts/.
- `/chat/projects/`: projects created without choosing a folder.
- `workspace/` was removed in v0.10.3; its contents move automatically on the first start.
- `/tanitim`: GitHub README TR/EN, screenshots, banner, R10 BBCode and HTML promo.

## Completed Features (Done)
- [x] install.bat / run.bat / requirements.txt
- [x] Python 3.12 & Node 26 compatibility
- [x] LLM Router (Ollama, LM Studio, OpenAI, Anthropic, Evren API)
- [x] Background Process Manager (asyncio, WebSocket log stream)
- [x] Monaco Editor integration
- [x] i18n (tr/en) and automatic translation

## In Progress / Planned (TODO)
- [x] Multi-agent swarm architecture (agents chat with each other)
- [x] Self-debugging loop (catch the traceback and fix it automatically)
- [x] Visual feedback (Playwright + Base64 vision model)
- [x] Git automation and time machine (smart rollback)
- [x] Office document generation (PDF, Word, Excel, PPT)
- [x] v0.6:
  - uninterrupted orchestration
  - live to-do list
  - automatic skill detection
  - document preview
  - drawing pad

### Roadmap (revised, by priority)
- [x] Partial file edit tool (`edit_file`), in-project code search (`search_code`), `read_file` line ranges
- [x] Image viewer, in-app browser, retry on transient provider errors, stable system prompt (cache)
- [x] Symbol map (regex: functions/classes/methods, `symbols` tool, code map in project chats)
- [x] Multi-model:
  - automatic switch when a quota is full
  - 5-hour/weekly quota tracking
  - a model per agent and `ask_model`
  - local models never join the pool
- [x] Tree-sitter syntax trees: exact definitions, `impact` analysis (grammars download on first use; regex otherwise)
- [x] MCP client: stdio + Streamable HTTP, Settings > MCP, `mcp` tool, tokens in secrets.json
- [x] Project memory: AIIQ.md rules per project, global rules, `remember` tool
- [x] Guide/Settings/About pages enlarged for wide screens
- [x] Diff view before approval: the approval card shows the diff for a new file, edit, overwrite or delete
- [x] Model profiles, set per model in Settings > Models: thinking, vision input, streaming, tool-call format, temperature, max output
- [x] v0.10.0: document engine rewritten:
  - docs_gen.py turns Markdown/HTML into one shared HTML.
  - Chromium + KaTeX make the PDF and HTML.
  - python-docx; python-pptx with two columns; openpyxl.
  - ReportLab + DejaVu as the fallback.
  - make_doc gained source=, theme= and landscape=.
- [x] v0.10.0: Settings > Security:
  - stream_timeout, first_token_timeout, local_stream_timeout, provider_retries
  - parallel work
  - unlimited steps and debugging
- [x] v0.10.0: interrupted tasks:
  - a run_state.json checkpoint
  - recovery of interrupted tasks at startup, with resume_note
  - a second task in the same chat is blocked (409)
- [x] v0.10.0: stream reliability:
  - agents/intents.json (14+ languages)
  - SSE keep-alive and mid-stream error classification
  - detection of cut-off tool calls
  - write_file append and a rewrite guard
  - leak patterns
- [x] v0.10.0: providers:
  - provider rpm rate limit (NVIDIA 40)
  - account balance (OpenRouter/DeepSeek/EVREN)
  - a real "Try now" button
  - Nemotron 3 1M context
  - fixed late binding of map/search API keys
- [x] v0.10.1: answer guards:
  - promise/announcement guard (is_promise)
  - an "image asked but missing from the document" guard
  - image verification
  - figure evidence check (ctx.evidence)
  - XML-namespaced reading
  - document sources in .doc-sources/
- [x] v0.10.1: documents and the live view:
  - HTML components (kpis, bars, callout, badge, cols) with visuals for DOCX/PPTX
  - steering while running (run.steer)
  - tool results kept on resume (results)
  - model-made titles (title_auto)
  - live timer and preparation phase
- [x] v0.10.1: teams:
  - pool selection (provider TPM, spread across providers, per-stage reservation)
  - tag-protocol team members
  - instant model switch on rate limit
  - shared tasks closed when done
- [x] v0.10.2: partial file recovery after a dropped connection (_salvage, partial_call.json, save_partial)
- [x] v0.10.2: a silent provider switches to the text protocol
- [x] v0.10.2: read_file re-read cache and base64 trimming
- [x] v0.10.2: make_doc advances the todo; parallel writes to different files
- [x] v0.10.2: documents and output:
  - HTML utf-8 meta and preview charset
  - JS error check (js_check)
  - no wildcard path chips
  - DOCX cover, headings and page x/y
  - PPTX section band
- [x] v0.10.2: VERSION + set_version.py
- [x] v0.10.2: vision-model descriptions, language sync, fallback-model scope, step window (60)
- [x] v0.10.2 live test: web_screenshot PDF as A4 pages
- [x] v0.10.2 live test: looks_python (Python code without a shell)
- [x] v0.10.2 live test: completing a todo item closes the earlier open one
- [x] v0.10.3: code and output guards:
  - fenced_commands: run the command written in a code block
  - a code_nudges limit
  - tools/verify.py: no text written into a binary format, and command output is checked
  - unresolved: a failed step is never counted as done
  - ffmpeg -y
- [x] v0.10.3: in full access, delete files and run risky commands without approval
- [x] v0.10.3: VideoPlayer.jsx
- [x] v0.10.3: _own_site: in full access, passwords and buttons without approval on the site named in the request (cards excluded)
- [x] v0.10.3: CAPTCHA handoff in a visible window, continuing automatically once solved (CAPTCHA_STATE_JS); file:// %20 fix
- [x] v0.10.3: pop-ups:
  - DISMISS_JS + AGENT.dismiss_popups close modals and cookie bars on every site
  - cookies are always rejected
  - password and card windows are left alone
  - the browser.dismiss_popups setting
- [x] v0.10.3: workspace/ removed:
  - chats move to chat/<id>/ (+ .session/); projects go to chat/projects/
  - workspace.migrate_layout moves old files on first start and updates project paths in the DB
  - empty state for Files in a new chat
- [x] v0.10.3: kept_answers: an answer is kept when a steering message arrives
- [x] v0.10.3: a message sent as the task ends becomes an automatic follow-up task (skip_user_msg/steer_parts)
- [x] v0.10.3: silent providers: SILENT_TOOL_LIMIT=75, persisted in stream_tools.json
- [x] v0.10.3: the race on the store's started time is fixed
- [x] v0.10.3: SteerMessage and steer-step design
- [x] v0.10.3: hostinfo.os_line plus an environment/capability summary
- [x] v0.10.3: router._Slots: a concurrency queue per cloud provider, serial for 5 min after busy/429
- [x] v0.10.3: providers_default concurrency/free_rpm defaults:
  - Ollama Cloud 1
  - DeepSeek 8
  - Mistral rpm 60, concurrency 2
  - SambaNova rpm 20
  - OpenRouter free_rpm 20
  - HF 2, Cerebras 2, evren 3
- [x] v0.10.3: Parallel requests field on the provider card
- [x] v0.10.4: capability icons in model selectors, RangeField sliders, live sync via /api/models/health
- [x] v0.10.4: Ollama/LM Studio runtime settings
- [x] v0.10.4: mcp_add plus the Windows npx fix
- [x] v0.10.4: toolchain (static-ffmpeg, composer, php.ini), tool setup in install.bat/install.sh, 8 new skills
- [x] v0.10.5: context from real usage data (saved ratios, LAST_REAL), Ollama overflow detection + window growth, vision model on screenshots, settings audit
- [ ] Optional Docker (WSL2) sandbox
- [ ] Full timeline video editor (ffmpeg, faster-whisper subtitles)
- [ ] Strong image generation (Pollinations + keyed services, format/size detection)
- [ ] Stock image/video services (free + paid, approval for paid)
- [x] Parallel agent teams (`team` tool, cloud pool) and a live task board
- [x] Spoken replies (browser speech synthesis, auto-read) and voice command mode (send/stop/approve/reject)
- [x] Messaging between team members and a shared task list (team_message / team_tasks)
- [x] Anthropic: extended thinking with tools (signed thinking blocks are kept)
- [x] Active language everywhere: thinking, notes, plans and team reports; app texts from `ai_*` keys in languages/*.json
- [x] Effort setting: real levels from the API data, otherwise by instruction
- [x] Narrow-screen layout (container queries, sidebar as an overlay under 1024 px)
- [x] v0.8: web page screenshot tool (`web_screenshot`): a thumbnail and viewer in the chat; models without vision get the page text
- [x] v0.8: chat-wide file/folder drop zone; draw/text editor on attached images (original resolution)
- [x] v0.8: natural edge-tts voices (female/male, chosen per language); emoji/symbols are not read; browser voice as fallback
- [x] v0.8: 13 professional skills/agents, a token-saving tool set via `tools:`, `save_catalog` (skill/agent maker)
- [x] v0.8: jump-to-latest button, 360 px message box layout, automatic layout check (zero findings)
- [x] v0.8: only Ollama on by default; a provider turns on when its key is saved; runs on any port (origin check)
- [x] v0.8.1: real token counting (built-in tokenizer, tool definitions included), live context counter, compression that keeps the steps done
- [x] v0.8.1: PowerShell 5.1 compatibility (&&/||, rm -rf, del, persistent cd, real exit code)
- [x] v0.8.1: note view, merged team calls, loop lock
- [x] v0.9.0: chat replies go straight to the chat (reply_mode); identity questions count as chat
- [x] v0.9.0: weak-model calls that use the tool name as a tag (`<research .../>`, `<run>..</run>`) work
- [x] v0.9.0: image editor pans with hand/space/middle button and zooms at the cursor
- [x] v0.8.1: provider errors:
  - Retry-After
  - context overflow recovery
  - cutting stuck cloud requests
  - an answer-without-reading lock
- [x] v0.8.1: NVIDIA NIM and Cloudflare Workers AI providers (error codes mapped)
- [x] v0.8.5: leak-free streaming:
  - thinking, reasoning, a lone `</think>`, harmony
  - GLM and harmony tool calls
  - calls written inside thinking
  - retry on an empty answer
- [x] v0.8.5: key masking in tool output and secrets.json protection
- [x] v0.8.5: a working folder per chat; readable step details (no raw JSON)
- [x] v0.8.5: per-category context with the tokenizer
- [x] v0.8.5: context counter fixes:
  - cached prompt and Cloudflare chunk usage
  - ring/card sync (live value + running model)
  - double scaling and the counter after compression
- [x] v0.8.5: incremental live counting, team member context/tokens, Gemini thought signature
- [x] v0.8.5: hallucination-free compression that keeps the action log and matches the language
- [x] v0.8.5: model info cache (background refresh); folder and prompt work on a worker thread
- [x] v0.8.5: research:
  - more site variety
  - short-page filtering and a time limit
  - no needless browser rendering
  - archive error fix
- [x] v0.8.6: dynamic tool groups + need_tools; short tool definitions in small windows; rule sections per tool
- [x] v0.8.6: compression loop fix (fixed share for the static part, hysteresis, a step only on real gain)
- [x] v0.8.6: Ollama "No user query found" treated as context overflow
- [x] v0.8.6: background browser:
  - new headless mode with a full profile (UA, language, screen)
  - crash recovery, blocked after two crashes
  - the visible window closes at task end
- [x] v0.8.6: "Fast reader" option; Saved sessions card redesigned
- [x] v0.8.7: errors and limits:
  - wait/rate-limit errors appear in the chat at once (countdown)
  - fitting under the TPM 413 limit
  - an agent-call delivery note
- [x] v0.8.7: multiple agents (@a @b), YAML tools list
- [x] v0.8.7: installs and commands:
  - current PATH
  - real winget/download rules
  - web search after an error
  - Start-Process URL note
  - shell=python command-line fix
- [x] v0.8.7: live note/thinking view, command details, md opens in Monaco, provider-prefixed model picker
- [x] v0.8.8: the live task in one fixed area (no flicker or leak display); the action-log echo hidden
- [x] v0.8.8: when "run" is asked and only code is printed, it is really run; to-dos complete at task end
- [x] v0.8.9: agent servers:
  - a stop rule and a start reminder
  - timed automatic shutdown after the task (setting, countdown, paused on a new task)
  - a server started with run moves to the background
  - a stopped task's command is closed
  - orphaned processes are cleaned up at startup

## Key Decisions and Notes
- **Security:** PowerShell commands go through a smart safety filter, even in "Full access" mode.
- **VRAM management:** while 30B/35B models load, background jobs such as FFmpeg are paused, or the model unload mechanism steps in.
- **Anti-bot:** bot protections are never bypassed; a blocked site is reported and the model moves to another source.
- **Token saving:** no needless context between agents; only the diff and the traceback are sent.

## Next Step
Suggested next (by value):
1. An automated test suite in the repository (the scripted model server + the 27 end-to-end checks of this round) and a CI run.
2. Split `agents/orchestrator.py` (3,500 lines) into modules: prompt, context, continuity, guards, run loop.
3. Step details and large diffs stored outside the message row (lazy loading in the UI), SQLite FTS search over chats.
4. Reading speed and failure rate per model shown in Settings > Models; automatic choice of the fastest pool model.
5. LM Studio: KV estimate and window shrink like Ollama (today only Ollama models are resized by the guard).
6. Optional Docker (WSL2) sandbox, timeline video editor, stronger image generation, stock services.
