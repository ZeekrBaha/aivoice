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
    async def transcribe(
        self,
        audio: np.ndarray,
        samplerate: int = 16000,
        initial_prompt: str | None = None,
    ) -> str: ...


class _CleanerLike(Protocol):
    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str: ...


class _InjectorLike(Protocol):
    async def inject(self, text: str) -> None: ...


class Orchestrator:
    # Trailing-silence pad (SuperWhisper's documented fix for end-of-utterance
    # word drops — Whisper's encoder needs a beat of silence after the last
    # phoneme to commit the final token).
    TAIL_PAD_SECONDS = 1.0

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
        self._initial_prompt = _build_initial_prompt(self.vocabulary)
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
            audio = _pad_trailing_silence(audio, self.TAIL_PAD_SECONDS)
            text = await self.stt.transcribe(audio, initial_prompt=self._initial_prompt)
            if not text:
                return
            if self.cleaner is not None:
                text = await self.cleaner.clean(text, mode=self.mode, vocabulary=self.vocabulary)
            if not text:
                return
            await self.injector.inject(text)
        except Exception:
            log.exception("pipeline failed")


def _build_initial_prompt(vocabulary: list[str]) -> str | None:
    """Build a Whisper initial_prompt biasing decoding toward the user's vocabulary.

    Whisper's prompt is fed to the decoder as if it were the previous segment's
    transcript and is capped at 224 tokens (only the last 224 survive). The
    OpenAI cookbook recommends a comma list with a short category prefix; keep
    the most-important terms last because earlier terms get truncated first.
    """
    terms = [t.strip() for t in vocabulary if t and t.strip()]
    if not terms:
        return None
    # ~4 chars/token, target ~200 tokens = ~800 chars for the term list.
    joined = ", ".join(terms)
    if len(joined) > 800:
        joined = joined[-800:]
    return f"Glossary: {joined}."


def _pad_trailing_silence(audio: np.ndarray, seconds: float, samplerate: int = 16000) -> np.ndarray:
    """Append `seconds` of zero-valued samples so Whisper sees a beat of silence
    after the final phoneme. Push-to-talk users often release the key mid-word;
    without the pad the encoder commits to a shorter token sequence and drops
    the last word. SuperWhisper landed the same fix in their changelog."""
    n = int(seconds * samplerate)
    if n <= 0:
        return audio
    return np.concatenate([audio, np.zeros(n, dtype=audio.dtype)])
