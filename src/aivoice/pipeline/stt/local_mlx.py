from __future__ import annotations

import asyncio

import numpy as np

from aivoice.pipeline.stt.base import STTEngine


class LocalMLXEngine(STTEngine):
    def __init__(self, model: str = "mlx-community/distil-whisper-large-v3", language: str = "en") -> None:
        self.model = model
        self.language = language
        self._warmed = False

    async def warmup(self) -> None:
        if self._warmed:
            return
        import mlx_whisper  # noqa: F401

        # silent pass to download + JIT-compile the model
        await asyncio.to_thread(
            mlx_whisper.transcribe,
            np.zeros(8000, dtype=np.float32),
            path_or_hf_repo=self.model,
            language=self.language,
        )
        self._warmed = True

    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        import mlx_whisper

        result = await asyncio.to_thread(
            mlx_whisper.transcribe,
            audio,
            path_or_hf_repo=self.model,
            language=self.language,
        )
        return result["text"].strip()
