# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.9.0b1 - beta, **not released** (no tag) |
| Active work | Engineering Brief 009 (Motion Engine 2.0, real-time, passive eyes) implemented; **Director validation pending** |
| Engineering decision | PARTIALLY READY - SPECIFIC HUMAN OR HARDWARE VERIFICATION REQUIRED |
| Last updated | 2026-11-28 |

## Brief 009 in one paragraph

A full-application replay benchmark ran identical hand input through every presentation mode:
recognition latency is about 10 ms median in all of them and the recognized gestures are
identical, so no mode-specific recognition defect exists in replay. On the real camera,
however, frames were lost at the capture handoff (up to 5 %, most in Broadcast Mode with every
optional model) because the webcam delivers bursts; a two-frame bounded buffer removed that
(39.5 -> 0.0 dropped per minute). Downward swipes (previous Short) now fire sooner at >= 22 fps
(255 -> 192 ms finger, 432 -> 367 ms whole hand), the Broadcast overlay no longer repaints in a
loop (CPU 6.1 -> 4.4 % with everything on), display smoothing lags less, the real camera limit
(720p at 30 fps) is documented, driver frame times are recorded, and an optional eye and gaze
overlay shows an honest, quality-gated estimate (display only). False positives, repeated
gestures and gaze accuracy need new recordings or a person. Details:
[Brief 009 report](docs/milestones/BRIEF_009_REPORT.md), [Audit 011](docs/audits/INTEGRATION_AUDIT_011.md),
[performance](docs/benchmarks/PERFORMANCE_009.md), [gestures](docs/benchmarks/GESTURE_BENCHMARK_009.md),
[validation](docs/milestones/BRIEF_009_VALIDATION.md).

## Brief 008 in one paragraph

Normal Mode replaces the developer dashboard: a minimal top bar, the camera with a compact
Off/Test/Live strip next to **Now playing** - the Short from the user's browser, live in the
app through the extension's tab capture (one chosen tab, video area only, loopback, no
sound; gestures reach that tab while the app is in front) - and Browser, **Doomscroll
Together** and Today on the right, with a collapsible diagnostics console at the bottom.
Doomscroll Together gained host/join dialogs, invitations, private-network-only listening,
expiring codes, plain-language errors, reconnection and rate limiting. Broadcast settings make
the transparent background one click away; the clown effect is now makeup (nose, lips,
translucent white) instead of a mask and wig. Real-YouTube failures from Brief 007 were traced
to the test harness, and the Background Mode drop rate was re-measured (0.2/min with a new
Windows timer opt-out). The gesture engine is unchanged (gate: no regression). Open: two
computers, a real person for clown/transparency, the live preview and audio by the Director.
Details: [Brief 008 report](docs/milestones/BRIEF_008_REPORT.md),
[Audit 010](docs/audits/INTEGRATION_AUDIT_010.md),
[performance](docs/benchmarks/PERFORMANCE_008.md),
[validation](docs/milestones/BRIEF_008_VALIDATION.md).

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
| Brief 008 product redesign (M35-M44) | implemented; technical pass; preview, visual and two-computer checks need the Director | [Brief 008 report](docs/milestones/BRIEF_008_REPORT.md) |
| Integration Audit 010 | technical PASS; not a full pass | [Audit 010](docs/audits/INTEGRATION_AUDIT_010.md) |
| Brief 009 Motion Engine 2.0 (M45-M53) | implemented; technical pass; Broadcast feel, gaze accuracy and independent recognition data need the Director | [Brief 009 report](docs/milestones/BRIEF_009_REPORT.md) |
| Integration Audit 011 | technical PASS with one open intermittent test | [Audit 011](docs/audits/INTEGRATION_AUDIT_011.md) |

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

## Test results (2026-11-28, Brief 009)

| Command | Result |
|---|---|
| `ruff format --check` / `ruff check` | clean |
| `pytest` | 773 passed, 0 failed, 6 skipped in 2 of 3 final runs; 1 intermittent browser fixture failure in the third (not reproduced in 13 runs) |
| `pytest tests/hardware --hardware` | 5 passed |
| Gesture regression gate | no regression in all five 0.6.0b1 configurations |
| Packaged build `--self-test` | PASS (0.9.0b1) |
| GitHub Actions | checked after the last push |

