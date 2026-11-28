# Project status

Source of truth for the current state of the project. Update it with every checkpoint.

| | |
|---|---|
| Version | 0.8.0b1 - beta, **not released** (no tag) |
| Active work | Engineering Brief 008 (product redesign, live Shorts preview, Doomscroll Together) implemented; **Director validation pending** |
| Engineering decision | PARTIALLY READY - SPECIFIC PREVIEW, VISUAL OR TWO-DEVICE VERIFICATION REQUIRED |
| Last updated | 2026-11-28 |

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

## Test results (2026-11-28, Brief 008)

| Command | Result |
|---|---|
| `ruff format --check` / `ruff check` | clean |
| `pytest` | 755 passed, 0 failed, 0 expected failures, 6 skipped (webcam and live tests, run separately) - Brief 007 end 699 |
| Repeated full runs | 3 consecutive runs on the final code: all 755 passed |
| `pytest tests/hardware --hardware` | 5 passed |
| `pytest tests/live --live-youtube` | 19 of 20 runs passed after the harness fix (25 of 30 before); see Audit 010 |
| Gesture regression gate | no regression in all five 0.6.0b1 configurations |
| Packaged build `--self-test` | PASS (0.8.0b1) |
| GitHub Actions | checked after the last push |

## Performance (development machine, 1280x720; see docs/benchmarks/PERFORMANCE_008.md)

| Run (automated) | fps capture/processing | Latency | App CPU | Memory |
|---|---|---|---|---|
| Normal, webcam only, 4 min | 30.1 / 30.0 | 15.4 ms | 4.5 % | 385 -> 405 MB |
| Normal + live preview (real YouTube), 3 min | 30.2 / 30.2 | 18.5 ms | 4.6 % (+1.7 % in the browser) | 395 -> 408 MB |
| Broadcast + transparency + face/eye models, 3 min | 30.1 / 30.1 | 13.8 ms | 4.9 % | 431 -> 420 MB |
| Combined (preview + models), 3 min | 30.1 / 30.1 | 19.6 ms | 6.4 % | 434 -> 440 MB |
| Background, 2 x 4 min | 30.1 / 30.0 | 15.5-16.7 ms | 3.7-3.9 % | 386 -> 388-401 MB |

## Director validation

Nothing in Briefs 002-004 has been verified by the Director yet (M1 was). Start with
[BRIEF_008_VALIDATION.md](docs/milestones/BRIEF_008_VALIDATION.md) (about 30 minutes, plus a session with a friend); the older
[checklist](docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md) covers the remaining Brief 003
features (OBS, co-op on two PCs, packaging on a second PC).

## Known issues and limitations

| Severity | Issue |
|---|---|
| High (verification) | Doomscroll Together not tested on two computers; no real-person check of clown makeup, transparency or the new UI; gesture data from one person |
| Medium | Live preview: popup click needed per session; extension reload after updating; Chrome and audio-by-ear unchecked |
| Medium | One undiagnosed first-navigation failure in 20 live YouTube runs |
| Medium | UI stalls 110-180 ms on window resize in the new layout; one unexplained 393 ms stall; rare Qt stalls not resolved |
| Medium | OBS Windows Graphics Capture unverified; second monitor untested |
| Medium | Any hand shape: about twice the accidental swipes of pointing finger only; low-fps flick returns |
| Low | Together messages authenticated, not encrypted (VPN encrypts); packaged build unsigned |

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

1. Director: [BRIEF_008_VALIDATION.md](docs/milestones/BRIEF_008_VALIDATION.md) - reload the
   extension, try the live preview, the clown strength, Broadcast settings.
2. A Doomscroll Together session with a friend on the same Wi-Fi (and optionally over Tailscale).
3. A held-out gesture recording with each hand (all existing ones were used for development).
