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
