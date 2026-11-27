# Engineering Brief 004 - checkpoint report (beta stabilization)

Statuses follow `docs/ENGINEERING_CONVENTIONS.md`: COMPLETED only with evidence. Requirements
that need the Director's hands, a signed-in account or new recordings stay IN_PROGRESS or
BLOCKED. Measurements: [GESTURE_BENCHMARK_004.md](../benchmarks/GESTURE_BENCHMARK_004.md).

## Phase A - root causes

| CP | Status | Evidence / remaining |
|---|---|---|
| A1 Baseline | COMPLETED | HEAD 88255ac clean; 562 passed, 6 skipped; benchmark reproduced; the Director's statistics database analysed (benchmark section 1) |
| A2 Failure instrumentation | COMPLETED | `RejectCode` with measured/required values; `GestureDiagnostics` (tracked, candidates, confirmed, rejected by code, browser outcomes); "Copy diagnostics"; opt-in landmark recorder |
| A3 Coordinates and directions | COMPLETED | user-space directions verified on recorded sweeps (right sweeps measure right); preview mirroring display-only; mapping finger up -> next with migration and notice; UI says "Move finger up -> Next Short" |

## Phase B - engine

| CP | Status | Evidence / remaining |
|---|---|---|
| B1 Existing limitations | COMPLETED | measured: pose rule (down flicks), arming (horizontal inversion), small-hand 3D angles, detection at arm's length, scale swings; distance/speed sweeps |
| B2 Strategies A-D | COMPLETED (on available data) | A geometric (pose rule, scale, hybrid finger states - rejected), B temporal (arming, pending flick, stroke-end confirmation - rejected, pause rule - rejected), C personal calibration (cross-session 8/8 both ways), D nearest-neighbour classifier (rejected, 0/19 cross-session); iteration table |
| B3 Stabilization | COMPLETED | EMA 20/40/80 ms, none, One Euro compared (jitter, lag, recall); frame rates 30/15/10 fps and 10 % dropped frames; 40 ms kept; low-fps hint |
| B4 Scale and distance | COMPLETED (technical) | rotation-tolerant hand scale frozen during strokes; window stillness for small hands; "move closer" and "edge of picture" hints from measured size/position |

## Phase C - swipes

| CP | Status | Evidence / remaining |
|---|---|---|
| C1 Low-effort family | IN_PROGRESS - Director pending | finger flicks (down 1/4 -> 4/4) and hand/wrist swipes 4/4 + 4/4 on recordings; left/right: proxy 9/12 and synthetic only |
| C2 Directions separately | IN_PROGRESS - recordings required | up 8/8, down 8/8 reported separately; separate left/right distance available (calibration); no real horizontal index swipes exist |
| C3 Returns | COMPLETED (technical) | settle-based return kept; blocked strokes' returns suppressed; pause-anywhere rule measured and rejected; intentional reversal after a brief pause near the start tested (regression + evaluator `eval_up_then_down`) |
| C4 Responsiveness | COMPLETED | early confirmation (0 s waiting for pointing swipes); stroke-end confirmation +0.30 s rejected; flick waiting 0.3-0.56 s reported; processing 0.156 ms/frame |

## Phase D - half-heart and stop

| CP | Status | Evidence / remaining |
|---|---|---|
| D1 Half-heart | IN_PROGRESS - Director pending | tolerant rule (no extra false frames in 5,579 hand frames), plain-language checklist of unmet conditions, personal template, drawn guide; no real half-heart recording |
| D2 Timing | IN_PROGRESS - Director pending | 0.3-0.6 s holds: no false half-heart in the recordings; 0.5 s chosen; one event per hold, release required, progress shown |
| D3 Like action | IN_PROGRESS - signed-in test pending | the Director's only like was a correct "no Shorts tab" rejection; fixture: like, idempotent "already liked", signed-out refusal, correct Short; live signed-out refusal; no account actions performed |
| D4 Stop | IN_PROGRESS - Director pending | detection loss at arm's length measured (open palm visible ~0.5 s; one prompt never detected); stillness fixed for small hands; hint to move closer; shorter holds and image-space fingers rejected; default gesture unchanged |

