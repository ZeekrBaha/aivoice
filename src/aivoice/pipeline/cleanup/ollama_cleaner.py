from __future__ import annotations

from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.prompts import build_prompt


class OllamaCleaner(LLMCleaner):
    def __init__(
        self,
        model: str = "qwen2.5:7b-instruct",
        host: str = "http://127.0.0.1:11434",
    ) -> None:
        self.model = model
        self.host = host

    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        if not text.strip():
            return ""
        import ollama

        client = ollama.AsyncClient(host=self.host)
        resp = await client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": build_prompt(mode=mode, vocabulary=vocabulary)},
                {"role": "user", "content": text},
            ],
            options={
                "temperature": 0.0,
                "top_p": 0.1,
                "repeat_penalty": 1.0,
                "num_predict": 512,
                "stop": ["\n\nInput:", "\n\nOutput:"],
            },
        )
        # Strip any quote wrapping qwen sometimes adds
        return resp["message"]["content"].strip().strip('"').strip("'")
