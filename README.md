<p align="center"><img src="screenshots/banner.en.png" alt="AI IQ 300 — Autonomous AI Command Center" width="100%"></p>

<p align="center">
  <b>An autonomous AI command center that writes, tests and runs code with local and cloud AI models.</b><br>
  <a href="README.tr.md">Türkçe</a> · <a href="https://github.com/AppsTRDesign">GitHub</a> · <a href="https://wplugins.shop">wplugins.shop</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.8.3-2563eb" alt="version">
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

## 🖼️ Screenshots

| Maps: detail cards, distance from you, directions, dark mode | Review card of every change (tools and commands) and the task's time split |
|---|---|
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
| **PHP** | 8.2+ | Optional | Running PHP projects |
| **WSL2 + Docker** | latest | Optional | Running projects in containers; the planned sandbox |
| **Browser** | Chrome / Edge / Firefox | ✅ Required | The UI |

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

```
backend/   FastAPI · agent orchestrator · agent teams · provider adapters · MCP client · Tree-sitter · process manager · policy
           Playwright screenshots · edge-tts voices
frontend/  React + Vite + Tailwind · Monaco · Zustand · SheetJS · docx-preview
agents/    Agent roles (Markdown)          skills/    Skills (Markdown)
languages/ tr.json · en.json               chat/      Session folders
workspace/ Workspace for chats without a project (generated documents go to workspace/docs/)
tanitim/   Banners, screenshots and promo texts
```

## 🆕 New in v0.8.3 (commands, documents, review, timing, location)

- **Commands at full speed, version-aware:**
  - At start the app detects the OS release and build (e.g. Windows 10 22H2 build 19045), every shell with its version (Windows PowerShell 5.1, PowerShell 7, cmd, Git Bash) and the tools on PATH (git, Node, npm, Python, Java…), and gives this to the model, so it writes commands that exist on this machine.
  - New `argv=[...]` runs a program directly without a shell (git starts in 0.05 s).
  - New shells: `powershell5`, `pwsh`, and `bash` (Git Bash on Windows, never WSL).
  - Multi-line scripts run as script files.
- **The PowerShell layer keeps native meaning:**
  - `rm -rf`, `mkdir -p a b`, `ls -la`, `del /s /q` and `touch` are handled only when written in that style.
  - `ls -Filter *.txt`, `Remove-Item -Recurse` and `dir | Where-Object` go to the real cmdlet unchanged; plain `rm folder` no longer deletes recursively and silently.
  - Failures return real exit codes.
- **Heredocs fixed for good:**
  - A bash heredoc sent to PowerShell runs in Git Bash. Without it, it becomes a file write or piped input.
  - Indented PowerShell here-string endings are repaired.
- **Background processes:**
  - `start` returns as soon as a server prints that it is ready (0.3 s instead of a fixed 6 s).
  - Dev servers no longer take the slots of normal commands; with 9 servers running, commands still start at once.
- **New skill `/host-commands`:**
  - It checks local help, then the vendor docs of the exact version (Microsoft Learn, git-scm, docs.python.org, nodejs.org) before using uncertain syntax.
  - It knows the classic version traps and verifies every result.
- **Where the time goes:**
  - Every task shows its total time, with a split: first reply, model (waiting for the first token), tools per type, team, side calls, waiting to retry, and the app itself.
  - `/api/perf` gives p50/p95/max over recent tasks, `/api/health` a summary.
  - MCP servers no longer hold the first reply for up to 25 s.
- **Change review card:**
  - Every file a task added, changed or deleted in its folder is listed under the answer: by the tools and also by commands, scripts, formatters and package managers.
  - Each row shows its source, +/− lines and a colored diff, and opens in the editor.
  - The snapshot is taken in the background while the model writes its first reply, so it costs no time.
- **Document research:**
  - `read_document` and `fetch_url` read PDF, Word, Excel, PowerPoint, OpenDocument (odt/ods/odp), CSV, text and images, with page, slide, sheet-row or paragraph labels for every quote.
  - Scanned pages are OCR'd with Windows' built-in OCR (offline, about 0.1 s per page, keeps Turkish characters). On Linux/macOS Tesseract or RapidOCR is used.
  - Long documents return the best passages for a question, with their page numbers.
  - Web research reads documents as sources too, in parallel, and reads a dated Wayback copy of a blocked document as a document.
