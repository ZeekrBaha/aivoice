from __future__ import annotations

from abc import ABC, abstractmethod


class LLMCleaner(ABC):
    @abstractmethod
    async def clean(self, text: str, mode: str = "raw", vocabulary: list[str] | None = None) -> str:
        """Return cleaned text. Return '' if input is empty or pure filler."""
