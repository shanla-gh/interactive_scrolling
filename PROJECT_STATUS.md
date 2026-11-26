# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.2.0.dev0 (development build, not released) |
| Active work | M2 + M3 awaiting Director verification; next: M4 (requires a new brief) |
| Last updated | 2026-11-26 |

## Milestones

| Milestone | Status | Evidence |
|---|---|---|
| M0 Project Foundation | COMPLETED | [M0 report](docs/milestones/M0_PROJECT_FOUNDATION.md) |
| M1 Computer Vision & Live Visualization | COMPLETED (Director verified) | [M1 report](docs/milestones/M1_COMPUTER_VISION.md), [verification](docs/milestones/M1_DIRECTOR_VERIFICATION.md) |
| Integration Audit 001 | PASSED | [audit](docs/audits/INTEGRATION_AUDIT_001.md) |
| M2 Gesture Recognition Engine | IN_PROGRESS: technical verification passed, Director sign-off pending | [M2 report](docs/milestones/M2_GESTURE_RECOGNITION.md) |
| M3 YouTube Shorts Integration | IN_PROGRESS: technical verification passed, Director live verification pending | [M3 report](docs/milestones/M3_YOUTUBE_INTEGRATION.md) |
| Integration Audit 002 | Technical PASS; Director verification pending (not a full pass) | [audit](docs/audits/INTEGRATION_AUDIT_002.md) |
| M4 - M6 | NOT_STARTED | [ROADMAP.md](ROADMAP.md) |

All M2 and M3 checkpoints are implemented and verified with automated, hardware, browser-fixture
and (partly) live-website tests. What remains is human verification: performing the gestures in
front of the webcam and controlling YouTube Shorts in the Director's own browser and account,
following [M2_M3_DIRECTOR_CHECKLIST.md](docs/milestones/M2_M3_DIRECTOR_CHECKLIST.md).

### Director verification

* M1: recorded in [M1_DIRECTOR_VERIFICATION.md](docs/milestones/M1_DIRECTOR_VERIFICATION.md).
* M2/M3: the Director performed two guided calibration recordings (poses, swipes, sweeps,
  natural movement) used to design and tune the recognizers. The live checklist has not been
  performed yet.

## Test results (2026-11-26)

| Command | Result |
|---|---|
| `ruff format --check src tests scripts` / `ruff check ...` | clean |
| `pytest --hardware` | 393 passed, 1 skipped (opt-in live website test) |
| `pytest` (CI equivalent) | 388 passed, 6 skipped (5 webcam, 1 live website, by design) |
| `pytest tests/live --live-youtube` | 1 full pass recorded; other runs affected by the automated browser (see M3 report) |
| GitHub Actions (Windows, incl. browser tests with Edge) | success on 7ac48ef |
| Gesture replay (`scripts/evaluate_gestures.py`, balanced) | pointing swipes 8/8, 0 false triggers in negative segments, sweeps 4/12 |

## Performance (Gesture test mode, 10 minutes, 1280x720)

Capture / processing / display 30.9 / 29.8 / 29.8 FPS; latency 13.2 ms mean, 16.4 ms p99;
inference 9.7 ms; gesture recognition 0.13 ms per frame with hands (replayed recordings);
CPU 3.5 %; RSS 357 -> 362 MB (no growth); 4/4 camera restarts; no errors; shutdown 0.29 s.
No hand was in view and other workloads ran concurrently (483 dropped frames, one 357 ms UI
stall). Baseline comparison: [Integration Audit 002](docs/audits/INTEGRATION_AUDIT_002.md).

## Architecture decisions

[DECISIONS.md](docs/architecture/DECISIONS.md): ADR-001 to ADR-010 (foundation and vision),
ADR-011 extension + loopback bridge, ADR-012 rule-based gestures calibrated on recordings,
ADR-013 finger swipe as moving pointing hand, ADR-014 safety-first dispatch, ADR-015 SQLite
analytics. Details: [GESTURES.md](docs/architecture/GESTURES.md),
[YOUTUBE_INTEGRATION.md](docs/architecture/YOUTUBE_INTEGRATION.md).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Physical gestures controlling the Director's real browser and account not yet verified |
| Medium | YouTube markup changes would make actions fail (reported honestly as failed/unknown) |
| Medium | Hand sweeps: low recall at the balanced preset; some face-touching movements look like sweeps (no action mapped yet) |
| Low | Calibration from one person, one camera; an open hand held still 0.8 s is a stop gesture |
| Low | Rare unexplained UI stalls (222 ms in M1, 357 ms under concurrent load) |
| Low | CI actions use the deprecated Node.js 20 runtime (warning only) |
| Low | MediaPipe native console warnings; first model load after reboot can take seconds |

## Commits for Engineering Brief 002

```
ce55224 docs: record director verification of vision milestone
b732f66 docs: refine approved product roadmap
e054f71 feat(gestures): analyze static hand poses from landmarks
45d5b05 feat(gestures): add temporal swipe and static pose recognition
d6753b7 build: add gesture recording and evaluation tools
4e7c4d7 feat(actions): add control modes and safe action dispatcher
ca5e9d4 feat(pipeline): run gesture recognition on the processing thread
d6fbe2d feat(storage): persist user settings locally
79b493f feat(browser): integrate YouTube Shorts through a companion extension
7e5362a feat(analytics): persist gesture and action events locally
f036902 feat(services): compose gesture control, browser bridge and analytics
8ece71a feat(ui): display live gesture recognition and control state
ca24ba4 fix(bridge): handle the expected socket error when the bridge stops
c1cbec9 ci: report failed tests as workflow annotations
cfd7ec3 test(browser): wait for extension APIs before configuring the worker
7ac48ef test(browser): wait for the new Short before sending the next command
b0bbaa8 fix: clean up failed settings writes and cap bridge connections
2e49a5e test: measure gesture recognition in the stability session
```

Followed by the documentation commit that adds this file. The shutdown fix itself landed in
f036902; ca24ba4 contains its regression test.

## Recommended next steps

1. Director: complete [M2_M3_DIRECTOR_CHECKLIST.md](docs/milestones/M2_M3_DIRECTOR_CHECKLIST.md)
   and report results; then M2 and M3 can be marked COMPLETED.
2. Co-Director: M4 brief (Windows integration, Academic Comeback / Relapse). Sweeps are already
   recognized and routed through the dispatcher; their recall should be revisited with more
   recordings before they switch applications.
