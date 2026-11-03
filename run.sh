#!/usr/bin/env bash
# AI IQ 300 - Linux / macOS baslatici (launcher). Kullanim / usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Once ./install.sh calistirin / Run ./install.sh first."
  exit 1
fi
PORT="${1:-8300}"
exec .venv/bin/python launcher.py --port "$PORT"
