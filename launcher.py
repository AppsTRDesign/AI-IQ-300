"""AI IQ 300 launcher: starts the FastAPI backend on loopback and opens the browser."""
import argparse
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    parser = argparse.ArgumentParser(description="AI IQ 300")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (loopback by default)")
    parser.add_argument("--port", type=int, default=8300)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"AI IQ 300 -> {url}")
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
