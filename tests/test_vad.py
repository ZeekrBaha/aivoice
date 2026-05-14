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
    # original is ~0.5s pad + word + 0.5s pad; trimmed must be shorter
    assert 0 < len(trimmed) < len(audio)
    # and at least 100ms long (the word itself)
    assert len(trimmed) > 1600


def test_returns_empty_on_pure_silence():
    vad = VAD()
    audio = _load("silence_5s.wav")
    trimmed = vad.trim(audio)
    assert len(trimmed) == 0


def test_passes_speech_through_within_tolerance():
    vad = VAD()
    audio = _load("hello_world.wav")
    trimmed = vad.trim(audio)
    # hello_world has minimal padding; trimmed should be within 20% of original
    assert abs(len(trimmed) - len(audio)) < 0.2 * len(audio)
