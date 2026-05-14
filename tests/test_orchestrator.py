import asyncio

import numpy as np
import pytest

from aivoice.pipeline.orchestrator import Orchestrator
from aivoice.pipeline.stt.base import STTEngine


class FakeSTT(STTEngine):
    def __init__(self):
        self.last_initial_prompt: str | None = None

    async def warmup(self) -> None:
        pass

    async def transcribe(self, audio, samplerate=16000, initial_prompt=None):
        self.last_initial_prompt = initial_prompt
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


@pytest.mark.asyncio
async def test_vocabulary_becomes_initial_prompt():
    stt = FakeSTT()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=PassthroughVAD(),
        stt=stt,
        cleaner=None,
        injector=FakeInjector(),
        vocabulary=["README", "ZeekrBaha"],
    )
    await orch.on_press()
    await orch.on_release()
    assert stt.last_initial_prompt is not None
    assert "README" in stt.last_initial_prompt
    assert "ZeekrBaha" in stt.last_initial_prompt


@pytest.mark.asyncio
async def test_empty_vocabulary_means_no_initial_prompt():
    stt = FakeSTT()
    orch = Orchestrator(
        audio=FakeAudio(),
        vad=PassthroughVAD(),
        stt=stt,
        cleaner=None,
        injector=FakeInjector(),
    )
    await orch.on_press()
    await orch.on_release()
    assert stt.last_initial_prompt is None


@pytest.mark.asyncio
async def test_trailing_silence_padded_before_stt():
    class CapturingSTT(STTEngine):
        def __init__(self):
            self.received_len = 0

        async def warmup(self):
            pass

        async def transcribe(self, audio, samplerate=16000, initial_prompt=None):
            self.received_len = len(audio)
            return "x"

    stt = CapturingSTT()
    orch = Orchestrator(
        audio=FakeAudio(),  # produces 16000 samples (1s) at 16kHz
        vad=PassthroughVAD(),
        stt=stt,
        cleaner=None,
        injector=FakeInjector(),
    )
    await orch.on_press()
    await orch.on_release()
    # FakeAudio gives 16000 samples; pad adds 16000 more (1s at 16kHz).
    assert stt.received_len == 32000
