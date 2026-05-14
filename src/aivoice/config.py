from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Settings(BaseModel):
    stt_engine: Literal["local_mlx", "cloud_groq"] = "local_mlx"
    local_mlx_model: str = "mlx-community/whisper-large-v3-turbo"
    cloud_groq_model: str = "whisper-large-v3-turbo"

    cleanup_enabled: bool = True
    cleanup_engine: Literal["openai", "ollama"] = "ollama"
    openai_cleanup_model: str = "gpt-4o-mini"
    ollama_cleanup_model: str = "qwen2.5:7b-instruct"

    hotkey: str = "alt"
    mode: Literal["raw", "email", "code-comment", "slack"] = "raw"
    vocabulary: list[str] = Field(default_factory=list)

    @classmethod
    def config_dir(cls) -> Path:
        return Path(os.environ.get("AIVOICE_CONFIG_DIR", Path.home() / ".config" / "aivoice"))

    @classmethod
    def load(cls) -> "Settings":
        path = cls.config_dir() / "settings.toml"
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls(**data)
