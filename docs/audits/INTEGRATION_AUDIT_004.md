# Integration Audit 004 (after M5 and M6: UI, browser, analytics)

Date: 2026-11-26. Scope: all modules together, with focus on the three UI modes, shared camera
ownership, transparency, focus behaviour, browser context safety, reporting and privacy.

**Technical verification: PASSED.** **Director verification: PENDING** (visual quality,
OBS capture, real browser; checklist sections 2-4).

| Area | Check | Evidence |
|---|---|---|
| Shared runtime | one camera, dispatcher, engine and session across mode switches; no extra threads | `test_mode_switches_share_one_runtime` |
| Emergency disable | works while only the overlay is visible | `test_emergency_disable_works_while_in_creator_mode`; tray menu action wired to the same handler |
| Overlay focus | `Tool` + `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating` + `WS_EX_NOACTIVATE` | `test_overlay_window_is_frameless_on_top_and_never_takes_focus`; real behaviour in the checklist |
| Transparency safety | segmentation never runs while disabled or hidden; worker sees read-only frames; tracker frames unmodified; stale or missing mask hides the camera | `test_segmentation_runs_only_while_the_transparent_overlay_is_shown`, `test_hand_tracker_receives_unmodified_frames_with_transparency_on`, `test_transparent_overlay_removes_background_and_hides_camera_without_mask` |
| Capture | desktop composition and PrintWindow checked with `scripts/verify_overlay_capture.py` (results in Audit 005); OBS methods in the checklist | |
| Browser context | Shorts actions still need a visible Shorts tab; tab actions need OS focus; unchanged safety boundaries | bridge and fixture-browser tests |
| Session accounting | active definition, gaps, restarts, crash (heartbeat), midnight split | `tests/unit/test_wellbeing.py`, `test_services_wellbeing.py` |
| Report correctness | daily counts separate gestures from confirmed actions; success rate over dispatched actions | `test_daily_report_from_recorded_activity`, `test_performance_report_uses_dispatched_actions_as_denominator` |
| Anti-Doomscroll | off by default; pause affects only next/previous; reversible; ends with the session | wellbeing tests |
| Database consistency | unique event ids; new tables created idempotently on existing 0.2 databases; fresh store reads as empty | analytics tests, regression A3-5 |
| Privacy | no URLs/titles/ids stored; analytics opt-out records nothing; delete removes events and eye totals | analytics tests |
| UI work off the UI thread | daily report and performance report computed on the activity thread; the UI only displays cached objects | `ui/main_window.py` (no SQLite on the UI thread any more) |
| Resource cleanup | close: overlay, tray, workers, pipeline, co-op, activity, analytics | stability sessions: 0.28 s, no worker threads left |

Findings in this phase: A3-5 (fresh database error, fixed), and a wrong assumption in my own
new code caught by an existing test (OSError when the data folder cannot be created, fixed
before commit). No critical or high-severity defects open.
