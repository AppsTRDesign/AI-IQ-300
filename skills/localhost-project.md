---
name: localhost-project
title: Run and test any project on localhost
title_tr: Her projeyi localhost'ta kur, başlat ve test et
title_en: Run and test any project on localhost
description: Finds or takes any project that needs a local server (Node, Python, PHP, Ruby, Java, Go, Rust, .NET / ASP, static sites, Docker Compose), installs every missing runtime, package and database on Windows, macOS or Linux, fixes the setup, starts it on localhost and tests it end to end in a real browser with a report.
description_tr: Yerel sunucu isteyen her projeyi (Node, Python, PHP, Ruby, Java, Go, Rust, .NET / ASP, statik site, Docker Compose) bulur veya alır; Windows, macOS ya da Linux'ta eksik çalışma ortamını, paketleri ve veritabanını kurar, kurulum hatalarını giderir, localhost'ta başlatır ve gerçek tarayıcıda uçtan uca test edip rapor verir.
description_en: Finds or takes any project that needs a local server (Node, Python, PHP, Ruby, Java, Go, Rust, .NET / ASP, static sites, Docker Compose), installs every missing runtime, package and database on Windows, macOS or Linux, fixes the setup, starts it on localhost and tests it end to end in a real browser with a report.
triggers: localhost|127\.0\.0\.1|yerel sunucu|local (dev )?server|sunucu(yu)? (kur|başlat|ayağa)|(start|run) the (dev )?server|xampp|wamp|mamp|\blamp\b|docker.compose|projeyi (kur|çalıştır|ayağa)|(kur|indir)(up|ip) (çalıştır|başlat|test)|(install|set ?up|run|clone) (and (run|test) )?(the|this|a|my) (repo|project|app)
tools: run, start, stop, write_file, read_file, edit_file, list_dir, search_code, web_search, fetch_url, system_info, browser_navigate, browser_snapshot, browser_find, browser_click, browser_form, browser_type, browser_key, browser_wait, browser_inspect, browser_screenshot, browser_batch, browser_check, web_screenshot, make_doc, todo
---
Goal: the project really answers on http://127.0.0.1:<port> and a test report says what works. Work like a senior
DevOps + QA engineer: fast, one step at a time, read every command's output, fix the cause, never claim "running"
or "passed" without a tool result that shows it (an HTTP 200, a page snapshot, a test runner summary).

## 0. Rules
- Light, user-level installs need no question: language packages (pip / npm / composer / cargo / go / dotnet
  tools), portable zips, a runtime the project cannot start without (PHP, Node, Python, Go, .NET SDK).
- Ask first (one line: what, why, the lighter option) and wait for the answer: database servers (MySQL, MariaDB,
  PostgreSQL, MongoDB, Redis as installed services), XAMPP / WAMP / MAMP stacks, Docker Desktop, IIS or other
  Windows features, anything with sudo or admin rights, services that start with the computer, firewall or hosts
  changes, and anything that deletes data. A runtime that is already installed is never installed again
  (check `--version` first; PHP, Node, Python and git may already be on PATH).
- Lightest database first: SQLite or the project's file storage; then a throw-away Docker container when Docker is
  already running; a real database server install only after the user agrees.
- Keep everything inside the project folder (a venv, node_modules, vendor, a local SQLite file, a `.data/` folder
  for portable databases). Never touch other projects or global configs unless needed and approved.
- Secrets: only test values in `.env`; never print the user's real keys; never commit.
- Long commands (install, build, first migration) run with `run` and a generous timeout; servers and watchers run
  with `start` (they keep running), never with `run`.

## 1. Plan and the machine (todo)
`software_info` once (`system_info` for OS/CPU/RAM): which tools are on PATH (git, node/npm/pnpm/yarn/bun, python/pip/uv,
php/composer, ruby/bundler, java/mvn/gradle, go, cargo, dotnet, docker, mysql/mariadb, psql, mongod, redis-server).
todo list: get project, detect stack, install runtimes, install packages, config + env, database, build, start,
smoke test, browser tests, automated tests, report.

## 2. Get the project
- The user's folder or a path in the chat: use it as is. A Git URL: `run` argv
  `["git","clone","--depth","1",<url>,<folder>]` (no git: the ZIP
  `https://github.com/<owner>/<repo>/archive/refs/heads/<branch>.zip`).
- No project given, only a topic: GitHub search API, no key needed (10/min):
  `fetch_url https://api.github.com/search/repositories?q=<topic>+language:<Lang>&sort=stars&per_page=10`
  (`gh search repos` when gh is installed). Choose by stars, recent pushes, a licence, a README with run steps,
  not archived, and **what it needs to run**: prefer one that runs with SQLite / files and the runtimes already on
  this machine over one that needs a database server. Say the choice and why in one line.
- Get the WHOLE repository in ONE step and read it on disk. Never browse it file by file through
  api.github.com/.../contents, blob or raw URLs (60 API calls per hour without a token, slow, and it loops).
  Fastest: `fetch_url url="https://github.com/<owner>/<repo>/archive/HEAD.zip" save="<repo>.zip"` (saved to disk,
  no git needed), then `tar -xf <repo>.zip` (Windows 10+, macOS, Linux); or `git clone --depth 1`.
