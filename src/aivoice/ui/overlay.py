from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


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


class WaveformBuffer:
    """Pure rolling buffer of recent mic levels (0..1), newest last.

    Holds the waveform's data model so the bar-height math is unit-testable
    without AppKit. The view layer reads `bar_heights` to size its bars.
    """

    def __init__(self, capacity: int = 28) -> None:
        self.capacity = capacity
        self._levels: list[float] = []

    def push(self, level: float) -> None:
        v = 0.0 if level < 0 else 1.0 if level > 1 else float(level)
        self._levels.append(v)
        overflow = len(self._levels) - self.capacity
        if overflow > 0:
            del self._levels[:overflow]

    def clear(self) -> None:
        self._levels.clear()

    @property
    def levels(self) -> list[float]:
        return list(self._levels)

    def bar_heights(self, min_h: float, max_h: float) -> list[float]:
        """Return exactly `capacity` bar heights, newest on the right.

        Slots with no data yet (buffer not full) are left-padded with `min_h`,
        so the waveform fills in from the right as audio arrives.
        """
        out = [min_h] * self.capacity
        n = len(self._levels)
        span = max_h - min_h
        for i in range(n):
            out[self.capacity - n + i] = min_h + self._levels[i] * span
        return out


# --------------------------------------------------------------------------- #
# AppKit controller                                                            #
# --------------------------------------------------------------------------- #
#
# Everything below touches AppKit and must run on the main thread. The dictation
# pipeline calls these methods from a background asyncio thread and the audio tap
# from PortAudio's thread, so every public method marshals onto the main thread
# via PyObjCTools.AppHelper.callAfter. AppKit is imported lazily *inside* methods
# so importing this module (and running the pure tests above) never needs a GUI.

# Panel + waveform geometry.
_PANEL_W = 220.0
_PANEL_H = 60.0
_MARGIN_BOTTOM = 130.0
_CORNER = 16.0
_BAR_COUNT = 28
_BAR_W = 3.0
_BAR_GAP = 2.0
_BAR_MIN_H = 3.0
_BAR_MAX_H = 30.0
_DOT_SIZE = 12.0


