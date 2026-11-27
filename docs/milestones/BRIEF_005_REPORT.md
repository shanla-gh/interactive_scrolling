# Engineering Brief 005 - checkpoint report (motion-first gestures)

Statuses follow `docs/ENGINEERING_CONVENTIONS.md`. Evidence:
[GESTURE_BENCHMARK_005.md](../benchmarks/GESTURE_BENCHMARK_005.md). Evidence classes: real,
real use (the Director's statistics), semi-synthetic, synthetic.

| CP | Status | Evidence / remaining |
|---|---|---|
| Baseline | COMPLETED | cb30b37: 615 passed; benchmark reproduced; Director's database and settings analysed (calibration 1.34 / 2.5; 7 of 13 live downward swipes were first-Short refusals) |
| 12.1 Multi-landmark analysis | COMPLETED | fingertip, fingertip-relative-to-palm, palm centre, wrist and flexion change per stroke group (`analyze_motion_references.py`); a downward flick equals the return of an upward flick |
| 12.2 Motion segmentation | COMPLETED (technical) | shared lifecycle (rest, onset, commitment, confirmation, recovery, return phase, rearming); time-based; leaving-the-picture phase |
| 12.3 Directional scoring | COMPLETED | documented in GESTURES.md (heuristic, not a probability); direction-specific thresholds evaluated (smaller down distance rejected) |
| 13.1 Index-finger motion | IN_PROGRESS - Director pending | hand/wrist strokes confirmed at once when the palm moves with the finger; curl flicks wait for recovery; 16/16 real |
| 13.2 Closed-fist motion | IN_PROGRESS - real recordings required | four directions, either hand, palm-centre reference, still-fist activation, stationary fist and open/close tested; semi-synthetic 18/20; no real fist recording |
| 13.3 Palm experiment | COMPLETED (rejected) | real sweeps 0/12 with 7 opposite events; off by default; stop pose unaffected |
| 13.4 Hybrid | COMPLETED (technical), default pending data | finger / finger-or-fist / fist; one event per physical gesture; default finger because fist is unvalidated (+2 false events in real negatives, both while lowering thumbs-ups) |
| 14.1 Downward asymmetry | COMPLETED | causes: calibration defect (confirmed), boundary refusals (confirmed), flick/return identity (measured); tracking, normalization and direction commitment not implicated in the data |
| 14.2 Downward experiments A-H | COMPLETED | A global tip (baseline), B relative tip and C flexion (same signature as returns), D/F palm/fist (fist detector), E combined (palm-share path), G direction-specific (rejected), H trajectory matching not justified with the data; benchmark section 3 |
| 14.3 Comfortable thresholds | COMPLETED (on available data) | 0.4/0.5/0.6/0.7 down, 0.4/0.6 shared (0.15/0.25 below the safe range): smaller values break upward flicks; calibration personalizes within 0.5-1.4 |
| 14.4 Natural return | COMPLETED (synthetic + real) | scenario tests: up-return-up, down-return-down, deliberate reversals after a pause, rapid repeats, slow swipes, hand lowered out of view |
| 15.1 Extended calibration | COMPLETED (technical) | finger or fist method, single-gesture redo |
| 15.2 Direction-specific personalization | COMPLETED | per-direction distances; cross-session simulation 8/8 both ways; bounded; reversible |
| 15.3 Dynamic thresholds | COMPLETED (bounded) | hand scale and frame-rate hints, calibration bounds; no continuous learning |
| 16.1 Motion vectors | COMPLETED | measured stroke overlay with detector and phase |
| 16.2 Diagnostics | COMPLETED | stored rejections, new codes (not activated), boundary feedback |
| 16.3 Practice | COMPLETED (technical) | method choice, detector shown, never executes browser actions |
| 17.1 Half-heart | IN_PROGRESS - Director pending | unchanged recognizer; 2 confirmed in real Practice use; not confused with fist (test) |
| 17.2 Stop | IN_PROGRESS | real use: 4 confirmed incl. 2 live toggles at a normal distance; arm's-length recordings still 0/3 (detection) |
| 18 Continuous experimentation | COMPLETED (on available data) | 14 rows in the benchmark history, including rejected strategies, one defect found by the new scenario tests (M3b) and one regression found by the calibration simulation (C1) |
| Recognition targets (95 %) | NOT MEASURABLE | no representative labeled recording of the new controls |
| Audit 007 | see [INTEGRATION_AUDIT_007.md](../audits/INTEGRATION_AUDIT_007.md) | |