- **Maps with your location:**
  - "Near me" searches use your real position: the browser's location service (Wi-Fi/GPS, asks permission once), or else an approximate one from the internet address, clearly marked.
  - The map page has pro detail cards: rating stars, distance from you, address, today's hours and phone.
  - Each card has Directions from your position, Call, Website and On map buttons.
  - Plus filters, sorting, a "you are here" marker with its accuracy circle, numbered pins and dark mode.
- **Tested:** 21 command-layer checks, 15 new end-to-end checks, and all earlier mock suites.

## 🆕 New in v0.8.2 (teams, web search, maps, guide)

- **Staged agent teams (pipelines):** a team can now run in order. Parts of the same stage work at the same time; a later stage starts when the earlier ones finish and gets their reports, models and file names. Example: team 1 writes an HTML page, team 2 analyzes it, team 3 writes the analysis into Word, each on a different cloud model. If the model forgets to set stages but a part clearly builds on another one ("analyze team 1's HTML"), the parts still run in order. The task board shows a *Stage 1, 2, 3* label on every member. Members can also create documents (Word/Excel/PDF), research the web and search the map.
- **Honest about who did what:** the next turns know exactly which agent ran on which model (and that *Asked another model* is a consultation, not a team), so the model no longer says "we did not really work as a team" afterwards. When you ask for a team, group or several agents, the model uses the team tool instead of doing everything itself.
- **No invented facts:** a question about current facts or sources (prices, news, weather, "with sources") that the model answered from memory is sent back once to be looked up first, so prices and URLs are not made up.
- **Language slips fixed cheaply:** when a reply contains a word in another language (e.g. a Chinese word), only the reply is fixed by a short request. The model does not think a second time, the answer is not written twice and the context does not grow.
- **Much stronger web search:**
  - The search APIs you set up are used first: Google Programmable Search, Yandex Search API, Bing Web Search API, Brave, Tavily, SearXNG.
  - Without them, the free **ddgs** library searches Google, Yahoo, Bing, Yandex and Brave in parallel, together with Wikipedia and Wikidata.
  - As a last resort, a warm background browser (Playwright) runs the same search.
  - Results found by several engines rank higher, and off-topic results are dropped. An engine that answers with unrelated results or a check page is rested for a while. Searches are cached.
  - Pages are read with their structured data (prices, ratings, addresses, opening hours). A page that cannot be read comes from its Wayback Machine archived copy.
  - Settings > Web shows each engine's state when you test a search.
- **Maps and places:**
  - The new `places` tool finds venues around a district, address or coordinates, with distance, address, phone, website and opening hours.
  - It uses free OpenStreetMap, or Google Places / Yandex Places with a key (adds ratings, review counts and price level).
  - It draws an interactive map page you can open in the app.
- **New skills:**
  - `/place-research`: finds places and researches their reviews and prices.
  - `/place-compare`: compares two or more places.
  - `/map-market`: competitor density, gaps, SWOT and a marketing strategy for a location.
  - `/catalog`: product catalogs as Excel, Word/PDF or a searchable web page.
- **A real wiki for the Guide:**
  - Topics in a tree, with search and highlighted matches.
  - An "on this page" list and previous/next links.
  - Full pages on multi-model work, teams, pipelines, quotas, search APIs and maps, in TR/EN.
- **Tested:**
  - Mock suites: 51 scenarios, 53 API checks and the new round-5 checks.
  - Real cloud runs: NVIDIA NIM, Groq, Cloudflare Workers AI and EVREN, with the staged team, places and research.

## 🆕 New in v0.8.1 (reliability and testing)

- **Real token counting:** a bundled tokenizer (offline) plus the provider's own count; tool definitions are counted too. The context meter moves live while the model thinks or writes a long file, and it no longer jumps when the real count arrives.
- **Context compression you can trust:** chats with a few very long messages are compressed too. In-task summaries carry an exact list of the steps already done, so the model does not repeat or invent progress. Summaries are spaced out instead of running every turn.
- **Errors handled like a pro:**
  - A rate limit waits as long as the provider asks (`Retry-After`).
  - A "context too long" error trims and retries instead of failing.
  - A stalled cloud request is cut after 3 minutes and retried.
  - Quota errors switch to the next pool model and continue from the same step.
  - New error texts in TR/EN.
- **Windows commands that just work:**
  - `&&` / `||` chains on Windows PowerShell 5.1.
  - Unix/cmd habits are understood (`rm -rf`, `del a b`, `rmdir /s /q`, `mkdir -p`, `ls -la`, `touch`).
  - A lone `cd` is remembered for the next commands.
  - Real exit codes: before this, a failed build looked successful.
