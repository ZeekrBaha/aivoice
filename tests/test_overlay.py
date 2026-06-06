from aivoice.ui.overlay import (
    OverlayController,
    OverlayIndicator,
    OverlayPhase,
    OverlayPresentation,
)


def test_idle_is_hidden():
    p = OverlayPresentation.for_phase(OverlayPhase.IDLE)
    assert p.visible is False
    assert p.label == ""
    assert p.indicator is OverlayIndicator.NONE


def test_recording_shows_waveform():
    p = OverlayPresentation.for_phase(OverlayPhase.RECORDING)
    assert p.visible is True
    assert p.label == "Recording…"
    assert p.indicator is OverlayIndicator.WAVEFORM


def test_recording_reduce_motion_shows_static_dot():
    p = OverlayPresentation.for_phase(OverlayPhase.RECORDING, reduce_motion=True)
    assert p.visible is True
    assert p.indicator is OverlayIndicator.DOT


def test_processing_shows_spinner():
    p = OverlayPresentation.for_phase(OverlayPhase.PROCESSING)
    assert p.visible is True
    assert p.label == "Transcribing…"
    assert p.indicator is OverlayIndicator.SPINNER


def test_stale_hide_does_not_finish_after_processing_starts():
    c = OverlayController()
    c._phase = OverlayPhase.IDLE
    c._transition_id = 1
    assert c._should_finish_hide(1) is True

    c._phase = OverlayPhase.PROCESSING
    c._transition_id = 2
    assert c._should_finish_hide(1) is False
    assert c._should_finish_hide(2) is False
