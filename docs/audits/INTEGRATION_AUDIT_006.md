# Integration Audit 006 (beta stabilization, Brief 004)

Date: 2026-11-27. Scope: the whole application after the gesture engine rework, the browser
reliability fixes, diagnostics, Practice and Quick Calibration.

| Verdict | |
|---|---|
| Technical verification | **passed** (unit, integration, regression, browser fixture, hardware, live website signed out, 6- and 10-minute GUI sessions) |
| Recognition evidence | development data only (one person, two sessions); left/right, half-heart and stop at a normal distance not measured |
| Director validation | **pending** (`docs/milestones/BRIEF_004_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Camera ownership | one camera, one processing thread; the diagnostics/recorder/calibration tap runs inside the processing loop (fast, locked, bounded) | `VisionPipeline.add_gesture_tap`; stability sessions: 30.0 fps processing |
| Landmark tracking | unchanged model and settings; positioning hints from measured hand size and position | engine tests `test_small_hand_gets_a_positioning_hint` |
| Smoothing | 40 ms moving average kept after comparison with none, 20/80 ms and One Euro | `scripts/experiment_filtering.py`, benchmark section 7 |
| Classification | 3D finger states kept (image-space variant rejected); tolerant half-heart; time-based pointing rule | `evaluate_poses.py`, engine tests |
| Lifecycle | arming on one rest, followed blocked strokes, pending flicks, dropout tolerance, unchanged return rule and cooldowns | 81 engine tests, regression tests |
| Calibration | bounded, explicit, reversible; derived numbers only; calibration collector only runs while a prompt is active | `test_calibration.py`, `test_practice_dialog.py` |
| Configuration persistence | settings v3: mapping migration once (with notice), named presets follow preset values, custom/personal kept, calibration section | `test_settings_store.py` (incl. invalid-field fallbacks) |
| Practice Mode | Gesture test mode while open; Live control never restored silently; emergency disable kept | `test_practice_dialog.py` |
| Browser communication | first Short refused at once; state re-reported after URL changes; transient waits bounded (1.2 s, one attempt); arriving-Short id | fixture browser tests (16), bridge tests, live website 3/4 runs (the fourth: a correct refusal while Edge's own startup tab was in front) |
| Dispatcher | one gesture may wait behind the running action (third refused, expires after 2.5 s, dropped by disable/mode change); stale and context checks unchanged | `test_action_dispatcher.py`, `test_dispatcher_transient_state.py` |
| Emergency disable | ends a transient wait, drops a waiting gesture, cancels the running action, survives closing Practice | dispatcher and dialog tests; independent of `RecognizerOptions` (the engine never executes actions) |
| Developer / Creator / Background modes | unchanged runtime sharing; gesture panel and video overlay extended; creator overlay unchanged | `test_ui_modes.py`, `test_control_ui.py` |
| Co-op | Guest requests still enter the Host's dispatcher; gesture-to-action map follows the new direction; a Guest computer runs the same improved engine | `test_coop.py`, `test_coop_ui.py` (incl. separate-process guest) |
| Statistics | the Shorts session no longer ends and restarts around every navigation (transient states keep it) | `test_shorts_session_does_not_end_while_the_short_changes` |
| Thread synchronization | taps use locks; the Practice dialog receives records through a thread-safe queue and reads diagnostics by timer on the UI thread; profile and settings changes reach the engine by reference / `request_settings` | code review; dialog tests |
| Resource cleanup | Practice closes its timer, listener, calibration and recorder; shutdown 0.29 s, no worker threads left | stability sessions |
| Privacy | diagnostics export: no pairing code, URLs, titles, video ids or images (tested); landmark recording only on request; calibration stores derived numbers | `test_export_contains_no_pairing_code_or_page_data` |

## Defects found and fixed in this brief

| Defect | Severity | Fix / test |
|---|---|---|
| "Previous" at the first Short clicked a hidden button and failed after 3 s (Director's 5 failures) | High | page reports `can_previous`; `test_browser_first_short_and_navigation_state.py` |
| Missing/stale page state right after a navigation refused quick gestures | High | transient states, re-report, arriving id; regression tests |
| Horizontal movements confirmed in the opposite direction (arming) | High | `test_gesture_arming_confirms_return.py` |
| Downward finger flicks rejected (pose rule) | High | `test_gesture_down_flick_rejected.py` |
| Up mapped to "previous" against the Director's expectation | Medium | default + migration; settings tests |
| Stop hold cancelled by jitter on small hands | Medium | `test_gesture_stop_small_hand_jitter.py` |
| Second quick gesture refused while the first navigation waited for loading | Medium | waiting slot; dispatcher tests |
| Shorts session flicker around navigations | Low | regression test |
| Evaluator mirrored replay did not swap handedness labels | Low | `test_evaluator_mirror_swaps_handedness.py` |
| Own change caught before commit: a settings file without a preset field lost the user's value | - | fixed; `test_invalid_fields_fall_back_individually` caught it |

No critical defect is open. Open high-severity *verification* items (not defects): left/right
swipes, half-heart and stop pose on real recordings; signed-in liking.

## Performance

See the table in `PROJECT_STATUS.md` (development machine, Windows 11, i7-13700H, built-in
camera, 1280x720). Recognition: 0.156 ms per frame on replayed recordings (0.112 ms in 0.3);
in the GUI sessions the gesture stage (engine + taps) measured 0.25 ms mean.

## GUI sessions

6 and 10 minutes, production services, Gesture test mode, camera restarts every 2 min: 30.0-30.1
fps, latency 13.3-15.8 ms mean, gesture stage 0.17-0.25 ms, CPU 4.5-5.4 %, memory 396 -> 362 MB
over 10 min (no growth), 6/6 restarts, shutdown 0.29-0.63 s with no threads left. A person was
in view during both sessions (44-64 % of samples) and 21 gestures were recognized in each
(Gesture test mode, nothing executed); intent is unknown, so they count neither as recall
nor as false triggers. Packaged build: `--self-test` PASS.

## UI stalls

Two stalls in the 6-minute session (582 ms with 153 ms garbage collection outside application
handlers; 339 ms while the session script resized the window) and one (181 ms) in the 10-minute
session. As in Audits 003-005 they occur
inside Qt's event loop without an application handler running, the capture and processing
threads keep running (worker gaps 0 ms), and they are not reproducible on demand. Unchanged
status: Low, instrumented.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | Recognition numbers are development results from one person; no held-out data |
| Medium | Lowering a pointing hand out of view can be read as a downward swipe (one recorded case) |
| Medium | Finger flicks need ~30 fps; at 15 fps they are undersampled (hand movements still work) |
| Medium | Stop pose at arm's length: detector loses the hand |
| Medium | YouTube markup changes would make Shorts actions fail (reported honestly) |
| Low | Rare UI stalls inside Qt (instrumented) |
