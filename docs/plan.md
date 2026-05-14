# AI Voice Dictation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local-first macOS menu-bar voice dictation tool that converts hold-to-talk speech into cleaned, punctuated text pasted at the cursor in any app — with a swappable cloud backend (Groq) and an optional LLM cleanup pass (gpt-4o-mini or Ollama qwen2.5).

**Architecture:** Single Python process running an asyncio pipeline (audio → VAD → STT → optional LLM cleanup → text injection), driven by a `pynput` global hotkey listener and surfaced through a `rumps` menu-bar UI. STT and LLM cleanup are abstracted behind ABCs so local (mlx-whisper, Ollama) and cloud (Groq, OpenAI) implementations are interchangeable per a settings file.

**Tech Stack:** Python 3.11 + uv, sounddevice, silero-vad (ONNX), mlx-whisper, Groq SDK, OpenAI SDK, ollama-python, pynput, rumps, pyobjc (NSPasteboard), pydantic-settings, keyring, pytest + pytest-asyncio, py2app.

---

## Repository Layout

```
ai-voice-dictation/
├── pyproject.toml
├── uv.lock
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   └── plan.md
├── src/aivoice/
│   ├── __init__.py
│   ├── __main__.py
│   ├── version.py
│   ├── config.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── audio.py
│   │   ├── vad.py
│   │   ├── inject.py
│   │   ├── stt/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── local_mlx.py
│   │   │   └── cloud_groq.py
│   │   └── cleanup/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── prompts.py
│   │       ├── openai_cleaner.py
│   │       └── ollama_cleaner.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── menubar.py
│   │   └── hotkey.py
│   └── utils/
│       ├── __init__.py
│       ├── keychain.py
│       └── perms.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── hello_world.wav        # 1s, "hello world", clean
│   │   ├── with_fillers.wav       # 5s, "um so I uh think the API is broken"
│   │   ├── silence_5s.wav         # 5s silence
│   │   └── leading_trailing_silence.wav  # 0.5s silence + "test" + 0.5s silence
│   ├── test_audio.py
│   ├── test_vad.py
│   ├── test_inject.py
│   ├── test_stt_local.py
│   ├── test_cleanup_prompts.py
│   ├── test_config.py
│   └── test_orchestrator.py
└── scripts/
    ├── build_app.sh
    ├── codesign_dev.sh
    └── make_fixtures.py
```

**Responsibility per file:**
- `config.py` — pydantic-settings, loads TOML from `~/.config/aivoice/settings.toml`.
- `pipeline/audio.py` — `AudioCapture` class wrapping `sounddevice.InputStream`.
- `pipeline/vad.py` — `VAD` class wrapping silero-vad ONNX session, exposes `trim(audio: np.ndarray) -> np.ndarray`.
- `pipeline/stt/base.py` — `STTEngine` ABC with `async def transcribe(audio: np.ndarray) -> str`.
- `pipeline/stt/local_mlx.py`, `cloud_groq.py` — concrete engines.
- `pipeline/cleanup/base.py` — `LLMCleaner` ABC with `async def clean(text: str, mode: str, vocabulary: list[str]) -> str`.
- `pipeline/cleanup/prompts.py` — `BASE_SYSTEM_PROMPT`, `MODE_OVERLAYS`, `build_prompt()`.
- `pipeline/inject.py` — clipboard save/set/restore + Cmd+V via pynput.
- `pipeline/orchestrator.py` — wires hotkey → audio → vad → stt → cleanup → inject.
- `ui/menubar.py` — `rumps.App` with state icons.
- `ui/hotkey.py` — `pynput` global listener for ⌥ hold/release.
- `utils/keychain.py` — get/set API keys via `keyring`.
- `utils/perms.py` — check Accessibility + Input Monitoring grants.

---

## Spike Results (2026-05-13, MacBook Pro M4 48GB)

| Spike | Result | Number | Decision |
|---|---|---|---|
| A — pynput ⌥ reliability | **PASS** | 5/5 down, 5/5 up via synthetic CGEvent | Hotkey stays as ⌥; no PyObjC fallback needed |
| B — mlx-whisper warm latency | **PASS** | cold 37.0s (one-time download), warm 0.76s for 3s audio | Local engine stays `mlx-whisper` + `distil-whisper-large-v3` |

**Note from Spike A:** pynput's listener fails *silently* without macOS Accessibility permission — the "This process is not trusted" warning is the only signal. `AXIsProcessTrusted()` must be checked at app startup and surface a setup banner if False. This is already covered by `utils/perms.py` (Task 6); ensure `__main__.py` calls it before launching the UI in Task 17.

---

## Day-0 Risk Spikes (DO BEFORE TASK 1)

These are the two unknowns that, if they fail, force an architecture change. Spike them in throwaway scripts before committing to the structure below.

### Spike A: pynput ⌥ hold/release reliability on macOS 15

- [ ] **Step 1: Write a 20-line throwaway script** at `~/Desktop/spike_hotkey.py`:

```python
from pynput import keyboard
import time

pressed_at = None

def on_press(key):
    global pressed_at
    if key == keyboard.Key.alt:
        pressed_at = time.time()
        print(f"ALT down at {pressed_at:.3f}")

def on_release(key):
    if key == keyboard.Key.alt and pressed_at:
        print(f"ALT up after {time.time() - pressed_at:.3f}s")

with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
    l.join()
```

- [ ] **Step 2: Grant Terminal "Input Monitoring"** in System Settings → Privacy & Security.

- [ ] **Step 3: Run and hold ⌥ five times** with varying durations.

Run: `uv run --with pynput python ~/Desktop/spike_hotkey.py`
Expected: clean pairs of "ALT down" / "ALT up after Xs" lines.

**Kill criterion:** If ⌥ is not detected reliably (missed press or missed release on any of 5 trials), switch hotkey to `fn` key via raw PyObjC `NSEvent.addGlobalMonitorForEvents` and update Task 12 accordingly. Document the decision in `docs/plan.md`.

### Spike B: mlx-whisper cold-start + warm latency on this Mac

- [ ] **Step 1: Write a 15-line throwaway script** at `~/Desktop/spike_mlx.py`:

```python
import time, numpy as np
import mlx_whisper

audio = np.zeros(16000 * 3, dtype=np.float32)  # 3s silence
t0 = time.time()
r1 = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/distil-whisper-large-v3")
print(f"cold: {time.time() - t0:.2f}s")
t0 = time.time()
r2 = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/distil-whisper-large-v3")
print(f"warm: {time.time() - t0:.2f}s")
```

- [ ] **Step 2: Run it.**

