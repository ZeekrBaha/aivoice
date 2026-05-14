from __future__ import annotations

import io

import numpy as np
import soundfile as sf

from aivoice.pipeline.stt.base import STTEngine
from aivoice.utils.keychain import get_secret


class CloudGroqEngine(STTEngine):
    def __init__(self, model: str = "whisper-large-v3-turbo", language: str = "en") -> None:
        self.model = model
        self.language = language
        self._client = None

    async def warmup(self) -> None:
        from groq import AsyncGroq

        api_key = get_secret("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set (env or keychain)")
        self._client = AsyncGroq(api_key=api_key)

    async def transcribe(self, audio: np.ndarray, samplerate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        if self._client is None:
            await self.warmup()

        buf = io.BytesIO()
        sf.write(buf, audio, samplerate, format="WAV", subtype="PCM_16")
        buf.seek(0)
        buf.name = "audio.wav"  # groq client inspects .name for content-type

        resp = await self._client.audio.transcriptions.create(
            file=buf,
            model=self.model,
            language=self.language,
            response_format="text",
        )
        return resp.strip() if isinstance(resp, str) else resp.text.strip()
