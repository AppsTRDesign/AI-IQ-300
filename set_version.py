"""AI IQ 300 version: the VERSION file is the single source.

    python set_version.py 0.11.0     # sets the version everywhere
    python set_version.py            # copies the current VERSION everywhere (after editing VERSION by hand)

The app reads VERSION at run time (backend: /api/health and the About page; frontend build: __APP_VERSION__).
This script also writes it into the places that cannot read a file: frontend/package.json and the version
badges of tanitim/README.md and tanitim/README.tr.md."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BADGE = re.compile(r"(img\.shields\.io/badge/(?:version|s%C3%BCr%C3%BCm|sürüm)-)[\w.]+(-)")


def check() -> int:
    """CI: the version is the same everywhere it is written, and a release tag matches it.
    python set_version.py --check [tag]"""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    problems = []
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8")).get("version")
    if pkg != version:
        problems.append(f"frontend/package.json has {pkg}, VERSION has {version}")
    for name, pattern in (("README.md", rf"New in v{re.escape(version)}\b"),
                          ("README.tr.md", rf"v{re.escape(version)} ile gelenler"),
                          ("PROJECT_STATE.md", rf"## v{re.escape(version)}\b"),
                          ("PROJECT_STATE.tr.md", rf"## v{re.escape(version)}\b")):
        f = ROOT / name
        if f.exists() and not re.search(pattern, f.read_text(encoding="utf-8")):
            problems.append(f"{name} has no section for v{version}")
    for name in ("README.md", "README.tr.md"):
        f = ROOT / name
        for m in BADGE.finditer(f.read_text(encoding="utf-8") if f.exists() else ""):
            badge = f.read_text(encoding="utf-8")[m.end(1):m.start(2)]
            if badge != version:
                problems.append(f"{name} version badge shows {badge}, VERSION has {version}")
    tag = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
    if tag.startswith("v") and tag.lstrip("v") != version:
        problems.append(f"release tag {tag} does not match VERSION {version}")
    for p in problems:
        print("version check:", p)
    print(f"version check: {'FAILED' if problems else 'ok'} ({version})")
    return 1 if problems else 0


def main() -> None:
    vf = ROOT / "VERSION"
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        raise SystemExit(check())
    if len(sys.argv) > 1:
        version = sys.argv[1].lstrip("v").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+([.-][\w.]+)?", version):
            raise SystemExit(f"not a version: {sys.argv[1]} (use e.g. 0.11.0)")
        vf.write_text(version + "\n", encoding="utf-8")
    version = vf.read_text(encoding="utf-8").strip()
    pkg = ROOT / "frontend" / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    data["version"] = version
    pkg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # The root READMEs are the ones GitHub shows: their badge stayed at 0.18.6 for four releases.
    for f in (ROOT / "README.md", ROOT / "README.tr.md", ROOT / "tanitim" / "README.md", ROOT / "tanitim" / "README.tr.md"):
        if f.exists():
            s = f.read_text(encoding="utf-8")
            s = BADGE.sub(rf"\g<1>{version}\2", s)
            f.write_text(s, encoding="utf-8")
    print(f"version {version}: VERSION, frontend/package.json, README badges (root and tanitim/)")


if __name__ == "__main__":
    main()
