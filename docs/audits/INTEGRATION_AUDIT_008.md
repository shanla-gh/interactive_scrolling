# Integration Audit 008 (pose-independent motion, Brief 006)

Date: 2026-11-27. Scope: the whole application after the duplicate-hand fix, the any-hand-shape
engine, the tracking-gap rules, settings v5 and the diagnostics additions.

| Verdict | |
|---|---|
| Technical verification | **passed**: 686 tests (0 failed, 0 expected failures, 6 skipped = webcam/live, run separately), hardware 5/5, live website 3/3, repeated full runs green (5 during development, 3 on the final code), packaged self-test PASS |
| Recognition evidence | development data from one person; one held-out look (finger 5/5, whole hand 5/16) |
| Director validation | **pending** (`docs/milestones/BRIEF_006_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Camera ownership, frame scheduling | unchanged; webcam delivers 30 fps only (60 requested: 30 measured); delivery jitter sd 5 ms measured, not causal | camera timing measurement, replay with sample-grid timestamps |
| Motion analysis / landmark stability | duplicate detections ignored (age < 0.3 s, overlapping); no motion measured across gaps; jump limits | `test_gesture_duplicate_hand_cancels_fast_swipe.py`, `test_unified_motion.py` |
| Hand-shape transitions | only the onset shape counts on the whole-hand path; pointing hands unchanged | `test_hand_shape_change_during_the_movement_does_not_cancel_it` |
| Gesture lifecycle | one event per physical swipe across detectors; return scenarios unchanged | `test_return_scenarios.py`, unified-motion tests |
| Static gestures | half-heart and stop excluded from whole-hand onset (release is not a swipe); mappings unchanged | `test_lowering_the_hand_after_a_half_heart_is_not_a_swipe` |
| Calibration migration | settings v5: 0.5 styles -> any hand shape once, with a notice; open-palm experiment off; v0.4 repair kept | `test_settings_store.py` |
| Browser actions | unchanged path; live 3/3 (next 278-623 ms, previous 234-242 ms, like refused signed out) | `tests/live` |
| Co-op Lite | Guest sends actions; same engine on each computer; restrictions unchanged | co-op tests |
| Emergency disable, Developer / Broadcast / Background modes | unchanged code paths; covered by the existing UI tests | integration suite |
| Optional model scheduling | hand-only latency 9.7 ms, with segmentation + face 11.0 ms (p95 17.8), 30 fps both | `benchmark_pipeline.py` (no hand in view) |
| Statistics accounting | rejections stored (rate-limited) as in 0.5; tracking quality added to the export | `test_tracking_quality.py`, diagnostics tests |
| Thread synchronization | engine counters are written by the processing thread only and read for the export (plain ints and a bounded deque; a torn read affects only the exported numbers) | code review |
| Resource cleanup | no worker threads after close, memory 381 -> 375 MB in 6 min, 2/2 camera restarts, shutdown 0.28 s | `reports/stability_brief006.json` (local) |
| Packaging | 0.6.0b1 built; self-test PASS in a fresh data folder | `docs/RELEASE.md` |

## Defects found and fixed

| Defect | Severity | Test |
|---|---|---|
| Duplicate hand detections cancelled fast swipes (phase lock in the Director's downward swipes) | High | `test_gesture_duplicate_hand_cancels_fast_swipe.py` |
| A hand lost and re-acquired elsewhere could be read as a swipe | Medium | `test_hand_lost_at_rest_and_found_elsewhere_is_not_a_swipe` |
| (Before commit) whole-hand path confirmed a hand being lowered out of view | High | `test_gesture_hand_lowered_out_of_view.py` (existing regression test caught it) |
| (Before commit) tracking-jump check referenced a helper before its definition (NameError on the first real jump) | High | caught by lint; check moved |

## Qt stalls

Two in the 6-minute session: 524 ms during `window.show()` before the measured session, and
185 ms during a scripted resize with the capture and processing threads also paused (124 ms) -
a machine-wide pause, not UI work. Status: Low, instrumented.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | All recognition numbers are one person's development data; no independent data remains |
| High | Whole-hand swipes: 33/44 development, 5/16 held-out; rhythmic swipes without a pause and the preparation raise before a downward whole-hand swipe |
| Medium | Ordinary activity: 11 false events in 249 s with any hand shape (6 with pointing finger only) |
| Medium | Below ~20 fps or with frame loss, wrong-direction events for missed upward flicks (synthetic) |
| Medium | Stop pose at arm's length; YouTube markup changes |
| Low | Rare Qt stalls; unsigned build |
