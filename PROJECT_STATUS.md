# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.3.0rc1 - release candidate, **not released** (no tag) |
| Active work | Engineering Brief 003 implemented; **Director acceptance pending** |
| Release decision | PARTIALLY READY - specific blockers remain (Director acceptance, see below) |
| Last updated | 2026-11-26 |

## Milestones

| Milestone | Status | Evidence |
|---|---|---|
| M0 Project Foundation | COMPLETED | [M0](docs/milestones/M0_PROJECT_FOUNDATION.md) |
| M1 Computer Vision | COMPLETED (Director verified) | [M1](docs/milestones/M1_COMPUTER_VISION.md) |
| M2 Gesture Recognition | technical pass; Director pending; gestures partly superseded by M4 | [M2](docs/milestones/M2_GESTURE_RECOGNITION.md) |
| M3 YouTube Shorts | technical pass; Director pending | [M3](docs/milestones/M3_YOUTUBE_INTEGRATION.md) |
| M4 Gestures and tab control | implemented; technical pass; Director pending | [Brief 003 report](docs/milestones/BRIEF_003_REPORT.md), [GESTURES](docs/architecture/GESTURES.md) |
| Integration Audit 003 | technical PASS; Director pending | [Audit 003](docs/audits/INTEGRATION_AUDIT_003.md) |
| M5 Three UI modes | implemented; technical pass; Director pending (visuals, OBS, tray) | [UI and effects](docs/architecture/UI_AND_EFFECTS.md) |
| M6 Anti-Doomscroll and reports | COMPLETED (optional grayscale/delays not built) | [REPORTING](docs/architecture/REPORTING.md) |
| Integration Audit 004 | technical PASS; Director pending | [Audit 004](docs/audits/INTEGRATION_AUDIT_004.md) |
| M7 Clown Transformation | implemented; Director pending (live alignment) | [UI and effects](docs/architecture/UI_AND_EFFECTS.md) |
| M8 Passive eye analytics | implemented; Director pending (plausibility) | [UI and effects](docs/architecture/UI_AND_EFFECTS.md) |
| M9 Doomscroll Wrapped | COMPLETED | Brief 003 report |
| M10 Co-op | implemented; loopback verified; **BLOCKED** on a two-computer test | [COOP](docs/architecture/COOP.md) |
| Integration Audit 005 | technical PASS; not a full pass (Director acceptance pending) | [Audit 005](docs/audits/INTEGRATION_AUDIT_005.md) |
| M11 Packaging / RC | build and clean-folder validation done; second clean PC pending | [RELEASE](docs/RELEASE.md) |

Every checkpoint with its evidence: [docs/milestones/BRIEF_003_REPORT.md](docs/milestones/BRIEF_003_REPORT.md).

## Director acceptance

Nothing in Briefs 002 and 003 has been verified by the Director yet (M1 was). The single
consolidated checklist is
[DIRECTOR_ACCEPTANCE_CHECKLIST.md](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md)
(~60-75 min; co-op needs two computers, liking needs a signed-in account, one item needs OBS).

## Test results (2026-11-26)

| Command | Result |
|---|---|
| `ruff format --check src tests scripts` / `ruff check src tests scripts` | clean |
| `pytest --hardware` | 567 passed, 1 skipped (opt-in live test) - baseline 392 passed, 1 skipped, 1 flaky failure |
| `pytest tests/live --live-youtube` | 1 passed |
| Gesture replay (`scripts/evaluate_gestures.py`) | pointing swipes 8/8 at low/balanced/high and mirrored; 0 false triggers in 190 s of negatives; stop pose 0/3 in prompt windows (tracking at arm's length); left/right and half-heart: no recordings |
| Packaged build `--self-test` in a clean folder with fresh user data | PASS |
| GitHub Actions (Windows) | success on de6ddb1 (M4-M8); later runs: see the repository's Actions page |

## Performance (development machine, 1280x720)

Hand tracking only: 30.0 FPS processing, 12.7 ms mean latency, 2.9 % CPU, 251 MB. All optional
models (segmentation + face): 29.5 FPS, 15.3 ms, 3.6 %, 303 MB; segmentation 3.4 ms, face
7.1 ms per inference at ~13/s. 10-minute GUI sessions: 29.6-30.0 FPS, no memory growth, 4/4
camera restarts, shutdown 0.28 s. Details: [Audit 005](docs/audits/INTEGRATION_AUDIT_005.md).

## Architecture decisions

ADR-001..015 as before; ADR-016 four-direction recognizer and settle-based returns, ADR-017
half-heart geometry, ADR-018 focus-gated tab navigation, ADR-019 optional models as read-only
frame taps, ADR-020 hide the camera without a fresh mask, ADR-021 procedural clown and coarse
eye states, ADR-022 co-op as signed control events ([DECISIONS.md](docs/architecture/DECISIONS.md)).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Left/right swipes, half-heart, visual effects, OBS capture, co-op on two PCs, signed-in liking not verified by a person |
| Medium | A fast preparation movement made while already pointing can be read as the opposite swipe (back-and-forth ambiguity; GESTURES.md) |
| Medium | Stop pose unreliable with the open hand far from the camera |
| Medium | YouTube markup changes would make Shorts actions fail (reported as failed/unknown) |
| Medium | Transparent background quality depends on lighting and clothing; OBS BitBlt window capture shows black instead of transparency (use Display Capture or test WGC) |
| Low | Rare UI stalls inside Qt's event loop (instrumented, attribution logged; gesture control unaffected) |
| Low | Packaged build unsigned (SmartScreen warning), validated on one machine |
| Low | MediaPipe native console warnings; first model load after a reboot can take seconds |

## Commits for Engineering Brief 003

```
a52ce60 test(browser): wait for the reconnect attempt instead of a fixed delay
8afe6cc docs: migrate the roadmap to the revised product scope
6720e83 test(ui): wait for the queued tracker-state update before reading the panel
6c615fd feat(gestures): unify index-finger swipes in four directions and add the half-heart
975bf2e feat(browser): navigate between tabs of the active browser window
347bd7f build: benchmark the Brief 003 gestures on recordings
0c30272 docs: document the Brief 003 gestures, tab navigation and benchmark
8259c4f perf(diagnostics): stop enumerating all system threads on the UI thread
badd8fa feat(diagnostics): detect and attribute UI stalls
d46cf21 feat(vision): add optional local segmentation and face landmark models
8fcb9a2 feat(wellbeing): account scrolling sessions and add daily reports
de6ddb1 feat(ui): add Content Creator, Background Mode, reports and face effects
d082675 feat(ui): export Doomscroll Wrapped as a 1080x1920 PNG
887b6b8 feat(coop): add a minimal two-person co-op session
543be53 build: package a one-folder Windows release candidate
ac1f59f test: benchmark optional models and check overlay capture paths
```

Followed by the documentation commit that adds this file.

## Recommended next steps

1. Director: run the consolidated checklist; record session 3 with each hand
   (`scripts\record_gestures.py --session 3`) and send the evaluation table.
2. Tune left/right swipes and the half-heart from those recordings; then decide on 1.0.
3. If OBS Window Capture (WGC) does not keep transparency, document Display Capture + crop as
   the supported setup.
