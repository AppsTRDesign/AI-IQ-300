"""Mobile app test environment for the agent (install.bat / install.sh / installer.py call this when asked):
Android SDK + emulator + Pixel AVD + Gradle + JDK + Maestro. What the machine already has (Android Studio's SDK and
JDK, ANDROID_HOME, an earlier install) is used and only updated; only missing parts are downloaded.

    python backend/mobile_setup.py            # set up (progress lines start with '  - ')
    python backend/mobile_setup.py --check    # only report what is there (JSON), install nothing"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.tools import mobile  # noqa: E402


async def check() -> dict:
    sdks = mobile.existing_sdks()
    jh = mobile.java_home()
    inv = mobile.sdk_inventory(sdks[0]) if sdks else {}
    return {"sdk": str(sdks[0]) if sdks else None, "sdk_found": bool(sdks), "jdk": str(jh) if jh else None,
            "gradle": mobile.gradle_bin(), "platforms": inv.get("platforms", []), "build_tools": inv.get("build_tools", []),
            "images": inv.get("system_images", []), "maestro": bool(mobile._which("maestro"))}


async def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if "--check" in sys.argv:
        print(json.dumps(await check()))
        return 0
    last = [-1.0, ""]

    def meter(frac: float, detail: str) -> None:
        # "PROGRESS 0.4213 detail" lines: installer.py turns them into its live bar (at most every 0.2 % or new text)
        if frac - last[0] >= 0.002 or detail.split(" · ")[0] != last[1] or frac >= 1:
            last[0], last[1] = frac, detail.split(" · ")[0]
            print(f"PROGRESS {frac:.4f} {detail}", flush=True)
    try:
        st = await mobile.setup(progress=lambda m: print("  -", m, flush=True), meter=meter)
    except Exception as e:  # noqa: BLE001
        print("[WARN] mobile test setup failed:", e, flush=True)
        return 1
    print("RESULT " + json.dumps({k: st.get(k) for k in ("sdk", "java", "avds", "gradle", "maestro")}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
