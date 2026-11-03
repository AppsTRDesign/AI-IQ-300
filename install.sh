#!/usr/bin/env bash
# AI IQ 300 - Linux / macOS kurulum (installer)
set -euo pipefail
cd "$(dirname "$0")"
echo "=== AI IQ 300 - Kurulum / Install ==="

# Python 3.12+
PY=""
for c in python3.12 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[HATA/ERROR] Python 3.12+ bulunamadi / not found: https://www.python.org/downloads/"
  echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
  exit 1
fi
"$PY" -c 'import venv' 2>/dev/null || { echo "[HATA/ERROR] python venv modulu yok / missing: sudo apt install python3.12-venv"; exit 1; }

# Node.js 20+ and npm
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "[HATA/ERROR] Node.js (npm) bulunamadi / not found: https://nodejs.org/"
  exit 1
fi
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "$NODE_MAJOR" -lt 20 ]; then
  echo "[HATA/ERROR] Node.js 20+ gerekli / required (bulunan/found: $(node --version))"; exit 1
fi
command -v git >/dev/null 2>&1 || echo "[UYARI/WARN] git bulunamadi; zaman makinesi (git) calismaz / time machine disabled: https://git-scm.com/downloads"

echo "Python: $($PY --version) | Node: $(node --version)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Playwright browser for visual tests / web research. System libraries may need: sudo .venv/bin/python -m playwright install-deps
.venv/bin/python -m playwright install chromium || echo "[UYARI/WARN] Playwright Chromium kurulamadi / could not be installed"

(cd frontend && npm install && npm run build)

chmod +x run.sh
echo
echo "Kurulum tamamlandi / Installed. Baslatmak icin / Start with: ./run.sh"