## Performance (see docs/benchmarks/PERFORMANCE_009.md)

| Measurement | Result |
|---|---|
| Replay, 9 modes, capture -> recognition | about 10 ms median, <= 22 ms p99, identical gestures |
| Broadcast with everything, app CPU (replay) | 6.1 % -> 4.4 % |
| Real camera, dropped frames (Broadcast + all models, A/B) | 39.5 -> 0.0 per minute |
| Endurance (real camera, automated) | 30 min Normal + preview, 30 min Broadcast + all models, 10 min mode cycling: no leaks, 0 invariant violations |

## Director validation

Nothing in Briefs 002-004 has been verified by the Director yet (M1 was). Start with
[BRIEF_009_VALIDATION.md](docs/milestones/BRIEF_009_VALIDATION.md) (about 25 minutes, optional recordings 25 minutes); the older
[checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md) covers the remaining Brief 003
features (OBS, co-op on two PCs, packaging on a second PC).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Broadcast feel not checked by a person; no independent labelled recordings (recall/precision targets unmeasured); gaze accuracy unknown; Doomscroll Together not tested on two computers |
| Medium | False positives unchanged (11 / 249 s any shape, 6 finger only); rapid repeats unmeasured |
| Medium | Stalls during a 30-minute live-preview session (likely the test harness, not excluded); rare UI stalls |
| Medium | Camera limited to 30 fps; recognition on arrival times (driver times recorded) |
| Low | Intermittent browser fixture test (about 1 in 10 runs); packaged build unsigned |

## Commits for Engineering Brief 009

```
6c19c42 feat(gestures): confirm low downward swipes on a clear slow-down at well-sampled frame rates
19b6ea4 style: format and lint the decision-delay analysis script
481fcc5 perf(ui): stop the repaint storm while feedback fades; cross-mode recognition test
79950e9 perf(broadcast): less display-smoothing lag (beta 0.2 -> 0.5), measured on the recordings
6e271dc feat(camera): record the driver's frame sample times; measured camera limits and delivery
bf4c41e feat(eyes): optional eye and gaze overlay with an honest, quality-gated gaze estimate
4177cec feat(eyes): gaze calibration evaluation tool (9 calibration, 8 separate evaluation points)
6395bf0 feat(wrapped): optional eye analytics line (estimated, with unknown time shown)
e529f28 feat(recordings): rapid-repeat recording session and scorer labels for held-out evaluation
a92ef38 perf(pipeline): two-frame bounded handoff so camera bursts no longer lose frames
(plus the commit with this status update)
```

## Commits for Engineering Brief 008

```
0d38e19 feat(browser): live Shorts preview through tab capture, with preview-tab control
5b44f5b feat(coop): private networks only, expiring invitations, plain-language refusals, reconnect
8900261 feat(ui): Normal Mode redesign with Now playing, Doomscroll Together, Broadcast settings and natural clown makeup
e0a3873 feat(clown): feather the white makeup towards eyes, brows and lips; preview and live tools
0ad7ab6 docs(coop): Doomscroll Together user guide, security and trust assumptions; overhead benchmark
48df125 test(live): close Edge first-run tabs and accept the post-consent /shorts URL; record failures
b2a97bd fix: background timer opt-out, a real 'Remove' for Doomscroll Together guests, Broadcast settings fits 150 %
026d08d docs: Brief 008 architecture, guides, performance and validation; version 0.8.0b1
(plus the commit with this status update)
```

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

1. Director: [BRIEF_009_VALIDATION.md](docs/milestones/BRIEF_009_VALIDATION.md) - Broadcast vs
   Normal feel, downward swipes, eye overlay.
2. The optional held-out recordings (directions, rapid repeats, ordinary activity) for the first
   independent recognition numbers and the driver-timestamp evaluation.
3. The gaze calibration run, then decide on a passive gaze point.