## Phase E - calibration

| CP | Status | Evidence / remaining |
|---|---|---|
| E1 Quick Calibration | COMPLETED (technical) | six gestures x 3 demonstrations, either hand, per-gesture redo; integration test drives the full flow |
| E2 Quality validation | COMPLETED (technical) | measured feedback: hand not visible, too far, wrong direction (when no return follows), too short, diagonal, not pointing, pose not held |
| E3 Profiles | COMPLETED | Personal preset + calibration section (derived numbers only); restore standard; per-gesture reset via redo; one profile for both hands (hand recorded) |
| E4 Adaptive sensitivity | COMPLETED | bounded (0.5-1.4 distance, speed 1.2-2.5, duration only grows, tilt <= 70), explicit (applied only on "Use my profile"), reversible; no silent learning |

## Phase F - practice and feedback

| CP | Status | Evidence / remaining |
|---|---|---|
| F1 Practice Mode | COMPLETED (technical) | drawn guide, live skeleton, state, progress, result and reason per attempt; no browser action; Live control never restored silently |
| F2 Live feedback | COMPLETED | READY / POINTING / MOVEMENT DETECTED / ... state, gesture banner, final browser outcome banner, hints; technical text only in Developer Mode |
| F3 Trajectory | COMPLETED | existing fingertip trail and candidate progress bar; measured distance in explanations |
| F4 Simplified configuration | COMPLETED | Relaxed / Balanced / Precise with measured trade-offs, Personal, Custom; restore defaults |

## Phase G - browser

| CP | Status | Evidence / remaining |
|---|---|---|
| G1 64 % success | COMPLETED | 5 failures = previous at the first Short (live-site root cause), 4 rejections caused by those waits, 1 correct context rejection |
| G2 Navigation reliability | COMPLETED (fixture + live signed out) | first Short refused at once; transient states waited for; arriving-Short id; quick repeated gestures queued (one); live 12/12 |
| G3 Tab navigation | COMPLETED (fixture), Director pending | unchanged, fixture tests pass; recognizer not blocked by non-YouTube tabs (tab actions need only browser focus) |
| G4 End-to-end latency | COMPLETED (measured parts) | movement 0.25-0.33 s, processing 0.16 ms, waiting 0 / 0.3-0.56 s (flicks), browser 0.2-0.6 s (next after a navigation ~1 s incl. load), immediate gesture banner then verified outcome |

## Phase H - iteration

COMPLETED: 18 documented iterations and experiments with retained or rejected outcomes
(benchmark section 3). Further iteration requires real recordings.

## Phase I - benchmarks and targets

| CP | Status | Evidence / remaining |
|---|---|---|
| I1 Dataset | IN_PROGRESS | recorder session 4 (per hand, calibration separated from evaluation) and a negatives session; synthetic and proxy sets labeled as such; **real recordings needed** |
| I2 Recognition targets | NOT MET / NOT MEASURABLE | 95 % recall/precision per gesture with >= 30 attempts cannot be shown: vertical 16/16 (CI 81-100 %) on development data; left/right/heart/stop not measured |
| I3 UX targets | BLOCKED (Director) | subjective comfort needs the Director |
| I4 Browser targets | IN_PROGRESS | fixture and live (12/12) without failures; 99 % needs a larger live sample |
| I5 Performance | COMPLETED | see PROJECT_STATUS and Audit 006 |

## Phase J and Audit 006

J: all features preserved (full suite, UI and co-op tests; co-op guest uses the same dispatcher).
Audit 006: [INTEGRATION_AUDIT_006.md](../audits/INTEGRATION_AUDIT_006.md).
