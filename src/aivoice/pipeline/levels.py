from __future__ import annotations

import math

import numpy as np


def rms(block: np.ndarray) -> float:
    """Root-mean-square amplitude of a mono float block (samples in -1..1).

    Returns 0.0 for an empty block.
    """
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))


def normalized(rms_value: float, floor_db: float = -50.0) -> float:
    """Map an RMS amplitude (0..1 linear) to a 0..1 meter value on a dB scale.

    At or below `floor_db` reads 0.0; at 0 dB (rms 1.0) reads 1.0. Clamped 0..1.
    """
    if rms_value <= 0.0:
        return 0.0
    db = 20.0 * math.log10(rms_value)
    if db <= floor_db:
        return 0.0
    if db >= 0.0:
        return 1.0
    return (db - floor_db) / -floor_db
