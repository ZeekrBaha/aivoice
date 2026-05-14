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
