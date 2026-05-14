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
        return np.ones(16000, dtype=np.float32)


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
async def test_empty_audio_after_vad_skips_injection():
    class SilenceVAD:
        def trim(self, audio, samplerate=16000):
            return np.zeros(0, dtype=np.float32)

    inj = FakeInjector()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=SilenceVAD(),
        stt=FakeSTT(),
        cleaner=None,
        injector=inj,
    )
    await orch.on_press()
    await orch.on_release()
    assert inj.injected == []


@pytest.mark.asyncio
async def test_cleaner_result_is_injected():
    class UpperCleaner:
        async def clean(self, text, mode="raw", vocabulary=None):
            return text.upper()

    inj = FakeInjector()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=PassthroughVAD(),
        stt=FakeSTT(),
        cleaner=UpperCleaner(),
        injector=inj,
    )
    await orch.on_press()
    await orch.on_release()
    assert inj.injected == ["HELLO WORLD"]


@pytest.mark.asyncio
async def test_double_press_is_idempotent():
    inj = FakeInjector()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=PassthroughVAD(),
        stt=FakeSTT(),
        cleaner=None,
        injector=inj,
    )
    await orch.on_press()
    await orch.on_press()  # second press while held — should be ignored
    await orch.on_release()
    assert len(inj.injected) == 1
