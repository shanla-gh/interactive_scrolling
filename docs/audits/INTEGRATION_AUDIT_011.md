# Integration Audit 011 (Motion Engine 2.0, real-time, passive eyes - Brief 009)

Date: 2026-11-28. Scope: the whole application after the downward-confirmation change, the
repaint fix, display smoothing, driver frame times, the eye and gaze overlay, the Wrapped eye
line and the new tools. The UI layout is unchanged.

| Verdict | |
|---|---|
| Technical verification | **passed with one open intermittent failure**: 773 tests passed, 0 failed, 6 skipped (webcam/live, run separately) in 2 of 3 final full runs; the third had 1 failure (`test_tab_navigation_leaves_and_returns_to_shorts`, browser fixture) that 13 further runs did not reproduce; CI then failed once in the same module ('no next Short available'); probable cause, fixed in 4c39040: the shared-browser helper accepted a stale report from the previous test's page (an earlier attempted fix that closed foreign tabs broke other tests and was reverted); hardware 5/5; packaged 0.9.0b1 self-test PASS; ruff clean |
| Recognition | gate: no regression in all five frozen configurations; mode consistency identical in 4 window configurations and 9 replay scenarios |
| Real YouTube | not re-run in this brief (no browser-path change); Brief 008: 19 of 20 |
| Not verified | Broadcast feel with a real person, gaze accuracy, recognition on independent data, two computers, higher camera frame rates (hardware limited to 30 fps) |
| Director validation | **pending** (`docs/milestones/BRIEF_009_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Camera acquisition, adaptive FPS, timestamps | modes probed; driver times mapped and recorded; recognition on arrival times | CAMERA.md, `test_camera.py` (DriverClock), hardware 5/5 |
| Motion reference, direction, fast, repeated, false positives | 9 candidates, 1 adopted | GESTURE_BENCHMARK_009.md, `test_gesture_down_near_bottom_waits.py`, existing regression tests (incl. hand lowered out of view) |
| Gesture arbitration, calibration | unchanged | existing tests |
| Normal / Broadcast / Background | identical recognition; latency ~10 ms median in all | `test_mode_consistency.py`, PERFORMANCE_009.md |
| Gesture-to-action latency | stage breakdown | PERFORMANCE_009.md |
| Browser focus, live preview | unchanged code paths | browser fixture tests |
| Eye landmarks, head pose, gaze vectors | estimate + overlay, quality gated, display only | `test_gaze.py`, synthetic renders |
| Passive gaze crosshair, heatmap | not implemented (no accuracy evidence) | EYE_TRACKING.md |
| Eye analytics, Wrapped | reviewed; optional eye line | `test_wrapped.py` |
| Clown, transparent background | unchanged; costs measured in replay | PERFORMANCE_009.md |
| Doomscroll Together | regression suites | `test_coop*.py` |
| Privacy | no gaze coordinates stored; tools save aggregates; recordings local | code review |
| Emergency disable | unchanged; independent of face/eye models | existing tests |
| Thread synchronization, shutdown | no new threads in the app; workers stop on close | endurance reports |
| Packaging | 0.9.0b1 built, self-test PASS in a fresh data folder | `docs/RELEASE.md` |

## Defects found and fixed

| Defect | Severity | Fix / test |
|---|---|---|
| Frames lost at the capture handoff on the real camera (up to 85/min, most in Broadcast with every model) | High (reliability) | two-frame bounded buffer; real-camera A/B 39.5 -> 0.0/min; `test_two_slot_mailbox_keeps_a_burst_and_stays_bounded` |
| Overlay and camera view repainted in a loop while feedback faded (73 overlay paints/s) | Medium (efficiency, Broadcast) | bounded fade timer; paint count halved |
| Downward swipes waited up to 0.5 s after the stroke | Medium (responsiveness) | frame-rate-aware slow-down rule; regression test |
| Candidate bottom zone 0.90 re-opened a known false swipe | caught before adoption | rejected; existing regression test |
| A commit went in with an unformatted file (exit code masked by a pipe) | Low (process) | follow-up style commit |
| An automatic "unsafe" lint fix broke array arithmetic in a new script | Low (process) | fixed by hand before commit |

## Development failures

* One full-suite failure in the very first baseline run could not be identified (the output
  kept only the summary line); 4 further baseline runs passed. In the final runs one browser
  fixture test failed once (tab navigation) and passed 13 times after; possibly the same
  intermittent failure. Open.
* The first mode benchmark omitted the application's power-throttling opt-out and showed a
  false Normal-vs-Broadcast difference (26 vs 11 ms); corrected and explained.
* Running a downloaded package was not attempted in this brief; all tools use existing
  dependencies.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | The Director's Broadcast complaint was not reproduced; no human session |
| High (verification) | No independent labelled recordings: recall/precision targets unmeasured |
| Medium | False positives unchanged (11 / 249 s any shape, 6 finger only) |
| Medium | Gaze estimate accuracy unknown; no calibration data |
| Medium | Rare UI stalls unexplained |
| Medium | Camera delivers bursts; recognition still uses arrival times |
| Low | Intermittent browser fixture failure: probable cause (stale context in a test helper) fixed in 4c39040, CI green; watch for recurrence |
| Medium | Stalls during the 30-minute live-preview session (likely the in-process test harness; not excluded for long sessions) |
