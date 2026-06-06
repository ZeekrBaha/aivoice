import asyncio
import time

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


@pytest.mark.asyncio
async def test_stop_timeout_aborts_stream_and_returns_audio():
    class SlowStoppingStream:
        def __init__(self):
            self.aborted = False
            self.closed = False

        def stop(self):
            time.sleep(0.05)

        def abort(self):
            self.aborted = True

        def close(self):
            self.closed = True

    stream = SlowStoppingStream()
    cap = AudioCapture(stop_timeout=0.001, abort_timeout=0.1)
    cap._stream = stream
    cap._frames = [np.ones(16, dtype=np.float32)]

    audio = await cap.stop()

    assert stream.aborted is True
    assert cap._stream is None
    assert audio.dtype == np.float32
    assert len(audio) == 16


@pytest.mark.asyncio
async def test_stop_failure_clears_stream_state():
    class FailingStream:
        def stop(self):
            raise RuntimeError("coreaudio stop failed")

        def close(self):
            pass

    cap = AudioCapture()
    cap._stream = FailingStream()
    cap._frames = [np.ones(8, dtype=np.float32)]

    audio = await cap.stop()

    assert cap._stream is None
    assert len(audio) == 8
