"""Tests for the AudioCapture.on_level callback wiring.

These drive the PortAudio callback directly with synthetic blocks so they need
no microphone and run in CI.
"""
from __future__ import annotations

import numpy as np

from aivoice.pipeline.audio import AudioCapture


def test_on_level_invoked_with_value_in_unit_range():
    cap = AudioCapture()
    seen: list[float] = []
    cap.on_level = seen.append

    # A loud-ish block (half amplitude) and a silent block.
    cap._callback(np.full((512, 1), 0.5, dtype=np.float32), 512, None, None)
    cap._callback(np.zeros((512, 1), dtype=np.float32), 512, None, None)

    assert len(seen) == 2
    assert all(0.0 <= v <= 1.0 for v in seen)
    assert seen[0] > seen[1]  # louder block reads higher than silence


def test_on_level_absent_is_noop():
    cap = AudioCapture()  # on_level is None by default
    # Should not raise, and should still record the frame.
    cap._callback(np.full((512, 1), 0.2, dtype=np.float32), 512, None, None)
    assert len(cap._frames) == 1


def test_on_level_exception_does_not_propagate():
    cap = AudioCapture()

    def boom(_level: float) -> None:
        raise ValueError("callback blew up")

    cap.on_level = boom
    # The audio stream must survive a misbehaving UI callback.
    cap._callback(np.full((512, 1), 0.3, dtype=np.float32), 512, None, None)
    assert len(cap._frames) == 1