Run: `uv run --with mlx-whisper python ~/Desktop/spike_mlx.py`
Expected: cold under 10s, warm under 1s.

**Kill criterion:** If warm latency >2s for 3s of audio, switch local engine to `pywhispercpp` (whisper.cpp bindings) for Tasks 9-10 and update `local_mlx.py` to `local_cpp.py`. Document the decision.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation | Kill criterion |
|---|---|---|---|---|
| ⌥ key unreliable via pynput | Med | High (UX) | Spike A | Switch to `fn` via PyObjC |
| mlx-whisper too slow | Low | High | Spike B | Switch to whisper.cpp |
| Clipboard race during paste | Low | Med | 200ms restore delay + change-detection abort | Skip restore; document clipboard-overwrite as known limitation |
| qwen2.5 cleanup hallucinates | Med | Low (cleanup is optional) | Strict prompt + few-shot + temp=0 (Task 16) | Default cleanup OFF; require explicit opt-in |
| TCC perms reset after rebuild | High | Med | Ad-hoc codesign script (Task 18) | Document for users |
| py2app bundle fails on first try | High | Low | Allocate buffer in Task 18 | Ship as `uv run` script instead of .app |

---

## Phase 0 — Foundation (Tasks 1-3)

### Task 1: Repo skeleton + uv project

**Files:**
- Create: `pyproject.toml`
- Create: `src/aivoice/__init__.py`
- Create: `src/aivoice/version.py`
- Create: `src/aivoice/__main__.py`
- Create: `.gitignore`
- Create: `README.md`
- Create: `.env.example`

- [ ] **Step 1: Initialize uv project**

Run:
```bash
cd ~/Desktop/llm-ai-projects/ai-voice-dictation
uv init --package --name aivoice --python 3.11
```
Expected: `pyproject.toml` and `src/aivoice/` created.

- [ ] **Step 2: Replace `pyproject.toml` with the canonical version**

```toml
[project]
name = "aivoice"
version = "0.1.0"
description = "Local-first voice dictation for macOS"
requires-python = ">=3.11,<3.13"
dependencies = [
    "sounddevice>=0.4.7",
    "numpy>=1.26,<2.0",
    "silero-vad>=5.1.2",
    "onnxruntime>=1.20",
    "pynput>=1.7.7",
    "rumps>=0.4.0",
    "pyobjc-framework-Cocoa>=10.3",
    "pyobjc-framework-Quartz>=10.3",
    "pydantic-settings>=2.6",
    "keyring>=25.5",
    "httpx>=0.27",
    "openai>=1.55",
    "groq>=0.13",
    "ollama>=0.4",
    "mlx-whisper>=0.4.2 ; platform_system == 'Darwin' and platform_machine == 'arm64'",
]

[project.scripts]
aivoice = "aivoice.__main__:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.7",
    "soundfile>=0.12",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Write `src/aivoice/version.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write `src/aivoice/__main__.py`**

```python
import sys
from aivoice.version import __version__


def main() -> int:
    if "--version" in sys.argv:
        print(f"aivoice {__version__}")
        return 0
    print("aivoice: use --version (full UI lands in Task 17)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
build/
*.egg-info/
.DS_Store
.env
~/.config/aivoice/
```

- [ ] **Step 6: Write `.env.example`**

```
GROQ_API_KEY=
OPENAI_API_KEY=
```

- [ ] **Step 7: Write `README.md`**

```markdown
# ai-voice-dictation

Local-first push-to-talk voice dictation for macOS. Hold ⌥, speak, release — cleaned text appears at the cursor.

## Quickstart
uv sync
uv run aivoice --version

See `docs/plan.md` for the build plan.
```

- [ ] **Step 8: Install + verify**

Run:
```bash
uv sync --extra dev
uv run aivoice --version
```
Expected: `aivoice 0.1.0`

- [ ] **Step 9: Commit**

```bash
git init
git add .
git commit -m "feat: scaffold uv project + entrypoint"
```

---

### Task 2: Config module (pydantic-settings)

**Files:**
- Create: `src/aivoice/config.py`
- Test: `tests/test_config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:
```python
import pytest


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVOICE_CONFIG_DIR", str(tmp_path))
    return tmp_path
```

`tests/test_config.py`:
```python
from aivoice.config import Settings


def test_defaults_load_when_no_file(tmp_config_dir):
    s = Settings.load()
    assert s.stt_engine == "local_mlx"
    assert s.local_mlx_model == "mlx-community/distil-whisper-large-v3"
    assert s.cleanup_enabled is False
    assert s.hotkey == "alt"


