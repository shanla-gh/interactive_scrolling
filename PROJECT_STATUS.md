# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.5.0b1 - beta, **not released** (no tag) |
| Active work | Engineering Brief 005 (motion-first gestures) implemented; **Director validation pending** |
| Engineering decision | PARTIALLY READY - TARGETED PHYSICAL DATA REQUIRED |
| Last updated | 2026-11-27 |

## Brief 005 in one paragraph

The Director's test after 0.4 showed that downward swipes *were* recognized in Live control
(13 in a minute) but 7 of them were correct "already at the first Short" refusals that looked
like failures, and that Quick Calibration had raised the up/down distance to 1.34 hand lengths
(recorded finger flicks: 8/8 -> 0/8 with those values). Both are fixed (calibration defect,
repair migration, clearer banner). Measurements show that a downward finger flick is
physically the same movement as the curl back after an upward flick, so finger-only "down"
depends on context; gesture recognition is now one motion engine with a finger detector and a
fist detector (palm centre, activated by a still fist), per-direction calibration, a motion
overlay and stored rejections. Fist control is experimental: it has no real recording yet.
Details: [Brief 005 report](docs/milestones/BRIEF_005_REPORT.md),
[benchmark 005](docs/benchmarks/GESTURE_BENCHMARK_005.md),
[Audit 007](docs/audits/INTEGRATION_AUDIT_007.md),
[validation](docs/milestones/BRIEF_005_VALIDATION.md).

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
| Brief 005 motion-first (M12-M18) | implemented; technical pass; fist control and downward comfort need real data | [Brief 005 report](docs/milestones/BRIEF_005_REPORT.md) |
| Integration Audit 007 | technical PASS; not a full pass | [Audit 007](docs/audits/INTEGRATION_AUDIT_007.md) |

## Recognition results (development data unless stated)

| Gesture | Result | Source |
|---|---|---|
| Finger up / down | 8/8 / 8/8 (also mirrored) | real recordings (flicks and hand swipes) |
| Finger right / left | 4/4 / 2/4 | semi-synthetic (rotated real swipes) |
| Fist up / down / right / left | 3/4, 4/4, 6/6, 5/6 | semi-synthetic (real palm motion, fingers re-posed) |
| Open-palm swipes (experiment) | 0/12, 7 opposite | real sweeps - rejected, off |
| Half-heart | 2 confirmed in Practice | real use (attempts unknown) |
| Stop | 4 confirmed incl. 2 live toggles; arm's-length recordings 0/3 | real use / real |
| False events | finger: 2 in the replay (1 in 190 s of negatives); finger or fist: 4 (the 2 extra while lowering thumbs-ups) | real |

## Test results (2026-11-27)

| Command | Result |
|---|---|
| `ruff format --check` / `ruff check` | clean |
| `pytest` | 650 passed, 6 skipped - Brief 004 end 615 passed |
| `pytest tests/hardware --hardware` | 5 passed |
| `pytest tests/live --live-youtube` | 3 of 3 runs passed (next 298-304 ms, previous 222-244 ms) |
| Packaged build `--self-test` | PASS (0.5.0b1) |
| GitHub Actions | see the commit list; checked after the last push |

## Performance (development machine, 1280x720, Gesture test mode, production services)

| Measure | Brief 004 | Brief 005 |
|---|---|---|
| Capture / processing FPS | 30.0-30.1 | 30.1 / 30.1 (6 min) |
| Capture-to-result latency | 13.3-15.8 ms | 14.0 ms mean, 23.4 ms p95 |
| Recognition per frame (replay) | 0.156 ms | finger 0.144 ms, finger or fist 0.149 ms |
| CPU / memory | 4.5-5.4 % / no growth | 4.3 % / 383 -> 365 MB |
| UI stalls | 1-2 per session | none in 6 minutes |

## Director validation

Nothing in Briefs 002-004 has been verified by the Director yet (M1 was). Start with
[BRIEF_005_VALIDATION.md](docs/milestones/BRIEF_005_VALIDATION.md) (about 20 minutes); the older
[checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md) covers the remaining Brief 003
features (OBS, co-op on two PCs, packaging on a second PC).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Fist control unvalidated on real hands; all gesture numbers come from one person's development recordings |
| Medium | Downward finger *curl* flicks wait for the finger to straighten (they move like the return of an upward flick); hand or wrist movement down is immediate |
| Medium | Finger-or-fist style: closed hands moved after a thumbs-up can trigger fist swipes (2 recorded cases) |
| Medium | Finger flicks need about 30 fps; stop pose unreliable at arm's length |
| Medium | YouTube markup changes would make Shorts actions fail (reported as failed/unknown) |
| Low | Rare UI stalls inside Qt (instrumented); packaged build unsigned |

## Commits for Engineering Brief 005

```
cc85442 fix(calibration): stop slow returns from raising the swipe thresholds
c221a94 feat(diagnostics): keep meaningful gesture rejections in the local statistics
cc930ce feat(gestures): one motion engine for finger, fist and palm swipes
12a8f7c feat(gestures): remember fist movements that were not activated
1b22049 feat(calibration): personal distances per direction and for fist swipes
69458bc feat(ui): choose finger or fist swipes, practise and calibrate both
b52d13e feat(ui): show the measured stroke on the video
0e3b787 fix(gestures): never remember a fist swipe's return as a stroke of its own
2965ed4 feat(ui): say that a boundary refusal recognized the gesture; add the Brief 005 recording
```

Followed by the documentation commit (benchmark, audit, guides, version 0.5.0b1).

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

1. Director: [BRIEF_005_VALIDATION.md](docs/milestones/BRIEF_005_VALIDATION.md) - compare finger
   and fist swipes, especially downward; recalibrate (the 0.4 profile was reset).
2. `scripts\record_gestures.py --session 5 --hand right` and `--hand left` (about 3 minutes
   each): decides whether fist or finger-or-fist control can become the default.
3. Signed-in like test by the Director.
