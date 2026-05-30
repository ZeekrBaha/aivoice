from __future__ import annotations

import logging
from typing import Callable

import numpy as np
import sounddevice as sd

from aivoice.pipeline.levels import normalized, rms

log = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, samplerate: int = 16000, blocksize: int = 512) -> None:
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        # Optional per-block mic level (0..1). Called on the PortAudio audio
        # thread; consumers must marshal to their own thread before touching UI.
        self.on_level: Callable[[float], None] | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        # copy to avoid buffer reuse by PortAudio
        block = indata[:, 0].astype(np.float32, copy=True)
        self._frames.append(block)
        if self.on_level is not None:
            try:
                self.on_level(normalized(rms(block)))
            except Exception:  # never let a UI callback kill the audio stream
                log.debug("on_level callback failed", exc_info=True)

    async def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("AudioCapture already started")
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    async def stop(self) -> np.ndarray:
        if self._stream is None:
            raise RuntimeError("AudioCapture not started")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames)
