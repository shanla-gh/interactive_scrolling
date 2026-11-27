# Integration Audit 007 (motion-first gestures, Brief 005)

Date: 2026-11-27. Scope: the whole application after the shared motion engine, fist swipes,
per-direction calibration, motion visualization and stored rejections.

| Verdict | |
|---|---|
| Technical verification | **passed**: 650 tests, hardware 5/5, live website 3/3 runs, 6-minute GUI session, packaged build self-test |
| Recognition evidence | finger: 16/16 real (development data); fist: semi-synthetic only |
| Director validation | **pending** (`docs/milestones/BRIEF_005_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Motion analysis | detectors read positions and velocities already produced by the motion analyzer (fingertip and palm centre); no second analyzer in the processing loop; time-based windows | code review; recognition cost 0.144-0.149 ms per frame |
| Hand-pose gating | finger: pointing at threshold or held before; fist: still fist before; palm: off; half-heart is not a fist (test) | `test_motion_detectors.py`, `test_gesture_engine.py` |
| Detector conflicts | one event per frame; the confirming detector blocks the others and they adopt its swipe; a pointing swipe followed by a fist return gives one event | `test_one_physical_swipe_gives_one_event_and_its_return_is_suppressed_everywhere` |
| Temporal state machines | return scenarios incl. deliberate reversals and repeats; the fist-return defect (M3b) found and fixed here | `test_return_scenarios.py` |
| Adaptive sensitivity | calibration bounded (+15 % max raise, speed never raised, 0.5-1.4, fist 0.3-0.8); no continuous learning | `test_calibration.py`, regression test for the 0.4 defect |
| Calibration | finger and fist methods; per-direction; cross-session simulation 8/8 both ways | `simulate_calibration.py` |
| Configuration migration | settings v4: 0.4 profiles that raised thresholds are capped once with a notice; control style and palm choice survive named presets | `test_settings_store.py` |
| Browser dispatch | unchanged path; all detectors' events go through the same dispatcher; boundary refusals explained | dispatcher, bridge, fixture and live tests |
| Co-op routing | Guest requests carry actions, not detector events; a Guest computer runs the same engine (incl. fist if chosen); guest restrictions unchanged | `test_coop.py`, `test_coop_ui.py` |
| Emergency disable | independent of detectors; Practice switches fist detection on only while open and restores the saved settings | dialog tests |
| UI visualization | motion overlay from `GestureFrame.motion` (measured); state line moved clear of the source chip | screenshot check, UI tests |
| Thread synchronization | stored rejections use the non-blocking analytics queue with a rate limit; Practice settings changes go through `request_settings` | code review, tests |
| Performance | 30.1 fps, 14.0 ms latency, CPU 4.3 %, memory 383 -> 365 MB, 2/2 restarts, shutdown 0.28 s | `reports/stability_brief005.json` (local) |
| Resource cleanup | no worker threads after close | stability session |
| Packaging | rebuilt 0.5.0b1; self-test PASS in a fresh data folder | `docs/RELEASE.md` |

## Defects found and fixed in this brief

| Defect | Severity | Test |
|---|---|---|
| Calibration raised the distance (to 1.34) and speed for users who pause before returning | High | `test_calibration_slow_return_raised_distance.py`, migration test |
| Missed attempts invisible afterwards | Medium | `test_meaningful_rejections_are_stored_for_later_analysis` |
| Hand lowered out of view read as a downward swipe | Medium | `test_gesture_hand_lowered_out_of_view.py` |
| Boundary refusals looked like recognition failures | Medium | `test_outcome_banner.py` |
| (Before release) fist return remembered as a stroke | High | `test_return_scenarios.py` |
| (Before release) calibration with returns as floors made small flicks fail | High | cross-session simulation; `test_returns_do_not_raise_the_distance_but_opposite_wind_ups_do` |
| (Before release) control style reset by a named preset | Medium | `test_control_style_survives_a_named_preset` |

## Qt stalls

No UI stall in the 6-minute session (Brief 004 sessions: one or two per session inside Qt's
event loop). Not reproducible on demand; instrumentation unchanged. Status: Low.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | Fist control unvalidated on real hands; finger results are development data from one person |
| Medium | Finger curl flicks downwards wait for the finger to recover (by design; hand or wrist movement is immediate) |
| Medium | Hybrid style: 2 fist events while thumbs-ups were lowered in the recordings |
| Medium | Stop pose at arm's length (detection) |
| Medium | YouTube markup changes |
| Low | Rare Qt stalls |
