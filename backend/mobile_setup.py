"""Mobile app test environment for the agent (install.bat / install.sh call this when asked):
Android SDK + emulator + Pixel AVD + Maestro, user-level, into data/mobile. Java 17+ must be installed first.
Run: .venv/Scripts/python backend/mobile_setup.py   (or .venv/bin/python on macOS / Linux)"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.tools import mobile  # noqa: E402


async def main() -> int:
    st = await mobile.status()
    if not st["java_ok"]:
        print("[UYARI/WARN]", mobile.JAVA_HINT)
        return 2
    try:
        st = await mobile.setup(progress=lambda m: print("  -", m, flush=True))
    except Exception as e:  # noqa: BLE001
        print("[UYARI/WARN] mobile test setup failed:", e)
        return 1
    print(json.dumps(st, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