- **New providers:** NVIDIA NIM (build.nvidia.com) and Cloudflare Workers AI (just enter the Account ID and an API token; the models are listed with context size, tools and reasoning). Their error codes are mapped one by one, for example Cloudflare's daily free neurons (3036) wait until midnight UTC, and "paid plan required" (5035) moves on to another model.
- **Cleaner chat:** text the model writes between tool calls is shown as a small work note, not as a reply that disappears.
- **Agent teams:** parts sent as separate calls run as one team. A call that keeps failing the same way is stopped, so there are no endless loops.
- **Leaks fixed:**
  - Finished process records are now limited.
  - The live chat no longer freezes in covered windows (the event queue could grow without limit).
- **Tested** with mock suites and real models (EVREN, OpenRouter, NVIDIA NIM, Cloudflare Workers AI, Groq; error paths live with Gemini 503 and 402 credit errors): leaks, bottlenecks, parallel chats, multi-model teams, model-to-model messages, compression, prompt injection, cancel and security cases.

## 🆕 New in v0.8

- **Web page screenshots** taken by the model when useful, shown inline and opened in the viewer.
- **Image editor** on attachments (arrow, text, shapes, eraser) and a **chat-wide drop zone** for files and folders.
- **Natural voices** (edge-tts) with female/male labels, chosen per language; emoji and symbols are not read.
- **13 pro skills and agents** (researcher, comparer, writer, prompt wizard, skill and agent makers, web research/summary/report, web-to-document, article, prompt, docs) with **token-thrifty tool sets** and a validated `save_catalog` tool.
- **Jump-to-latest** button while a task runs; composer that fits 360 px phones; layout audit with zero findings.
- **Only Ollama enabled by default**; a provider turns on when you save its key. The app works on any port (`run.bat 8400`).

## 🆕 v0.7

- **Diff before approval** on the approval card; present-tense step labels while a change waits.
- **Model profiles** and a realistic **effort setting** based on each model's API data (instruction fallback for local models).
- **MCP client** (stdio + Streamable HTTP) with a settings page, read-only/approval rules and tokens in the secret store.
- **Tree-sitter syntax trees:** exact symbols, code map and `impact` analysis.
- **Parallel agent teams** on the cloud pool with a live **task board**.
- **Voice control:** spoken replies and voice commands (send, stop, approve, deny, new chat).
- **Team messaging and a shared task list** for agent teams; **Anthropic extended thinking with tools**.
- **Active language everywhere:** thinking, plans, notes, team reports and the app's own notes follow the active language (texts come from the language files, so new languages get them too).
- Fixes: Python script calls sent to the python shell run as scripts (no debug loops); claimed-but-not-done edits are caught and done for real; file links without their folder open the right file; the team step shows member names (no raw JSON); short notes before a tool call no longer appear and vanish; errors are kept with the message; an unreachable provider fails in seconds instead of minutes.
- Multi-model pool with automatic switching, per-agent models, `ask_model`, 5-hour/weekly quotas; partial file edits and code search; project memory (`AIIQ.md`); image viewer and in-app browser; retries for busy providers.
- Layout that adapts to narrow windows; faster model lists (400 models: 92 → 0.5 ms), cached symbol maps and an impact analysis ~10× faster on big projects.

v0.6: uninterrupted orchestration, live to-do list, goal mode, automatic skill detection, document cards and preview, drawing pad.

## 🗺️ Roadmap

1. **Full timeline video editor (ffmpeg):** trim, cut, join, text and logo, music, transitions, format conversion; subtitles from speech (faster-whisper) or from given text; preview in the chat.
2. **Stronger image generation:** free Pollinations (FLUX) by default, Hugging Face, Together, OpenAI, Gemini, Stability with a key; detects the wanted format and size and prints text sharply over the image.
3. **Stock image and video services:** Pexels, Pixabay, Unsplash, Openverse, Wikimedia (free) and Shutterstock, Getty, Adobe Stock, Storyblocks (paid, approval with the price on every download).
4. **Optional Docker (WSL2) sandbox:** run commands in an isolated container.

## 👤 Developer

**Onur Öztaş** · [GitHub/AppsTRDesign](https://github.com/AppsTRDesign) · [wplugins.shop](https://wplugins.shop)

> ⚠️ Commands run directly on your computer; the command filter is not a sandbox. The approval mode is the real control. Use **Ask** mode in sensitive environments.
