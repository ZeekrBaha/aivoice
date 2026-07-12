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
                    │  whisper-large-v3-turbo│
                    │  runs on Apple Silicon │
                    │  Neural Engine (ANE)   │
                    │  + initial_prompt      │
                    │    biasing from vocab  │
                    │  + 1s trailing silence │
                    │    pad (no word drops) │
                    ├────────────────────────┤
                    │  cloud_groq (optional) │
                    │  whisper-large-v3-turbo│
                    │  via Groq API          │
                    └────────────────────────┘
                             │
                             ▼
                    LLMCleaner.clean()  (on by default)
                    ┌────────────────────────┐
                    │  ollama (default)      │
                    │  qwen2.5:7b-instruct   │
                    │  runs locally          │
                    ├────────────────────────┤
                    │  openai (optional)     │
                    │  gpt-4o-mini           │
                    └────────────────────────┘
                    fixes filler words, punctuation,
                    proper-noun phonetic mis-matches
                    (via vocabulary + few-shot examples)
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

## On-screen feedback

While you dictate, a floating glass overlay appears at the bottom-center of the
screen so you always know what the app is doing — no need to glance at the menu
bar.

```
   Hold ⌥                        Release ⌥                   Text pasted
      │                              │                            │
      ▼                              ▼                            ▼
 ┌─────────────────────┐    ┌─────────────────────┐      (overlay fades
 │ ▁▃▅█▆▃▂  Recording… │ →  │  ◐  Transcribing…   │ →      and scales out)
 └─────────────────────┘    └─────────────────────┘
  live waveform reacts        indeterminate spinner
  to your real mic level      while STT + cleanup run
```

- **Recording** — a live waveform whose bars react to your actual microphone
  level (louder speech → taller bars), so you can see the mic is capturing.
- **Transcribing** — the waveform morphs into a spinner while speech-to-text and
  the optional LLM cleanup run; it stays up until the text is pasted.
- **Done / empty / error** — the overlay always springs away, so it never hangs.
- **Reduce Motion** — if macOS *Reduce Motion* is on, the waveform is replaced by
  a static dot and the spring transitions become plain fades.

Implementation notes:

- `OverlayController` (`src/aivoice/ui/overlay.py`) owns a single reusable
  borderless, non-activating, click-through `NSPanel`. The dictation pipeline runs
  on a background thread and the audio tap on PortAudio's thread, so every public
  method marshals onto the main thread via `PyObjCTools.AppHelper.callAfter`.
- Mic levels feed the waveform through `AudioCapture.on_level`, computed by the
  pure `aivoice.pipeline.levels` helpers (RMS → dB-normalized `0..1`). The
  phase→display mapping (`OverlayPresentation`) and the waveform model
  (`WaveformBuffer`) are pure and unit-tested; the AppKit layer is verified by a
  manual smoke test (see `docs/overlay-hud-spec.md`).

---

## Architecture

```
src/aivoice/
├── __main__.py            # CLI entrypoint (--version flag, launches UI)
├── config.py              # pydantic-settings + TOML loader
├── version.py
│
├── pipeline/
│   ├── audio.py           # AudioCapture — sounddevice InputStream + on_level meter
│   ├── levels.py          # RMS → dB-normalized 0..1 mic-level helpers (pure)
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
│   ├── hotkey.py          # pynput global hotkey listener
│   └── overlay.py         # on-screen glass overlay (waveform + spinner)
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
| STT | `mlx-community/whisper-large-v3-turbo` (local, Apple Silicon) | `whisper-large-v3-turbo` via Groq |
| Cleanup | `qwen2.5:7b-instruct` via Ollama (local, on by default) | `gpt-4o-mini` via OpenAI |
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
- [Ollama](https://ollama.com) with `qwen2.5:7b-instruct` pulled (for cleanup)
- macOS permissions: **Microphone**, **Accessibility**, **Input Monitoring**

---

## Installation

```bash
# 1. Clone
git clone https://github.com/ZeekrBaha/aivoice.git
cd aivoice

# 2. Install dependencies
uv sync

# 3. Pull the local LLM (for cleanup)
ollama pull qwen2.5:7b-instruct

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
local_mlx_model = "mlx-community/whisper-large-v3-turbo"

# LLM cleanup (on by default — removes fillers, fixes punctuation,
# corrects phonetic mis-recognitions of proper nouns)
cleanup_enabled = true
cleanup_engine = "ollama"          # "ollama" or "openai"
ollama_cleanup_model = "qwen2.5:7b-instruct"

# Hotkey: "alt" (Option), "cmd", "ctrl", "shift"
hotkey = "alt"

# Cleanup mode: "raw", "email", "code-comment", "slack"
mode = "raw"

# Vocabulary — names, technical terms, emails, etc.
# Used in two places:
#   1. Whisper's initial_prompt (biases decoding toward these spellings)
#   2. The cleanup LLM (corrects phonetic mis-matches against this list)
# Keep under ~30 items — Whisper only honors the last ~200 tokens.
vocabulary = ["README", "ZeekrBaha", "baha.sadri@gmail.com", "kubectl", "Playwright"]
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

Covers: config loading, audio capture, VAD trimming, STT engines, cleanup prompts, clipboard injection, orchestrator pipeline (including `initial_prompt` plumbing and trailing-silence padding), hotkey guard logic, mic-level math, and the overlay phase/waveform logic.

---

## Project structure

```
ai-voice-dictation/
├── src/aivoice/        # Main package
├── tests/              # pytest test suite
├── scripts/
│   ├── build_app.sh    # Builds dist/aivoice.app
│   └── codesign_dev.sh # Ad-hoc codesign for local dev
├── app_main.py         # Bundle entry point
├── setup_app.py        # py2app config (fallback)
├── pyproject.toml      # Project metadata + dependencies
└── .env                # GROQ_API_KEY (never committed)
```

---

## Limitations / next steps

- **Local dev distribution only.** `scripts/codesign_dev.sh` ad-hoc signs the `.app` to skip the Gatekeeper prompt on first launch — this is not a notarized release path. There's no App Store / notarized-DMG distribution story; anyone else running this needs their own dev machine and Xcode command-line tools.
- **Apple Silicon only for local transcription.** `mlx-whisper` is gated on `platform_machine == 'arm64'` — Intel Macs fall back to the cloud Groq engine (or fail if no `GROQ_API_KEY` is set). No local-STT path for Intel.
- **No type checker.** For a pyobjc/AppKit-heavy codebase, a real type checker (pyright, basic mode) would catch import/attribute errors static analysis alone can't — exactly the class of bug fixed in an earlier commit (`683f1aa`, a Quartz import error).
- **No documented language/locale testing.** Whisper is multilingual by default and vocabulary biasing exists, but this README doesn't state which languages transcription accuracy has actually been verified against.
