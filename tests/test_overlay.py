from aivoice.ui.overlay import OverlayPhase, OverlayPresentation


def test_idle_is_hidden():
    p = OverlayPresentation.for_phase(OverlayPhase.IDLE)
    assert p.visible is False
    assert p.label == ""
    assert p.dot_pulsing is False
    assert p.spinner is False


def test_recording_shows_pulsing_dot():
    p = OverlayPresentation.for_phase(OverlayPhase.RECORDING)
    assert p.visible is True
    assert p.label == "Recording…"
    assert p.dot_pulsing is True
    assert p.spinner is False


def test_processing_shows_spinner():
    p = OverlayPresentation.for_phase(OverlayPhase.PROCESSING)
    assert p.visible is True
    assert p.label == "Transcribing…"
    assert p.dot_pulsing is False
    assert p.spinner is True


def test_recording_with_reduce_motion_has_static_dot():
    p = OverlayPresentation.for_phase(OverlayPhase.RECORDING, reduce_motion=True)
    assert p.visible is True
    assert p.dot_pulsing is False
    assert p.spinner is False
