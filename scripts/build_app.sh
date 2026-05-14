#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "==> Installing py2app into venv…"
uv pip install py2app

echo "==> Building aivoice.app…"
uv run python setup_app.py

echo "==> Build complete: dist/aivoice.app"
echo "    Next: bash scripts/codesign_dev.sh && open dist/aivoice.app"
