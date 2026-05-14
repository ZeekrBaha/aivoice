from __future__ import annotations

import numpy as np
from silero_vad import get_speech_timestamps, load_silero_vad


class VAD:
    def __init__(self, threshold: float = 0.5, min_speech_ms: int = 150) -> None:
        self._model = load_silero_vad(onnx=True)
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms

    def trim(self, audio: np.ndarray, samplerate: int = 16000) -> np.ndarray:
        if len(audio) == 0:
            return audio
        ts = get_speech_timestamps(
            audio,
            self._model,
            threshold=self.threshold,
            sampling_rate=samplerate,
            min_speech_duration_ms=self.min_speech_ms,
            return_seconds=False,
        )
        if not ts:
            return np.zeros(0, dtype=np.float32)
        start = ts[0]["start"]
        end = ts[-1]["end"]
        return audio[start:end]
