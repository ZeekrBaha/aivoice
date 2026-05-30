# On-Screen Recording Overlay — Implementation Plan

> **For agentic workers:** implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A floating on-screen panel that shows a pulsing red dot while recording and a native spinner while transcribing, then disappears — driven from the existing menu-bar handlers.

**Architecture:** A pure `OverlayPresentation` (phase → display mapping, unit-tested) plus a thin `OverlayController` that owns one reusable `NSPanel` and marshals all AppKit work to the main thread via `PyObjCTools.AppHelper.callAfter` (the pipeline runs on a background asyncio thread). `menubar.py` calls `show_recording()` / `show_processing()` / `hide()`.

**Tech Stack:** Python 3.11, pyobjc (AppKit, Quartz/QuartzCore), pytest. No new dependencies.

---

## Conventions

- **Project root:** `/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation`
- **Run the overlay unit tests:** `uv run pytest tests/test_overlay.py -v`
- **Run the full suite (no regressions):** `uv run pytest -v`
- **Lint:** `uv run ruff check src/aivoice/ui/overlay.py`
- Existing tests must stay green. AppKit cannot run headlessly, so `overlay.py`'s
  AppKit class is verified by a build/import check + manual smoke test, while the
  pure `OverlayPresentation` is unit-tested.

## File structure

- **Create** `src/aivoice/ui/overlay.py` — `OverlayPhase`, `OverlayPresentation` (pure), `OverlayController` (AppKit).
- **Create** `tests/test_overlay.py` — unit tests for `OverlayPresentation`.
- **Modify** `src/aivoice/ui/menubar.py` — instantiate `OverlayController`; call show/hide in `_on_press`/`_on_release`.

---

## Task 1: `OverlayPresentation` (pure mapping) + tests

**Files:**
- Create: `src/aivoice/ui/overlay.py` (pure part only this task)
- Test: `tests/test_overlay.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_overlay.py`:

```python
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
    assert p.dot_pulsing is False   # dot shown but not animated
    assert p.spinner is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_overlay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aivoice.ui.overlay'`.

- [ ] **Step 3: Write the pure implementation** — create `src/aivoice/ui/overlay.py` with ONLY this (the AppKit `OverlayController` is added in Task 2, so this file imports no AppKit yet):

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_overlay.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
git add src/aivoice/ui/overlay.py tests/test_overlay.py && \
git commit -m "feat(ui): pure OverlayPresentation phase mapping

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `OverlayController` (AppKit panel, thread-safe)

**Files:**
- Modify: `src/aivoice/ui/overlay.py` (append the AppKit controller)

No unit test (AppKit can't run headlessly); verified by import/build check + Task 4 manual smoke. All AppKit imports are done lazily *inside* methods so importing the module (and thus Task 1's pure tests) never requires a GUI session.

- [ ] **Step 1: Append `OverlayController` to `src/aivoice/ui/overlay.py`**

Add these imports at the top of the file (below the existing `from __future__` line):

```python
import logging

log = logging.getLogger(__name__)
```

Then append at the end of the file:

