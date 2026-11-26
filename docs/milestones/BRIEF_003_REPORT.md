# Engineering Brief 003 - milestone and checkpoint report

Statuses follow the conventions: COMPLETED only with evidence; requirements that need a person,
a second computer, OBS or a signed-in account are marked *Director pending* and the checkpoint
stays IN_PROGRESS (implementation complete, technical verification passed) or BLOCKED.

## Phase 0

| CP | Status | Evidence / remaining |
|---|---|---|
| 0.1 Codebase inspection | COMPLETED | HEAD c0f99d9, clean tree; baseline 392 passed, 1 skipped, **1 failed** (browser test timing race, fixed a52ce60) |
| 0.2 M2/M3 reconciliation | COMPLETED (technical) | replay reproduced 8/8 pointing swipes and 4/12 sweeps; the Director has **not** performed the M2/M3 checklist; its thumbs-up and sweep items are superseded, the rest is merged into the consolidated checklist |
| 0.3 Roadmap migration | COMPLETED | ROADMAP.md (8afe6cc): academic concepts removed, new scope documented |

## M4 Gesture refinement and browser tab control

| CP | Status | Evidence / remaining |
|---|---|---|
| 4.1 Four-direction engine | IN_PROGRESS - Director pending | one 2D recognizer, either hand, diagonals rejected, settle-based return phase; 70 engine tests; replay 8/8 vertical at all presets and mirrored, 0 false triggers in 190 s of negatives. Left/right not recorded on real hands |
| 4.2 Sensitivity and calibration | COMPLETED | presets, distance, speed, holds, cooldown, return window, control hand, per-gesture enable, any-gesture-to-any-action mapping, persisted; shared thresholds chosen (GESTURES.md) |
| 4.3 Half-heart | IN_PROGRESS - Director pending | geometric definition, both hands, hold 0.6 s, release required; confusions (pinch, C, thumbs up, pointing, fist) rejected in synthetic tests; 0 false half-hearts in all recorded negatives; no real half-heart recording yet |
| 4.4 Browser tab navigation | IN_PROGRESS - Director pending | real extension in headless Edge: right/left, no wrap at either end, back to Shorts, other window untouched; focus-gated; no new permissions. Real browser by the Director |
| 4.5 Gesture benchmark | COMPLETED (with stated limits) | per-category recall and false triggers with sample sizes (GESTURES.md); 4/12 sweep investigation done; replacement cannot be scored on sweep data; target >= 95 % not demonstrable without session-3 recordings |
| Audit 003 | PASSED (technical), Director pending | INTEGRATION_AUDIT_003.md: stall instrumentation, ~13 ms UI-thread block fixed, startup stall explained, rare runtime stalls narrowed (unresolved) |

## M5 Three UI modes

| CP | Status | Evidence / remaining |
|---|---|---|
| 5.1 Developer Mode | COMPLETED | dashboard kept and extended (Today, Browser, Co-op, Performance, View tabs; UI stall counter) |
| 5.2 Content Creator Mode | IN_PROGRESS - Director pending | overlay: move, resize, layers, opacity, feedback, counters, non-activating; capture: desktop composition OK, PrintWindow shows black, OBS WGC pending |
| 5.3 Transparent background | IN_PROGRESS - Director pending | local Selfie Segmenter, presentation only, read-only frames, safe fallback hides the camera; 3.4 ms/inference, -0.5 FPS; visual quality with a real person pending |
| 5.4 Background Mode | IN_PROGRESS - Director pending | tray with state colours, start/stop, disable, modes, quit; tray menu not testable on the offscreen test platform |
| 5.5 Visual customization | COMPLETED | Appearance dialog, persisted; renderer style tests |
| 5.6 Shared runtime | COMPLETED | `test_mode_switches_share_one_runtime` |

## M6 Anti-Doomscroll and daily reporting

