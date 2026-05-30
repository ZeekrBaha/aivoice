# On-Screen Recording Overlay — Design Spec (v2, premium)

**Date:** 2026-05-30
**Status:** Approved design (upgraded to live waveform + spring transitions)
**Branch:** `feature/recording-overlay-hud`
**Project:** `ai-voice-dictation` (Python menu-bar app, `aivoice`)

## Goal

When the user holds ⌥, a polished glass panel **springs onto the screen** showing
a **live waveform that reacts to the real microphone level**. On release, it
**morphs to an indeterminate spinner** ("Transcribing…") while STT + optional LLM
cleanup run. When the text is injected (or on error/empty), the panel **fades and
scales away**. Target feel: Cluely / Wispr Flow — a dark, frosted, unobtrusive
pill with smooth motion.

## Current behavior (verified)

- `rumps` menu-bar app; only feedback today is the menu-bar emoji
  (`🎙`→`🔴`→`⚙️`→`🎙`, `ui/menubar.py:30-33`, handlers `:114-129`).
- Push-to-talk ⌥ via `pynput` (`ui/hotkey.py`), re-entrant.
- Pipeline (`Orchestrator.on_release`) is all-at-once (record → VAD → STT →
  cleanup → inject); no streaming → one indeterminate spinner is correct.
- **Threading constraint (critical):** AppKit/`rumps` run on the **main thread**;
  the pipeline + hotkey callbacks run on a **background asyncio thread**
  (`menubar.py:54`). The PortAudio capture callback runs on **its own audio
  thread**. All NSPanel work must be marshaled to the main thread.

## Decisions

- **Floating glass NSPanel** (frosted `NSVisualEffectView`, rounded, dark, shadow,
  click-through), bottom-center.
- **Recording:** live waveform bars driven by **real mic RMS**. Reduce Motion →
  static dot fallback.
- **Processing:** native `NSProgressIndicator` (indeterminate spinner).
- **Transitions:** spring entrance (fade + scale-up), waveform↔spinner crossfade,
  fade + scale-down exit. Reduce Motion → plain fades.
- Keep the menu-bar emoji (complementary, free).

## Architecture

### Pipeline change (small, tested): mic level callback

`src/aivoice/pipeline/levels.py` (pure, unit-tested):

```python
def rms(block: np.ndarray) -> float          # sqrt(mean(square)), 0 for empty
def normalized(rms_value: float, floor_db: float = -50) -> float  # dB → 0..1, clamped
```

`AudioCapture` (`pipeline/audio.py`): add `on_level: Callable[[float], None] | None`.
In the existing PortAudio `_callback`, after copying the block, compute
`normalized(rms(block))` and invoke `on_level(level)` if set. The callback runs on
the audio thread; the consumer marshals to main. The capture's recorded-frames
behavior is unchanged.

### Overlay: `src/aivoice/ui/overlay.py`

**1. `OverlayPresentation` (pure, unit-tested).** Phase → what to show, via a
single `indicator` value (cleaner than multiple booleans, and lets Reduce Motion
swap waveform→dot):

```python
class OverlayPhase(str, Enum): IDLE, RECORDING, PROCESSING
class OverlayIndicator(str, Enum): NONE, WAVEFORM, DOT, SPINNER

@dataclass(frozen=True)
class OverlayPresentation:
    visible: bool
    label: str
    indicator: OverlayIndicator
    @classmethod
    def for_phase(cls, phase, reduce_motion=False) -> "OverlayPresentation": ...
```

Mapping:
- `IDLE` → `visible=False, label="", indicator=NONE`
- `RECORDING` → `visible=True, label="Recording…", indicator=WAVEFORM` (or `DOT` if `reduce_motion`)
- `PROCESSING` → `visible=True, label="Transcribing…", indicator=SPINNER`

**2. `OverlayController` (AppKit, thin).** Thread-safe public API callable from any
thread (each marshals via `PyObjCTools.AppHelper.callAfter`):

```python
show_recording() / show_processing() / hide()
push_level(level: float)   # feed a 0..1 mic sample to the waveform
```

- Lazily builds one reusable borderless, non-activating, floating `NSPanel`
  (`ignoresMouseEvents=True`) on the main thread; content is a rounded
  `NSVisualEffectView` (dark, frosted).
- **Waveform:** a custom layer-backed view holding N `CALayer` bars (newest on the
  right, scrolling). `push_level` appends to a rolling buffer and updates bar
  heights; under Reduce Motion the waveform view is hidden and a static dot shown.
- **Spinner:** `NSProgressIndicator` (spinning), `displayedWhenStopped=False`.
- **Spring transitions:** `CASpringAnimation` on the content layer's
  `transform.scale` + opacity for entrance; crossfade swapping waveform↔spinner;
  scale-down + fade for exit. Reduce Motion → plain `CABasicAnimation` opacity
  fades (no scale).