class OverlayController:
    """Owns a single reusable glass NSPanel showing recording/processing state.

    Public API (`show_recording`, `show_processing`, `hide`, `push_level`) is safe
    to call from any thread; each hops to the main thread before touching AppKit.
    """

    def __init__(self) -> None:
        self._panel = None
        self._content = None          # NSVisualEffectView
        self._wave_view = None        # container NSView for bar layers
        self._bars: list = []         # CALayer per bar
        self._dot = None              # NSView (static dot, reduce-motion)
        self._spinner = None          # NSProgressIndicator
        self._label = None            # NSTextField
        self._buffer = WaveformBuffer(capacity=_BAR_COUNT)
        self._recording = False

    # -- public API (any thread) ---------------------------------------- #

    def show_recording(self) -> None:
        self._buffer.clear()
        self._call_main(self._apply, OverlayPhase.RECORDING)

    def show_processing(self) -> None:
        self._call_main(self._apply, OverlayPhase.PROCESSING)

    def hide(self) -> None:
        self._call_main(self._apply, OverlayPhase.IDLE)

    def push_level(self, level: float) -> None:
        # Buffer mutation + bar update both happen on the main thread to avoid a
        # data race with rendering.
        self._call_main(self._on_level, float(level))

    # -- marshaling ----------------------------------------------------- #

    @staticmethod
    def _call_main(fn, *args) -> None:
        try:
            from PyObjCTools import AppHelper
        except Exception:  # pragma: no cover - non-macOS / pyobjc missing
            log.debug("AppHelper unavailable; overlay disabled")
            return
        AppHelper.callAfter(fn, *args)

    # -- main-thread work ----------------------------------------------- #

    def _on_level(self, level: float) -> None:
        try:
            self._buffer.push(level)
            if self._recording and self._wave_view is not None:
                self._update_bars()
        except Exception:  # pragma: no cover - defensive
            log.exception("overlay push_level failed")

    def _apply(self, phase: OverlayPhase) -> None:
        try:
            reduce_motion = self._reduce_motion()
            pres = OverlayPresentation.for_phase(phase, reduce_motion=reduce_motion)
            self._recording = pres.indicator in (
                OverlayIndicator.WAVEFORM,
                OverlayIndicator.DOT,
            )
            if not pres.visible:
                self._animate_out(reduce_motion)
                return
            self._ensure_panel()
            self._label.setStringValue_(pres.label)
            self._render(pres)
            self._panel.orderFrontRegardless()
            self._animate_in(reduce_motion)
        except Exception:  # pragma: no cover - never crash the host app
            log.exception("overlay apply failed")

    def _render(self, pres: OverlayPresentation) -> None:
        want_wave = pres.indicator is OverlayIndicator.WAVEFORM
        want_dot = pres.indicator is OverlayIndicator.DOT
        want_spinner = pres.indicator is OverlayIndicator.SPINNER

        self._wave_view.setHidden_(not want_wave)
        self._dot.setHidden_(not want_dot)
        if want_wave:
            self._update_bars()
        if want_spinner:
            self._spinner.setHidden_(False)
            self._spinner.startAnimation_(None)
        else:
            self._spinner.stopAnimation_(None)
            self._spinner.setHidden_(True)

    # -- environment ---------------------------------------------------- #

    @staticmethod
    def _reduce_motion() -> bool:
        try:
            from AppKit import NSWorkspace

            ws = NSWorkspace.sharedWorkspace()
            if hasattr(ws, "accessibilityDisplayShouldReduceMotion"):
                return bool(ws.accessibilityDisplayShouldReduceMotion())
        except Exception:  # pragma: no cover
            pass
        return False

    # -- panel construction --------------------------------------------- #

    def _ensure_panel(self) -> None:
        if self._panel is not None:
            return
        import AppKit
        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSPanel,
            NSProgressIndicator,
            NSTextField,
            NSView,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectStateActive,
            NSVisualEffectView,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSMakeRect

        # A few enum constants aren't exported under their modern names in older
        # pyobjc builds; resolve with fallbacks to their documented raw values.
        spinning_style = getattr(
            AppKit,
            "NSProgressIndicatorStyleSpinning",
            getattr(AppKit, "NSProgressIndicatorSpinningStyle", 1),
        )
        hud_material = getattr(AppKit, "NSVisualEffectMaterialHUDWindow", 13)

        # macOS floating window level constant (NSFloatingWindowLevel == 3).
        floating_level = 3

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _PANEL_W, _PANEL_H), style, NSBackingStoreBuffered, False
        )
        panel.setLevel_(floating_level)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setReleasedWhenClosed_(False)

        content = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _PANEL_W, _PANEL_H)
        )
        content.setMaterial_(hud_material)
        content.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        content.setState_(NSVisualEffectStateActive)
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(_CORNER)
        content.layer().setMasksToBounds_(True)
        panel.setContentView_(content)

        # Waveform container (left side), vertically centred.
        wave_w = _BAR_COUNT * (_BAR_W + _BAR_GAP)
        wave_x = 18.0
        wave_view = NSView.alloc().initWithFrame_(
            NSMakeRect(wave_x, (_PANEL_H - _BAR_MAX_H) / 2.0, wave_w, _BAR_MAX_H)
        )
        wave_view.setWantsLayer_(True)
        content.addSubview_(wave_view)
        self._build_bars(wave_view)

        # Static dot (reduce-motion fallback), same anchor as the waveform start.
        dot = NSView.alloc().initWithFrame_(
            NSMakeRect(wave_x, (_PANEL_H - _DOT_SIZE) / 2.0, _DOT_SIZE, _DOT_SIZE)
        )
        dot.setWantsLayer_(True)
        dot.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
        dot.layer().setCornerRadius_(_DOT_SIZE / 2.0)
        dot.setHidden_(True)
        content.addSubview_(dot)

        # Spinner (shares the left anchor; shown only while processing).
        spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(wave_x, (_PANEL_H - 18) / 2.0, 18, 18)
        )
        spinner.setStyle_(spinning_style)
        spinner.setDisplayedWhenStopped_(False)
        spinner.setHidden_(True)
        content.addSubview_(spinner)

        # Label to the right of the indicator area.
        label_x = wave_x + wave_w + 10.0
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(label_x, (_PANEL_H - 18) / 2.0, _PANEL_W - label_x - 12.0, 18)
        )
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setStringValue_("")
        label.setTextColor_(NSColor.whiteColor())
        content.addSubview_(label)

        self._panel = panel
        self._content = content
        self._wave_view = wave_view
        self._dot = dot
        self._spinner = spinner
        self._label = label
        self._position_panel()

    def _build_bars(self, wave_view) -> None:
        from AppKit import NSColor
        from QuartzCore import CALayer

        self._bars = []
        for i in range(_BAR_COUNT):
            bar = CALayer.layer()
            x = i * (_BAR_W + _BAR_GAP)
            y = (_BAR_MAX_H - _BAR_MIN_H) / 2.0
            bar.setFrame_(((x, y), (_BAR_W, _BAR_MIN_H)))
            bar.setCornerRadius_(_BAR_W / 2.0)
            bar.setBackgroundColor_(NSColor.whiteColor().CGColor())
            wave_view.layer().addSublayer_(bar)
            self._bars.append(bar)

    def _update_bars(self) -> None:
        if not self._bars:
            return
        heights = self._buffer.bar_heights(_BAR_MIN_H, _BAR_MAX_H)
        for bar, h in zip(self._bars, heights):
            x = bar.frame().origin.x
            y = (_BAR_MAX_H - h) / 2.0
            bar.setFrame_(((x, y), (_BAR_W, h)))

    def _position_panel(self) -> None:
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen is None:
                return
            frame = screen.visibleFrame()
            x = frame.origin.x + (frame.size.width - _PANEL_W) / 2.0
            y = frame.origin.y + _MARGIN_BOTTOM
            self._panel.setFrameOrigin_((x, y))
        except Exception:  # pragma: no cover
            log.debug("could not position overlay panel")

    # -- transitions ---------------------------------------------------- #

    def _animate_in(self, reduce_motion: bool) -> None:
        if self._content is None:
            return
        layer = self._content.layer()
        if reduce_motion:
            self._fade(layer, 0.0, 1.0, 0.15)
            return
        from QuartzCore import CABasicAnimation, CASpringAnimation

        layer.setOpacity_(1.0)
        fade = CABasicAnimation.animationWithKeyPath_("opacity")
        fade.setFromValue_(0.0)
        fade.setToValue_(1.0)
        fade.setDuration_(0.18)
        layer.addAnimation_forKey_(fade, "fade-in")

        spring = CASpringAnimation.animationWithKeyPath_("transform.scale")
        spring.setFromValue_(0.85)
        spring.setToValue_(1.0)
        spring.setDamping_(12.0)
        spring.setInitialVelocity_(6.0)
        spring.setDuration_(spring.settlingDuration())
        layer.addAnimation_forKey_(spring, "spring-in")

    def _animate_out(self, reduce_motion: bool) -> None:
        if self._panel is None:
            return
        panel = self._panel
        layer = self._content.layer() if self._content is not None else None
        if layer is None:
            panel.orderOut_(None)
            return

        from QuartzCore import CABasicAnimation

        dur = 0.14
        fade = CABasicAnimation.animationWithKeyPath_("opacity")
        fade.setFromValue_(1.0)
        fade.setToValue_(0.0)
        fade.setDuration_(dur)
        layer.addAnimation_forKey_(fade, "fade-out")
        if not reduce_motion:
            scale = CABasicAnimation.animationWithKeyPath_("transform.scale")
            scale.setFromValue_(1.0)
            scale.setToValue_(0.9)
            scale.setDuration_(dur)
            layer.addAnimation_forKey_(scale, "scale-out")

        # Order the panel out after the fade completes. If the user starts
        # recording again within the window, _apply has already set _recording
        # True and re-shown the panel, so we guard on the live phase.
        def _finish() -> None:
            if not self._recording:
                panel.orderOut_(None)

        try:
            from PyObjCTools import AppHelper

            AppHelper.callLater(dur + 0.02, _finish)
        except Exception:  # pragma: no cover
            panel.orderOut_(None)

    @staticmethod
    def _fade(layer, frm: float, to: float, dur: float) -> None:
        from QuartzCore import CABasicAnimation

        layer.setOpacity_(to)
        anim = CABasicAnimation.animationWithKeyPath_("opacity")
        anim.setFromValue_(frm)
        anim.setToValue_(to)
        anim.setDuration_(dur)
        layer.addAnimation_forKey_(anim, "fade")

