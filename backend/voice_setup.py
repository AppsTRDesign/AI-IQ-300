"""Local voices for the installer (installer.py calls this): a Turkish female + male Piper voice and the Kokoro
English model, so spoken replies, text_to_speech and video voice-overs work offline from the first start. Each voice
is measured (pitch -> female/male). More voices (and Chatterbox) are added from Settings > Voices.

    python backend/voice_setup.py            # download the default voices (PROGRESS lines for the installer)
    python backend/voice_setup.py --check    # only report what is there (JSON)"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import toolchain  # noqa: E402
from app.voice import catalog  # noqa: E402

DEFAULTS = [("piper:tr_TR-fettah-medium", 63), ("piper:tr_TR-99eren99-medium", 64), ("kokoro:af_heart", 117)]


def installed(vid: str) -> bool:
    e, _, n = vid.partition(":")
    return catalog.piper_installed(n) if e == "piper" else catalog.kokoro_installed()


async def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if "--check" in sys.argv:
        print(json.dumps({v: installed(v) for v, _ in DEFAULTS}))
        return 0
    toolchain.setup_paths()
    try:
        toolchain._ffmpeg()
    except Exception:  # noqa: BLE001 - only gender measuring needs it
        pass
    todo = [(v, mb) for v, mb in DEFAULTS if not installed(v)]
    total = sum(mb for _, mb in todo) or 1
    done = 0.0
    failed = 0
    for vid, mb in todo:
        task = asyncio.create_task(catalog.install(vid))
        while not task.done():
            frac = (catalog.PROGRESS.get(vid) or {}).get("frac") or 0.0
            print(f"PROGRESS {(done + frac * mb) / total:.4f} {vid.split(':')[1]} · {mb} MB", flush=True)
            await asyncio.sleep(0.5)
        try:
            task.result()
            print("  -", vid, "ok", flush=True)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[WARN] {vid}: {e}", flush=True)
        done += mb
    print(f"PROGRESS 1.0000 {len(DEFAULTS) - failed}/{len(DEFAULTS)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
