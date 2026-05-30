# On-Screen Recording Overlay — Implementation Plan (v2, premium)

**Goal:** A glass NSPanel that springs in with a live mic-reactive waveform while recording, morphs to a spinner while transcribing, then springs out — driven from the menu-bar handlers.

**Execution rule:** dependent tasks are sequential. The AppKit `OverlayController`
(animation/layout judgment) is implemented on the main capable model, not a blind
subagent. Pure TDD pieces may be delegated.

**Tech:** Python 3.11, numpy, pyobjc (AppKit, QuartzCore), pytest. No new deps.

## Conventions
- Root: `/Users/baha/Desktop/llm-ai-projects/ai-voice-dictation`
- Tests: `uv run pytest -v` ; lint: `uv run ruff check <files>`
- Pure logic unit-tested in CI; AppKit verified by import-check + manual smoke.

---

## Task A: Audio level helpers (pure) — `levels.py`
Files: create `src/aivoice/pipeline/levels.py`, `tests/test_levels.py`.

- [ ] TDD `rms(block)`: empty→0.0; `[1,1,1,1]`→1.0; `[0.5,-0.5]`→0.5.
- [ ] TDD `normalized(rms, floor_db=-50)`: 0→0; sub-floor→0; 1.0→1.0; >1→1; midpoint(-25 dB)→~0.5.
- [ ] Implement with numpy; clamp to 0..1. Commit.

## Task B: `OverlayPresentation` v2 (pure) — rewrite in `overlay.py`
Files: modify `src/aivoice/ui/overlay.py` (pure part), `tests/test_overlay.py`.

- [ ] Add `OverlayIndicator(NONE, WAVEFORM, DOT, SPINNER)`; presentation has
  `visible, label, indicator`.
- [ ] `for_phase`: IDLE→(False,"",NONE); RECORDING→(True,"Recording…",WAVEFORM)
  or DOT if reduce_motion; PROCESSING→(True,"Transcribing…",SPINNER).
- [ ] Update tests for the 4 cases. Commit.

## Task C: `on_level` callback on `AudioCapture`
Files: modify `src/aivoice/pipeline/audio.py`, `tests/test_audio.py`.

- [ ] Add `on_level: Callable[[float], None] | None = None` attribute.
- [ ] In `_callback`, after copying the block, compute
  `normalized(rms(block))` and call `on_level(level)` if set (guard exceptions).
- [ ] Test: set `on_level`, feed a synthetic block via the callback, assert it got
  a float in 0..1 (no real mic needed). Existing audio tests stay green. Commit.

## Task D: `OverlayController` (AppKit) — append to `overlay.py`  [main model]
Files: modify `src/aivoice/ui/overlay.py`.

- [ ] `show_recording()/show_processing()/hide()/push_level(level)` — all marshal
  to main via `AppHelper.callAfter`.
- [ ] Lazy glass `NSPanel` (borderless, nonactivating, floating, click-through,
  frosted dark `NSVisualEffectView`, corner radius, shadow), bottom-center.
- [ ] Waveform: layer-backed view, N bar `CALayer`s, rolling level buffer; static
  dot fallback under Reduce Motion. Spinner: `NSProgressIndicator`.
- [ ] Spring entrance (`CASpringAnimation` scale+opacity), waveform↔spinner
  crossfade, spring-out; plain fades under Reduce Motion.
- [ ] Verify: `uv run python -c "import aivoice.ui.overlay"`, pure tests pass,
  ruff clean. Commit.

## Task E: Wire into `menubar.py`
Files: modify `src/aivoice/ui/menubar.py`.

- [ ] Build `AudioCapture()` in `_async_main`, set `capture.on_level = lambda lvl:
  self._overlay.push_level(lvl)`, pass it into `Orchestrator(audio=capture, ...)`.
- [ ] `self._overlay = OverlayController()`; `show_recording()` in `_on_press`,
  `show_processing()` + `finally: hide()` in `_on_release` (+ hide on press error).
- [ ] Verify import + full suite + ruff. Commit.

## Task F: Manual smoke + docs
- [ ] Run `uv run aivoice`; verify spring-in, live waveform reacts to voice,
  morph→spinner, spring-out, too-short, Reduce Motion. Document checklist. Commit.

## Self-review vs spec
Live waveform (A,C,D), spring transitions (D), glass panel (D), spinner morph (D),
reduce-motion fallback (B,D), main-thread safety (D), hide-always (E), no new deps,
menu-bar emoji kept. ✓
