from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OverlayPhase(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


@dataclass(frozen=True)
class OverlayPresentation:
    """Pure description of what the overlay should show for a given phase.

    Kept free of AppKit so the phase→UI mapping is unit-testable in CI.
    """

    visible: bool
    label: str
    dot_pulsing: bool
    spinner: bool

    @classmethod
    def for_phase(
        cls, phase: OverlayPhase, reduce_motion: bool = False
    ) -> "OverlayPresentation":
        if phase is OverlayPhase.RECORDING:
            return cls(
                visible=True,
                label="Recording…",
                dot_pulsing=not reduce_motion,
                spinner=False,
            )
        if phase is OverlayPhase.PROCESSING:
            return cls(
                visible=True,
                label="Transcribing…",
                dot_pulsing=False,
                spinner=True,
            )
        return cls(visible=False, label="", dot_pulsing=False, spinner=False)
