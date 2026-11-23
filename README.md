<p align="center"><img src="screenshots/banner.en.png" alt="AI IQ 300 — Autonomous AI Command Center" width="100%"></p>

<p align="center">
  <b>An autonomous AI command center that writes, tests and runs code with local and cloud AI models.</b><br>
  <a href="README.tr.md">Türkçe</a> · <a href="https://github.com/AppsTRDesign">GitHub</a> · <a href="https://wplugins.shop">wplugins.shop</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.20.1-2563eb" alt="version">
  <img src="https://img.shields.io/badge/python-3.12-3776ab" alt="python">
  <img src="https://img.shields.io/badge/node-20%2B-339933" alt="node">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555" alt="platform">
  <img src="https://img.shields.io/badge/FastAPI-React-7c3aed" alt="stack">
  <img src="https://img.shields.io/badge/i18n-TR%20%2F%20EN-db2777" alt="i18n">
</p>

---

## ✨ What is AI IQ 300?

AI IQ 300 is a **software development and automation hub** that runs on your own computer behind a clean ChatGPT/Claude-style chat. Give it a goal: it creates folders and files, runs PowerShell/CMD/Python/Node/PHP commands, debugs errors, tests the app in a browser and reports back. Your data never leaves your computer unless you choose a cloud provider.

> Say "build a full e-commerce site in PHP". The project structure, database, UI and tests are built step by step. The model splits the work into a to-do list and you follow every step live in the chat.

## 📊 Benchmark: nine real tasks, scored from real output

Two NVIDIA models ran the same nine tasks in AI IQ 300 (v0.20.1, 2026-11-23, one model at a time). The model's words were not scored. Each check looks at what really exists afterwards: files on disk, hidden tests that run, a real browser clicking the page, documents opened with their own readers, git itself, Mermaid drawing the diagram, every cited web page opened.

| Model | Fully passed | Checks | Time | App errors |
|---|---|---|---|---|
| `nemotron-3.5-super-vl-120b-a12b` | **9/9 (100%)** | 65/65 | 7.6 min | none |
| `nemotron-3-ultra-550b-a55b` | **9/9 (100%)** | 65/65 | 32.8 min | none |

<p align="center"><img src="eval/benchmark/heatmap.en.svg" alt="Task × model: checks passed" width="100%"></p>
<p align="center"><img src="eval/benchmark/time.en.svg" alt="Where the time went, per task" width="100%"></p>

- **Tasks:** a to-do web app tested in a browser, broken Python fixed against hidden tests, a rename across five modules, a Word + PDF report, the connection really cut mid-task, web research with every source checked, a security code review, a Mermaid flowchart, and git branches.
- **What counts is the success rate and no app errors.** The time mostly depends on the provider: 80% of the 550B run was NVIDIA's free queue (about 26 s before each first token). The app itself took 0-1% of the time.
- Full report with hover details: [eval/benchmark/report.en.html](eval/benchmark/report.en.html) (download and open) · data: [results.json](eval/benchmark/results.json) · method and history: [eval/BENCHMARK.md](eval/BENCHMARK.md) · run it yourself: [eval/README.md](eval/README.md).

## 🎬 Promo video

<p align="center"><a href="https://www.youtube.com/watch?v=gSqQ8b9ssGs"><img src="https://img.youtube.com/vi/gSqQ8b9ssGs/maxresdefault.jpg" alt="AI IQ 300 promo video" width="100%"></a></p>

<p align="center"><b>▶ <a href="https://youtube.com/shorts/0TtX10L6p_k">Watch the promo (YouTube 16:9)</a></b> · 🇹🇷 <a href="https://www.youtube.com/watch?v=IxbYD4iCyb0">Türkçe</a></p>

From one sentence to a working app: the command is typed, the agent plans, writes every file in one turn, compiles with `tsc`, opens the app in a **real browser** to check console + network, fixes the error it catches on the spot and delivers a tested result. The video shows the real AI IQ 300 panel, every settings screen, hardware scan and system repair, web research, speech to text / text to speech, documents and the video studio.

