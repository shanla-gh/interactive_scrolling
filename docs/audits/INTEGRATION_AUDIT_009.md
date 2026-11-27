# Integration Audit 009 (product experience, Brief 007)

Date: 2026-11-27. Scope: the whole application after the UI wording and layout changes,
Broadcast Mode positioning and status, display smoothing, the transparent-background fill,
the first-use guide and the stability tooling. Gesture recognition is unchanged.

| Verdict | |
|---|---|
| Technical verification | **passed**: 699 tests (0 failed, 0 expected failures, 6 skipped = webcam/live, run separately), hardware 5/5, packaged self-test PASS, gesture regression gate "no regression" against all five frozen baselines, 4 automated endurance runs (55 min) without crash or leak |
| Real YouTube test | **intermittent**: 4 of 11 runs failed (fresh browser profile: consent redirect; "the active Short did not change"); the approved 0.6.0b1 code fails the same way (1 of 3) - an environment change on YouTube's side, not a regression; failures are reported as failed, never as success |
| Visual review | rendered screenshots at 1366x768 100 %, 1920x1080 125 % and 150 % (synthetic camera scene) |
| Director validation | **pending** (`docs/milestones/BRIEF_007_VALIDATION.md`) |

## Areas reviewed

| Area | Check | Evidence |
|---|---|---|
| Motion recognition baseline | engine unchanged; gate per row against v0.6.0b1 at 30 / 20 / 15 fps and 10 % loss, and finger-only | `docs/benchmarks/GESTURE_BENCHMARK_007.md` |
| False-positive behaviour | two candidates rejected by the gate; ordinary activity 11 (any shape) / 6 (finger only) in 249 s | same |
| Camera lifecycle | 8 automated stop/start cycles ok; camera-unavailable state shown in plain words | endurance runs, screenshot 10 |
| Calibration | unchanged; style not migrated (settings stay version 5) | settings tests |
| Browser integration and verification | unchanged code path; texts "Browser: ..." and "browser connection not available" | fixture tests, live runs |
| Developer Mode | header says CAMERA ON (not LIVE); five tabs fit at 150 %; status bar fits | screenshots |
| Broadcast Mode | control-state chip; counters/session timer filled; Position menu; off-screen recovery; display-only smoothing | `tests/integration/test_broadcast_mode.py`, screenshots 06-08 |
| Background Mode | tray: camera and gesture state, start/stop camera, stop gesture control, modes, quit; 5-min run | endurance run, screenshot 09 |
| Transparent segmentation | enclosed-hole fill (synthetic evaluation); privacy fallback unchanged (camera hidden without a fresh mask) | `tests/unit/test_compositing.py`, `scripts/experiment_mask_refinement.py` |
| Visual smoothing | display only; input landmarks unchanged | `test_display_smoothing_never_changes_the_input_used_for_recognition` |
| Overlay positioning, window focus | no-activate flags unchanged; positions clamped to screens | existing UI-mode tests, new tests |
| Multi-monitor | corners use the overlay's current screen; recovery when a screen is gone. **Not tested with a second physical monitor** | code + test with an off-screen position |
| OBS compatibility | desktop composition (Display Capture) shows the windows behind the transparent overlay; PrintWindow (like BitBlt Window Capture) shows black; OBS Windows-Graphics-Capture **not verified** (automated attempt hung OBS) | `docs/guides/BROADCAST_GUIDE.md` |
| Emergency disable | unchanged; works in Broadcast Mode (existing test); overlay chip follows | tests |
| Optional inference scheduling | segmentation only with the transparent overlay visible; face only with clown/eye analytics; verified every second during mode cycling | cycling run invariants |
| Co-op Lite | unchanged; regression tests pass (localhost only - no two-computer test) | `test_coop*.py` |
| Analytics and reporting | unchanged; counters read the existing daily report | tests |
| Configuration persistence | new fields (creator: control status, smoothing; appearance: guide shown) load with defaults from older files | settings tests |
| Packaging | 0.7.0b1 built; self-test PASS in a fresh data folder | `docs/RELEASE.md` |
| Shutdown and threads | no worker threads after close in all endurance runs | endurance reports |
| Performance | `docs/benchmarks/PERFORMANCE_007.md` | |

## Defects found and fixed in this brief

| Defect | Severity | Fix / test |
|---|---|---|
| Header showed "LIVE" when only the camera was on (confusable with Live control) | Medium | CAMERA ON; test updated |
| Checked mode button clipped at 125 % | Low | bold width reserved; `test_checked_mode_buttons_reserve_room_for_bold_text` |
| Side tabs hidden behind scroll arrows, status bar cut off at 150 % | Low | five tabs, shorter labels; screenshots |
| Gesture settings did not fit a 150 % laptop screen | Medium | advanced thresholds collapsed; screenshot |
| Broadcast "Today's counters" layer was never filled | Low | session timer and counters; test |
| A saved overlay position off every screen opened the overlay out of reach | Medium | clamped; test |
| Extension folder path wrapped mid-path in the Browser tab and the guide | Low | copy button; screenshots |
| Light clothing let the room show through in the transparent overlay (reported earlier) | Medium | enclosed-hole fill (synthetic evidence) |

## Development failures

* After renaming texts, 2 tests asserted old wording ("LIVE", "CAPTURE"/"PROCESSING"): updated to the new texts (intent unchanged).
* A new compositing test file was created without imports (lint caught it before running).
* Live YouTube: see the verdict table (environmental, pre-existing).
* The OBS automation script was stopped by an external timeout before its clean-up: OBS was left running with its websocket enabled. OBS was closed and its configuration restored from the backup (identical except one log file locked by the exiting process); **a Windows Firewall prompt for OBS Studio opened during the test and was left for the Director to answer**. The script was removed.

## Open risks

| Severity | Risk |
|---|---|
| High (verification) | No human-use validation of the new UI, Broadcast quality or transparency with a real person |
| Medium | Real YouTube navigation intermittently fails in fresh profiles (YouTube-side change) |
| Medium | Frames dropped while the main window is hidden (3 %), cause unknown |
| Medium | OBS Windows Graphics Capture unverified; second monitor untested; Chrome manual only |
| Medium | Accidental swipes with any hand shape; low-fps flick returns (unchanged) |
| Low | Rare Qt stalls (one 344 ms in 30 min) |
