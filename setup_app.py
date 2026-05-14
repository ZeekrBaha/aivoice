"""py2app build configuration for aivoice.app"""
from setuptools import setup

APP = ["app_main.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
    "plist": {
        "CFBundleName": "aivoice",
        "CFBundleDisplayName": "aivoice",
        "CFBundleIdentifier": "com.aivoice.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # menu-bar only, no Dock icon
        "NSMicrophoneUsageDescription": "aivoice needs microphone access to record your voice.",
        "NSAppleEventsUsageDescription": "aivoice uses AppleEvents to paste transcribed text.",
    },
    "packages": [
        "aivoice",
        "rumps",
        "pynput",
        "sounddevice",
        "numpy",
        "silero_vad",
        "onnxruntime",
        "mlx_whisper",
        "groq",
        "ollama",
        "openai",
        "pydantic",
        "pydantic_settings",
        "keyring",
        "dotenv",
    ],
    "excludes": ["matplotlib", "tkinter", "wx", "PyQt5", "PyQt6"],
}

setup(
    app=APP,
    name="aivoice",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
