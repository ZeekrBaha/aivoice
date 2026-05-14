from __future__ import annotations

from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.prompts import build_prompt
from aivoice.utils.keychain import get_secret


class OpenAICleaner(LLMCleaner):
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        from openai import AsyncOpenAI

        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=api_key)

    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        if not text.strip():
            return ""
        self._ensure_client()
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=512,
            messages=[
                {"role": "system", "content": build_prompt(mode=mode, vocabulary=vocabulary)},
                {"role": "user", "content": text},
            ],
        )
        return resp.choices[0].message.content.strip()