- Git missing or not on this shell's PATH: download the ZIP (PowerShell `Invoke-WebRequest -Uri <zip> -OutFile
  p.zip; Expand-Archive p.zip -DestinationPath .`, or `curl -L -o p.zip <zip>` + `unzip`). A ZIP unpacks into
  `<repo>-<branch>/`: list the folder once and use the paths exactly as list_dir shows them.
- Read README / CONTRIBUTING / docs/setup first: the authors' own steps beat guesses. Note the required versions
  (`.nvmrc`, `.node-version`, `engines`, `.python-version`, `pyproject` `requires-python`, `composer.json`
  `require.php`, `.ruby-version`, `global.json`, `go.mod`, `rust-toolchain`).

## 3. Detect the stack (list_dir + read the manifest)
| Marker | Stack | Install | Start (dev) |
|---|---|---|---|
| `docker-compose.yml` / `compose.yaml` | Compose | Docker running | `docker compose up -d --build`, then `docker compose ps` / `logs` |
| `package.json` (`next`, `vite`, `nuxt`, `@angular`, `express`, `nest`, `astro`, `svelte`) | Node | lock file decides: `npm ci` / `pnpm i --frozen-lockfile` / `yarn` / `bun i` | its `dev` or `start` script (`npm run dev -- --port 5173`) |
| `manage.py` | Django | venv + `pip install -r requirements.txt` | `python manage.py migrate` then `runserver 127.0.0.1:8000` |
| `app.py` / `wsgi.py` with Flask | Flask | venv + requirements | `flask --app app run --port 5000` |
| FastAPI in `main.py` / `pyproject` | FastAPI | venv (or `uv sync`) | `uvicorn main:app --port 8000` |
| `streamlit` / `gradio` in requirements | Python UI | venv | `streamlit run app.py` / `python app.py` |
| `artisan` | Laravel | `composer install`, `.env`, `php artisan key:generate` | `php artisan serve --port 8000` (+ `npm run dev` for Vite assets) |
| `wp-config-sample.php` | WordPress | DB + `wp-config.php` | `php -S 127.0.0.1:8000` then the install page |
| `spark` / `bin/console` / `index.php` | CodeIgniter / Symfony / PHP | `composer install` | `php spark serve` / `php -S 127.0.0.1:8000 -t public` |
| `Gemfile` + `config/routes.rb` | Rails | `bundle install` | `bin/rails db:prepare` then `bin/rails s -p 3000` |
| `pom.xml` / `build.gradle(.kts)` | Java / Spring | wrapper first: `./mvnw` / `./gradlew` | `./mvnw spring-boot:run` / `./gradlew bootRun` |
| `go.mod` | Go | `go mod download` | `go run .` (or `./cmd/<name>`) |
| `Cargo.toml` | Rust | `cargo build` | `cargo run` |
| `*.csproj` / `*.sln` / `Program.cs` | ASP.NET Core | `dotnet restore` | `dotnet run --urls http://127.0.0.1:5000` |
| `*.aspx` + `web.config`, `*.asp` | ASP.NET Framework / classic ASP | Windows only | IIS Express / IIS (see 6) |
| only `.html` / `.css` / `.js` | static | none | `python -m http.server 8080` or `npx --yes serve -l 8080` |
Monorepo (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `apps/*`): find the web app and the API it needs, start
both. Front end + back end in one repo: start the API first, point the front end's env (`VITE_API_URL`,
`NEXT_PUBLIC_API_URL`) at it.

## 4. Install missing runtimes (match the version the project asks for)
| Need | Windows (winget) | macOS (brew) | Linux (apt; dnf / pacman similar) |
|---|---|---|---|
| Node LTS | `OpenJS.NodeJS.LTS` (other versions: `fnm` / `nvm-windows`) | `node` or `fnm` | NodeSource / `fnm` |
| pnpm / yarn | `corepack enable` | `corepack enable` | `corepack enable` |
| Python | `Python.Python.3.12` | `python@3.12` | `python3 python3-venv` (`uv python install 3.12` works everywhere) |
| PHP + Composer | `PHP.PHP.8.3` (Composer: the app installs it) | `php composer` | `php-cli php-mbstring php-xml php-curl php-zip php-gd php-sqlite3 php-mysql composer` |
| Ruby | `RubyInstallerTeam.RubyWithDevKit.3.3` | `ruby` (or `rbenv`) | `ruby-full build-essential` |
| Java | `EclipseAdoptium.Temurin.21.JDK` | `temurin@21` (cask) | `openjdk-21-jdk` |
| Go | `GoLang.Go` | `go` | `golang` |
| Rust | `Rustlang.Rustup` | `rustup` | `curl https://sh.rustup.rs -sSf \| sh -s -- -y` |
| .NET SDK | `Microsoft.DotNet.SDK.8` | `dotnet-sdk` (cask) | `dotnet-sdk-8.0` |
| Docker | `Docker.DockerDesktop` (needs WSL2) | Docker Desktop / `colima` | `curl -fsSL https://get.docker.com \| sh` |
After an install, check in a fresh `run` (`node -v`, `php -v`, `dotnet --info`...). Not on PATH yet: use the full
path of the new binary (winget: `%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`) or reopen the shell.

