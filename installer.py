"""AI IQ 300 installer UI (called by install.bat; standard library only, so it runs before the virtual env exists).

Shows every step with what is being installed, a live progress bar, elapsed time and the estimated time left,
in Turkish on a Turkish Windows and in English everywhere else. A full log goes to data/logs/install-*.log.

    python installer.py            (install.bat passes the Python 3.12 it found)
Environment: AIIQ_MOBILE=1 / 0 answers the mobile question in advance; AIIQ_LANG=tr / en forces the language."""
from __future__ import annotations

import json
import locale
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LOG_DIR = ROOT / "data" / "logs"


# --- language -----------------------------------------------------------------------------------------------------
def ui_lang() -> str:
    forced = os.environ.get("AIIQ_LANG", "").lower()[:2]
    if forced in ("tr", "en"):
        return forced
    if os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x1F:  # LANG_TURKISH
                return "tr"
        except (AttributeError, OSError):
            pass
    loc = (locale.getlocale()[0] or os.environ.get("LANG", "") or "").lower()
    return "tr" if loc.startswith(("tr", "turkish")) else "en"


LANG = ui_lang()
T = {
    "title": ("AI IQ 300 · Kurulum", "AI IQ 300 · Setup"),
    "sub": ("Yerel ve bulut LLM'lerle çalışan otonom yazılım geliştirme merkezi",
            "Autonomous software development center for local and cloud LLMs"),
    "plan": ("Kurulacaklar", "Install plan"),
    "tools": ("Sistem araçları (ffmpeg, git, GitHub CLI, PHP)", "System tools (ffmpeg, git, GitHub CLI, PHP)"),
    "venv": ("Python sanal ortamı", "Python virtual environment"),
    "pip": ("Python paketleri", "Python packages"),
    "browser": ("Tarayıcı motoru (Chromium)", "Browser engine (Chromium)"),
    "npm": ("Arayüz paketleri (npm)", "Front-end packages (npm)"),
    "build": ("Arayüz derlemesi", "Front-end build"),
    "voices": ("Yerel sesler (Türkçe kadın + erkek Piper, İngilizce Kokoro; ~245 MB)",
               "Local voices (Turkish female + male Piper, English Kokoro; ~245 MB)"),
    "mobile": ("Mobil test ortamı (Android SDK, JDK, Gradle, emülatör, Maestro)",
               "Mobile test environment (Android SDK, JDK, Gradle, emulator, Maestro)"),
    "elapsed": ("geçen", "elapsed"),
    "left": ("kalan", "left"),
    "step": ("Adım", "Step"),
    "ok": ("tamam", "done"),
    "skip": ("atlandı", "skipped"),
    "warn": ("uyarı", "warning"),
    "fail": ("hata", "failed"),
    "found": ("bulundu", "found"),
    "missing": ("yok", "missing"),
    "mob_found": ("Bu bilgisayarda bulunanlar (yeniden kurulmaz, sadece eksikler eklenir ve eskiler güncellenir):",
                  "Already on this computer (not installed again; only missing parts are added and old ones updated):"),
    "mob_ask": ("Mobil uygulama test ortamı kurulsun/güncellensin mi? [E/h]: ",
                "Set up / update the mobile app test environment? [Y/n]: "),
    "mob_new": ("Android SDK bulunamadı: kullanıcı klasörüne kurulur (yönetici izni gerekmez, birkaç GB, bir kez).",
                "No Android SDK found: it is installed in the user folder (no admin, several GB, once)."),
    "done": ("Kurulum tamamlandı", "Setup complete"),
    "done_warn": ("Kurulum tamamlandı (uyarılarla)", "Setup complete (with warnings)"),
    "failed": ("Kurulum durdu", "Setup stopped"),
    "start": ("Başlatmak için:  run.bat", "To start:  run.bat"),
    "log": ("Ayrıntılı kayıt", "Full log"),
    "total": ("Toplam süre", "Total time"),
    "no_winget": ("winget yok: araçlar elle kurulabilir (uygulama ffmpeg ve Composer'ı kendisi indirir)",
                  "winget not available: install the tools by hand (the app fetches ffmpeg and Composer itself)"),
    "net_check": ("İnternet bağlantısı kontrol ediliyor…", "Checking the internet connection…"),
    "net_ok": ("İnternet bağlantısı var", "Internet connection OK"),
    "net_proxy": ("Sistem proxy'si kullanılıyor: {px}", "Using the system proxy: {px}"),
    "net_off": ("İnternete ulaşılamıyor ({why}). Wi-Fi/kablo, DNS, VPN veya güvenlik duvarını kontrol edin. "
                "Bilgisayarda zaten kurulu olanlarla çevrimdışı devam ediliyor; eksik bir şey varsa bağlantı gelince "
                "install.bat'ı yeniden çalıştırın.",
                "The internet cannot be reached ({why}). Check Wi-Fi/cable, DNS, VPN or the firewall. Continuing offline "
                "with what is already installed; if something is missing, run install.bat again once you are online."),
    "offline": ("çevrimdışı", "offline"),
    "retry_net": ("Bağlantı sorunu - yeniden deneniyor ({n}/{of}), inenler önbellekte kalıyor…",
                  "Connection problem - trying again ({n}/{of}); what was downloaded stays cached…"),
    "need_net": ("internet gerekiyor - eksik: {what}. Bağlantıyı kontrol edip install.bat'ı yeniden çalıştırın",
                 "needs the internet - missing: {what}. Check the connection and run install.bat again"),
    "net_lost": ("bağlantı koptu ({what}). Bağlantıyı kontrol edip install.bat'ı yeniden çalıştırın",
                 "the connection dropped ({what}). Check the connection and run install.bat again"),
}


