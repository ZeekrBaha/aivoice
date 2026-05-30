import numpy as np

from aivoice.pipeline.levels import normalized, rms


def test_rms_empty_is_zero():
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_rms_constant_amplitude():
    assert abs(rms(np.array([1, 1, 1, 1], dtype=np.float32)) - 1.0) < 1e-6
    assert abs(rms(np.array([0.5, -0.5], dtype=np.float32)) - 0.5) < 1e-6


def test_normalized_silence_and_subfloor_map_to_zero():
    assert normalized(0.0) == 0.0
    subfloor = 10 ** (-60 / 20)  # -60 dB, below the -50 floor
    assert normalized(subfloor) == 0.0


def test_normalized_ceiling_clamps_to_one():
    assert abs(normalized(1.0) - 1.0) < 1e-6
    assert normalized(2.0) == 1.0


def test_normalized_midpoint():
    mid = 10 ** (-25 / 20)  # -25 dB = midpoint of -50..0
    assert abs(normalized(mid) - 0.5) < 0.02
