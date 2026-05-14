"""py2app build — run via scripts/build_app.sh"""
import sys
import py2app.build_app  # noqa: F401 — registers py2app command
from distutils.core import Distribution

sys.setrecursionlimit(5000)  # py2app AST walker needs this on large codebases

APP = ["app_main.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "aivoice", "rumps", "pynput", "sounddevice", "numpy",
        "silero_vad", "onnxruntime", "mlx_whisper", "groq",
        "ollama", "openai", "pydantic", "pydantic_settings", "keyring", "dotenv",
    ],
    "excludes": ["matplotlib", "tkinter", "wx", "PyQt5", "PyQt6"],
    "plist": {
        "CFBundleName": "aivoice",
        "CFBundleDisplayName": "aivoice",
        "CFBundleIdentifier": "com.aivoice.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "aivoice needs microphone access to record your voice.",
        "NSAppleEventsUsageDescription": "aivoice uses AppleEvents to paste transcribed text.",
    },
}

sys.argv = ["setup_app.py", "py2app", "--dist-dir", "dist"]

dist = Distribution(attrs=dict(
    name="aivoice",
    app=APP,
    options={"py2app": OPTIONS},
))
dist.parse_command_line()
dist.run_commands()
