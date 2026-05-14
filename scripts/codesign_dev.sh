#!/usr/bin/env bash
# Ad-hoc codesign for local dev — avoids Gatekeeper prompt on first launch.
set -euo pipefail

APP="${1:-dist/aivoice.app}"

echo "==> Ad-hoc codesigning $APP…"
codesign --force --deep --sign - "$APP"
echo "==> Done. Launch with: open $APP"