<sub>Music: “Epic Trailer” · Soundrider/Dope ([Jamendo](https://www.jamendo.com/track/1670474)) · [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)</sub>

## 🖼️ Screenshots

| **PowerPoint preview: the real slide layout, pictures, thumbnails** | **Excel preview: formula bar, merged cells, sheet tabs** |
|---|---|
| ![PowerPoint preview](screenshots/en-51-pptx-preview.png) | ![Excel preview](screenshots/en-52-excel-preview.png) |
| **Free AI video engines (text / image to video)** | **∞ / Off / Auto buttons next to the sliders** |
| ![AI video engines](screenshots/en-53-video-engines.png) | ![Setting buttons](screenshots/en-54-setting-buttons.png) |

| **Video Studio: drag and style any text on the picture, timeline, live AI edits** | **Studio music: original tracks in 8 styles or a royalty-free library** |
|---|---|
| ![Video Studio](screenshots/en-44-video-studio.png) | ![Studio music](screenshots/en-45-studio-music.png) |
| **Logo maker: AI directions, AI symbols, transparent PNG** | **Text to speech from a free library of 400+ natural voices** |
| ![Logo maker](screenshots/en-47-logo-maker.png) | ![Voice library](screenshots/en-48-voice-library.png) |
| **The colorful (+) menu: a Create section** | **Image generation services with keys, quotas and a free fallback** |
| ![Create menu](screenshots/en-46-create-menu.png) | ![Image services](screenshots/en-49-image-services.png) |

<p align="center"><img src="screenshots/en-50-studio-mobile-dark.png" width="300" alt="Video Studio on a phone"><br><i>Video Studio on a phone: tap anything on the picture or the timeline and its settings open below</i></p>

| **No false "done": a plain warning when the PDF asked for is not on disk** | **Even a weak model makes a real PDF: `system_info` + `make_doc`** |
|---|---|
| ![False "ready" caught](screenshots/en-41-false-ready-caught.png) | ![Hardware report PDF](screenshots/en-40-hardware-pdf.png) |
| **Full-text chat search** | **Model report card: speed and failure rate** |
| ![Chat search](screenshots/en-42-chat-search.png) | ![Model performance](screenshots/en-43-model-performance.png) |
| **Browser agent: opens a real window, fills in a form, takes its own screenshot** | **Guide: the browser agent article** |
| ![Browser agent live trace](screenshots/en-39-browser-agent-trace.png) | ![Guide: browser agent](screenshots/en-38-guide-browser.png) |
| **Settings: browser agent (visible window, saved sign-ins)** | |
| ![Settings: browser agent](screenshots/en-37-browser-settings.png) | |
| Maps: detail cards, distance from you, directions, dark mode | Review card of every change (tools and commands) and the task's time split |
| ![Maps: detail cards, distance from you, directions, dark mode](screenshots/en-32-map-cards.png) | ![Review card of every change (tools and commands) and the task's time split](screenshots/en-33-changes-timing.png) |
| **Guide: reading documents, OCR and page numbers** | **Guide: version-aware commands (dark)** |
| ![Guide: reading documents, OCR and page numbers](screenshots/en-34-guide-documents.png) | ![Guide: version-aware commands (dark)](screenshots/en-35-guide-commands-dark.png) |
| **Staged agent team: HTML → analysis → Word on 3 cloud models** | **Places around a district on an interactive map** |
| ![Staged agent team (3 cloud models)](screenshots/en-30-staged-team.png) | ![Map and places](screenshots/en-31-map.png) |
| **Team messages and shared tasks between models (real run)** | |
| ![Team messages and shared tasks between models (real run)](screenshots/en-36-team-messages.png) | |
| **Wiki guide: topic tree, search, full multi-model pages** | **Web search: your APIs first, then free engines, with each engine's state** |
| ![Wiki guide](screenshots/en-28-guide.png) | ![Web search engines](screenshots/en-29-web-search-dark.png) |
| **Chat & activity** | **While a task runs: live steps and to-dos** |
| ![Chat](screenshots/en-01-chat.png) | ![Live task](screenshots/en-07-live-run.png) |
| **The agent checks its own work with screenshots** | **Draw and write on an image before sending it** |
| ![Agent screenshots](screenshots/en-23-agent-screenshots.png) | ![Image editor](screenshots/en-22-image-editor.png) |
| **Drop files anywhere on the chat** | **Natural voices, female / male** |
| ![Drop files](screenshots/en-21-drop-files.png) | ![Voices](screenshots/en-24-voices-dark.png) |
| **Built-in skills (/)** | **Built-in agents (@)** |
| ![Skills](screenshots/en-25-skills.png) | ![Agents](screenshots/en-26-agents-dark.png) |
| **Diff before approval** | **Parallel agent team and task board** |
| ![Diff before approval](screenshots/en-14-approval-diff.png) | ![Agent team](screenshots/en-18-agent-team.png) |
| **Effort levels from the model's API** | **Model profiles** |
| ![Effort](screenshots/en-15-effort-dark.png) | ![Model profiles](screenshots/en-16-model-profiles.png) |
| **MCP servers** | **Multi-model pool and quotas** |
| ![MCP](screenshots/en-17-mcp-dark.png) | ![Multi-model](screenshots/en-19-multi-model-dark.png) |
| **Project rules (AIIQ.md)** | **Context size from the model picker** |
| ![Project rules](screenshots/en-20-project-rules.png) | ![Model and context](screenshots/en-11-model-context-dark.png) |
| **Document cards** | **Excel preview** |
| ![Documents](screenshots/en-08-docs.png) | ![Excel preview](screenshots/en-09-preview-excel.png) |
| **Word preview** | **Context analytics** |
| ![Word preview](screenshots/en-10-preview-word.png) | ![Context](screenshots/en-02-context-dark.png) |
| **File manager** | **Drawing pad** |
| ![Files](screenshots/en-03-files.png) | ![Drawing](screenshots/en-13-drawing.png) |
| **Providers** | **Plus menu** |
| ![Providers](screenshots/en-04-providers-dark.png) | ![Plus menu](screenshots/en-12-plus-menu.png) |
| **About** | |
| ![About](screenshots/en-05-about.png) | |

<p align="center"><img src="screenshots/en-06-mobile-dark.png" width="280" alt="Mobile"> &nbsp; <img src="screenshots/en-27-mobile-jump-dark.png" width="280" alt="Mobile, jump to latest"><br><i>Mobile view (dark theme); scrolled up, the round button jumps back to the latest message</i></p>

## 🚀 Features

**Agents and orchestration**
- **Real tool use:** Native function calling for Ollama, OpenAI-compatible APIs and Anthropic. A universal parser also recognizes the Qwen-XML, Hermes-JSON and Mistral formats, so raw tool syntax never leaks into the chat.
- **Multi-agent:** Assistant, Planner, Coder, Debugger and Tester roles plus ready-made pro agents: `@researcher` (sourced web research), `@comparer` (product comparison with a table and verdict), `@writer` (articles, also into an existing Word/Markdown file), `@prompt-wizard`, `@skill-maker` and `@agent-maker`. An automatic debugging loop runs when a command fails; `@agent` switches roles.
- **Uninterrupted tasks:** Long jobs run to the end. If the model announces the next step and stops, returns nothing, or leaves to-do items open, the task is continued. Type "continue" to resume an interrupted task where it stopped.
- **Live to-do list:** For multi-step work the model opens a list when it needs one and ticks items off as it goes; the list stays in sync with the chat.
- **Automatic skill detection:** The model picks and loads the matching skill itself; only one line per skill is in the prompt until it is loaded. Built in: `/web-research`, `/web-summary`, `/web-report`, `/web-to-doc` (writes into an existing Word/Excel/Markdown document), `/compare`, `/article`, `/prompt`, `/docs`, `/webapp`, `/git`. An invoked skill applies to the latest request, not to an earlier topic.
- **Token-thrifty tool sets:** an agent or skill can list its tools (`tools:` in its file); while it is in use only those tool definitions are sent, 60–85% smaller, and small models make fewer wrong calls.
- **Skill and agent makers:** `@skill-maker` / `@agent-maker` turn your description into a professional skill or agent, validate it (format, tools, length) and add it to `skills/` or `agents/` with your approval; it can be used at once with `/` or `@`.
- **Web page screenshots:** like Claude, the model takes a screenshot when it helps: after building or changing a page (desktop and phone view), or when you ask how a site looks. Options: device, full page, one element, dark mode, PNG/JPEG/PDF. The image appears as a thumbnail under the steps and opens in the viewer; models that cannot see images get the page's real text, so they never invent what is on it.
- **Goal and plan modes:** In goal mode the model works on its own until the goal is reached; in plan mode it plans first.
- **Agent teams (parallel and staged):** With the multi-model pool on, the model splits a big job into 1–6 parts; each member works on a different cloud model. Independent parts run at the same time; dependent parts run stage by stage, and each later stage gets the earlier results (own tool loop: read, write, edit, run). Members message each other and share a task list (add, claim, finish). A live task board shows each member's model, state, steps, files and report, plus the messages and the shared list.
- **MCP client:** Connect Model Context Protocol servers (stdio commands or Streamable HTTP) in Settings > MCP: GitHub, PostgreSQL, file system, browsers… Their tools are offered to the model in every chat. Read-only tools run without asking, the others ask for approval; tokens stay in the secret store. Crashed servers restart on the next call.
- **Smart code editing:** Partial edits (`edit_file`, SEARCH/REPLACE blocks, indentation-tolerant matching), project-wide code search and line ranges instead of rewriting whole files.
- **Syntax trees (Tree-sitter):** Exact functions/classes/methods for 20+ languages, a code map in every project chat, and impact analysis: before a change the model sees which files use what it touches (matches in comments and strings do not count). Falls back to regex when a grammar is unavailable offline.
- **Smart guards:** Repeated page fetches, false "I created a file" claims, invented absolute paths and replies in the wrong language are corrected automatically. Plain questions get read-only tools, so no unrequested files are written.

**Context and models**
- **Live context:** Context is counted at every step while a task runs. In long tasks old file bodies are trimmed and, if needed, steps are summarized, so a task never breaks because the window filled up. Per-category analytics, compression at an 80% threshold and persistent session summaries.
- **Context size from the model picker:** Change a local model's context with the size chip in the model picker (slider or 8K–262K presets); it stays in sync with Settings and the context panel instantly.
- **31 providers:** Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, NVIDIA NIM, Cloudflare Workers AI, DeepSeek, Mistral, xAI, Together, EVREN and more. Models load per provider in parallel, with tools/vision/thinking badges.
- **Multi-model and quotas:** A pool of cloud models with capability tags. When a quota, credit or rate limit runs out the task continues on the most available model; agents can get their own models; a model can hand a sub-task to another (`ask_model`). 5-hour and weekly usage with reset times and your own limits. Local models never enter the pool.
- **Effort setting:** The gauge menu next to the model shows the reasoning levels the model really supports, taken from its API data: OpenRouter `reasoning.effort`, OpenAI `reasoning_effort`, Anthropic thinking budget, Gemini `thinkingBudget`, Ollama `think`. Models whose API has no such control (most local ones) get the level as an instruction. On Anthropic, extended thinking also works in tool-using tasks (signed thinking blocks are kept across tool turns).
- **Model profiles:** Per model: thinking, image input, streaming and tool-call format (native / tags) on or off, plus temperature and maximum output.
- **Retries:** Busy (503) or rate-limited providers are retried with growing waits before switching models; a task does not die on one error.
- **VRAM-friendly:** Switching to a local model unloads the other local models automatically.
- **Built for slow hardware:** While the model writes a file silently, a "Preparing · N s" indicator shows progress; long generations never time out.

**Workspace**
- **Pro IDE:** Monaco editor, a file manager with a folder tree and type filters, a process panel and a git time machine.
- **Documents with preview:** Word, Excel, PDF and PowerPoint. Generated documents appear as color-coded cards in the chat; click a card or a document path in the reply to preview it inside the app (Excel: SheetJS, Word: docx-preview, PDF: the browser viewer, PowerPoint: slide cards).
- **Drawing pad and image editor:** Pen, line, arrow, rectangle, ellipse, text, eraser, colors, undo/redo. Click an attached image to mark it up; the edited image replaces the attachment at its original resolution (the eraser never touches the photo).
- **Attachments:** File and folder upload (folder structure is kept), drag & drop anywhere on the chat with a full drop zone, paste and voice typing.
- **Web research:**
  - Your search APIs come first: Google, Yandex, Bing, Brave, Tavily, SearXNG.
  - Otherwise free ddgs metasearch (Google, Yahoo, Bing, Yandex, Brave) runs together with Wikipedia and Wikidata, and a warm background browser is the last resort.
  - Results are fused across engines and off-topic ones are dropped. Engines that misbehave are rested.
  - Pages are read with their structured data; archived copies are used for pages that cannot be read.
  - Answers are cited. Bot checks are never solved.
- **Maps and places:**
  - The `places` tool finds venues around a district, address or coordinates: distance, address, phone, website and hours.
  - It uses free OpenStreetMap, or Google/Yandex Places with a key for ratings and reviews.
  - It draws interactive map pages.
  - Skills: `/place-research`, `/place-compare`, `/map-market` (competitors, gaps, SWOT, marketing strategy) and `/catalog`.
- **Project memory:** Per-project rules in `AIIQ.md` (Project rules in the project menu) and global rules in Settings are added to every chat; say "remember this" and the model saves the rule itself.
- **Images and pages:** Generated images open in a zoomable viewer; HTML pages open in an in-app browser.
- **Voice control:** Answers are read aloud automatically or with the speaker under each answer. Natural Microsoft neural voices (edge-tts, free, no key) are listed with a female/male label and chosen per language; offline the browser's voices are used. Emoji, symbols and text emoticons are not read. In voice command mode speech is typed into the box and spoken commands run the app: "send", "stop", "approve", "deny", "new chat", "read", "quiet".
- **Sessions:** Every chat keeps its transcript, summaries, state file and uploads in `chat/<id>-session/`.
- **Safety:** Three permission modes (Ask / Approve for me / Full access). Even in full access, a smart fence guards destructive commands. **Diff before approval:** when a file change needs approval, the card shows exactly what will change (added lines green, removed red; full content for a new file, the content to be deleted for a deletion) before you decide.
- **UI:** Light/dark themes, fully responsive (settings and panels adapt to the width of their own column, so a narrow window never squeezes the text), menus that toggle open/closed on click, a jump-to-latest button while you scroll up, and an automated layout audit (4 widths × TR/EN: no overflow, overlap or controls stuck together); TR/EN built in and new languages translated automatically in one click (agent and skill texts included).

## 📦 Requirements

| Component | Version | Status | Used for |
|---|---|---|---|
| **Python** | 3.12 | ✅ Required | Backend (FastAPI) |
| **Node.js** (with npm) | 20+ (22 LTS recommended) | ✅ Required | Building the UI |
| **Git** | 2.40+ | ⭐ Recommended | Time machine, automatic commits |
| **Ollama** or **LM Studio** | latest | ⭐ For local models (either one) | Running models on your computer |
| **FFmpeg** | 7+ (the app downloads it when missing) | ⭐ Recommended | Video Studio, video tools, speech to text |
| **PHP** + Composer | 8.2+ | Optional | Running PHP projects (the `localhost-project` skill installs it on request) |
| **.NET SDK** | 8+ | Optional | Running ASP.NET projects (classic ASP / ASP.NET Framework: Windows + IIS) |
| **WSL2 + Docker** | latest | Optional | Running projects in containers; the planned sandbox |
| **Browser** | Chrome / Edge / Firefox | ✅ Required | The UI |

> Python packages for the media features come with `requirements.txt`: `gradio_client` (free AI image-to-video), `uv` (Python MCP servers via `uvx`), `edge-tts` (voices), `faster-whisper` (speech to text), `numpy` + `Pillow` (music generator, logo cut-out). Video text uses the system fonts (Arial / Georgia / Impact on Windows and macOS; `install.sh` adds DejaVu on Linux). No new npm packages are needed.

> Syntax-tree grammars download automatically on first use (an internet connection is needed once). Many MCP servers are started with `npx` (Node.js) or `uvx` (Python).
> Don't want local models? Enter a cloud API key (OpenRouter, OpenAI, Anthropic, Gemini, EVREN…) in Settings > Providers.
> Recommended hardware: 16 GB+ RAM. With a GPU, 8 GB+ VRAM for 7B–14B models and 16–24 GB VRAM for 30B+ models. On systems without a supported GPU, 30B MoE models (e.g. `qwen3-coder:30b`) also run on the CPU with 32 GB RAM, just more slowly.

### 🪟 Windows 10 / 11

Run the commands in PowerShell. [winget](https://learn.microsoft.com/windows/package-manager/winget/) ships with Windows 11; or download the installers from the links.

| Component | Download | Install with winget |
|---|---|---|
| Python 3.12 | [python.org/downloads/windows](https://www.python.org/downloads/windows/) — tick **"Add python.exe to PATH"** | `winget install Python.Python.3.12` |
| Node.js LTS | [nodejs.org/en/download](https://nodejs.org/en/download) | `winget install OpenJS.NodeJS.LTS` |
| Git | [git-scm.com/download/win](https://git-scm.com/download/win) | `winget install Git.Git` |
| Ollama | [ollama.com/download/windows](https://ollama.com/download/windows) | `winget install Ollama.Ollama` |
| LM Studio | [lmstudio.ai](https://lmstudio.ai/) | `winget install ElementLabs.LMStudio` |
| PHP 8.2+ | [windows.php.net/download](https://windows.php.net/download/) — unzip and add the folder to PATH | — |
| Docker Desktop | [docs.docker.com/desktop/setup/install/windows-install](https://docs.docker.com/desktop/setup/install/windows-install/) | `winget install Docker.DockerDesktop` |

After installing, reopen the terminal and check the versions:

```bash
python --version
```
```bash
node --version
```

**WSL2 + Docker (optional):**

1. Open PowerShell **as administrator**, install WSL2 and restart the computer:
   ```bash
   wsl --install
   ```
2. Update WSL and check that the default version is 2:
   ```bash
   wsl --update
   ```
   ```bash
   wsl --status
   ```
3. Install Docker Desktop (table above), start it and make sure **Settings > General > Use the WSL 2 based engine** is ticked.
4. Verify it works:
   ```bash
   docker run hello-world
   ```

> Virtualization (Intel VT-x / AMD-V) must be enabled in the BIOS. Details: [learn.microsoft.com/windows/wsl/install](https://learn.microsoft.com/windows/wsl/install)

### 🐧 Linux (Ubuntu / Debian / Fedora)

**Ubuntu 24.04 / Debian 13** (Python 3.12+ in the repositories):

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git curl
```

**Ubuntu 22.04** (Python 3.12 from the deadsnakes PPA):

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update && sudo apt install -y python3.12 python3.12-venv git curl
```

**Fedora:**

```bash
sudo dnf install -y python3.12 git curl nodejs npm
```

**Node.js 22 LTS** (Ubuntu/Debian, [NodeSource](https://github.com/nodesource/distributions)):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
```

**Ollama** ([ollama.com/download/linux](https://ollama.com/download/linux)):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**LM Studio:** download the AppImage from [lmstudio.ai](https://lmstudio.ai/) and make it executable.

**PHP (optional):**

```bash
sudo apt install -y php-cli php-sqlite3 php-mbstring
```

**Docker Engine (optional,** [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)**):**

```bash
curl -fsSL https://get.docker.com | sh
```
```bash
sudo usermod -aG docker $USER
```

Log out and back in, then verify:

```bash
docker run hello-world
```

### 🍎 macOS

With [Homebrew](https://brew.sh/): `brew install python@3.12 node git` · Ollama: [ollama.com/download/mac](https://ollama.com/download/mac) · Docker: [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)

## 🛠️ Installation

`install.bat` / `install.sh` set up everything automatically: the Python virtual environment (`.venv`), the `requirements.txt` packages (FastAPI, Uvicorn, httpx, Playwright, python-docx, openpyxl, reportlab, python-pptx…), Playwright Chromium, and the UI packages plus build.

### Windows

```bash
install.bat
```
```bash
run.bat
```

### Linux / macOS

```bash
chmod +x install.sh run.sh
```
```bash
./install.sh
```
```bash
./run.sh
```

If Playwright's system libraries are missing (Linux):

```bash
sudo .venv/bin/python -m playwright install-deps
```

The app opens at `http://127.0.0.1:8300` (another port: `run.bat 9000` / `./run.sh 9000`). On first start the UI uses your system language (English if there is no translation).

**First model:** with Ollama installed, pull a model:

```bash
ollama pull qwen3-coder:30b
```

or add a cloud provider in Settings > Providers and press **Test**.

## 🧭 Usage

1. Create a project with **+** in the sidebar and pick a folder; the agent writes its output there.
2. Pick the model and the permission mode under the message box; set the context size from the chip in the model picker.
3. Type your request. Use `@coder`, `@tester` for agents and `/webapp`, `/docs` for skills, or let the model choose.
4. Use the **+** menu to add files or folders, draw, or turn on Goal or Plan mode.
5. While a task runs, click the step group for details and follow the to-do list. The context ring shows usage, outputs and background tasks.
6. Click a generated document's card to preview it inside the app.
7. Set the thinking level with the gauge menu next to the model; per-model details are in Settings > Models > Model profiles.
8. Connect tools in Settings > MCP; build a cloud model pool in Settings > Multi-model so the model can switch on quota and form agent teams.
9. Turn on spoken replies in Settings > General and pick a voice (female/male), or click the speaker under an answer.
10. Drop files anywhere on the chat; click an attached image to draw or write on it before sending.
11. Ask how a page looks (or let the model check its own pages): screenshots appear under the steps; click to open them.
12. Use `@skill-maker` / `@agent-maker` to add your own skills and agents.
13. Only Ollama is enabled out of the box; saving an API key for a cloud provider turns it on.

See the in-app **Guide** for details.

## 🏗️ Architecture

> Folder layout and the full feature history: [PROJECT_STATE.md](PROJECT_STATE.md) · [Türkçe](PROJECT_STATE.tr.md)

```
backend/   FastAPI · agent orchestrator · agent teams · provider adapters · MCP client · Tree-sitter · process manager · policy
           Playwright screenshots · edge-tts voices
frontend/  React + Vite + Tailwind · Monaco · Zustand · SheetJS · docx-preview
agents/    Agent roles (Markdown)          skills/    Skills (Markdown)
languages/ tr.json · en.json
chat/      One folder per chat: chat/<chat id>/ (its files) + .session/ (its record); chat/projects/ (projects without a chosen folder)
screenshots/ Banners and screenshots used by this README
```

### 🔀 How a message is handled

> Full workflow with a turn-by-turn sequence and the agent-team flow (GitHub draws the diagrams):
> [WORKFLOW.md](WORKFLOW.md) · [Türkçe](WORKFLOW.tr.md)

<p align="center"><img src="screenshots/workflow-en.png" width="640" alt="AI IQ 300 workflow"></p>

## 🧩 Skills from other tools' commands (npx skills, hf skills, gradio skills)

A skills install command copies `SKILL.md` instructions into an agent's skills folder and exits - it is **not an MCP server**, so it cannot be started as one. AI IQ 300 recognizes these commands and imports them as **Skills** instead:

| Command | What is imported |
|---|---|
| `npx skills add owner/repo` (also `npx -y`, `bunx`, `pnpm dlx`, `yarn dlx`) | Every `SKILL.md` in that GitHub repository, to pick from (`--skill name` comes pre-selected) |
| `owner/repo`, `https://github.com/owner/repo`, `…/tree/main/folder` | The same, the whole repository or one folder of it |
| `hf skills add [name]` | The Hugging Face skills marketplace (25 skills); no name = `hf-cli`, as the `hf` command does |
| `gradio skills add` | Gradio's own skill (building Gradio UIs) |
| `gradio skills add user/space` | A skill generated from that Hugging Face Space's API: every endpoint, its parameters and a ready Python call |

**Where:** paste the command into the import box on the **Skills** page, or into the MCP server form - there the Save button is replaced by **Import skills**. A server card that failed with such a command gets the same button (and the useless server entry can be removed after the import).

**How it works:** a picker lists the skills (grouped, searchable, with descriptions; already imported ones are marked). Each picked skill is saved with its source, so importing again updates it instead of making a copy; a built-in skill with the same name is never overwritten (the new one gets the owner's name in front). Files next to a skill (references, scripts) are listed as links the model opens when the skill points to them. Every skill adds a short line (~40 tokens) to the model's prompt, so the picker shows the total and allows at most 60 at once - pick only what you will use. Flags such as `--global`, `--force`, `--cursor`, `--claude` or `--dest` are ignored: skills always go to the app's own Skills.

## 🆕 Release notes

Latest: **New in v0.20.1 (models follow the app: no runaway turns, no guessed paths, nine-task benchmark)**

What every version brought, from v0.6 to today: **[CHANGELOG.md](CHANGELOG.md)**. Downloads: [GitHub releases](https://github.com/AppsTRDesign/AI-IQ-300/releases).

## 📌 Project status

The full project state (vision, architecture and folder layout, every completed feature by version, open tasks, key decisions, next step) is kept in two languages:

- 🇬🇧 **English:** [PROJECT_STATE.md](PROJECT_STATE.md)
- 🇹🇷 **Türkçe:** [PROJECT_STATE.tr.md](PROJECT_STATE.tr.md)

**Now:** v0.14.1 is complete (mobile app testing with the Android emulator and Maestro, AI clips from text or images, HTML-first documents, pro PowerPoint / Excel previews, sturdier tools: pip into .venv, no loops, ordered to-do lists; big-task fixes: careful model switching with handover, quota switch mid-task, loop and overwrite protection, whole-file reads, translated errors). v0.13.0 is complete (Video Studio with draggable styled texts, live AI edits, effects, AI image-to-video, original and library music, mobile layout; logo maker; voice library with text to speech and speech to text; keyed image and photo services with quota fallback; MCP OAuth and self-install; `localhost-project` skill). v0.12.0 is complete (no false "done": plain-text tool calls are run, the requested file is checked on disk; `system_info` and the right-tool hint for weak models; full-text chat search; model report card; LM Studio memory guard; a test suite in the repo). v0.11.0 is complete (full audit: no stalls, nothing forgotten after drops and model switches, half-size first prompt, RAM / VRAM guard that keeps the model loaded, exact reconnects). v0.10.7 is complete (bulk select and delete, every ability from the first message, tool detection in 14 languages, no-split writing). v0.10.6 is complete (professional web design with real stock photos, pages tested for JS errors and broken images, a context meter anchored on the provider's real counts, no local-window overflow, Markdown-rendered live answers). v0.10.5: context from real token counts, vision model on screenshots, settings audit. v0.10.4: Settings, local GPU tuning, live sync, MCP from npm / PyPI / GitHub, automatic tool setup and eight new skills were all tested live.

| Area | State |
|---|---|
| Settings | Capability icons in every model selector; slider + number for every numeric field |
| Local models | Live detection of Ollama / LM Studio; Ollama env tuning (Vulkan, FP16, flash attention, KV cache) and LM Studio load options |
| MCP | `mcp_add`: npm, PyPI, GitHub-built and remote servers; tested end to end |
| Toolchain | ffmpeg, git, gh, php, composer installed automatically (winget / brew / apt) |
| Skills | site-test, remote-server, social-media, ads-manager, graphics, mcp-servers, packages, code-review |
| Next | Timeline video editor, image generation, stock services, optional Docker sandbox |

## 🗺️ Roadmap

1. **Full timeline video editor (ffmpeg):** trim, cut, join, text and logo, music, transitions, format conversion; subtitles from speech (faster-whisper) or from given text; preview in the chat.
2. **Stronger image generation:** free Pollinations (FLUX) by default, Hugging Face, Together, OpenAI, Gemini, Stability with a key; detects the wanted format and size and prints text sharply over the image.
3. **Stock image and video services:** Pexels, Pixabay, Unsplash, Openverse, Wikimedia (free) and Shutterstock, Getty, Adobe Stock, Storyblocks (paid, approval with the price on every download).
4. **Optional Docker (WSL2) sandbox:** run commands in an isolated container.

## 👤 Developer

**Onur Öztaş** · [GitHub/AppsTRDesign](https://github.com/AppsTRDesign) · [wplugins.shop](https://wplugins.shop)

> ⚠️ Commands run directly on your computer; the command filter is not a sandbox. The approval mode is the real control. Use **Ask** mode in sensitive environments.