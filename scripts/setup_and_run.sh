#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/setup_and_run.sh [PORT]
PORT="${1:-${PORT:-5000}}"

echo "== SeaMaster bootstrap (Unix/macOS) =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 is required but not found. Please install Python 3.10+ and re-run." >&2
  exit 1
fi

# Ensure we run from repo root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

if [ ! -d .venv ]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Upgrading pip/setuptools/wheel..."
pip install --upgrade pip setuptools wheel

echo "Installing requirements.txt ..."
pip install -r requirements.txt

echo "Starting Flask dev server on port ${PORT} ..."
flask --app app.py init-db
flask --app app.py run --debug -p "${PORT}"