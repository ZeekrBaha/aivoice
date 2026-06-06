from __future__ import annotations

import asyncio
import logging
from typing import Callable

import numpy as np
import sounddevice as sd

from aivoice.pipeline.levels import normalized, rms

log = logging.getLogger(__name__)


class AudioCapture:
    def __init__(
        self,
        samplerate: int = 16000,
        blocksize: int = 512,
        stop_timeout: float = 3.0,
        abort_timeout: float = 1.0,
    ) -> None:
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.stop_timeout = stop_timeout
        self.abort_timeout = abort_timeout
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

        stream = self._stream
        frames = self._frames
        self._stream = None
        self._frames = []

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_stop_and_close_stream, stream),
                timeout=self.stop_timeout,
            )
        except TimeoutError:
            log.warning(
                "audio stream stop timed out after %.1fs; aborting stream",
                self.stop_timeout,
            )
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_abort_stream, stream),
                    timeout=self.abort_timeout,
                )
            except TimeoutError:
                log.error(
                    "audio stream abort also timed out after %.1fs; continuing with captured audio",
                    self.abort_timeout,
                )
            except Exception:
                log.exception("audio stream abort failed; continuing with captured audio")
        except Exception:
            log.exception("audio stream stop failed")

        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames)


def _stop_and_close_stream(stream: sd.InputStream) -> None:
    try:
        stream.stop()
    finally:
        stream.close()


def _abort_stream(stream: sd.InputStream) -> None:
    try:
        stream.abort()
    finally:
        stream.close()
