# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.1.0.dev0 (development build, not released) |
| Active milestone | M1 - awaiting owner visual sign-off; next: M2 (requires a new brief) |
| Last updated | 2026-11-26 |

## Milestones and checkpoints

| Checkpoint | Status | Evidence |
|---|---|---|
| M0 CP 0.1 Workspace and GitHub initialization | COMPLETED | [M0 report](docs/milestones/M0_PROJECT_FOUNDATION.md) |
| M0 CP 0.2 Technology stack and architecture | COMPLETED | ADR-001..010, architecture tests |
| M0 CP 0.3 Testing and development infrastructure | COMPLETED | local suite + CI run 45752920939 green |
| M0 CP 0.4 Persistent documentation | COMPLETED | this file, conventions, README, roadmap |
| **M0 Project Foundation** | **COMPLETED** | |
| M1 CP 1.1 Webcam acquisition | COMPLETED | hardware tests, failure-path tests |
| M1 CP 1.2 Hand tracking | COMPLETED | real-model tests, live detections |
| M1 CP 1.3 Skeleton and landmark visualization | COMPLETED (owner visual sign-off pending) | pixel-alignment tests, real-landmark screenshots |
| M1 CP 1.4 Motion and vector engine | COMPLETED | 37 motion tests, 87-88 px/s measured vs 86.7 px/s true |
| M1 CP 1.5 Desktop application | COMPLETED (owner visual sign-off pending) | UI tests, stability sessions |
| M1 CP 1.6 Stability and performance | COMPLETED | two 10-minute GUI sessions, benchmarks |
| **M1 Computer Vision & Live Visualization** | **BLOCKED** on the owner's visual confirmation ([checklist](docs/milestones/M1_MANUAL_VERIFICATION.md)) | [M1 report](docs/milestones/M1_COMPUTER_VISION.md) |
| **Integration Audit 001** | **PASSED** (automated and hardware scope); owner visual check open | [audit](docs/audits/INTEGRATION_AUDIT_001.md) |
| M2 - M6 | NOT_STARTED | [ROADMAP.md](ROADMAP.md) |

Why M1 is BLOCKED rather than COMPLETED: whether the skeleton visibly sits on the user's own
fingers, whether handedness labels match the user's hands, and whether arrows match
perceived movement can only be judged by a person in front of the camera. Everything that
can be measured has been verified (pixel-level alignment, real landmarks on a real photo,
live detections through the webcam, measured motion accuracy). Once the owner completes the
checklist, record the results below and set M1 to COMPLETED.

### Owner verification results

Not yet performed.

## Test results (2026-11-26, commit 09c8c5f)

| Command | Result |
|---|---|
| `python -m ruff format --check src tests scripts` | 60 files already formatted |
| `python -m ruff check src tests scripts` | All checks passed |
| `python -m pytest` | 202 passed, 5 skipped (hardware tests, by design) |
| `python -m pytest --hardware` | 207 passed, 0 skipped |
| GitHub Actions CI (Windows, run 45752920939) | success (format, lint, model download, tests) |

## Performance (development machine)

Windows 11, Intel Core i7-13700H, 15.6 GB RAM, built-in HP HD Camera, 1280x720.
Details: [M1 report](docs/milestones/M1_COMPUTER_VISION.md).

| Metric | Session 1 (before audit fixes D-1, D-5, D-9) | Session 2 (code of commit 833bd84) |
|---|---|---|
| Duration | 600.4 s | 600.7 s |
| Capture / processing / display FPS (mean) | 30.2 / 30.3 / 30.3 | 30.2 / 30.3 / 30.3 |
| Latency capture-to-result (mean / p99) | 15.5 / 21.9 ms | 16.2 / 23.3 ms |
| Inference (mean) | 14.9 ms | 15.4 ms |
| CPU (share of machine, mean) | 4.1 % | 4.9 % |
| RSS first / last minute | 365 / 336 MB | 368 / 342 MB |
| UI heartbeat lateness p99 / max | 14.3 / 222 ms | 12.5 / 39 ms |
| Camera restarts | 4/4 | 4/4 |
| Dropped frames | 5 | 9 |
| Warnings/errors | none | none |

Session 1 ran on the pre-commit working tree before audit fixes D-1, D-5 and D-9; session 2
ran on the code of commit 833bd84, i.e. after all audit fixes except D-6 and D-8 (statistics
reset after model load, label styling), which are covered by automated tests. Session 2 overlapped for about 10 s
with a UI screenshot run.

## Architecture decisions

See [docs/architecture/DECISIONS.md](docs/architecture/DECISIONS.md): Python 3.12 venv
(ADR-001), MediaPipe Tasks VIDEO mode (ADR-002), opencv-contrib 4.12 (ADR-003), two
threads + latest-frame mailbox (ADR-004), Qt Widgets + QPainter overlay (ADR-005),
framework-free core (ADR-006), pixel/palm-length motion units (ADR-007), Windows power
throttling opt-out (ADR-008), model downloaded not committed (ADR-009), user-initiated
camera scan (ADR-010).

## Known issues and limitations

| Severity | Issue |
|---|---|
| Medium | Owner visual sign-off of live overlay alignment pending (see above). |
| Low | Tested on one machine and one built-in camera; busy-camera and USB-disconnect paths tested only with simulated devices. |
| Low | One unexplained 222 ms UI stall in session 1 (none above 40 ms in session 2). |
| Low | MediaPipe prints native log lines and a "NORM_RECT without IMAGE_DIMENSIONS" warning to the console from inside its graph. |
| Low | First launch after a reboot can take several seconds to load the model (preview is live meanwhile). |
| Low | Cameras listed by index, not by name; settings are not persisted between sessions. |
| Info | Latency roughly doubles with `--allow-power-throttling` (Windows default behaviour). |

## Commits (M0, M1, Integration Audit 001)

```
713af8b chore: initialize project foundation
f05edbc feat(core): add high-resolution timing and latest-frame mailbox
d6a88b1 feat(vision): implement webcam acquisition
8daf536 feat(vision): integrate real-time hand landmark tracking
2dd4aa7 feat(motion): implement timestamped movement analysis
765c7e3 feat(core): add threaded vision pipeline and process diagnostics
0ea6e0c feat(ui): add live computer vision dashboard
63dfafd test: add regression tests for defects fixed during verification
59269a0 test: add webcam hardware tests and performance measurement tools
6c0b2f6 build: add Windows setup scripts and CI workflow
6be0b61 test(visualization): cover letterbox and mirror coordinate mapping
833bd84 build: normalize line endings with .gitattributes
9580829 fix(pipeline): restart latency statistics when the tracker becomes ready
09c8c5f fix(overlay): draw velocity labels on a background beyond the arrow head
```

Followed by the documentation commit that adds this file.

## Recommended next steps

1. Owner: run `scripts\run.ps1` and complete the
   [M1 manual verification checklist](docs/milestones/M1_MANUAL_VERIFICATION.md); record the
   results above and mark M1 COMPLETED (or report failures).
2. Co-Director: review Integration Audit 001 and prepare the M2 (Gesture Recognition Engine)
   brief. The motion engine already exposes per-hand fingertip/palm velocity, direction,
   window displacement and stationary state for swipe detection; thumbs-up will need static
   hand-shape features computed from the landmarks.
3. Consider in M2/M5: persisted settings, camera names, profiling of the rare UI stall.
