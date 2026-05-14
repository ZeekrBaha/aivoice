# aivoice

A local-first push-to-talk voice dictation app for macOS. Hold **⌥ Option**, speak, release — your words appear wherever your cursor is. No cloud required by default.

---

## How it works

```
Hold ⌥                    Release ⌥
   │                           │
   ▼                           ▼
AudioCapture.start()    AudioCapture.stop()
(sounddevice 16kHz)          │
                             ▼
                        VAD.trim()
                    (silero-vad ONNX)
                    strips leading/trailing silence
                             │
                             ▼
                      STTEngine.transcribe()
                    ┌────────────────────────┐
                    │  local_mlx (default)   │
                    │  mlx-whisper           │
                    │  distil-whisper-large-v3│
                    │  runs on Apple Silicon │
                    │  Neural Engine (ANE)   │
                    ├────────────────────────┤
                    │  cloud_groq (optional) │
                    │  whisper-large-v3-turbo│
                    │  via Groq API          │
                    └────────────────────────┘
                             │
                             ▼
                    LLMCleaner.clean()  (optional)
                    ┌────────────────────────┐
                    │  ollama (default)      │
                    │  qwen2.5-coder:7b      │
                    │  runs locally          │
                    ├────────────────────────┤
                    │  openai (optional)     │
                    │  gpt-4o-mini           │
                    └────────────────────────┘
                    removes filler words, fixes punctuation
                             │
                             ▼
                    ClipboardInjector.inject()
                    saves clipboard → pastes text
                    via Cmd+V → restores clipboard
                             │
                             ▼
                    Text appears in focused app
```

---

## Architecture

```
src/aivoice/
├── __main__.py            # CLI entrypoint (--version flag, launches UI)
├── config.py              # pydantic-settings + TOML loader
├── version.py
│
├── pipeline/
│   ├── audio.py           # AudioCapture — sounddevice InputStream, async start/stop
│   ├── vad.py             # VAD — silero-vad ONNX silence trimmer
│   ├── inject.py          # ClipboardInjector — NSPasteboard + Cmd+V paste
│   ├── orchestrator.py    # Orchestrator — wires audio→vad→stt→cleaner→inject
│   │
│   ├── stt/
│   │   ├── base.py        # STTEngine ABC
│   │   ├── local_mlx.py   # mlx-whisper on Apple Silicon (default)
│   │   └── cloud_groq.py  # Groq Whisper API fallback
│   │
│   └── cleanup/
│       ├── base.py        # LLMCleaner ABC
│       ├── prompts.py     # System prompt builder (modes + vocabulary)
│       ├── ollama_cleaner.py   # Ollama local LLM (default)
│       └── openai_cleaner.py  # OpenAI API fallback
│
├── ui/
│   ├── menubar.py         # rumps NSStatusBar app + async pipeline thread
│   └── hotkey.py          # pynput global hotkey listener
│
└── utils/
    ├── perms.py           # macOS TCC permission probes
    └── keychain.py        # macOS keychain + env var secret loader
```

### Thread model

```
Main thread (macOS run loop)
  └── rumps.App.run()
        └── NSStatusBar icon + menu

Background thread (daemon)
  └── asyncio event loop
        ├── Orchestrator (audio → vad → stt → clean → inject)
        └── HoldHotkey (pynput listener → run_coroutine_threadsafe)
```

---

## Models

| Component | Default | Alternative |
|-----------|---------|-------------|
| STT | `mlx-community/distil-whisper-large-v3` (local, Apple Silicon) | `whisper-large-v3-turbo` via Groq |
| Cleanup | `qwen2.5-coder:7b` via Ollama (local) | `gpt-4o-mini` via OpenAI |
| VAD | `silero-vad` ONNX (local) | — |

**Local vs cloud trade-offs:**

| | Local (default) | Cloud |
|---|---|---|
| Privacy | All data stays on device | Audio/text sent to API |
| Cost | Free (electricity) | Groq ~$0.04/hr, OpenAI ~$0.01/1k tokens |
| Latency | ~0.8s warm (M4) | ~400ms (Groq) |
| Offline | Works offline | Requires internet |
| First run | Downloads model once (~1.5GB) | No setup |

---

## Requirements

- macOS 13+ on Apple Silicon (M1/M2/M3/M4)
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Ollama](https://ollama.com) with `qwen2.5-coder:7b` pulled (for cleanup)
- macOS permissions: **Microphone**, **Accessibility**, **Input Monitoring**

---

## Installation

```bash
# 1. Clone
git clone https://github.com/ZKirbaha/aivoice.git
cd aivoice

# 2. Install dependencies
uv sync

# 3. Pull the local LLM (for cleanup)
ollama pull qwen2.5-coder:7b

# 4. Optional: set Groq API key for cloud STT
echo "GROQ_API_KEY=your_key_here" > .env
```

---

## Running

**Development (terminal):**
```bash
uv run aivoice
```

**As a macOS app bundle:**
```bash
bash scripts/build_app.sh
open dist/aivoice.app
```

Grant **Accessibility** and **Input Monitoring** to `aivoice` (and `python3.11`) in System Settings → Privacy & Security when prompted.

---

## Configuration

Edit `~/.config/aivoice/settings.toml`:

```toml
# STT engine: "local_mlx" (default) or "cloud_groq"
stt_engine = "local_mlx"

# Enable LLM cleanup (removes filler words, fixes punctuation)
cleanup_enabled = true
cleanup_engine = "ollama"          # "ollama" or "openai"
ollama_cleanup_model = "qwen2.5-coder:7b"

# Hotkey: "alt" (Option), "cmd", "ctrl", "shift"
hotkey = "alt"

# Cleanup mode: "raw", "email", "code-comment", "slack"
mode = "raw"

# Custom vocabulary hints passed to the cleaner
vocabulary = ["myCompany", "productName"]
```

---

## Cleanup modes

| Mode | What it does |
|------|-------------|
| `raw` | Removes filler words, fixes basic punctuation |
| `email` | Formats as professional email prose |
| `code-comment` | Formats as a concise code comment |
| `slack` | Casual tone, keeps it short |

---

## Permissions required

| Permission | Why |
|------------|-----|
| Microphone | Record audio when Option is held |
| Accessibility | Read keyboard events globally via pynput |
| Input Monitoring | Listen to Option keydown/keyup globally |

---

## Running tests

```bash
uv sync --extra dev
uv run pytest
```

20 tests covering: config loading, audio capture, VAD trimming, STT engines, cleanup prompts, clipboard injection, orchestrator pipeline, and hotkey guard logic.

---

## Project structure

```
ai-voice-dictation/
├── src/aivoice/        # Main package
├── tests/              # pytest test suite (20 tests)
├── scripts/
│   ├── build_app.sh    # Builds dist/aivoice.app
│   └── codesign_dev.sh # Ad-hoc codesign for local dev
├── app_main.py         # Bundle entry point
├── setup_app.py        # py2app config (fallback)
├── pyproject.toml      # Project metadata + dependencies
└── .env                # GROQ_API_KEY (never committed)
```

---

## License

MIT
