from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OverlayPhase(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class OverlayIndicator(str, Enum):
    NONE = "none"
    WAVEFORM = "waveform"
    DOT = "dot"
    SPINNER = "spinner"


@dataclass(frozen=True)
class OverlayPresentation:
    """Pure description of what the overlay should show for a given phase.

    Kept free of AppKit so the phase->UI mapping is unit-testable in CI.
    """

    visible: bool
    label: str
    indicator: OverlayIndicator

    @classmethod
    def for_phase(
        cls, phase: OverlayPhase, reduce_motion: bool = False
    ) -> "OverlayPresentation":
        if phase is OverlayPhase.RECORDING:
            indicator = OverlayIndicator.DOT if reduce_motion else OverlayIndicator.WAVEFORM
            return cls(visible=True, label="Recording…", indicator=indicator)
        if phase is OverlayPhase.PROCESSING:
            return cls(visible=True, label="Transcribing…", indicator=OverlayIndicator.SPINNER)
        return cls(visible=False, label="", indicator=OverlayIndicator.NONE)