| CP | Status | Evidence / remaining |
|---|---|---|
| 6.1 Session and event accounting | COMPLETED | definitions in REPORTING.md; restart, crash, midnight tests |
| 6.2 Daily Activity Report | COMPLETED | Today tab; gestures vs confirmed actions separated |
| 6.3 Gesture Performance Report | COMPLETED | Performance tab; denominator = dispatched actions |
| 6.4 Anti-Doomscroll controls | COMPLETED (grayscale and delays not implemented, optional) | limits, budget, Reality Checks, break suggestion, reversible pause |
| 6.5 Doomscroll Index | COMPLETED | formula documented; boundary and missing-data tests |
| Audit 004 | PASSED (technical), Director pending | INTEGRATION_AUDIT_004.md |

## M7 Progressive Clown Transformation

| CP | Status | Evidence / remaining |
|---|---|---|
| 7.1 Face landmark infrastructure | COMPLETED | Face Landmarker adapter, shared worker, runs only when needed |
| 7.2 Progressive AR effect | IN_PROGRESS - Director pending | three procedural stages from session time, configurable, preview, fade, follows landmarks; rendered on a real photo; live alignment and flicker need a person |
| 7.3 Performance and alignment | IN_PROGRESS - Director pending | face 7.3 ms/inference, latency +2.6 ms with all models; live alignment pending |

## M8 Passive eye analytics

| CP | Status | Evidence / remaining |
|---|---|---|
| 8.1 Eye and iris tracking | IN_PROGRESS - Director pending | screen / away / unknown, blinks, broad direction; synthetic tests; plausibility on a real person pending |
| 8.2 Calibration | IN_PROGRESS - Director pending | optional one-point calibration with quality check; benefit on real users not measured |
| 8.3 Visual Behavior Report | COMPLETED | consistent durations (unknown never counted as away) |
| 8.4 Privacy and performance | COMPLETED | daily totals only; no inference when both face features are off |

## M9 Doomscroll Wrapped

| CP | Status | Evidence |
|---|---|---|
| 9.1 Daily and session summaries | COMPLETED | real report / session counts |
| 9.2 Visual design | COMPLETED (Director taste pending) | rendered and inspected; layout tests |
| 9.3 Export | COMPLETED | 1080x1920 PNG, user-chosen path, no upload, no personal data |

## M10 Minimal Co-op Doomscroll

| CP | Status | Evidence / remaining |
|---|---|---|
| 10.1 Architecture | COMPLETED | COOP.md |
| 10.2 Private session connection | COMPLETED (loopback) | code, mutual HMAC, approval, lockout, signed sequenced messages |
| 10.3 Shared gesture execution | COMPLETED (loopback) | first accepted wins, cooldown, duplicates, stale, likes/tabs refused, emergency disable |
| 10.4 Co-op UI | COMPLETED | Co-op panel with attribution, outcomes, duration, counts, RTT |
| 10.5 Creator compatibility | COMPLETED | independent of the overlay; no frames transmitted |
| 10.6 Duo Wrapped | COMPLETED | Host-side session card |
| 10.7 Co-op verification | BLOCKED (two computers) | loopback and separate-process tests pass; a real two-device session is required |

## Integration Audit 005

Technical PASS, Director acceptance pending (INTEGRATION_AUDIT_005.md).

## M11 Packaging and release candidate

| CP | Status | Evidence / remaining |
|---|---|---|
| 11.1 Windows distribution | COMPLETED | PyInstaller one-folder build, 365 MB, no Python needed |
| 11.2 Setup experience | COMPLETED | README, RELEASE.md, packaged README, consolidated checklist (step-by-step for every feature) |
| 11.3 Clean-environment validation | IN_PROGRESS | clean folder + fresh user data on the development machine: self-test PASS (after fixing a packaging defect), GUI start and clean exit; a second clean computer pending |
| 11.4 Release candidate preparation | COMPLETED | 0.3.0rc1, changelog, no tag, nothing published |