def tr(key: str, **kw) -> str:
    s = T[key][0 if LANG == "tr" else 1]
    return s.format(**kw) if kw else s


# --- terminal -----------------------------------------------------------------------------------------------------
TTY = sys.stdout.isatty()
if os.name == "nt":
    os.system("")  # turns on ANSI escape handling in the Windows console
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
C = {"r": "\x1b[0m", "b": "\x1b[1m", "d": "\x1b[2m", "cy": "\x1b[36m", "gr": "\x1b[32m", "ye": "\x1b[33m",
     "re": "\x1b[31m", "mg": "\x1b[35m", "bl": "\x1b[34m"} if TTY else {k: "" for k in ("r", "b", "d", "cy", "gr", "ye", "re", "mg", "bl")}
WIDTH = max(60, min(100, shutil.get_terminal_size((90, 20)).columns - 2))
# The classic Windows console (conhost, raster / Consolas font) shows "?" for ✓ ✗ ╭ and braille spinners; Windows
# Terminal, VS Code and other terminals draw them. Fancy glyphs only where they render, a safe set everywhere else
# (√ × ┌ ─ █ ░ exist in every console font and in code page 437 / 850 / 857).
FANCY = os.name != "nt" or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))


def _console_font() -> str:
    """The classic console's font face ('Consolas', 'Lucida Console', '' for raster 'Terminal' fonts)."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class FontInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.ULONG), ("nFont", wintypes.DWORD), ("dwFontSize", wintypes._COORD),
                        ("FontFamily", wintypes.UINT), ("FontWeight", wintypes.UINT), ("FaceName", wintypes.WCHAR * 32)]
        info = FontInfo()
        info.cbSize = ctypes.sizeof(FontInfo)
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        if ctypes.windll.kernel32.GetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
            return info.FaceName
    except Exception:  # noqa: BLE001 - only a cosmetic choice
        pass
    return "Consolas"


# Consolas / Lucida Console (the default since Windows 10) have √ × ┌ █ ░ ·; a raster font only has code-page glyphs
RASTER = os.name == "nt" and not FANCY and _console_font() in ("", "Terminal")
G = ({"ok": "✓", "fail": "✗", "warn": "!", "skip": "–", "have": "✓", "miss": "✗", "tl": "╭", "tr": "╮", "bl": "╰",
      "br": "╯", "dot": "·"} if FANCY else
     {"ok": "+" if RASTER else "√", "fail": "x" if RASTER else "×", "warn": "!", "skip": "-",
      "have": "+" if RASTER else "√", "miss": "x" if RASTER else "×", "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
      "dot": "·"})
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if FANCY else "|/-\\"


def fmt(sec: float) -> str:
    sec = int(max(0, sec))
    return f"{sec // 60:d}:{sec % 60:02d}" if sec < 3600 else f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def banner() -> None:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else ""
    line = "─" * (WIDTH - 2)
    print(f"{C['cy']}{G['tl']}{line}{G['tr']}{C['r']}")
    for text, style in ((f"  {tr('title')}  v{ver}", C["b"]), (f"  {tr('sub')}", C["d"])):
        pad = WIDTH - 2 - len(text)
        print(f"{C['cy']}│{C['r']}{style}{text}{C['r']}{' ' * max(0, pad)}{C['cy']}│{C['r']}")
    print(f"{C['cy']}{G['bl']}{line}{G['br']}{C['r']}")


# --- steps --------------------------------------------------------------------------------------------------------
class Step:
    def __init__(self, key: str, weight: float, fn) -> None:
        self.key, self.weight, self.fn = key, weight, fn
        self.state, self.secs, self.note = "wait", 0.0, ""


class UI:
    """Two live lines under the plan: the overall bar with the current step, and the latest output line."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps, self.t0, self.cur, self.sub, self.last = steps, time.time(), None, 0.0, ""
        self.lock, self.stop = threading.Lock(), False
        self.log = open(LOG_DIR / time.strftime("install-%Y%m%d-%H%M%S.log"), "w", encoding="utf-8")
        self.drawn = False
        self.err = ""

    def eta(self) -> float:
        done = [s for s in self.steps if s.state in ("ok", "warn", "fail", "skip")]
        est_done = sum(s.weight for s in done if s.state != "skip") or 1
        real_done = sum(s.secs for s in done if s.state != "skip")
        speed = min(3.0, max(0.4, real_done / est_done)) if real_done > 20 else 1.0
        left = sum(s.weight for s in self.steps if s.state == "wait")
        cur_left = 0.0
        if self.cur:  # the step under way: by its own measured pace when it reports progress, else by its estimate
            spent = time.time() - self.cur_t
            if self.sub >= 0.03 and spent > 8:
                cur_left = spent / self.sub * (1 - self.sub)  # real seconds, not scaled by the speed guess
            else:
                left += self.cur.weight * (1 - self.sub) if self.sub else max(self.cur.weight * 0.05, self.cur.weight - spent)
        return left * speed + cur_left

    def frac(self) -> float:
        total = sum(s.weight for s in self.steps if s.state != "skip") or 1
        done = sum(s.weight for s in self.steps if s.state in ("ok", "warn", "fail"))
        if self.cur:
            part = self.sub if self.sub else min(0.95, (time.time() - self.cur_t) / max(1.0, self.cur.weight))
            done += self.cur.weight * part
        return min(1.0, done / total)

    def draw(self, final: bool = False) -> None:
        if not TTY:
            return
        with self.lock:
            f = self.frac()
            bar_w = WIDTH - 40
            full = int(bar_w * f)
            bar = f"{C['gr']}{'█' * full}{C['d']}{'░' * (bar_w - full)}{C['r']}"
            spin = SPIN[int(time.time() * 10) % len(SPIN)] if not final else G["ok"]
            n = sum(1 for s in self.steps if s.state != "skip")
            k = sum(1 for s in self.steps if s.state in ("ok", "warn", "fail")) + (1 if self.cur else 0)
            head = (f" {C['cy']}{spin}{C['r']} {bar} {C['b']}{int(f * 100):3d}%{C['r']}  "
                    f"{C['d']}{tr('elapsed')}{C['r']} {fmt(time.time() - self.t0)}  "
                    f"{C['d']}{tr('left')}{C['r']} ~{fmt(self.eta())}")
            cur = ""
            if self.cur:
                name = f"   {C['b']}{tr('step')} {k}/{n}{C['r']} {G['dot']} {tr(self.cur.key)}"
                if self.sub > 0:  # the step reports its own progress: a small bar of its own, in step with the big one
                    sw = 18
                    sf = int(sw * self.sub)
                    name = (f"   {C['b']}{tr('step')} {k}/{n}{C['r']} {G['dot']} {tr(self.cur.key)[:WIDTH - 44]}  "
                            f"{C['cy']}{'█' * sf}{C['d']}{'░' * (sw - sf)}{C['r']} {int(self.sub * 100):3d}%")
                cur = name
            out = (self.last[: WIDTH - 6]).replace("\x1b", "")
            lines = [head, cur, f"   {C['d']}{out}{C['r']}"]
            if self.drawn:
                sys.stdout.write("\x1b[3F")
            sys.stdout.write("".join(f"\x1b[2K{ln}\n" for ln in lines))
            sys.stdout.flush()
            self.drawn = True

    def clear(self) -> None:
        if TTY and self.drawn:
            sys.stdout.write("\x1b[3F" + "\x1b[2K\n" * 3 + "\x1b[3F")
            self.drawn = False

    def line(self, text: str) -> None:
        self.log.write(text + "\n")
        self.log.flush()
        t = text.strip()
        if t:
            self.last = t
        if not TTY and t:
            print("   " + t[:WIDTH])

    def result(self, s: Step) -> None:
        self.clear()
        mark = {"ok": f"{C['gr']}{G['ok']}", "warn": f"{C['ye']}{G['warn']}", "fail": f"{C['re']}{G['fail']}",
                "skip": f"{C['d']}{G['skip']}"}[s.state]
        word = tr({"ok": "ok", "warn": "warn", "fail": "fail", "skip": "skip"}[s.state])
        note = f"  {C['d']}{s.note}{C['r']}" if s.note else ""
        print(f" {mark}{C['r']} {tr(s.key):<58} {C['d']}{fmt(s.secs):>6}  {word}{C['r']}{note}")

    def run(self) -> bool:
        ticker = threading.Thread(target=self._tick, daemon=True)
        ticker.start()
        ok = True
        for s in self.steps:
            if s.state == "skip":
                self.result(s)
                continue
            self.cur, self.cur_t, self.sub, self.last = s, time.time(), 0.0, ""
            self.line(f"== {tr(s.key)}")
            try:
                res = s.fn(self)
                s.state = res if res in ("ok", "warn", "skip") else "ok"
            except StepError as e:
                s.state, s.note = "fail", str(e)
            s.secs = time.time() - self.cur_t
            self.cur = None
            self.result(s)
            if s.state == "fail":
                ok = False
                break
        self.stop = True
        ticker.join(1)
        self.clear()
        return ok

    def _tick(self) -> None:
        while not self.stop:
            self.draw()
            time.sleep(0.12)