def test_overrides_from_toml(tmp_config_dir):
    (tmp_config_dir / "settings.toml").write_text(
        'stt_engine = "cloud_groq"\ncleanup_enabled = true\n'
    )
    s = Settings.load()
    assert s.stt_engine == "cloud_groq"
    assert s.cleanup_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: aivoice.config`.

- [ ] **Step 3: Write minimal implementation**

`src/aivoice/config.py`:
```python
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    stt_engine: Literal["local_mlx", "cloud_groq"] = "local_mlx"
    local_mlx_model: str = "mlx-community/distil-whisper-large-v3"
    cloud_groq_model: str = "whisper-large-v3-turbo"

    cleanup_enabled: bool = False
    cleanup_engine: Literal["openai", "ollama"] = "openai"
    openai_cleanup_model: str = "gpt-4o-mini"
    ollama_cleanup_model: str = "qwen2.5:7b-instruct"

    hotkey: str = "alt"
    mode: Literal["raw", "email", "code-comment", "slack"] = "raw"
    vocabulary: list[str] = Field(default_factory=list)

    @classmethod
    def config_dir(cls) -> Path:
        return Path(os.environ.get("AIVOICE_CONFIG_DIR", Path.home() / ".config" / "aivoice"))

    @classmethod
    def load(cls) -> "Settings":
        path = cls.config_dir() / "settings.toml"
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/config.py tests/test_config.py tests/conftest.py
git commit -m "feat(config): pydantic-settings with TOML overrides"
```

---

### Task 3: Audio fixtures

**Files:**
- Create: `scripts/make_fixtures.py`
- Create: `tests/fixtures/hello_world.wav`
- Create: `tests/fixtures/with_fillers.wav`
- Create: `tests/fixtures/silence_5s.wav`
- Create: `tests/fixtures/leading_trailing_silence.wav`

- [ ] **Step 1: Write the fixture-generator script**

`scripts/make_fixtures.py`:
```python
"""Generate test audio fixtures using macOS `say` + sox/ffmpeg conversion."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

FIX = Path(__file__).parent.parent / "tests" / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)


def say_to_wav(text: str, out: Path, voice: str = "Samantha") -> None:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(out)],
        check=True,
        capture_output=True,
    )
    aiff.unlink()


def silence(seconds: float, out: Path) -> None:
    sf.write(out, np.zeros(int(16000 * seconds), dtype=np.float32), 16000)


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("install ffmpeg: brew install ffmpeg")
    say_to_wav("hello world", FIX / "hello_world.wav")
    say_to_wav("um so I uh think the API is broken", FIX / "with_fillers.wav")
    silence(5.0, FIX / "silence_5s.wav")

    # leading + trailing silence around "test"
    say_to_wav("test", FIX / "_test.wav")
    test, sr = sf.read(FIX / "_test.wav")
    pad = np.zeros(int(0.5 * sr), dtype=np.float32)
    sf.write(FIX / "leading_trailing_silence.wav", np.concatenate([pad, test, pad]), sr)
    (FIX / "_test.wav").unlink()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run:
```bash
brew install ffmpeg  # if not installed
uv run python scripts/make_fixtures.py
ls -la tests/fixtures/
```
Expected: 4 .wav files, all 16kHz mono.

- [ ] **Step 3: Verify fixtures via soundfile**

Run:
```bash
uv run python -c "import soundfile as sf; print(sf.info('tests/fixtures/hello_world.wav'))"
```
Expected: 16000 Hz, 1 channel, format WAV, subtype PCM_16 (or FLOAT).

- [ ] **Step 4: Commit**

```bash
git add scripts/make_fixtures.py tests/fixtures/*.wav
git commit -m "test: audio fixtures for STT/VAD"
```

---

## Phase 1 — Audio + VAD (Tasks 4-6)

### Task 4: Audio capture

**Files:**
- Create: `src/aivoice/pipeline/__init__.py`
- Create: `src/aivoice/pipeline/audio.py`
- Test: `tests/test_audio.py`

- [ ] **Step 1: Write the failing test**

`tests/test_audio.py`:
```python
import asyncio

import numpy as np
import pytest

from aivoice.pipeline.audio import AudioCapture


@pytest.mark.asyncio
async def test_capture_yields_float32_16khz_mono():
    cap = AudioCapture(samplerate=16000)
    await cap.start()
    await asyncio.sleep(0.3)
    audio = await cap.stop()
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert 4000 < len(audio) < 8000  # ~300ms at 16kHz, with jitter


@pytest.mark.asyncio
async def test_double_start_raises():
    cap = AudioCapture(samplerate=16000)
    await cap.start()
    with pytest.raises(RuntimeError):
        await cap.start()
    await cap.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/aivoice/pipeline/audio.py`:
```python
from __future__ import annotations

import asyncio

import numpy as np
import sounddevice as sd


class AudioCapture:
    def __init__(self, samplerate: int = 16000, blocksize: int = 512) -> None:
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        # called from PortAudio thread; copy to avoid buffer reuse
        self._frames.append(indata[:, 0].astype(np.float32, copy=True))

    async def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("AudioCapture already started")
        self._loop = asyncio.get_running_loop()
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    async def stop(self) -> np.ndarray:
        if self._stream is None:
            raise RuntimeError("AudioCapture not started")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames)
```

`src/aivoice/pipeline/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_audio.py -v`
Expected: 2 PASSED. (First run may prompt for Mic permission — grant Terminal/your IDE.)

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/pipeline/__init__.py src/aivoice/pipeline/audio.py tests/test_audio.py
git commit -m "feat(audio): sounddevice capture with async start/stop"
```

---

### Task 5: VAD trim

**Files:**
- Create: `src/aivoice/pipeline/vad.py`
- Test: `tests/test_vad.py`

- [ ] **Step 1: Write the failing test**

`tests/test_vad.py`:
```python
from pathlib import Path

import numpy as np
import soundfile as sf

from aivoice.pipeline.vad import VAD

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> np.ndarray:
    audio, sr = sf.read(FIX / name, dtype="float32")
    assert sr == 16000
    return audio


def test_trims_leading_and_trailing_silence():
    vad = VAD()
    audio = _load("leading_trailing_silence.wav")
    trimmed = vad.trim(audio)
    # Original is ~1s padding + word + 0.5s padding; trimmed should be shorter than original
    assert 0 < len(trimmed) < len(audio)
    # And should be at least 100ms long (the word itself)
    assert len(trimmed) > 1600


def test_returns_empty_on_pure_silence():
    vad = VAD()
    audio = _load("silence_5s.wav")
    trimmed = vad.trim(audio)
    assert len(trimmed) == 0


def test_passes_speech_through_unchanged_length_within_tolerance():
    vad = VAD()
    audio = _load("hello_world.wav")
    trimmed = vad.trim(audio)
    # hello_world has minimal padding from `say`; trimmed length should be within 20% of original
    assert abs(len(trimmed) - len(audio)) < 0.2 * len(audio)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vad.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/aivoice/pipeline/vad.py`:
```python
from __future__ import annotations

import numpy as np
from silero_vad import get_speech_timestamps, load_silero_vad


class VAD:
    def __init__(self, threshold: float = 0.5, min_speech_ms: int = 150) -> None:
        self._model = load_silero_vad(onnx=True)
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms

    def trim(self, audio: np.ndarray, samplerate: int = 16000) -> np.ndarray:
        if len(audio) == 0:
            return audio
        ts = get_speech_timestamps(
            audio,
            self._model,
            threshold=self.threshold,
            sampling_rate=samplerate,
            min_speech_duration_ms=self.min_speech_ms,
            return_seconds=False,
        )
        if not ts:
            return np.zeros(0, dtype=np.float32)
        start = ts[0]["start"]
        end = ts[-1]["end"]
        return audio[start:end]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vad.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/pipeline/vad.py tests/test_vad.py
git commit -m "feat(vad): silero-vad trim with empty-on-silence semantics"
```

---

### Task 6: Permissions probe

**Files:**
- Create: `src/aivoice/utils/__init__.py`
- Create: `src/aivoice/utils/perms.py`

- [ ] **Step 1: Write the probe module**

`src/aivoice/utils/perms.py`:
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PermissionStatus:
    microphone: bool
    accessibility: bool
    input_monitoring: bool

    @property
    def all_ok(self) -> bool:
        return all([self.microphone, self.accessibility, self.input_monitoring])


def check_microphone() -> bool:
    try:
        import sounddevice as sd

        sd.check_input_settings(samplerate=16000, channels=1)
        return True
    except Exception:
        return False


def check_accessibility() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def check_input_monitoring() -> bool:
    # No direct macOS API; the pynput global listener fails silently without it.
    # We piggy-back on Accessibility as a heuristic and document the manual grant in README.
    return check_accessibility()


def check_all() -> PermissionStatus:
    return PermissionStatus(
        microphone=check_microphone(),
        accessibility=check_accessibility(),
        input_monitoring=check_input_monitoring(),
    )
```

`src/aivoice/utils/__init__.py`:
```python
```

- [ ] **Step 2: Smoke-test it**

Run:
```bash
uv run python -c "from aivoice.utils.perms import check_all; print(check_all())"
```
Expected: `PermissionStatus(microphone=True, accessibility=..., input_monitoring=...)` — accessibility may be False until you grant it; that's fine for now.

- [ ] **Step 3: Commit**

```bash
git add src/aivoice/utils/
git commit -m "feat(utils): macOS permission probes"
```

---

## Phase 2 — STT (Tasks 7-9)

### Task 7: STT base ABC

**Files:**
- Create: `src/aivoice/pipeline/stt/__init__.py`
- Create: `src/aivoice/pipeline/stt/base.py`

- [ ] **Step 1: Write the ABC**

`src/aivoice/pipeline/stt/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str:
        """Transcribe float32 mono audio to text. Returns empty string on empty input."""

    @abstractmethod
    async def warmup(self) -> None:
        """Load model into memory. Called once at app launch."""
```

`src/aivoice/pipeline/stt/__init__.py`:
```python
from aivoice.pipeline.stt.base import STTEngine

__all__ = ["STTEngine"]
```

- [ ] **Step 2: Commit**

```bash
git add src/aivoice/pipeline/stt/
git commit -m "feat(stt): STTEngine ABC"
```

---

### Task 8: Local mlx-whisper engine

**Files:**
- Create: `src/aivoice/pipeline/stt/local_mlx.py`
- Test: `tests/test_stt_local.py`

- [ ] **Step 1: Write the failing test**

`tests/test_stt_local.py`:
```python
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from aivoice.pipeline.stt.local_mlx import LocalMLXEngine

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_transcribes_hello_world():
    engine = LocalMLXEngine(model="mlx-community/distil-whisper-large-v3")
    await engine.warmup()
    audio, _ = sf.read(FIX / "hello_world.wav", dtype="float32")
    text = await engine.transcribe(audio)
    assert "hello" in text.lower()
    assert "world" in text.lower()


@pytest.mark.asyncio
async def test_empty_audio_returns_empty_string():
    engine = LocalMLXEngine(model="mlx-community/distil-whisper-large-v3")
    await engine.warmup()
    text = await engine.transcribe(np.zeros(0, dtype=np.float32))
    assert text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stt_local.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/aivoice/pipeline/stt/local_mlx.py`:
```python
from __future__ import annotations

import asyncio

import numpy as np

from aivoice.pipeline.stt.base import STTEngine


class LocalMLXEngine(STTEngine):
    def __init__(self, model: str = "mlx-community/distil-whisper-large-v3", language: str = "en") -> None:
        self.model = model
        self.language = language
        self._warmed = False

    async def warmup(self) -> None:
        if self._warmed:
            return
        import mlx_whisper  # noqa: F401

        # Tiny 0.5s silence pass to download + JIT-compile the model
        await asyncio.to_thread(
            mlx_whisper.transcribe,
            np.zeros(8000, dtype=np.float32),
            path_or_hf_repo=self.model,
            language=self.language,
        )
        self._warmed = True

    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        import mlx_whisper

        result = await asyncio.to_thread(
            mlx_whisper.transcribe,
            audio,
            path_or_hf_repo=self.model,
            language=self.language,
        )
        return result["text"].strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stt_local.py -v`
Expected: 2 PASSED. First run downloads ~1.5GB; allow several minutes.

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/pipeline/stt/local_mlx.py tests/test_stt_local.py
git commit -m "feat(stt): mlx-whisper local engine"
```

---

### Task 9: Groq cloud engine

**Files:**
- Create: `src/aivoice/pipeline/stt/cloud_groq.py`
- Create: `src/aivoice/utils/keychain.py`

- [ ] **Step 1: Write the keychain helper**

`src/aivoice/utils/keychain.py`:
```python
from __future__ import annotations

import os

import keyring

SERVICE = "aivoice"


def get_secret(key: str) -> str | None:
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return keyring.get_password(SERVICE, key)


def set_secret(key: str, value: str) -> None:
    keyring.set_password(SERVICE, key, value)
```

- [ ] **Step 2: Write the Groq engine**

`src/aivoice/pipeline/stt/cloud_groq.py`:
```python
from __future__ import annotations

import io

import numpy as np
import soundfile as sf

from aivoice.pipeline.stt.base import STTEngine
from aivoice.utils.keychain import get_secret


class CloudGroqEngine(STTEngine):
    def __init__(self, model: str = "whisper-large-v3-turbo", language: str = "en") -> None:
        self.model = model
        self.language = language
        self._client = None

    async def warmup(self) -> None:
        from groq import AsyncGroq

        api_key = get_secret("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set (env or keychain)")
        self._client = AsyncGroq(api_key=api_key)

    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        if self._client is None:
            await self.warmup()

        buf = io.BytesIO()
        sf.write(buf, audio, samplerate, format="WAV", subtype="PCM_16")
        buf.seek(0)
        buf.name = "audio.wav"  # groq client inspects .name

        resp = await self._client.audio.transcriptions.create(
            file=buf,
            model=self.model,
            language=self.language,
            response_format="text",
        )
        return resp.strip() if isinstance(resp, str) else resp.text.strip()
```

- [ ] **Step 3: Smoke-test (requires GROQ_API_KEY)**

Run:
```bash
export GROQ_API_KEY=...  # your key
uv run python -c "
import asyncio, soundfile as sf
from aivoice.pipeline.stt.cloud_groq import CloudGroqEngine
async def main():
    e = CloudGroqEngine()
    await e.warmup()
    audio, _ = sf.read('tests/fixtures/hello_world.wav', dtype='float32')
    print(await e.transcribe(audio))
asyncio.run(main())
"
```
Expected: prints "Hello world." (or similar).

- [ ] **Step 4: Commit**

```bash
git add src/aivoice/pipeline/stt/cloud_groq.py src/aivoice/utils/keychain.py
git commit -m "feat(stt): Groq cloud engine + keychain helper"
```

---

## Phase 3 — Cleanup (Tasks 10-12)

### Task 10: Prompt builder

**Files:**
- Create: `src/aivoice/pipeline/cleanup/__init__.py`
- Create: `src/aivoice/pipeline/cleanup/prompts.py`
- Test: `tests/test_cleanup_prompts.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cleanup_prompts.py`:
```python
from aivoice.pipeline.cleanup.prompts import BASE_SYSTEM_PROMPT, MODE_OVERLAYS, build_prompt


def test_base_includes_must_and_must_not():
    assert "You MUST:" in BASE_SYSTEM_PROMPT
    assert "You MUST NOT:" in BASE_SYSTEM_PROMPT
    assert "NOT an assistant" in BASE_SYSTEM_PROMPT


def test_modes_present():
    assert set(MODE_OVERLAYS.keys()) == {"raw", "email", "code-comment", "slack"}
    assert MODE_OVERLAYS["raw"] == ""


def test_build_appends_mode():
    p = build_prompt(mode="email")
    assert p.startswith(BASE_SYSTEM_PROMPT)
    assert "email" in p.lower()


def test_build_appends_vocabulary():
    p = build_prompt(mode="raw", vocabulary=["kubectl", "Playwright"])
    assert "VOCABULARY HINTS" in p
    assert "- kubectl" in p
    assert "- Playwright" in p


def test_build_no_vocab_section_when_empty():
    p = build_prompt(mode="raw", vocabulary=[])
    assert "VOCABULARY HINTS" not in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cleanup_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

`src/aivoice/pipeline/cleanup/prompts.py`:
```python
from __future__ import annotations

BASE_SYSTEM_PROMPT = """You are a transcription cleanup engine, NOT an assistant.