## 5. Packages, config, database, build
- Packages: the lock file's tool and its frozen mode. Python: always a venv in the project
  (`python -m venv .venv`; Windows `.venv\Scripts\python`). Ask the venv what it has before installing:
  `.venv\Scripts\python -m pip list --format=json` (macOS/Linux `.venv/bin/python`), compare with
  requirements.txt / pyproject, install only the missing ones with `.venv\Scripts\python -m pip install ...`, and run
  every project command with that python (a bare `pip` goes into the app's own environment, not the project's). Native build errors: install the build tools
  (Windows: `Microsoft.VisualStudio.2022.BuildTools` with C++; macOS: `xcode-select --install`; Linux:
  `build-essential`), or pick a prebuilt wheel / older pinned version.
- Env: copy `.env.example` / `.env.sample` / `appsettings.Development.json` to the real file, fill only what
  is needed locally (APP_URL, ports, DB). Generate app keys with the framework's command. Missing third-party keys
  (Stripe, mail, maps): use the framework's fake / log drivers (`MAIL_MAILER=log`) or leave the feature off and
  say so.
- Database (prefer what needs no service):
  - SQLite when the framework supports it (Django default, Laravel `DB_CONNECTION=sqlite`, Rails `sqlite3`,
    EF Core `Data Source=app.db`, Prisma `file:./dev.db`).
  - Docker available: `docker run -d --name <proj>-db -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16`
    (MySQL `mysql:8` / MariaDB `mariadb:11`, `mongo:7`, `redis:7`); wait until it accepts connections.
  - No Docker and the project only supports a server database: ask the user first, then install it (Windows
    `winget install PostgreSQL.PostgreSQL.16` / `MariaDB.Server`, macOS `brew install postgresql@16 && brew
    services start postgresql@16`, Linux packages). A PHP / MySQL project can often switch to SQLite through PDO:
    say so as the lighter option.
  - Then the project's migrations and seeds: `migrate`, `db:prepare`, `prisma migrate dev`,
    `dotnet ef database update`, `php artisan migrate --seed`, or import its `.sql`.
- Build what dev mode does not: `npm run build` for SSR / production checks, `./mvnw package -DskipTests` when
  only the jar runs.

## 6. Start it
- `start` the dev command, bound to 127.0.0.1 and a free port (busy: the next one; read the port the server
  prints). Then poll `fetch_url http://127.0.0.1:<port>/` (or the health route) until 200 or a clear error;
  read the server output for stack traces, PHP warnings, failed migrations, missing env.
- Several processes (API + web + worker + queue): start each with its own `start`, in dependency order.
- Classic ASP / ASP.NET Framework (Windows only): IIS Express `winget install Microsoft.IISExpress`, then
  `"C:\Program Files\IIS Express\iisexpress.exe" /path:<folder> /port:8080`; classic `.asp` needs full IIS
  (`dism /online /enable-feature /featurename:IIS-ASP /all`, admin: ask first). On macOS / Linux say they do not
  run there and offer a Windows VM or porting to ASP.NET Core.
- Fix loop: an error → find the cause in the log → fix config / install / code the setup broke → restart → check
  again. Three failed attempts on the same error: stop, report it with the log lines and the options.

## 7. Test
1. Smoke: home, health and main routes return 200; static assets load (no 404s).
2. Fast crawl (`run` python with httpx, parallel): every same-site link, status, response time, broken images.
3. Real browser (browser_* tools, batch where possible): navigation, search, forms and validation, sign-up and
   login with test data, CRUD of the main object (create, list, edit, delete), file upload if any, language
   switch, 404 page. After each page: console errors and failed requests (browser_inspect).
4. Layout: browser_check at 1440 px and 390 px: overflow, overlapping, unreadable text, broken menus.
5. The project's own tests when present: `npm test`, `pytest`, `php artisan test` / `vendor/bin/phpunit`,
   `bundle exec rspec`, `./mvnw test`, `go test ./...`, `cargo test`, `dotnet test`; e2e (`npx playwright test`)
   if configured. Report counts from the runner's summary.
6. API projects: call the main endpoints (`fetch_url` / a python script) with valid and invalid input; check
   status codes and JSON shape; OpenAPI at `/docs` or `/swagger`.

## 8. Report (make_doc or Markdown)
- Summary: works / partly / does not, the URL(s), how to start again (exact commands), test login if created.
- What was installed (name + version) and what was changed in config (files and keys, no secret values).
- A table: area, check, result, evidence (status code, screenshot, log line), severity for failures.
- Problems left and concrete fixes. Leave the servers running unless the user asks to stop them (`stop`).
