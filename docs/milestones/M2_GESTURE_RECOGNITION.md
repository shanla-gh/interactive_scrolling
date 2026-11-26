# M2 - Gesture Recognition Engine

Status: **technical verification passed; Director sign-off pending**
([checklist](M2_M3_DIRECTOR_CHECKLIST.md)). Gesture definitions, criteria and calibration
evidence: [GESTURES.md](../architecture/GESTURES.md).

| Checkpoint | Technical status | Evidence |
|---|---|---|
| CP 2.1 Engine architecture | Done | `gestures/` consumes `TrackingResult` + `MotionFrame` only; no Qt; events go to `actions/` (no direct execution); layering enforced by `tests/unit/test_architecture.py`; synthetic sequences processed without a webcam (`tests/gesture_helpers.py`) |
| CP 2.2 Finger swipes | Done | engine tests (exact single events, return suppression, repeats, small/slow/diagonal/open-hand/flick/entering-hand rejection, tracking loss, 15/30/60 FPS); recordings: pointing-hand swipes 8/8 |
| CP 2.3 Hand sweeps | Done (weak recall) | engine tests (direction from the user's perspective, wind-up into sweep, closed/vertical/small rejection, handedness-flip regression); recordings 4/12 at balanced; no Windows switching (mapped actions marked "planned", never executed) |
| CP 2.4 Static gestures | Done | tests: one event per hold, release-and-repeat, brief/moving/flicker cases, stop vs sweep preparation; recordings: one event per presentation |
| CP 2.5 State machine and false positives | Done | explicit lifecycles, cooldowns, return window, rearming, global cooldown, control hand AUTO/LEFT/RIGHT, ambiguity suspension, stale-event rejection in the dispatcher; 0 false triggers in all negative recording segments |
| CP 2.6 Configuration | Done | presets Low/Balanced/High, restore defaults, per-gesture enable, control hand, mapping; persisted in `%LOCALAPPDATA%\interactive_scrolling\settings.json` with per-field fallback (`tests/unit/test_settings_store.py`, `tests/integration/test_control_ui.py`) |
| CP 2.7 Visualization and history | Done | Gestures tab (candidate + progress, state, cooldown, rejection, control hand), on-video banner and progress bar outside the hand area, bounded history table distinguishing not executed / dispatched / succeeded / no change / rejected / failed / unknown; usable at 1280x720 logical pixels |
| CP 2.8 Safe activation | Done | starts in Tracking only; Gesture test executes nothing; Live control requires a click; Disable button, Esc and system-wide Ctrl+Alt+D; mode changes invalidate queued and in-flight requests (`tests/unit/test_action_dispatcher.py`) |

## M2 verification gate

* All automated tests: 393 passed with `--hardware` (1 opt-in live test skipped); ruff clean.
* Production vision-to-gesture pipeline: running in the real window with the real webcam and
  model for 10 minutes in Gesture test mode (no errors, 29.8 FPS); gesture cost 0.13 ms/frame
  with hands (replayed recordings).
* Real webcam observations: two labeled recordings of the Director (about 9,000 frames).
* Pending Director items: performing the gestures live in Gesture test and Live control.

## Design decisions made on evidence

See GESTURES.md "Calibration evidence": finger swipes redefined as pointing-hand movements
because flicks are ambiguous; return window from the end of the movement; motion-based sweep
start with reversal from the turning point; handedness smoothing; 0.6 s thumbs-up hold.
