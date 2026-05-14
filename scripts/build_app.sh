#!/usr/bin/env bash
# Builds a minimal .app bundle that launches aivoice via the uv venv Python.
# No py2app needed — just a shell wrapper + Info.plist.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

APP="dist/aivoice.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

echo "==> Creating bundle structure…"
rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES"

# Launcher script — runs aivoice inside the repo's venv
cat > "$MACOS/aivoice" <<'LAUNCHER'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"
exec "$DIR/.venv/bin/python" -m aivoice "$@"
LAUNCHER
chmod +x "$MACOS/aivoice"

# Info.plist
cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>             <string>aivoice</string>
  <key>CFBundleDisplayName</key>      <string>aivoice</string>
  <key>CFBundleIdentifier</key>       <string>com.aivoice.app</string>
  <key>CFBundleVersion</key>          <string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleExecutable</key>       <string>aivoice</string>
  <key>CFBundlePackageType</key>      <string>APPL</string>
  <key>LSUIElement</key>              <true/>
  <key>NSMicrophoneUsageDescription</key>
    <string>aivoice needs microphone access to record your voice.</string>
  <key>NSAppleEventsUsageDescription</key>
    <string>aivoice uses AppleEvents to paste transcribed text.</string>
  <key>PyRuntimeLocations</key>
    <array/>
</dict>
</plist>
PLIST

echo "==> Ad-hoc codesigning…"
codesign --force --deep --sign - "$APP"

echo ""
echo "==> Done: $APP"
echo "    Launch: open $APP"
echo "    Or drag to /Applications for permanent install."
