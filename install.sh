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

# Optional system tools the agent uses (video, git, GitHub CLI, PHP + Composer). Installed when missing; a failure
# only prints a note (the app also fetches ffmpeg and Composer by itself: backend/app/toolchain.py).
install_tool() {  # $1 command, $2 brew formula, $3 apt package, $4 dnf package
  command -v "$1" >/dev/null 2>&1 && { echo "[OK] $1"; return 0; }
  echo "$1 kuruluyor / installing..."
  if command -v brew >/dev/null 2>&1; then brew install "$2" && return 0
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y "$3" && return 0
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y "$4" && return 0
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm "$3" && return 0
  fi
  echo "[UYARI/WARN] $1 kurulamadi / could not be installed"
}
if [ "${AIIQ_SKIP_SYSTEM_TOOLS:-0}" != "1" ]; then
  command -v apt-get >/dev/null 2>&1 && ! command -v brew >/dev/null 2>&1 && sudo apt-get update -y >/dev/null 2>&1 || true
  install_tool ffmpeg ffmpeg ffmpeg ffmpeg-free || true
  install_tool git git git git || true
  install_tool gh gh gh gh || true
  install_tool php php php-cli php-cli || true
  install_tool composer composer composer composer || true
  # Fonts for video titles, captions and logos (Windows and macOS ship Arial / Georgia / Impact; Linux gets DejaVu).
  if [ "$(uname)" = "Linux" ] && ! ls /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /usr/share/fonts/TTF/DejaVuSans.ttf \
       /usr/share/fonts/dejavu/DejaVuSans.ttf >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y fonts-dejavu-core || true
    elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y dejavu-sans-fonts dejavu-serif-fonts dejavu-sans-mono-fonts || true
    elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm ttf-dejavu || true
    else echo "[UYARI/WARN] DejaVu yazi tiplerini kurun / install DejaVu fonts (video text)"; fi
  fi
fi

echo "Python: $($PY --version) | Node: $(node --version)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Playwright browser for visual tests / web research. System libraries may need: sudo .venv/bin/python -m playwright install-deps
.venv/bin/python -m playwright install chromium || echo "[UYARI/WARN] Playwright Chromium kurulamadi / could not be installed"

(cd frontend && npm install && npm run build)

# Turkish voice packs (TTS): each in its own environment, PyTorch picked for this computer (CUDA / Apple / CPU).
# AIIQ_TTS=0|light|medium|all|"seda xtts" answers without asking. Settings > Voices adds or removes them later.
TTS="${AIIQ_TTS:-}"
if [ -z "$TTS" ] && [ -t 0 ]; then
  echo
  echo "Turkce yerel ses paketleri (TTS) kurulsun mu? / Install the local Turkish voice packs (TTS)?"
  echo "  0) Hayir / No"
  echo "  1) Hafif / Light: Seda, Clarvia, Supertonic, EMA Lightning, Ahenk Cep, Pocket TTS (~3 GB) - onerilen / recommended"
  echo "  2) Hafif + Orta / Light + Medium: + MMS, Turkish VITS, OpenBible, XTTS v2, Anka, Freya, Drifting (~17 GB)"
  echo "  3) Hepsi / All: + Kizagan, Trendyol, Ahenk, Nefes, Fish S2 Pro (NVIDIA GPU, ~53 GB)"
  echo "  4) Kendim secerim / Let me choose"
  echo "  5) Hepsi, GPU paketleri NVIDIA olmadan da (CPU'da cok yavas) / All, GPU packs on the CPU too (very slow)"
  echo "  Not / Note: MMS, XTTS v2, Anka, Fish S2 Pro: ticari kullanim yok / non-commercial licences"
  read -r -p "Secim / Choice [0-5, Enter=1]: " TTS || TTS=""
  [ -z "$TTS" ] && TTS=1
  if [ "$TTS" = "4" ]; then
    .venv/bin/python backend/voice_packs.py --list || true
    read -r -p "Paketler, ornek / Packs, e.g. seda pocket xtts: " TTS || TTS=""
  fi
fi
case "$TTS" in
  ""|0|n|N|no) TTS_ARGS="" ;;
  1|light) TTS_ARGS="light" ;;
  2|medium) TTS_ARGS="light medium" ;;
  3|all) TTS_ARGS="all" ;;
  5|force) TTS_ARGS="all --force" ;;
  *) TTS_ARGS="$TTS" ;;
esac
if [ -n "$TTS_ARGS" ]; then
  # shellcheck disable=SC2086 - the pack names are separate arguments
  .venv/bin/python backend/voice_packs.py $TTS_ARGS || echo "[UYARI/WARN] bazi ses paketleri kurulamadi / some voice packs failed (Settings > Voices)"
fi

# Mobile app testing (Android emulator + Maestro; iOS simulator on macOS with Xcode): several GB, so asked
# (AIIQ_MOBILE=1 yes, AIIQ_MOBILE=0 no). The agent can also set it up later (mobile_env action=setup).
MOB="${AIIQ_MOBILE:-}"
if [ -z "$MOB" ] && [ -t 0 ]; then
  read -r -p "Android/iOS uygulama test ortami kurulsun mu? / Set up the mobile app test environment? (y/N): " MOB || MOB=""
fi
case "$MOB" in 1|y|Y|e|E)
  if ! java -version 2>&1 | grep -Eq 'version "(1[7-9]|2[0-9])'; then
    if command -v brew >/dev/null 2>&1; then brew install --cask temurin@17 || true
    elif command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y openjdk-17-jdk || true
    elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y java-17-openjdk || true; fi
  fi
  .venv/bin/python backend/mobile_setup.py || echo "[UYARI/WARN] mobile test setup failed; the agent can run mobile_env action=setup later"
  ;;
esac

chmod +x run.sh
echo
echo "Kurulum tamamlandi / Installed. Baslatmak icin / Start with: ./run.sh"