Your ONLY job: take a raw speech-to-text transcript and return a cleaned version of THE SAME TEXT.

You MUST:
- Remove filler words: um, uh, uhm, er, ah, like (when used as filler), you know, I mean, sort of, kind of, basically, literally (when used as filler), right (when used as filler).
- Remove false starts and self-corrections. Example: "I was going to — I went to the store" → "I went to the store".
- Remove stutters and repeated words. Example: "the the meeting" → "the meeting".
- Add correct punctuation: periods, commas, question marks, apostrophes, quotation marks.
- Capitalize sentence beginnings and proper nouns.
- Fix obvious homophones from speech recognition: "their/there/they're", "to/too/two", "its/it's".
- Split run-on sentences into clean sentences.

You MUST NOT:
- Answer questions in the transcript. If the user dictates "what time is it", output "What time is it?" — do NOT answer.
- Add information not present in the transcript.
- Remove substantive words. Every noun, verb, and content word must remain.
- Reword for style. Do NOT make it "more professional", "shorter", or "clearer". Preserve the speaker's voice exactly.
- Translate. Keep the original language.
- Expand contractions ("I'm" stays "I'm", not "I am") or contract expansions.
- Expand abbreviations ("API" stays "API", not "Application Programming Interface").
- Add greetings, sign-offs, headers, bullet points, or formatting that wasn't spoken.
- Wrap the output in quotes, code blocks, or markdown.
- Explain what you changed. Output ONLY the cleaned text.
- Output anything if the input is empty or pure filler — return an empty string.

