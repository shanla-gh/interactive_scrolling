# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.4.0b1 - beta, **not released** (no tag) |
| Active work | Engineering Brief 004 (beta stabilization) implemented; **Director beta validation pending** |
| Engineering decision | PARTIALLY READY - REAL GESTURE DATA REQUIRED |
| Last updated | 2026-11-27 |

## Brief 004 in one paragraph

The Director's real test was analysed from the local statistics database and live-site probes.
All five failed actions were "previous" at the first Short (YouTube hides the button without
disabling it), four rejections came from those 3 s waits, and up was mapped to "previous"
although the Director moves the finger up for the next Short. Recognition had two measured
defects: downward finger flicks were rejected because the curling finger reads as a fist, and
horizontal movements came out in the opposite direction because of the arming rule. Both are
fixed, the browser path is reliable on the fixture and the live site, every rejection is now
explained with measured values, and Practice, Quick Calibration and a diagnostics export were
added. Left/right swipes, the half-heart and the stop pose at a normal distance have no real
recordings yet - that is the remaining blocker. Details:
[Brief 004 report](docs/milestones/BRIEF_004_REPORT.md),
[benchmark](docs/benchmarks/GESTURE_BENCHMARK_004.md),
[Audit 006](docs/audits/INTEGRATION_AUDIT_006.md),
[validation procedure](docs/milestones/BRIEF_004_VALIDATION.md).

## Milestones

| Milestone | Status | Evidence |
|---|---|---|
| M0 Project Foundation | COMPLETED | [M0](docs/milestones/M0_PROJECT_FOUNDATION.md) |
| M1 Computer Vision | COMPLETED (Director verified) | [M1](docs/milestones/M1_COMPUTER_VISION.md) |
| M2 Gesture Recognition | technical pass; superseded by M4 and Brief 004 | [M2](docs/milestones/M2_GESTURE_RECOGNITION.md) |
| M3 YouTube Shorts | technical pass; Director pending | [M3](docs/milestones/M3_YOUTUBE_INTEGRATION.md) |
| M4-M11 (Brief 003) | implemented; Director acceptance pending | [Brief 003 report](docs/milestones/BRIEF_003_REPORT.md) |
| Brief 004 beta stabilization | implemented; technical pass; Director validation and recordings pending | [Brief 004 report](docs/milestones/BRIEF_004_REPORT.md) |
| Integration Audit 006 | technical PASS; not a full pass | [Audit 006](docs/audits/INTEGRATION_AUDIT_006.md) |

## Recognition results (development data: two recorded sessions, one person)

| Gesture | Result | Source |
|---|---|---|
| Finger up | 8/8 (version 0.3: 8/8) | recorded: 4 flicks + 4 hand swipes |
| Finger down | 8/8 (version 0.3: 5/8) | recorded: 4 flicks + 4 hand swipes |
| Up + down, mirrored | 16/16 | simulated other hand |
| Right / left | proxy 9/12 (0.3: 0/12); semi-synthetic 6/8 | open-hand sweeps; rotated real swipes - not recall claims |
| Half-heart | not measured | synthetic hands only; 0 false half-hearts in all recordings |
| Stop | 0/3 (unchanged) | arm's length; detector loses the hand |
| False triggers | 2 in the replay (1 in 190 s of negatives; 0.3: 1 / 0) | |

## Test results (2026-11-27)

| Command | Result |
|---|---|
| `ruff format --check` / `ruff check` (src, tests, scripts) | clean |
| `pytest` | 615 passed, 6 skipped (hardware, live) - baseline 562 passed, 6 skipped |
| `pytest tests/hardware --hardware` | 5 passed |
| `pytest tests/live --live-youtube` | 3 of 4 runs passed; the fourth a correct refusal while Edge's own startup tab was in front |
| Fixture browser tests (real extension, headless Edge) | 16 passed, stable over 4 repetitions |
| GitHub Actions (Windows) | success on every pushed commit except f4a8a31 (a lint warning, fixed in the next commit) |
| Packaged build (`scripts\build.ps1`) `--self-test` with fresh user data | PASS (0.4.0b1, three models verified, inference ok) |

