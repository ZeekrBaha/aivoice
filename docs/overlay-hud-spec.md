# On-Screen Recording Overlay — Design Spec

**Date:** 2026-05-30
**Status:** Draft for review
**Branch:** `feature/recording-overlay-hud`
**Project:** `ai-voice-dictation` (Python menu-bar app, `aivoice`)

## Goal

When the user holds the dictation key (⌥), a small panel **appears on screen**
showing it is recording (a pulsing red dot + "Recording…"). When the key is
released, the panel switches to an indeterminate **spinner** ("Transcribing…")
while STT + optional LLM cleanup run. When the text is injected (or on
error/empty), the panel **disappears**.

## Current behavior (verified)

- Menu-bar app built on `rumps`; the only feedback today is the menu-bar emoji
  changing: `🎙` idle → `🔴` listening → `⚙️` working → `🎙` idle
  (`ui/menubar.py:30-33`, `_on_press`/`_on_release` at `:114-129`).
- Push-to-talk is ⌥ via `pynput` (`ui/hotkey.py`), re-entrant (ignores repeat
  press while held).
- The pipeline (`Orchestrator.on_release`) is **all-at-once**: record → VAD trim
  → STT → optional cleanup → inject. There is no streaming, so a single
  indeterminate spinner is the correct processing indicator.
- **Threading (the critical constraint):** `rumps`/AppKit run the main run loop
  on the **main thread**. The pipeline runs on a **background asyncio thread**
  (`menubar.py:54`, `_run_loop`). `_on_press`/`_on_release` execute on that
  background thread. **All NSPanel creation and mutation must be marshaled to the
  main thread.**

## Decisions (from review)

- **Floating overlay panel** (a real on-screen `NSPanel`), not just the menu-bar glyph.
- **Recording animation:** pulsing red dot + "Recording…". No audio-pipeline change.
- **Processing:** native `NSProgressIndicator` (indeterminate spinner) + "Transcribing…".
- Keep the existing menu-bar emoji changes too — they're free and complementary.

## Design

### New module: `src/aivoice/ui/overlay.py`

Two pieces, split so the logic is testable without a running NSApplication:

**1. `OverlayPresentation` (pure, unit-tested).**
A tiny pure mapping from phase → what the panel should show. No AppKit imports.

```python
class OverlayPhase(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"

@dataclass(frozen=True)
class OverlayPresentation:
    visible: bool
    label: str          # "" when idle
    dot_pulsing: bool   # red dot shown + animated
    spinner: bool       # spinner shown + animated

    @classmethod
    def for_phase(cls, phase: OverlayPhase, reduce_motion: bool = False) -> "OverlayPresentation":
        ...
```

Mapping:
- `IDLE`      → `visible=False, label="",            dot_pulsing=False, spinner=False`
- `RECORDING` → `visible=True,  label="Recording…",  dot_pulsing=not reduce_motion, spinner=False`
- `PROCESSING`→ `visible=True,  label="Transcribing…",dot_pulsing=False, spinner=True`

(When `reduce_motion` is true, the dot is shown but static — `dot_pulsing=False`.)

**2. `OverlayController` (AppKit, thin, smoke-tested manually).**
Owns the `NSPanel` + content view and exposes a thread-safe API:

```python
class OverlayController:
    def show_recording(self) -> None: ...
    def show_processing(self) -> None: ...
    def hide(self) -> None: ...
```

- Each method marshals to the main thread via
  `PyObjCTools.AppHelper.callAfter`, so the background pipeline thread can call
  them directly. The actual panel work runs on main.
- The panel is created **lazily on first show, on the main thread**. It is a
  borderless, non-activating, floating `NSPanel` with a rounded translucent
  background (`NSVisualEffectView`), positioned bottom-center of the main screen.
- Content: a red dot view + an `NSProgressIndicator` (spinner style) + an
  `NSTextField` label. Per phase, `OverlayController` reads
  `OverlayPresentation.for_phase(...)` and shows/hides/animates each element.
- Pulsing dot: `CABasicAnimation` on the dot layer's `opacity` (and a subtle
  `transform.scale`), `autoreverses`, `repeatCount = infinity`. Removed when not
  recording.
- **Reduce Motion:** read
  `NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()` and
  pass into `for_phase`; when true, skip the pulse (static dot) — the spinner is
  a system control that already honors the setting.
- `hide()` orders the panel out (kept allocated for reuse).

### Integration: `src/aivoice/ui/menubar.py`

Minimal edits to the existing handlers:

```python
# in __init__ / _async_main: create the controller (main thread is fine here)
self._overlay = OverlayController()

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
    finally:
        self.title = IDLE
        self._overlay.hide()
```

The existing `try/finally` already guarantees the spinner is always dismissed —
including the empty-audio / error paths inside `Orchestrator.on_release` (which
swallows its own exceptions and returns).

## Data flow

```
Hold ⌥  → _on_press  → overlay.show_recording()  → (callAfter) panel fades in, dot pulses
Release → _on_release → overlay.show_processing() → (callAfter) dot→spinner, "Transcribing…"
          await on_release() (STT + cleanup + inject)
finally → overlay.hide() → (callAfter) panel orders out
```

## Error handling / edge cases

- **Empty audio / VAD trims everything / STT empty:** `on_release` returns
  normally → `finally` hides the overlay. Spinner never hangs.
- **Pipeline exception:** swallowed inside `Orchestrator` (logged); `finally`
  still hides. (And `_on_press` failure path hides explicitly.)
- **Rapid release→press:** `show_recording` after `hide`/`show_processing` just
  resets the phase; calls are idempotent and ordered on the main thread.
- **Reduce Motion on:** static dot, system spinner (honors setting).
- **No main screen / headless:** `OverlayController` guards `NSScreen.mainScreen()`
  being `None` (skips positioning); never crashes the app.
- **Permissions not granted:** unchanged — the app already gates on perms before
  wiring the hotkey, so the overlay is only ever driven when dictation is live.

## Testing

This project uses pytest + TDD (see `docs/plan.md`). AppKit panels can't run
headlessly, so:

- **Unit-tested (pure):** `OverlayPresentation.for_phase` for all three phases,
  and the `reduce_motion=True` recording case (dot static). New file
  `tests/test_overlay.py`. No AppKit import, runs in CI.
- **Manual smoke test:** documented steps to run `aivoice`, hold ⌥, and confirm
  the panel appears (pulsing dot), switches to the spinner on release, and
  disappears after paste — plus the too-short (tap-and-release) and Reduce-Motion
  cases.

## Scope guardrails (YAGNI)

- No live waveform / no audio-pipeline change (pulsing dot only).
- No streaming/partial results.
- No new dependencies — `pyobjc-framework-Cocoa`/`-Quartz` are already deps;
  `CABasicAnimation` (QuartzCore) and `PyObjCTools.AppHelper` ship with pyobjc.
- No change to the hotkey, STT, cleanup, or injection.
- Keep the menu-bar emoji feedback as-is (complementary).

## Files touched

- **Create** `src/aivoice/ui/overlay.py` — `OverlayPhase`, `OverlayPresentation`, `OverlayController`.
- **Create** `tests/test_overlay.py` — unit tests for `OverlayPresentation`.
- **Modify** `src/aivoice/ui/menubar.py` — instantiate controller; call show/hide in `_on_press`/`_on_release`.
- **Modify** `README.md` / `docs/` — short note + manual QA steps (optional).