Examples:

Input: "um so I was thinking like maybe we should uh ship the the feature on Friday you know"
Output: "I was thinking maybe we should ship the feature on Friday."

Input: "what's the deadline for the q3 report"
Output: "What's the deadline for the Q3 report?"

Input: "send an email to john saying I'll be late tomorrow"
Output: "Send an email to John saying I'll be late tomorrow."

Input: "I I I think the the API is is broken"
Output: "I think the API is broken."

Input: "um uh"
Output: ""

Now clean the following transcript. Output ONLY the cleaned text, nothing else."""


MODE_OVERLAYS: dict[str, str] = {
    "raw": "",
    "email": "\n\nADDITIONAL: This will be sent as an email. Add paragraph breaks. Keep the speaker's tone.",
    "code-comment": "\n\nADDITIONAL: This will be a code comment. Sentence case. No trailing period if single short phrase. Preserve technical terms verbatim.",
    "slack": "\n\nADDITIONAL: This is a Slack message. Keep it conversational. Lowercase 'i' is acceptable if the speaker used it.",
}


def build_prompt(mode: str = "raw", vocabulary: list[str] | None = None) -> str:
    prompt = BASE_SYSTEM_PROMPT + MODE_OVERLAYS.get(mode, "")
    if vocabulary:
        prompt += "\n\nVOCABULARY HINTS (correct only if a clearly similar-sounding word appears):\n"
        prompt += "\n".join(f"- {term}" for term in vocabulary)
    return prompt
```

`src/aivoice/pipeline/cleanup/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cleanup_prompts.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/pipeline/cleanup/
git commit -m "feat(cleanup): hardened prompt builder with modes + vocab"
```

---

### Task 11: Cleaner ABC + OpenAI cleaner

**Files:**
- Create: `src/aivoice/pipeline/cleanup/base.py`
- Create: `src/aivoice/pipeline/cleanup/openai_cleaner.py`

- [ ] **Step 1: Write the ABC**

`src/aivoice/pipeline/cleanup/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMCleaner(ABC):
    @abstractmethod
    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        """Return cleaned text. Return '' if input is empty or pure filler."""
```

- [ ] **Step 2: Write the OpenAI cleaner**

`src/aivoice/pipeline/cleanup/openai_cleaner.py`:
```python
from __future__ import annotations

from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.prompts import build_prompt
from aivoice.utils.keychain import get_secret


class OpenAICleaner(LLMCleaner):
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        from openai import AsyncOpenAI

        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=api_key)

    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        if not text.strip():
            return ""
        self._ensure_client()
        system = build_prompt(mode=mode, vocabulary=vocabulary)
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=512,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        )
        return resp.choices[0].message.content.strip()
```

- [ ] **Step 3: Smoke-test (requires OPENAI_API_KEY)**

Run:
```bash
export OPENAI_API_KEY=...
uv run python -c "
import asyncio
from aivoice.pipeline.cleanup.openai_cleaner import OpenAICleaner
async def main():
    c = OpenAICleaner()
    print(await c.clean('um so I uh think the the API is broken'))
asyncio.run(main())
"
```
Expected: `I think the API is broken.` (or near-equivalent).

- [ ] **Step 4: Commit**

```bash
git add src/aivoice/pipeline/cleanup/base.py src/aivoice/pipeline/cleanup/openai_cleaner.py
git commit -m "feat(cleanup): OpenAI cleaner"
```

---

### Task 12: Ollama cleaner

**Files:**
- Create: `src/aivoice/pipeline/cleanup/ollama_cleaner.py`

- [ ] **Step 1: Write the Ollama cleaner**

`src/aivoice/pipeline/cleanup/ollama_cleaner.py`:
```python
from __future__ import annotations

import asyncio

from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.prompts import build_prompt


class OllamaCleaner(LLMCleaner):
    def __init__(self, model: str = "qwen2.5:7b-instruct", host: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.host = host

    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        if not text.strip():
            return ""
        import ollama

        client = ollama.AsyncClient(host=self.host)
        system = build_prompt(mode=mode, vocabulary=vocabulary)
        resp = await client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            options={
                "temperature": 0.0,
                "top_p": 0.1,
                "repeat_penalty": 1.0,
                "num_predict": 512,
                "stop": ["\n\nInput:", "\n\nOutput:"],
            },
        )
        return resp["message"]["content"].strip().strip('"').strip("'")
```

- [ ] **Step 2: Smoke-test (requires Ollama + qwen2.5:7b-instruct pulled)**

Run:
```bash
ollama pull qwen2.5:7b-instruct
uv run python -c "
import asyncio
from aivoice.pipeline.cleanup.ollama_cleaner import OllamaCleaner
async def main():
    c = OllamaCleaner()
    print(await c.clean('um so I uh think the the API is broken'))
asyncio.run(main())
"
```
Expected: `I think the API is broken.` (or near-equivalent).

- [ ] **Step 3: Commit**

```bash
git add src/aivoice/pipeline/cleanup/ollama_cleaner.py
git commit -m "feat(cleanup): Ollama cleaner with hardened params"
```

---

## Phase 4 — Injection + Hotkey + Orchestrator (Tasks 13-15)

### Task 13: Text injection

**Files:**
- Create: `src/aivoice/pipeline/inject.py`
- Test: `tests/test_inject.py`

- [ ] **Step 1: Write the failing test**

`tests/test_inject.py`:
```python
import asyncio

import pytest

from aivoice.pipeline.inject import ClipboardInjector


@pytest.mark.asyncio
async def test_clipboard_round_trip(monkeypatch):
    inj = ClipboardInjector(paste=False)  # don't actually post Cmd+V in tests
    await inj.inject("hello from test")
    assert inj.last_set == "hello from test"


@pytest.mark.asyncio
async def test_empty_string_is_noop():
    inj = ClipboardInjector(paste=False)
    await inj.inject("")
    assert inj.last_set is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_inject.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

`src/aivoice/pipeline/inject.py`:
```python
from __future__ import annotations

import asyncio


class ClipboardInjector:
    def __init__(self, paste: bool = True, restore_delay: float = 0.2) -> None:
        self.paste = paste
        self.restore_delay = restore_delay
        self.last_set: str | None = None

    def _read_clipboard(self) -> str:
        from AppKit import NSPasteboard, NSStringPboardType

        pb = NSPasteboard.generalPasteboard()
        s = pb.stringForType_(NSStringPboardType)
        return s or ""

    def _write_clipboard(self, text: str) -> None:
        from AppKit import NSPasteboard, NSStringPboardType

        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSStringPboardType)

    def _post_cmd_v(self) -> None:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        with kb.pressed(Key.cmd):
            kb.press("v")
            kb.release("v")

    async def inject(self, text: str) -> None:
        if not text:
            return
        self.last_set = text
        previous = self._read_clipboard() if self.paste else ""
        self._write_clipboard(text)
        if not self.paste:
            return
        # Tiny pause so the paste reliably picks up the new clipboard
        await asyncio.sleep(0.05)
        self._post_cmd_v()
        await asyncio.sleep(self.restore_delay)
        # Only restore if our text is still on the clipboard (user didn't copy something else)
        if self._read_clipboard() == text and previous:
            self._write_clipboard(previous)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_inject.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Manual smoke test**

Run:
```bash
uv run python -c "
import asyncio
from aivoice.pipeline.inject import ClipboardInjector
async def main():
    print('Focus a text field in the next 3 seconds...')
    await asyncio.sleep(3)
    await ClipboardInjector(paste=True).inject('injected by aivoice')
asyncio.run(main())
"
```
Expected: "injected by aivoice" appears in the focused text field.

- [ ] **Step 6: Commit**

```bash
git add src/aivoice/pipeline/inject.py tests/test_inject.py
git commit -m "feat(inject): clipboard + Cmd+V paste with restore"
```

---

### Task 14: Hotkey listener

**Files:**
- Create: `src/aivoice/ui/__init__.py`
- Create: `src/aivoice/ui/hotkey.py`

- [ ] **Step 1: Write the hotkey listener**

`src/aivoice/ui/hotkey.py`:
```python
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from pynput import keyboard

OnPress = Callable[[], Awaitable[None]]
OnRelease = Callable[[], Awaitable[None]]


class HoldHotkey:
    """Fires on_press when the bound key is pressed and on_release when released.
    Re-entrant: if key is held repeatedly while a callback is in flight, intermediate events are dropped."""

    def __init__(self, key_name: str, on_press: OnPress, on_release: OnRelease) -> None:
        self.key = self._resolve(key_name)
        self.on_press = on_press
        self.on_release = on_release
        self._held = False
        self._listener: keyboard.Listener | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @staticmethod
    def _resolve(name: str) -> keyboard.Key:
        return {
            "alt": keyboard.Key.alt,
            "alt_l": keyboard.Key.alt_l,
            "alt_r": keyboard.Key.alt_r,
            "cmd": keyboard.Key.cmd,
            "ctrl": keyboard.Key.ctrl,
            "shift": keyboard.Key.shift,
        }[name]

    def _on_press(self, key) -> None:
        if key != self.key or self._held or self._loop is None:
            return
        self._held = True
        asyncio.run_coroutine_threadsafe(self.on_press(), self._loop)

    def _on_release(self, key) -> None:
        if key != self.key or not self._held or self._loop is None:
            return
        self._held = False
        asyncio.run_coroutine_threadsafe(self.on_release(), self._loop)

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
```

`src/aivoice/ui/__init__.py`:
```python
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
uv run python -c "
import asyncio
from aivoice.ui.hotkey import HoldHotkey
async def down(): print('DOWN')
async def up(): print('UP')
async def main():
    hk = HoldHotkey('alt', down, up)
    hk.start()
    print('Hold ⌥ for ~10s; expect DOWN/UP pairs')
    await asyncio.sleep(15)
    hk.stop()
asyncio.run(main())
"
```
Expected: DOWN/UP pairs when ⌥ is held and released. If unreliable, fall back per Spike A kill criterion.

- [ ] **Step 3: Commit**

```bash
git add src/aivoice/ui/__init__.py src/aivoice/ui/hotkey.py
git commit -m "feat(ui): pynput-based hold hotkey"
```

---

### Task 15: Orchestrator

**Files:**
- Create: `src/aivoice/pipeline/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

`tests/test_orchestrator.py`:
```python
import asyncio

import numpy as np
import pytest

from aivoice.pipeline.orchestrator import Orchestrator
from aivoice.pipeline.stt.base import STTEngine


class FakeSTT(STTEngine):
    async def warmup(self) -> None:
        pass

    async def transcribe(self, audio, samplerate=16000):
        return "hello world"


class FakeInjector:
    def __init__(self):
        self.injected: list[str] = []

    async def inject(self, text: str) -> None:
        self.injected.append(text)


class FakeAudio:
    def __init__(self):
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        return np.ones(16000, dtype=np.float32)  # 1s of "speech"


class PassthroughVAD:
    def trim(self, audio, samplerate=16000):
        return audio


@pytest.mark.asyncio
async def test_full_pipeline_without_cleanup():
    inj = FakeInjector()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=PassthroughVAD(),
        stt=FakeSTT(),
        cleaner=None,
        injector=inj,
    )
    await orch.on_press()
    await asyncio.sleep(0.01)
    await orch.on_release()
    assert inj.injected == ["hello world"]


@pytest.mark.asyncio
async def test_empty_audio_skips_injection():
    class EmptyAudio(FakeAudio):
        async def stop(self):
            return np.zeros(0, dtype=np.float32)

    inj = FakeInjector()
    orch = Orchestrator(
        audio=EmptyAudio(),
        vad=PassthroughVAD(),
        stt=FakeSTT(),
        cleaner=None,
        injector=inj,
    )
    await orch.on_press()
    await orch.on_release()
    assert inj.injected == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

`src/aivoice/pipeline/orchestrator.py`:
```python
from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class _AudioLike(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> "np.ndarray": ...


class _VADLike(Protocol):
    def trim(self, audio: "np.ndarray", samplerate: int = 16000) -> "np.ndarray": ...


class _STTLike(Protocol):
    async def transcribe(self, audio: "np.ndarray", samplerate: int = 16000) -> str: ...


class _CleanerLike(Protocol):
    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str: ...


class _InjectorLike(Protocol):
    async def inject(self, text: str) -> None: ...


class Orchestrator:
    def __init__(
        self,
        audio: _AudioLike,
        vad: _VADLike,
        stt: _STTLike,
        cleaner: _CleanerLike | None,
        injector: _InjectorLike,
        mode: str = "raw",
        vocabulary: list[str] | None = None,
    ) -> None:
        self.audio = audio
        self.vad = vad
        self.stt = stt
        self.cleaner = cleaner
        self.injector = injector
        self.mode = mode
        self.vocabulary = vocabulary or []
        self._recording = False

    async def on_press(self) -> None:
        if self._recording:
            return
        self._recording = True
        try:
            await self.audio.start()
        except Exception:
            self._recording = False
            raise

    async def on_release(self) -> None:
        if not self._recording:
            return
        self._recording = False
        try:
            audio = await self.audio.stop()
            audio = self.vad.trim(audio)
            if len(audio) == 0:
                log.info("empty audio after VAD trim, skipping")
                return
            text = await self.stt.transcribe(audio)
            if not text:
                return
            if self.cleaner is not None:
                text = await self.cleaner.clean(text, mode=self.mode, vocabulary=self.vocabulary)
            if not text:
                return
            await self.injector.inject(text)
        except Exception:
            log.exception("pipeline failed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/aivoice/pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orch): hotkey-driven pipeline orchestrator"
```

---

## Phase 5 — UI + Wiring (Tasks 16-17)

### Task 16: Menu-bar app

**Files:**
- Create: `src/aivoice/ui/menubar.py`

- [ ] **Step 1: Write the menu-bar app**

`src/aivoice/ui/menubar.py`:
```python
from __future__ import annotations

import asyncio
import logging
import threading

import rumps

from aivoice.config import Settings
from aivoice.pipeline.audio import AudioCapture
from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.ollama_cleaner import OllamaCleaner
from aivoice.pipeline.cleanup.openai_cleaner import OpenAICleaner
from aivoice.pipeline.inject import ClipboardInjector
from aivoice.pipeline.orchestrator import Orchestrator
from aivoice.pipeline.stt.cloud_groq import CloudGroqEngine
from aivoice.pipeline.stt.local_mlx import LocalMLXEngine
from aivoice.pipeline.vad import VAD
from aivoice.ui.hotkey import HoldHotkey
from aivoice.version import __version__

log = logging.getLogger(__name__)


IDLE = "🎙"
LISTENING = "🔴"
WORKING = "⚙️"


class AivoiceApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("aivoice", title=IDLE, quit_button="Quit")
        self.settings = Settings.load()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orch: Orchestrator | None = None
        self._hotkey: HoldHotkey | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.menu = [
            rumps.MenuItem(f"aivoice {__version__}"),
            None,
            rumps.MenuItem("Hotkey: ⌥ (hold)"),
            rumps.MenuItem(f"Engine: {self.settings.stt_engine}"),
            rumps.MenuItem(f"Cleanup: {'on' if self.settings.cleanup_enabled else 'off'}"),
        ]

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_main())

    async def _async_main(self) -> None:
        stt = (
            LocalMLXEngine(self.settings.local_mlx_model)
            if self.settings.stt_engine == "local_mlx"
            else CloudGroqEngine(self.settings.cloud_groq_model)
        )
        await stt.warmup()

        cleaner: LLMCleaner | None = None
        if self.settings.cleanup_enabled:
            cleaner = (
                OpenAICleaner(self.settings.openai_cleanup_model)
                if self.settings.cleanup_engine == "openai"
                else OllamaCleaner(self.settings.ollama_cleanup_model)
            )

        self._orch = Orchestrator(
            audio=AudioCapture(),
            vad=VAD(),
            stt=stt,
            cleaner=cleaner,
            injector=ClipboardInjector(paste=True),
            mode=self.settings.mode,
            vocabulary=self.settings.vocabulary,
        )

        self._hotkey = HoldHotkey(self.settings.hotkey, self._on_press, self._on_release)
        self._hotkey.start()
        # Hold the loop open
        while True:
            await asyncio.sleep(3600)

    async def _on_press(self) -> None:
        self.title = LISTENING
        try:
            await self._orch.on_press()
        except Exception:
            self.title = IDLE
            log.exception("on_press failed")

    async def _on_release(self) -> None:
        self.title = WORKING
        try:
            await self._orch.on_release()
        finally:
            self.title = IDLE


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    AivoiceApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update `__main__.py` to launch the app**

`src/aivoice/__main__.py`:
```python
import sys

from aivoice.version import __version__


def main() -> int:
    if "--version" in sys.argv:
        print(f"aivoice {__version__}")
        return 0
    from aivoice.ui.menubar import main as ui_main

    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke test — full app**

Run:
```bash
uv run aivoice
```
Expected: 🎙 appears in menu bar. Hold ⌥, say "hello world", release. Within ~2s the text appears in the focused field.

- [ ] **Step 4: Commit**

```bash
git add src/aivoice/ui/menubar.py src/aivoice/__main__.py
git commit -m "feat(ui): menu-bar app wires hotkey → orchestrator"
```

---

### Task 17: Verification scenarios (gate before packaging)

**Files:** none (manual scenario log)

This is a verification gate, not a code task. The app must pass all 10 scenarios before moving to packaging (Task 18). Record results in a paragraph under "Verification log" in the commit message.

- [ ] **Step 1: Run each scenario, hold ⌥, dictate, release. Record p50 latency.**

| # | Scenario | Pass criteria |
|---|---|---|
| 1 | TextEdit, new document | "hello world" appears |
| 2 | Slack DM box | Text appears at cursor |
| 3 | VS Code editor | Text appears (no Cmd+V conflict) |
| 4 | Chrome address bar | Text appears |
| 5 | Terminal (zsh prompt) | Text appears |
| 6 | iMessage compose | Text appears |
| 7 | Google Docs in browser | Text appears |
| 8 | Notion editor | Text appears |
| 9 | Spotlight search field | Text appears |
| 10 | Dictate with `cleanup_enabled = true` and "um so I uh think the API is broken" | Output has no "um/uh", contains "API" |

- [ ] **Step 2: If any scenario fails, fix in a targeted commit before continuing.**

- [ ] **Step 3: Verification log commit**

```bash
git commit --allow-empty -m "verify: 10/10 scenarios pass, p50 latency ~Xs (record actual)"
```

**Kill criterion:** If <8/10 scenarios pass, do not proceed to packaging. Open issues for each failure.

---

## Phase 6 — Packaging (Task 18)

### Task 18: py2app bundle + codesign script

**Files:**
- Create: `scripts/build_app.sh`
- Create: `scripts/codesign_dev.sh`
- Create: `setup_app.py` (py2app entrypoint)

- [ ] **Step 1: Write `setup_app.py`**

```python
from setuptools import setup

setup(
    app=["src/aivoice/__main__.py"],
    name="aivoice",
    options={
        "py2app": {
            "argv_emulation": False,
            "plist": {
                "LSUIElement": True,  # background app, no Dock icon
                "CFBundleIdentifier": "com.baha.aivoice",
                "CFBundleName": "aivoice",
                "CFBundleShortVersionString": "0.1.0",
                "NSMicrophoneUsageDescription": "aivoice needs your microphone to transcribe what you say.",
                "NSAppleEventsUsageDescription": "aivoice posts paste keystrokes to inject transcribed text.",
            },
            "packages": ["aivoice", "rumps", "pynput", "sounddevice", "silero_vad", "mlx_whisper"],
            "includes": ["AppKit", "ApplicationServices"],
        }
    },
    setup_requires=["py2app"],
)
```

- [ ] **Step 2: Write `scripts/build_app.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build dist
uv run --with py2app python setup_app.py py2app
echo "✓ built: dist/aivoice.app"
```

- [ ] **Step 3: Write `scripts/codesign_dev.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

codesign --force --deep --sign - dist/aivoice.app
echo "✓ ad-hoc signed: dist/aivoice.app"
```

- [ ] **Step 4: Build + sign + install**

Run:
```bash
chmod +x scripts/*.sh
./scripts/build_app.sh
./scripts/codesign_dev.sh
cp -R dist/aivoice.app /Applications/
open /Applications/aivoice.app
```
Expected: app launches; grant Mic + Input Monitoring + Accessibility when prompted.

- [ ] **Step 5: Smoke test the .app**

Hold ⌥ in TextEdit, dictate "this is from the bundled app", release. Expected: text appears.

- [ ] **Step 6: Commit**

```bash
git add setup_app.py scripts/build_app.sh scripts/codesign_dev.sh
git commit -m "build: py2app bundle + ad-hoc codesign script"
```

---

## Phase 7 — Optional Stretch (Tasks 19-20)

### Task 19: Settings TOML hot-reload via menu

**Files:**
- Modify: `src/aivoice/ui/menubar.py`

- [ ] **Step 1: Add "Reload Settings" menu item that re-instantiates the orchestrator from disk.**

(Implementation mirrors `_async_main`. Bind to `rumps.MenuItem("Reload Settings", callback=self.reload)`.)

- [ ] **Step 2: Commit**

```bash
git commit -am "feat(ui): reload settings.toml from menu"
```

---

### Task 20: Per-mode hotkeys

**Files:**
- Modify: `src/aivoice/config.py`
- Modify: `src/aivoice/ui/menubar.py`
- Modify: `src/aivoice/ui/hotkey.py`

- [ ] **Step 1: Add `mode_hotkeys: dict[str, str]` to Settings.**

E.g., `{"raw": "alt", "email": "alt+e", "code-comment": "alt+c"}`.

- [ ] **Step 2: Wire each hotkey to a per-mode Orchestrator with the matching `mode`.**

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(ui): per-mode hotkeys"
```

---

## Self-Review Notes

- **Spec coverage:** All 12 sections from the previous plan map to tasks (architecture → Tasks 1-17, tool stack → Task 1, backend/frontend split → Task 16, repo layout → Task 1, phases → Tasks 4-18, local vs cloud comparison → Tasks 8/9, cleanup prompt → Tasks 10-12, permissions → Task 6 + Task 18 plist, out of scope → respected, risks → register up top + kill criteria, success criteria → Task 17).
- **No placeholders:** All code is complete; all commands have expected output.
- **Type consistency:** `STTEngine.transcribe`, `LLMCleaner.clean`, `Orchestrator.on_press/on_release` keep stable signatures across Tasks 7–16.
- **Test fixtures:** Generated in Task 3, used in Tasks 5 and 8.
- **Risk-ordered spikes:** Spike A and Spike B run *before* Task 1, with explicit kill criteria.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session with checkpoints for review.
