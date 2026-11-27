# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.7.0b1 - beta, **not released** (no tag) |
| Active work | Engineering Brief 007 (product experience, Broadcast Mode) implemented; **Director validation pending** |
| Engineering decision | PARTIALLY READY - SPECIFIC VISUAL OR PHYSICAL VERIFICATION REQUIRED |
| Last updated | 2026-11-27 |

## Brief 007 in one paragraph

The Director approved the feel of 0.6.0b1's motion recognition; it is frozen as a baseline and
unchanged (two false-positive and one low-frame-rate candidate were rejected by the new
regression gate). The product work was reviewed on rendered screenshots at 100-150 % scaling:
the camera pill no longer says LIVE, nothing is clipped, Gesture settings fits a laptop, and the
wording separates camera, gesture control and browser state. Broadcast Mode gained a
gesture-control chip, a working counters/session-timer layer, corner positioning with
off-screen recovery and display-only skeleton smoothing; the transparent background keeps
low-confidence clothing inside the person (synthetic evidence). A first-use guide, broadcast
and extension guides, and 55 minutes of automated endurance runs (no leaks, safe mode
transitions) complete it. Open: human visual checks, OBS's Windows Graphics Capture, a hidden-
window frame-drop finding, and an intermittent real-YouTube failure that the approved 0.6
code shows too. Details: [Brief 007 report](docs/milestones/BRIEF_007_REPORT.md),
[Audit 009](docs/audits/INTEGRATION_AUDIT_009.md),
[performance](docs/benchmarks/PERFORMANCE_007.md),
[validation](docs/milestones/BRIEF_007_VALIDATION.md).

## Brief 006 in one paragraph

The Director's session-5 recordings confirmed that downward finger swipes failed (5/10, with
7 events in the wrong direction). The main cause was not the recognizer's rules but tracking:
during fast movements MediaPipe reports the blurred hand twice for a few frames, which
cancelled the swipe and locked the recognizer into the wrong phase. With duplicates ignored,
downward finger swipes are 18/18 on all recordings (held-out left hand 5/5). Real use of 0.5
also showed downward attempts failing because the hand was not pointing, so swipes now work
with any hand shape by default: pointing hands as before, other shapes at the centre of the
hand after a brief pause. That path is weaker (33/44 on development data, 5/16 in the one
held-out look) and raises accidental swipes in ordinary activity (11 instead of 6 in 249 s);
"pointing finger only" remains. Details: [Brief 006 report](docs/milestones/BRIEF_006_REPORT.md),
[benchmark 006](docs/benchmarks/GESTURE_BENCHMARK_006.md),
[Audit 008](docs/audits/INTEGRATION_AUDIT_008.md),
[validation](docs/milestones/BRIEF_006_VALIDATION.md).

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
| Brief 006 pose-independent motion (M19-M25) | implemented; technical pass; whole-hand swipes and accidental swipes need the Director | [Brief 006 report](docs/milestones/BRIEF_006_REPORT.md) |
| Integration Audit 008 | technical PASS; not a full pass | [Audit 008](docs/audits/INTEGRATION_AUDIT_008.md) |
| Brief 007 product experience (M26-M34) | implemented; technical pass; visual and creator checks need the Director | [Brief 007 report](docs/milestones/BRIEF_007_REPORT.md) |
| Integration Audit 009 | technical PASS; not a full pass | [Audit 009](docs/audits/INTEGRATION_AUDIT_009.md) |

## Recognition results (development data from one person; all four real recordings)

| Category | 0.6.0b1 (any hand shape) | Notes |
|---|---|---|
| Finger down / up | 18/18 / 8/8, 0 wrong direction | 0.5 on session 5: 5/10 with 7 wrong |
| Fist up / down / left / right | 5/8, 3/8 (1 wrong), 5/8, 7/8 | 0 with pointing finger only |
| Open hand left / right | 6/6 / 6/6 | 0 in 0.5 |
| Held-out look (left hand, before the last iterations) | finger 5/5; whole hand 5/16 | the only independent result |
| Ordinary activity (249 s) | 11 false events | 6 with pointing finger only |
| 15 fps / 10 % frame loss (synthetic) | finger up 4/8 (3 wrong) / 6/8 (2 wrong) | missed flicks let their return through |
| Half-heart, stop | unchanged from 0.5 | |

