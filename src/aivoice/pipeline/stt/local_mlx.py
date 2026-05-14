from __future__ import annotations

import asyncio

import numpy as np

from aivoice.pipeline.stt.base import STTEngine


class LocalMLXEngine(STTEngine):
    def __init__(self, model: str = "mlx-community/whisper-large-v3-turbo", language: str = "en") -> None:
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

    async def transcribe(
        self,
        audio: np.ndarray,
        samplerate: int = 16000,
        initial_prompt: str | None = None,
    ) -> str:
        if len(audio) == 0:
            return ""
        import mlx_whisper

        kwargs = {
            "path_or_hf_repo": self.model,
            "language": self.language,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        result = await asyncio.to_thread(mlx_whisper.transcribe, audio, **kwargs)
        return result["text"].strip()