## Performance (development machine, 1280x720, Gesture test mode, production services)

| Measure | Brief 003 (0.3) | Brief 004 (0.4) |
|---|---|---|
| Capture / processing FPS | 29.6-30.0 | 30.0-30.1 (6 and 10 min) |
| Capture-to-result latency | 15.5-19.2 ms mean | 13.3-15.8 ms mean, 20.0-23.1 ms p95 |
| Gesture recognition per frame | 0.112 ms (replay) | 0.156 ms (replay); 0.17-0.25 ms incl. diagnostics in the GUI |
| CPU (whole machine) | 4.1-4.3 % | 4.5-5.4 % mean (hands visible in 44-64 % of samples, earlier sessions 5-25 %) |
| Memory | 363-384 MB | 10 min: 396 -> 362 MB (no growth); 6 min: 378 -> 386 MB |
| Camera restarts / shutdown | 4/4, 0.28 s | 6/6 in ~1 s, 0.29-0.63 s, no threads left |
| Browser: next / previous (live) | 200-450 / 211 ms | 224-634 / 193-265 ms; next after a navigation ~1 s (waits for the load); first-Short refusal 11 ms |

## Director validation

Nothing in Briefs 002-004 has been verified by the Director yet (M1 was). Start with
[BRIEF_004_VALIDATION.md](docs/milestones/BRIEF_004_VALIDATION.md) (about 20 minutes); the older
[checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md) covers the remaining Brief 003
features (OBS, co-op on two PCs, packaging on a second PC).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Left/right swipes, half-heart and stop at a normal distance not measured on real recordings; all numbers are development results from one person |
| Medium | A pointing hand dropped out of view can be read as a downward swipe (one recorded case) |
| Medium | Finger flicks need about 30 fps (hint below 20 fps); hand movements work at 15 fps |
| Medium | Stop pose unreliable at arm's length (detector) |
| Medium | YouTube markup changes would make Shorts actions fail (reported as failed/unknown) |
| Medium | Transparent background quality depends on lighting/clothing; OBS BitBlt window capture shows black |
| Low | Rare UI stalls inside Qt's event loop (instrumented); gesture processing unaffected |
| Low | Packaged build unsigned, validated on one machine |

## Commits for Engineering Brief 004

```
4a7ebad fix(browser): make Short navigation reliable and move finger up to next
8376755 feat(gestures): rework swipe arming, pose rule and diagnostics from real-data analysis
dc12201 feat(gestures): explain rejections, export diagnostics and add Quick Calibration core
dc750f6 feat(ui): add Gesture Practice and Quick Calibration
f29a5d8 build: add the Brief 004 guided recording and its scoring
f4a8a31 build: compare a nearest-neighbour stroke classifier with the rules (Strategy D)
544887c style: mark the unused stroke duration in the classifier experiment
a4c216a feat(gestures): measure smoothing and frame-rate robustness; warn at low frame rates
e218663 feat(actions): let one quick gesture wait for the running action
5d592b7 test: keep every Brief 004 defect in the regression suite
775e186 docs: document Brief 004 results, guides and the beta validation procedure
```

```
9faf843 test(live): keep the Shorts tab in front for every action and report the refusal
```

Followed by the audit/status documentation commit.

## Recommended next steps

1. Director: [BRIEF_004_VALIDATION.md](docs/milestones/BRIEF_004_VALIDATION.md), then
   `scripts\record_gestures.py --session 4 --hand right` and `--hand left` (about 5 minutes
   each), optionally `--session negatives --minutes 30`.
2. Evaluate those recordings as held-out data; tune left/right, half-heart and stop on them.
3. Signed-in like test by the Director.
