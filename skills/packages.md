---
name: packages
title: Install packages and projects
title_tr: Paket ve proje kurulumu
title_en: Install packages and projects
description: Installs what a task needs into the working folder or the system: GitHub projects, Composer (PHP), npm, pip, Go, Cargo packages and Windows / macOS / Linux programs (winget, brew, apt), fast and verified.
description_tr: Görevin ihtiyacını çalışma klasörüne veya sisteme kurar: GitHub projeleri, Composer (PHP), npm, pip, Go, Cargo paketleri ve Windows / macOS / Linux programları (winget, brew, apt); hızlı ve doğrulanmış.
description_en: Installs what a task needs into the working folder or the system: GitHub projects, Composer (PHP), npm, pip, Go, Cargo packages and Windows / macOS / Linux programs (winget, brew, apt), fast and verified.
tools: run, start, write_file, read_file, list_dir, edit_file, web_search, fetch_url, todo
---
Install only what the task needs, prefer the project folder over the system, and verify every install.
Check the tool list in the system prompt first: what is listed is already installed (do not reinstall).

## Project-local (default; nothing changes outside the folder)
| Need | Command (run with argv, cwd = the project folder) |
|---|---|
| GitHub project | `["git","clone","--depth","1","https://github.com/OWNER/REPO.git","REPO"]`; a release file: `gh release download -R OWNER/REPO -p "*.zip"` or fetch the asset URL; then read its README for the build steps |
| PHP | `["composer","require","vendor/package"]` (new project: `composer init -n` or `composer create-project laravel/laravel app`); `composer install` for an existing composer.json. composer is on PATH (the app installs it when PHP is present) |
| Node | `["npm","install","pkg"]` (`npm ci` with a lock file); one-off CLIs: `npx -y pkg` |
| Python | a venv in the folder: `["python","-m","venv",".venv"]` then `.venv` pip install; quick scripts may use the app's own Python, which already has many libraries (see requirements) |
| Go / Rust / .NET | `go get`, `cargo add`, `dotnet add package` |

## System programs (only when the task needs a program, e.g. ffmpeg, ImageMagick, PostgreSQL)
- Windows: `winget install --id <Id> --exact --silent --accept-source-agreements --accept-package-agreements`
  (find the id: `winget search <name>`); fallback `choco install -y` or `scoop install`.
- macOS: `brew install <formula>` (casks: `brew install --cask <app>`).
- Linux: `sudo -n apt-get install -y <pkg>` (dnf / pacman / zypper by distribution). `sudo -n` fails instead of
  waiting for a password: then tell the user the one command to run.
- After installing: the new program may not be on this process's PATH yet. Call it by its full path
  (`where`/`which`, or the winget folder under %LOCALAPPDATA%\Microsoft\WinGet\Packages) and verify with --version.

## Rules
- Non-interactive flags always (`-y`, `--yes`, `-n`, `--no-input`, `--silent`). Long installs: timeout 600.
- A failure: read the error, fix the cause (version, missing dependency, proxy) and retry once differently; never
  loop on the same command.
- Pin versions in composer.json / package.json / requirements.txt so the project installs the same way again.
