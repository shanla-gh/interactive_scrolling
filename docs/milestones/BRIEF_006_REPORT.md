# Engineering Brief 006 - checkpoint report (pose-independent motion)

Statuses follow `docs/ENGINEERING_CONVENTIONS.md`. Evidence:
[GESTURE_BENCHMARK_006.md](../benchmarks/GESTURE_BENCHMARK_006.md).

| CP | Status | Evidence / remaining |
|---|---|---|
| 2.1 Baseline | COMPLETED | 77b1782: 650 passed, 6 skipped; session-5 recordings evaluated (finger down 5/10, 7 wrong-direction); Director's real-use database read (copy) |
| 2.2 Failed tests | COMPLETED | see section "Failed tests" below; no unresolved failure; 5 repeated full runs green |
| 19.1 Reduce pose dependence | COMPLETED (technical) | any hand shape default; pose only at the onset (reference selection, static-gesture exclusion); "pointing finger only" kept |
| 19.2 Multi-landmark representation | COMPLETED | fingertip (articulation) vs palm centre (translation) chosen by onset geometry; tracking-jump and gap rules; plain averaging of all landmarks not used (finger articulation would cancel palm motion) |
| 19.3 Trajectory tracking | COMPLETED | timestamped positions, no interpolation across gaps; trajectory drawn in the overlay |
| 19.4 Direction estimation | COMPLETED | unchanged method (dominant axis, ratio 1.8 = 29 deg; diagonals rejected); 34 deg evaluated and rejected |
| 20.1 Why fast gestures disappear | COMPLETED | duplicate detections (confirmed, fixed); timing jitter measured (not causal); 30 fps camera limit |
| 20.2 Multi-timescale | COMPLETED (analysis) | early confirmation already decides fast flicks in 3-6 frames; slow swipes up to ~1.2 s recognized; no further windows justified |
| 20.3 Fast-motion detector | COMPLETED (rejected) | no undersampled fast swipe found once duplicates were handled |
| 20.4 Scheduling / camera | COMPLETED | 60 fps not delivered; sample-time timestamps evaluated (no gain) |
| 20.5 Optical flow | COMPLETED (not adopted) | no landmark gap it would bridge in the data |
| 21.1-21.2 Scaling / thresholds | COMPLETED (bounded) | stable hand scale unchanged; distance sweeps on the whole-hand path recorded |
| 21.3 Continuous adaptation | NOT ADOPTED | no labelled data source in normal use; no learning from unlabelled movements |
| 21.4 Calibration safety | COMPLETED | whole-hand calibration for any shape; cross-hand comparison default = personal |
| 22.1-22.2 Lifecycle, consecutive gestures | COMPLETED (technical) | shared lifecycle; return tests; chained rearming evaluated and rejected |
| 22.3 Downward priority | IN_PROGRESS - Director pending | finger down 18/18 real; whole-hand down 3/8 (preparation raise) |
| 23 Static gestures, browser | COMPLETED (technical) | mappings unchanged; static gestures excluded from whole-hand onset; live test 3/3 |
| 24 Visualization, diagnostics | COMPLETED | trajectory, tracking-quality export, any-shape Practice |
| 25 Iterative optimization | COMPLETED (on available data) | 14 rows incl. 6 rejected; one held-out look |
| Targets (95 %) | NOT MET / NOT MEASURABLE | one person, development data |
| Audit 008 | see [INTEGRATION_AUDIT_008.md](../audits/INTEGRATION_AUDIT_008.md) | |

## Failed tests (CP 2.2)

GitHub Actions, all runs of the repository (32 before this brief): three failed, none open.

| Run / commit | Failed test(s) | Message | Cause | Production defect? | Resolution |
|---|---|---|---|---|---|
| ca24ba4 (2026-11-26) | not recorded (the annotation step did not exist yet) | - | most likely the same browser-test setup race as the next row (same day, same suite) - **not provable** | unknown | annotation reporting added in c1cbec9 |
| c1cbec9 (2026-11-26) | 10 tests in `tests/browser/test_extension_end_to_end.py` | `ReferenceError: chrome is not defined` on setup | the extension's service-worker target appeared before its APIs were bound | no (test harness) | cfd7ec3: wait for the extension APIs; green since |
| f4a8a31 (2026-11-27) | lint step | ruff on an experiment script | formatting | no | fixed in the next commit |

Brief 005 development run (local, before the commits; from the session log):

| Test | Message | Cause | Production defect? | Resolution |
|---|---|---|---|---|
| `test_gesture_engine::test_half_heart_while_moving_is_rejected`, `test_rejections_report_measured_and_required_values`, `test_gesture_diagnostics` (2) | events / required 0.5 instead of 0.8 | the new fist detector was briefly the default and its predicate included the half-heart | yes (uncommitted code) | fist predicate = FIST label only; finger default restored |
| `test_closed_hand_moving_sideways_is_not_a_swipe` | a RIGHT event | fist detector accepted any closed hand | yes (uncommitted) | still-fist activation cue |
| `test_calibration::test_small_swipes_lower...`, `test_very_small_swipes_keep...` | `0.8 < 0.8` | tests read the shared distance after the per-direction change | no (test outdated) | tests read the effective per-direction distance |
| `test_motion_detectors` (overlay) | travel >= 0.8 expected | the trace disappears at confirmation | no (test wrong) | assertion 0.5-0.8 |
| `test_return_scenarios::test_fist_scenarios[up, return, up]`, `[down, return, down]` | one event instead of two | a fist swipe's own return was remembered as a stroke | **yes** | 0e3b787 |

The specific failure the Director saw cannot be identified from the available evidence. The
evaluation scripts also print lines starting with "FAIL" for recording segments (not tests),
which may look like test failures; this is a possibility, not a finding.

Brief 006 development: after the any-shape default, 15 tests failed; one was a real defect of
the new code (`test_pointing_hand_lowered_out_of_view_is_not_a_swipe`: the whole-hand path
confirmed before the bottom zone - fixed by confirming downward hand strokes when the hand
stops), the others encoded the 0.5 pose rules for pointing hands (fixed by keeping pointing
hands on the fingertip path - no test changed) or the 0.5 UI/settings (3 tests changed with the
acceptance condition, see commit bdaf899). A NameError in uncommitted code (a check calling a
helper before its definition) was caught by lint before any commit.

Final: see PROJECT_STATUS (test totals).
