from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        samplerate: int = 16000,
        initial_prompt: str | None = None,
    ) -> str:
        """Transcribe float32 mono audio to text. Returns empty string on empty input.

        `initial_prompt` biases decoding toward a vocabulary/style. For Whisper it
        is fed to the decoder as if it were the previous segment's transcript
        (224-token limit). Pass `None` to disable.
        """

    @abstractmethod
    async def warmup(self) -> None:
        """Load model into memory. Called once at app launch."""