```python
# Layout constants for the panel.
_PANEL_W = 200.0
_PANEL_H = 56.0
_MARGIN_BOTTOM = 120.0


class OverlayController:
    """Owns a single reusable floating NSPanel showing recording/processing state.

    Thread-safety: the dictation pipeline runs on a background asyncio thread, but
    AppKit must be touched only on the main thread. Every public method marshals
    its work onto the main thread via PyObjCTools.AppHelper.callAfter, so callers
    on any thread are safe. The panel is created lazily on first show (on main).
    """

    def __init__(self) -> None:
        self._panel = None
        self._dot = None
        self._spinner = None
        self._label = None

    # -- public API (callable from any thread) --------------------------- #

    def show_recording(self) -> None:
        self._dispatch(OverlayPhase.RECORDING)

    def show_processing(self) -> None:
        self._dispatch(OverlayPhase.PROCESSING)

    def hide(self) -> None:
        self._dispatch(OverlayPhase.IDLE)

    # -- internals (run on the main thread) ------------------------------ #

    def _dispatch(self, phase: "OverlayPhase") -> None:
        try:
            from PyObjCTools import AppHelper
        except Exception:  # pragma: no cover - non-macOS / no pyobjc
            log.debug("AppHelper unavailable; overlay disabled")
            return
        AppHelper.callAfter(self._apply, phase)

    def _apply(self, phase: "OverlayPhase") -> None:
        try:
            pres = OverlayPresentation.for_phase(phase, reduce_motion=self._reduce_motion())
            if not pres.visible:
                if self._panel is not None:
                    self._panel.orderOut_(None)
                self._stop_pulse()
                return
            self._ensure_panel()
            self._label.setStringValue_(pres.label)
            self._render(pres)
            self._panel.orderFrontRegardless()
        except Exception:  # pragma: no cover - defensive; never crash the app
            log.exception("overlay apply failed")

    def _render(self, pres: "OverlayPresentation") -> None:
        # Dot
        self._dot.setHidden_(not (pres.dot_pulsing or pres.spinner is False and pres.visible and not pres.spinner))
        # The dot is shown whenever we're recording (pulsing or static); hidden while processing.
        show_dot = pres.visible and not pres.spinner
        self._dot.setHidden_(not show_dot)
        if pres.dot_pulsing:
            self._start_pulse()
        else:
            self._stop_pulse()
        # Spinner
        if pres.spinner:
            self._spinner.setHidden_(False)
            self._spinner.startAnimation_(None)
        else:
            self._spinner.stopAnimation_(None)
            self._spinner.setHidden_(True)

    def _reduce_motion(self) -> bool:
        try:
            from AppKit import NSWorkspace
            ws = NSWorkspace.sharedWorkspace()
            if hasattr(ws, "accessibilityDisplayShouldReduceMotion"):
                return bool(ws.accessibilityDisplayShouldReduceMotion())
        except Exception:  # pragma: no cover
            pass
        return False

    def _ensure_panel(self) -> None:
        if self._panel is not None:
            return
        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSPanel,
            NSProgressIndicator,
            NSTextField,
            NSView,
            NSVisualEffectView,
        )
        from AppKit import (
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
            NSFloatingWindowLevel,
            NSProgressIndicatorStyleSpinning,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectStateActive,
            NSTextAlignmentLeft,
        )
        from Foundation import NSMakeRect

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _PANEL_W, _PANEL_H), style, NSBackingStoreBuffered, False
        )
        panel.setLevel_(NSFloatingWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)

        effect = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _PANEL_W, _PANEL_H)
        )
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        effect.setWantsLayer_(True)
        effect.layer().setCornerRadius_(14.0)
        panel.setContentView_(effect)

        # Red dot (layer-backed view we can animate)
        dot = NSView.alloc().initWithFrame_(NSMakeRect(18, _PANEL_H / 2 - 6, 12, 12))
        dot.setWantsLayer_(True)
        dot.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
        dot.layer().setCornerRadius_(6.0)
        effect.addSubview_(dot)

        # Spinner (same anchor as the dot)
        spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(14, _PANEL_H / 2 - 9, 18, 18)
        )
        spinner.setStyle_(NSProgressIndicatorStyleSpinning)
        spinner.setDisplayedWhenStopped_(False)
        spinner.setHidden_(True)
        effect.addSubview_(spinner)

        # Label
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(42, _PANEL_H / 2 - 11, _PANEL_W - 54, 22)
        )
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setAlignment_(NSTextAlignmentLeft)
        label.setStringValue_("")
        effect.addSubview_(label)

        self._panel = panel
        self._dot = dot
        self._spinner = spinner
        self._label = label
        self._position_panel()

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

    def _start_pulse(self) -> None:
        if self._dot is None:
            return
        from QuartzCore import CABasicAnimation
        layer = self._dot.layer()
        if layer.animationForKey_("pulse") is not None:
            return
        anim = CABasicAnimation.animationWithKeyPath_("opacity")
        anim.setFromValue_(1.0)
        anim.setToValue_(0.3)
        anim.setDuration_(0.7)
        anim.setAutoreverses_(True)
        anim.setRepeatCount_(float("inf"))
        layer.addAnimation_forKey_(anim, "pulse")

    def _stop_pulse(self) -> None:
        if self._dot is not None and self._dot.layer() is not None:
            self._dot.layer().removeAnimationForKey_("pulse")
```

> Note: `_render` deliberately recomputes `show_dot` cleanly (the first
> `setHidden_` line is replaced by the explicit `show_dot` logic right below it).
> Keep the explicit `show_dot` version; remove the confusing first line if you
> prefer — they resolve to the same result, dot shown only while recording.

- [ ] **Step 2: Clean up `_render`** — simplify to exactly this (remove the redundant first `setHidden_`):

```python
    def _render(self, pres: "OverlayPresentation") -> None:
        show_dot = pres.visible and not pres.spinner
        self._dot.setHidden_(not show_dot)
        if pres.dot_pulsing:
            self._start_pulse()
        else:
            self._stop_pulse()
        if pres.spinner:
            self._spinner.setHidden_(False)
            self._spinner.startAnimation_(None)
        else:
            self._spinner.stopAnimation_(None)
            self._spinner.setHidden_(True)
```

