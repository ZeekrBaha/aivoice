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
