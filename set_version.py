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


def main() -> None:
    vf = ROOT / "VERSION"
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
    for name in ("README.md", "README.tr.md"):
        f = ROOT / "tanitim" / name
        if f.exists():
            s = f.read_text(encoding="utf-8")
            s = re.sub(r"(img\.shields\.io/badge/(?:version|s%C3%BCr%C3%BCm|sürüm)-)[\w.]+(-)", rf"\g<1>{version}\2", s)
            f.write_text(s, encoding="utf-8")
    print(f"version {version}: VERSION, frontend/package.json, tanitim/README badges")


if __name__ == "__main__":
    main()
