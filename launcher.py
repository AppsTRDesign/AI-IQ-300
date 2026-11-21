"""AI IQ 300 launcher: starts the FastAPI backend on loopback and opens the browser.

The console shows a short banner and a readable log: time, a coloured level, and for requests the method, path,
status and a compact form. Frequent polling and static files are left out unless --verbose is given."""
import argparse
import logging
import os
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

TTY = sys.stdout.isatty()
if os.name == "nt":
    os.system("")  # ANSI colours in the Windows console
C = {"r": "\x1b[0m", "b": "\x1b[1m", "d": "\x1b[2m", "cy": "\x1b[36m", "gr": "\x1b[32m", "ye": "\x1b[33m", "re": "\x1b[31m",
     "mg": "\x1b[35m", "bl": "\x1b[34m"} if TTY else {k: "" for k in ("r", "b", "d", "cy", "gr", "ye", "re", "mg", "bl")}


def ui_lang() -> str:
    try:
        from installer import ui_lang as detect
        return detect()
    except Exception:  # noqa: BLE001
        return "en"


LANG = ui_lang()
TXT = {"tr": {"ready": "Hazır", "open": "Tarayıcıda aç", "data": "Veri klasörü", "stop": "Durdurmak için Ctrl+C",
              "log": "Kayıt", "quiet": "(sık yoklamalar gizli; tümü için: run.bat --verbose)"},
       "en": {"ready": "Ready", "open": "Open in the browser", "data": "Data folder", "stop": "Press Ctrl+C to stop",
              "log": "Log", "quiet": "(frequent polling hidden; everything: run.bat --verbose)"}}[LANG]

# Requests that come every few seconds (health, active run, static files): hidden in the normal log
QUIET = re.compile(r'"(?:GET|HEAD) (?:/api/models/health|/api/sessions/[^/ ]+/active|/api/health|/assets/|/favicon|'
                   r'/api/context|/api/processes|/api/usage)')
ACCESS = re.compile(r'^(?P<client>\S+) - "(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[\d.]+" (?P<status>\d{3})')


class Pretty(logging.Formatter):
    LEVEL = {"DEBUG": ("dbg", "d"), "INFO": ("info", "cy"), "WARNING": ("warn", "ye"), "ERROR": ("err", "re"),
             "CRITICAL": ("crit", "re")}

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        name, col = self.LEVEL.get(record.levelname, (record.levelname.lower(), "r"))
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        if record.name == "uvicorn.access" and (m := ACCESS.match(msg)):
            st = int(m["status"])
            sc = "gr" if st < 300 else "cy" if st < 400 else "ye" if st < 500 else "re"
            path = m["path"] if len(m["path"]) <= 70 else m["path"][:67] + "..."
            return (f"{C['d']}{ts}{C['r']}  {C[sc]}{st}{C['r']}  {C['b']}{m['method']:<6}{C['r']} {path}")
        out = f"{C['d']}{ts}{C['r']}  {C[col]}{name:<4}{C['r']}  {msg}"
        if record.exc_info:
            out += "\n" + self.formatException(record.exc_info)
        return out


class Quiet(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not QUIET.search(record.getMessage())


def banner(url: str, verbose: bool) -> None:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else ""
    data = os.environ.get("AIIQ_DATA") or str(ROOT / "data")
    w = 64
    print(f"\n{C['cy']}╭{'─' * w}╮{C['r']}")
    rows = [(f"  AI IQ 300  v{ver}", C["b"]), (f"  {TXT['open']}: {url}", C["gr"]), (f"  {TXT['data']}: {data}", C["d"]),
            (f"  {TXT['stop']}", C["d"])]
    for text, style in rows:
        text = text if len(text) <= w else text[: w - 1] + "…"
        print(f"{C['cy']}│{C['r']}{style}{text}{C['r']}{' ' * (w - len(text))}{C['cy']}│{C['r']}")
    print(f"{C['cy']}╰{'─' * w}╯{C['r']}")
    if not verbose:
        print(f"  {C['d']}{TXT['log']} {TXT['quiet']}{C['r']}")
    print()


def main() -> None:
    for s in (sys.stdout, sys.stderr):  # Windows consoles (cp1254 / cp437) cannot print every log line's symbols
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="AI IQ 300")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (loopback by default)")
    parser.add_argument("--port", type=int, default=8300)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Log every request, also the frequent polling")
    args = parser.parse_args()

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    banner(url, args.verbose)
    handler = {"class": "logging.StreamHandler", "formatter": "pretty", "stream": "ext://sys.stdout"}
    log_config = {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"pretty": {"()": Pretty}},
        "filters": {"quiet": {"()": Quiet}},
        "handlers": {"default": handler, "access": {**handler, **({} if args.verbose else {"filters": ["quiet"]})}},
        "loggers": {"uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                    "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
                    "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
                    "app": {"handlers": ["default"], "level": "INFO", "propagate": False}},
    }
    # WebSocket: a ping every 20 s, but 60 s to answer (a busy moment on the server or a tab the browser throttles
    # must not drop the event stream; the app also pings every 15 s and the page reconnects by itself).
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info", log_config=log_config,
                ws_ping_interval=20.0, ws_ping_timeout=60.0, timeout_keep_alive=30)


if __name__ == "__main__":
    main()