- **Reduce Motion:** `NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()`.
- Defensive: all AppKit imported lazily inside methods (so importing the module —
  and running the pure tests — needs no GUI); every main-thread block wrapped so a
  failure logs and never crashes the app; `NSScreen.mainScreen()` None-guarded.

### Integration: `menubar.py`

```python
self._overlay = OverlayController()
# when building AudioCapture:
capture = AudioCapture()
capture.on_level = lambda lvl: self._overlay.push_level(lvl)
...
async def _on_press(self):
    self.title = LISTENING; self._overlay.show_recording()
    try: await self._orch.on_press()
    except Exception: log.exception("on_press failed"); self.title = IDLE; self._overlay.hide()

async def _on_release(self):
    self.title = WORKING; self._overlay.show_processing()
    try: await self._orch.on_release()
    except Exception: log.exception("on_release failed")
    finally: self.title = IDLE; self._overlay.hide()
```

`Orchestrator` currently constructs `AudioCapture()` internally (`menubar.py:97`).
To wire `on_level`, build the `AudioCapture` in `menubar` and pass it into
`Orchestrator` (the `Orchestrator` already accepts an `audio` arg — just hand it
the pre-wired instance).

## Data flow

```
Hold ⌥ → show_recording() → spring-in glass pill, waveform live
         audio thread → rms→normalized → on_level → push_level → bars react
Release → show_processing() → crossfade waveform→spinner, "Transcribing…"
          await on_release() (STT + cleanup + inject)
finally → hide() → spring-out (fade+scale)
```

## Error handling / edge cases

- Empty/too-short/VAD-trims-all/STT-empty → `on_release` returns → `finally` hides.
- Pipeline exception → swallowed in `Orchestrator` (logged); `finally` hides.
- Rapid release→press → idempotent, ordered on main thread; spring re-entry safe.
- Reduce Motion → static dot + plain fades; spinner honors system setting.
- No main screen / no pyobjc → controller no-ops, app keeps working.

## Testing

- **Unit (pure, CI):** `OverlayPresentation.for_phase` all phases + reduce-motion;
  `levels.rms` (empty, constant, half-amplitude) and `levels.normalized` (silence
  floor, 0 dB ceiling, midpoint, clamp). Files: `tests/test_overlay.py`,
  `tests/test_levels.py`.
- **Existing `tests/test_audio.py`** stays green; add one test that `on_level` is
  invoked with a 0..1 float during capture (or unit-test the callback wiring with a
  synthetic block to avoid mic dependence).
- **Manual smoke:** documented — spring-in, live waveform reacts to voice,
  morph to spinner, spring-out; too-short; Reduce Motion.

## Scope guardrails (YAGNI)

- No streaming/partial transcription.
- No new dependencies (pyobjc Cocoa/Quartz already present; QuartzCore +
  `PyObjCTools.AppHelper` ship with pyobjc; numpy already a dep).
- No change to hotkey, STT, cleanup, or injection logic (only `AudioCapture` gains
  an optional callback, and `menubar` constructs it).
- Menu-bar emoji kept.

## Files touched

- **Create** `src/aivoice/pipeline/levels.py` + `tests/test_levels.py`.
- **Modify** `src/aivoice/pipeline/audio.py` (+ `tests/test_audio_levels.py`) — `on_level`.
- **Create/extend** `src/aivoice/ui/overlay.py` + `tests/test_overlay.py`, `tests/test_waveform.py`.
- **Modify** `src/aivoice/ui/menubar.py` — build wired `AudioCapture`, drive overlay.

## Manual QA — recording overlay

Run `uv run aivoice` (grant Microphone, Accessibility, and Input Monitoring if
prompted; restart after granting). Then:

- [ ] **Hold ⌥** → a frosted glass pill **springs in** bottom-center with a
  **live waveform** + "Recording…". Speak: the bars **react to your voice**
  (louder = taller), quieter when silent.
- [ ] **Release ⌥** → the pill **morphs to a spinner** + "Transcribing…" and
  **stays** until the text is pasted at the cursor.
- [ ] After paste → the pill **springs/fades out**.
- [ ] **Too-short:** tap-and-release ⌥ instantly → spinner shows briefly, then
  the pill disappears (no stuck panel; VAD trims to empty, `finally` hides it).
- [ ] **Reduce Motion ON** (System Settings → Accessibility → Display → Reduce
  Motion) → static red dot instead of the waveform, plain fades (no scale/spring),
  spinner still spins.
- [ ] The menu-bar emoji still cycles 🎙 → 🔴 → ⚙️ → 🎙 alongside the overlay.