class StepError(Exception):
    pass


def sh(ui: UI, argv: list[str], *, cwd: Path = ROOT, total_lines: int = 0, count: re.Pattern | None = None,
       env: dict | None = None, ok_codes=(0,)) -> int:
    """Runs a command, streams its output into the log and the live line; sub-progress from matching lines."""
    seen = 0
    ui.err = ""
    try:
        p = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL,
                             env={**os.environ, **NET_ENV, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", **(env or {})})
    except OSError as e:
        ui.line(f"{argv[0]}: {e}")
        ui.err = str(e)
        return 127
    for raw in iter(p.stdout.readline, b""):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1254", errors="replace")
        # "\r\n" is one line end; a bare "\r" is a progress redraw - keep only its last state
        for part in text.rstrip("\r\n").split("\r"):
            if not part.strip():
                continue
            if part.startswith("PROGRESS "):  # "PROGRESS 0.4213 detail" from mobile_setup.py: the step's own progress
                try:
                    frac, _, detail = part[9:].partition(" ")
                    ui.sub = max(ui.sub, min(0.999, float(frac)))
                except ValueError:
                    continue
                ui.last = detail.strip()
                if int(ui.sub * 20) != getattr(ui, "_logged", -1):  # the log gets every 5 %, not every redraw
                    ui._logged = int(ui.sub * 20)
                    ui.log.write(f"{int(ui.sub * 100):3d}% {detail.strip()}\n")
                continue
            ui.line(part)
            if ERR_LINE.search(part):
                ui.err = part.strip()
            if total_lines and count and count.search(part):
                seen += 1
                ui.sub = min(0.97, seen / total_lines)
    return p.wait()


ERR_LINE = re.compile(r"^\s*(ERROR:|npm (ERR!|error)|error:|Error:)")
NET_ERR = re.compile(r"getaddrinfo|NewConnectionError|Name or service not known|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|"
                     r"ETIMEDOUT|ConnectTimeout|Failed to establish a new connection|No matching distribution found|"
                     r"Could not find a version that satisfies", re.I)


# --- network ------------------------------------------------------------------------------------------------------
def system_proxy() -> dict:
    """pip, npm and playwright do not read the Windows Internet settings proxy by themselves - pass it on."""
    try:
        import urllib.request
        px = urllib.request.getproxies()
    except Exception:  # noqa: BLE001 - a broken registry value must not stop the installer
        return {}
    env = {}
    for scheme in ("https", "http"):
        val = px.get(scheme)
        if val and not (os.environ.get(f"{scheme.upper()}_PROXY") or os.environ.get(f"{scheme}_proxy")):
            env[f"{scheme.upper()}_PROXY"] = val if "://" in val else f"http://{val}"
    return env


NET_ENV = system_proxy()
NET_HOSTS = ("pypi.org", "files.pythonhosted.org", "registry.npmjs.org", "github.com")


def net_problem(tries: int = 3) -> str:
    """'' when the package servers can be reached, else a short reason. Retries a few times: a Wi-Fi that has just
    woken up or a VPN still connecting answers a few seconds later."""
    import socket
    why = ""
    for attempt in range(tries):
        for host in NET_HOSTS:
            try:
                if NET_ENV:  # behind a proxy only the proxy itself has to answer
                    from urllib.parse import urlsplit
                    u = urlsplit(next(iter(NET_ENV.values())))
                    socket.create_connection((u.hostname, u.port or 80), timeout=6).close()
                    return ""
                socket.create_connection((host, 443), timeout=6).close()
            except socket.gaierror:
                why = f"DNS: {host}"
                break
            except OSError as e:
                why = f"{host}: {e.strerror or e}"
                break
        else:
            return ""
        if attempt + 1 < tries:
            time.sleep(3)
    return why


OFFLINE = False
PIP_NET = ["--retries", "3", "--timeout", "25", "--disable-pip-version-check"]


# --- the steps themselves -------------------------------------------------------------------------------------------
def _fail(ui: UI, what: str) -> StepError:
    """A clear reason instead of a bare command name: the network, or the tool's own last ERROR line."""
    if OFFLINE or NET_ERR.search(ui.err or ""):
        return StepError(tr("net_lost" if not OFFLINE else "need_net", what=_missing(ui.err) or what))
    return StepError(ui.err[:160] if ui.err else what)


def _again(ui: UI, run, tries: int = 3) -> int:
    """Runs a download step; a failure that looks like the network (a dropped connection, an index page that did not
    load: "from versions: none") is retried after the connection answers again - what was downloaded stays cached."""
    code = run()
    for attempt in range(1, tries):
        if code == 0 or OFFLINE or not (NET_ERR.search(ui.err or "") or "versions: none" in (ui.err or "")):
            return code
        ui.line(tr("retry_net", n=attempt + 1, of=tries))
        for _ in range(20):  # up to ~2 minutes for the connection to come back
            if not net_problem(tries=1):
                break
            time.sleep(4)
        code = run()
    return code


def _missing(err: str) -> str:
    m = re.search(r"(?:requirement|found for) ([A-Za-z0-9_.\-\[\]]+)", err or "")
    return m.group(1) if m else ""


def step_tools(ui: UI) -> str:
    if OFFLINE:
        ui.steps[0].note = tr("offline")
        return "warn"
    if not shutil.which("winget"):
        ui.steps[0].note = tr("no_winget")
        return "warn"
    want = [("ffmpeg", "Gyan.FFmpeg"), ("git", "Git.Git"), ("gh", "GitHub.cli"), ("php", "PHP.PHP.8.4")]
    missing = [(n, i) for n, i in want if not shutil.which(n)]
    have = [n for n, _ in want if shutil.which(n)]
    for k, (name, wid) in enumerate(missing):
        ui.sub = k / max(1, len(missing))
        ui.line(f"winget install {wid}")
        code = sh(ui, ["winget", "install", "--id", wid, "--exact", "--silent", "--accept-source-agreements",
                       "--accept-package-agreements", "--scope", "user"])
        if code != 0:
            sh(ui, ["winget", "install", "--id", wid, "--exact", "--silent", "--accept-source-agreements",
                    "--accept-package-agreements"])
    got = [n for n, _ in want if shutil.which(n)]
    ui.steps[0].note = ", ".join(got or have) or ""
    return "ok" if len(got) >= len(have) else "warn"


def step_venv(ui: UI) -> str:
    if VENV_PY.exists():
        return "ok"
    if sh(ui, [sys.executable, "-m", "venv", str(ROOT / ".venv")]) != 0:
        raise StepError("python -m venv")
    return "ok"


def step_pip(ui: UI) -> str:
    if not OFFLINE:  # optional: an old pip still installs everything
        sh(ui, [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", *PIP_NET])
    reqs = [ln for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    # offline: --no-index passes when everything is already installed and names the first missing package if not
    code = _again(ui, lambda: sh(ui, [str(VENV_PY), "-m", "pip", "install", "-r", "requirements.txt", *PIP_NET,
                                      *(["--no-index"] if OFFLINE else [])],
                                 total_lines=len(reqs), count=re.compile(r"^(Collecting|Requirement already satisfied)\b")))
    if code != 0:
        raise _fail(ui, "pip install -r requirements.txt")
    ui.steps[2].note = f"{len(reqs)}" + (f" · {tr('offline')}" if OFFLINE else "")
    return "ok"


def _chromium_ready() -> bool:
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright")
    return any(base.glob("chromium-*")) if base.is_dir() else False


def step_browser(ui: UI) -> str:
    if OFFLINE:
        ui.steps[3].note = tr("offline")
        return "ok" if _chromium_ready() else "warn"
    if sh(ui, [str(VENV_PY), "-m", "playwright", "install", "chromium"]) == 0:
        return "ok"
    ui.steps[3].note = (ui.err or "")[:120]
    return "warn"


def _npm() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def step_npm(ui: UI) -> str:
    if OFFLINE:
        if (ROOT / "frontend" / "node_modules" / "vite").is_dir():
            ui.steps[4].note = tr("offline")
            return "ok"
        raise StepError(tr("need_net", what="frontend/node_modules"))
    if _again(ui, lambda: sh(ui, [_npm(), "install", "--no-fund", "--no-audit"], cwd=ROOT / "frontend",
                             total_lines=60, count=re.compile(r"added|changed|http fetch|reify"))) != 0:
        raise _fail(ui, "npm install")
    return "ok"


def step_build(ui: UI) -> str:
    if sh(ui, [_npm(), "run", "build"], cwd=ROOT / "frontend", total_lines=12,
          count=re.compile(r"transforming|rendering|computing|built in|modules")) != 0:
        raise StepError((ui.err or "npm run build")[:160])
    return "ok"


def step_voices(ui: UI) -> str:
    """Default local voices (data/tts): offline speech from the first start; a failure is only a warning (the app
    falls back to the online voices and downloads others from Settings > Voices)."""
    me = next(s for s in ui.steps if s.key == "voices")
    if OFFLINE:
        me.note = tr("offline")
        return "warn"
    code = sh(ui, [str(VENV_PY), str(ROOT / "backend" / "voice_setup.py")])
    if code != 0:
        me.note = (ui.err or "")[:120]
    return "ok" if code == 0 else "warn"


def step_mobile(ui: UI) -> str:
    if OFFLINE:
        ui.steps[-1].note = tr("offline")
        return "warn"
    # mobile_setup.py reports "PROGRESS <0..1> <detail>" (bytes downloaded, sdkmanager's own %) -> live bars + ETA
    code = sh(ui, [str(VENV_PY), str(ROOT / "backend" / "mobile_setup.py")])
    if code != 0:
        ui.steps[-1].note = (ui.err or "")[:120]
    return "ok" if code == 0 else "warn"


def _dirs(p: Path) -> list[str]:
    try:
        return sorted(x.name for x in p.iterdir() if x.is_dir())
    except OSError:
        return []


def mobile_check() -> dict:
    """What the machine already has (SDK, JDK, Gradle, Maestro), found with the standard library only - the same
    places backend/app/tools/mobile.py looks (it runs before the virtual environment exists on a fresh install)."""
    home = Path.home()
    saved = {}
    try:
        saved = json.loads((ROOT / "data" / "mobile" / "paths.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
    sdks = [Path(v) for v in (saved.get("sdk"), os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")) if v]
    sdks += [local / "Android/Sdk", home / "Library/Android/sdk", home / "Android/Sdk", Path("C:/Android/Sdk"),
             ROOT / "data" / "mobile" / "android-sdk"]
    sdk = next((p for p in sdks if p.is_dir() and any((p / d).is_dir() for d in ("platform-tools", "cmdline-tools", "platforms"))), None)
    jdk = None
    for pat in ("C:/Program Files/Eclipse Adoptium/jdk-*", "C:/Program Files/Java/jdk-*", "C:/Program Files/Microsoft/jdk-*",
                "C:/Program Files/Android/Android Studio/jbr", str(ROOT / "data/mobile/jdk/jdk-*")):
        import glob
        for d in sorted(glob.glob(pat), reverse=True):
            m = re.search(r"jdk-?(\d+)", d)
            if (Path(d) / "bin" / "java.exe").exists() and (not m or int(m.group(1)) >= 17):
                jdk = jdk or d
    gradle = saved.get("gradle") or next(iter(sorted((ROOT / "data/mobile/gradle").glob("gradle-*/bin/gradle*"))), None) \
        or shutil.which("gradle")
    images = []
    if sdk:
        for api in _dirs(sdk / "system-images"):
            for tag in _dirs(sdk / "system-images" / api):
                images += [f"{api};{tag};{abi}" for abi in _dirs(sdk / "system-images" / api / tag)]
    return {"sdk": str(sdk) if sdk else None, "sdk_found": bool(sdk), "jdk": jdk, "gradle": str(gradle) if gradle else None,
            "platforms": _dirs(sdk / "platforms") if sdk else [], "build_tools": _dirs(sdk / "build-tools") if sdk else [],
            "images": images,
            "maestro": str(home / ".maestro" / "bin") if (home / ".maestro" / "bin").is_dir() else shutil.which("maestro")}


def ask_mobile(info: dict | None) -> bool:
    pre = os.environ.get("AIIQ_MOBILE", "").strip().lower()
    if pre in ("1", "y", "e", "yes", "evet"):
        return True
    if pre in ("0", "n", "h", "no", "hayir", "hayır"):
        return False
    print()
    if info and (info.get("sdk_found") or info.get("jdk")):
        print(f" {C['b']}{tr('mob_found')}{C['r']}")
        rows = [("Android SDK", info.get("sdk")), ("JDK", info.get("jdk")), ("Gradle", info.get("gradle")),
                ("Platforms", ", ".join(info.get("platforms") or [])), ("Build-tools", ", ".join(info.get("build_tools") or [])),
                ("Images", ", ".join(info.get("images") or [])),
                ("Maestro", info.get("maestro"))]
        for name, val in rows:
            mark = f"{C['gr']}{G['have']}{C['r']}" if val else f"{C['re']}{G['miss']}{C['r']}"
            print(f"   {mark} {name:<12} {C['d']}{val or tr('missing')}{C['r']}")
    else:
        print(f" {C['d']}{tr('mob_new')}{C['r']}")
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        ans = input(" " + tr("mob_ask")).strip().lower()
    except EOFError:
        return False
    return ans in ("", "e", "y", "evet", "yes")


def main() -> int:
    global OFFLINE
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    banner()
    print(f" {C['d']}{tr('net_check')}{C['r']}", end="\r", flush=True)
    why = net_problem()
    print("\x1b[2K" if TTY else "", end="")
    if why:
        OFFLINE = True
        print(f" {C['ye']}! {tr('net_off', why=why)}{C['r']}")
    else:
        print(f" {C['gr']}{G['ok']}{C['r']} {tr('net_ok')}")
        if NET_ENV:
            print(f"   {C['d']}{tr('net_proxy', px=next(iter(NET_ENV.values())))}{C['r']}")
    steps = [Step("tools", 60, step_tools), Step("venv", 15, step_venv), Step("pip", 240, step_pip),
             Step("browser", 90, step_browser), Step("npm", 120, step_npm), Step("build", 45, step_build),
             Step("voices", 90, step_voices), Step("mobile", 600, step_mobile)]
    info = mobile_check()
    mobile = ask_mobile(info)
    if not mobile:
        steps[-1].state = "skip"
    elif info and info.get("sdk_found"):
        steps[-1].weight = 120  # an SDK is there: only updates and missing parts
    print(f"\n {C['b']}{tr('plan')}{C['r']}")
    for i, s in enumerate(x for x in steps if x.state != "skip"):
        print(f"   {C['d']}{i + 1}.{C['r']} {tr(s.key)}")
    print()
    ui = UI(steps)
    ui.line(f"network: {'OFFLINE - ' + why if why else 'ok'}; proxy: {next(iter(NET_ENV.values()), '-')}; "
            f"python: {sys.version.split()[0]}; lang: {LANG}")
    t0 = time.time()
    ok = ui.run()
    warn = any(s.state == "warn" for s in steps)
    color = C["gr"] if ok and not warn else C["ye"] if ok else C["re"]
    title = tr("done") if ok and not warn else tr("done_warn") if ok else tr("failed")
    print(f"\n {color}{C['b']}{title}{C['r']}  ·  {tr('total')} {fmt(time.time() - t0)}")
    print(f" {C['d']}{tr('log')}: {ui.log.name}{C['r']}")
    if ok:
        print(f"\n {C['cy']}{C['b']}{tr('start')}{C['r']}\n")
    ui.log.close()
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{C['r']}")
        sys.exit(130)
