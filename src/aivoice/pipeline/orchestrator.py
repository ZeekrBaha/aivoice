from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class _AudioLike(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> np.ndarray: ...


class _VADLike(Protocol):
    def trim(self, audio: np.ndarray, samplerate: int = 16000) -> np.ndarray: ...


class _STTLike(Protocol):
    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str: ...


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