## Test results (2026-11-27, Brief 007)

| Command | Result |
|---|---|
| `ruff format --check` / `ruff check` | clean |
| `pytest` | 699 passed, 0 failed, 0 expected failures, 6 skipped (webcam and live tests, run separately) - Brief 006 end 686 |
| Repeated full runs | 3 consecutive runs on the final code: all 699 passed |
| `pytest tests/hardware --hardware` | 5 passed |
| `pytest tests/live --live-youtube` | 7 of 11 runs passed; the 4 failures are a YouTube-side change (consent redirect / Short not advancing in a fresh profile) that the approved 0.6.0b1 code shows too (1 of 3) |
| Gesture regression gate | no regression against all five 0.6.0b1 baselines |
| Packaged build `--self-test` | PASS (0.7.0b1) |
| GitHub Actions | see the commit list; checked after the last push |

## Performance (development machine, 1280x720; see docs/benchmarks/PERFORMANCE_007.md)

| Run (automated) | fps capture/processing | Latency | CPU | Memory |
|---|---|---|---|---|
| Developer, 30 min, hand in view 56 % | 30.1 / 30.1 | 15.3 ms | 4.6 % | 389 -> 367 MB |
| Broadcast + transparency + face/eye models, 10 min | 30.9 / 29.7 | 12.0 ms | 4.6 % | 440 -> 430 MB |
| Background, 5 min | 30.8 / 29.6 | 11.9 ms | 2.7 % | 387 -> 342 MB |
| Mode cycling every 20 s, 10 min (29 transitions, 0 violations) | 30.9 / 29.7 | 12.2 ms | 3.8 % | 426 -> 420 MB |

## Director validation

Nothing in Briefs 002-004 has been verified by the Director yet (M1 was). Start with
[BRIEF_007_VALIDATION.md](docs/milestones/BRIEF_007_VALIDATION.md) (about 20 minutes); the older
[checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md) covers the remaining Brief 003
features (OBS, co-op on two PCs, packaging on a second PC).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | No human check yet of the new UI, Broadcast presentation or transparency with a real person; gesture data from one person |
| Medium | Real YouTube navigation fails intermittently in fresh browser profiles (YouTube-side; reported as failed) |
| Medium | About 3 % of frames dropped while the main window is hidden (cause unknown) |
| Medium | OBS Window Capture (Windows Graphics Capture) unverified; BitBlt window capture shows black; second monitor untested; Chrome manual only |
| Medium | Any hand shape: about twice the accidental swipes of pointing finger only; low-fps flick returns |
| Low | Rare Qt stalls (344 ms once in 30 min); packaged build unsigned |

## Commits for Engineering Brief 007

```
ebdc193 test(gestures): freeze the 0.6.0b1 recognition baseline and add a regression gate
c4fe51e feat(ui): clearer status, wording and layout; Broadcast Mode positioning and status
11085ea feat(broadcast): keep low-confidence clothing inside the person in the transparent overlay
2a7f749 test: stability sessions in Broadcast and Background Mode, with optional models and mode cycling
e97294e feat(ui): first-use guide, extension setup without broken paths, guides and capture check
```

Followed by the documentation commit (audit 009, performance, validation, version 0.7.0b1).

## Commits for Engineering Brief 006

```
e4b8237 fix(gestures): ignore momentary duplicate detections of the moving hand
bdaf899 feat(gestures): recognize swipes with any hand shape in one motion engine
6ef5d6c feat(diagnostics): show the measured trajectory and report frame timing and duplicates
```

Followed by the documentation commit (benchmark 006, Audit 008, guides, version 0.6.0b1).

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

1. Director: [BRIEF_007_VALIDATION.md](docs/milestones/BRIEF_007_VALIDATION.md) (and answer or
   cancel the open Windows Firewall prompt for OBS Studio, if still shown).
2. A recording with OBS using Broadcast Mode and the transparent background with a real person.
3. A held-out gesture recording with each hand (all existing ones were used for development).