- [ ] **Step 3: Verify module imports without a GUI and pure tests still pass**

Run:
```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
uv run python -c "import aivoice.ui.overlay as o; print(o.OverlayController, o.OverlayPresentation.for_phase(o.OverlayPhase.RECORDING))" && \
uv run pytest tests/test_overlay.py -v && \
uv run ruff check src/aivoice/ui/overlay.py
```
Expected: prints the class + a recording presentation; 4 tests pass; ruff clean.

- [ ] **Step 4: Commit**

```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
git add src/aivoice/ui/overlay.py && \
git commit -m "feat(ui): OverlayController floating panel (main-thread marshaled)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the overlay into `menubar.py`

**Files:**
- Modify: `src/aivoice/ui/menubar.py`

- [ ] **Step 1: Import the controller** — add to the imports block (near the other `from aivoice.ui...` lines):

```python
from aivoice.ui.overlay import OverlayController
```

- [ ] **Step 2: Instantiate it in `__init__`** — after `self._hotkey: HoldHotkey | None = None` add:

```python
        self._overlay = OverlayController()
```

- [ ] **Step 3: Drive it from the handlers** — replace the existing `_on_press` and `_on_release` with:

```python
    async def _on_press(self) -> None:
        self.title = LISTENING
        self._overlay.show_recording()
        try:
            await self._orch.on_press()
        except Exception:
            log.exception("on_press failed")
            self.title = IDLE
            self._overlay.hide()

    async def _on_release(self) -> None:
        self.title = WORKING
        self._overlay.show_processing()
        try:
            await self._orch.on_release()
        except Exception:
            log.exception("on_release failed")
        finally:
            self.title = IDLE
            self._overlay.hide()
```

- [ ] **Step 4: Verify import + full suite (no regressions)**

Run:
```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
uv run python -c "import aivoice.ui.menubar" && \
uv run pytest -v && \
uv run ruff check src/aivoice/ui/menubar.py src/aivoice/ui/overlay.py
```
Expected: menubar imports cleanly; all existing tests + the 4 overlay tests pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
git add src/aivoice/ui/menubar.py && \
git commit -m "feat(ui): show recording/processing overlay from menubar handlers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Manual smoke test + docs

**Files:**
- Modify: `README.md` (or `docs/overlay-hud-spec.md` — append a "Manual QA" section)

- [ ] **Step 1: Run the app and verify the overlay**

Run: `uv run aivoice` (grant mic/accessibility/input-monitoring if prompted), then:

- [ ] Hold **⌥** → panel appears bottom-center with a **pulsing red dot** + "Recording…".
- [ ] Release → panel switches to a **spinner** + "Transcribing…" and **stays** until text is pasted.
- [ ] After paste → panel **disappears**.
- [ ] **Too-short:** tap-and-release ⌥ immediately → spinner appears briefly, then disappears (no stuck panel; VAD trims to empty and `finally` hides it).
- [ ] **Reduce Motion** (System Settings → Accessibility → Display → Reduce Motion ON) → dot is static, spinner still spins.

- [ ] **Step 2: Document the manual QA steps** — append a short "Manual QA — recording overlay" checklist (mirroring Step 1) to `docs/overlay-hud-spec.md` or `README.md`, matching the file's existing heading style.

- [ ] **Step 3: Commit**

```bash
cd "/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation" && \
git add -A && \
git commit -m "docs: manual QA checklist for recording overlay

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review against the spec

- Floating NSPanel overlay → Tasks 2, 3. ✓
- Pulsing dot (recording) → Task 2 (`_start_pulse`, `CABasicAnimation`). ✓
- Native spinner (processing) → Task 2 (`NSProgressIndicator`). ✓
- Hidden on completion/error → Task 3 (`finally: hide()` + `_on_press` failure hide). ✓
- Pure/testable phase mapping → Task 1 (`OverlayPresentation`, 4 unit tests). ✓
- Main-thread marshaling from background pipeline → Task 2 (`callAfter`). ✓
- Reduce Motion respected → Task 2 (`_reduce_motion` → `for_phase`). ✓
- No new deps, no pipeline/hotkey/STT change, menu-bar emoji kept → all tasks. ✓
- Spinner can't hang (empty/too-short/error) → Task 3 `finally`. ✓

**Type/name consistency:** `OverlayPhase.{IDLE,RECORDING,PROCESSING}`,
`OverlayPresentation.for_phase(phase, reduce_motion=)`, fields
`visible/label/dot_pulsing/spinner`, and `OverlayController.show_recording/
show_processing/hide` are used identically across Tasks 1–3.
