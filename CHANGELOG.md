# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.7.0b1] - beta (not released; Director validation pending)

Engineering Brief 007: product experience and Broadcast Mode. Gesture recognition is
unchanged from 0.6.0b1 (protected by a regression gate; `docs/benchmarks/GESTURE_BENCHMARK_007.md`).

### Changed

- Status wording: the header says CAMERA ON/OFF (it said LIVE when only the camera was on); the
  control bar reads Gestures off / Gesture test / Live control / Stop control and
  "Browser: ..."; "no controller available" became "browser connection not available".
- Layout at 125-150 % display scaling: no clipped mode buttons, five side tabs (display options
  and system figures share one), a status bar that fits, and a Gesture settings dialog that fits
  a laptop screen (raw thresholds behind "Show advanced thresholds").
- Practice and rejection texts no longer assume a pointing finger.
- "Creator overlay" is called Broadcast Mode everywhere.

### Added

- Broadcast Mode: gesture-control status chip, session timer and counters (the counters layer
  was never filled), Position menu, recovery of an overlay saved off every screen, display-only
  skeleton smoothing.
- Transparent background keeps low-confidence clothing enclosed by the person.
- Getting started window (first start and Help); extension folder copy button; broadcast and
  extension guides.
- Tools: recognition baselines and `benchmark_motion.py --baseline`, `capture_screenshots.py`,
  `experiment_mask_refinement.py`, stability sessions in Broadcast/Background Mode with optional
  models and mode cycling.

## [0.6.0b1] - beta (not released; Director validation pending)

Engineering Brief 006: pose-independent motion recognition. Evidence:
`docs/benchmarks/GESTURE_BENCHMARK_006.md`.

### Fixed

- Fast swipes were cancelled when MediaPipe briefly detected the blurred hand twice; in the
  Director's downward finger swipes the finger extensions then fired as swipes up.
- A hand lost for a moment and re-found elsewhere could be read as a swipe.

### Changed

- Swipes work with any hand shape (default): a pointing hand is measured at the fingertip as
  before, every other shape at the centre of the hand after a brief pause; the shape may change
  during the movement. "Pointing finger only" remains available. 0.5 settings move to it once
  with a notice; the open-palm experiment is removed from the settings.
- Practice accepts the asked direction with any hand shape; Practice and Quick Calibration
  offer "Pointing finger" or "Whole hand, any shape".

### Added

- The video shows the measured trajectory of the movement; Copy diagnostics reports frame
  timing, frames with a control hand and ignored duplicate detections.
- `scripts/benchmark_motion.py` (development / held-out rows, wrong-direction and duplicate
  counts, synthetic degradations).

## [0.5.0b1] - beta (not released; Director validation pending)

Engineering Brief 005: motion-first gesture recognition. Evidence:
`docs/benchmarks/GESTURE_BENCHMARK_005.md`.

### Fixed

- Quick Calibration could raise the swipe distance far too much when a swipe was held before a
  slow return (the Director's profile: 1.34 instead of 0.8 hand lengths and a higher speed;
  recorded finger flicks 8/8 -> 0/8). Profiles from 0.4 are repaired once with a notice.
- Lowering a pointing hand out of the picture could be read as a downward swipe.
- A fist swipe's own return could suppress the next fist swipe (found by new scenario tests
  before release).

### Added

- One motion engine for finger, fist and (experimental) open-palm swipes; fist swipes follow
  the palm centre and are activated by a fist held still for a moment. "Swipe with": index
  finger (default), finger or fist, fist only (both experimental). One physical swipe gives one
  action; returns are suppressed across detectors.
- Practice and Quick Calibration for finger or fist swipes; per-direction personal distances
  and a fist distance.
- The video shows the measured stroke (start, arrow, travel against the needed distance,
  detector, phase); recognized gestures name their detector.
- Meaningful gesture rejections are stored locally (no images) and included in the
  diagnostics export.
- Recorder session 5 (about 3 minutes per hand) for the open questions; strategy comparison,
  motion-reference analysis and semi-synthetic fist evaluation tools.

### Changed

- A finger stroke whose palm moves with the fingertip is confirmed at once even if blur makes
  the finger look curled.
- Boundary refusals ("already at the first Short") say that the gesture was recognized.

## [0.4.0b1] - beta (not released; Director validation pending)

Engineering Brief 004: beta stabilization of gesture recognition and browser reliability,
driven by the Director's real-world test. Evidence: `docs/benchmarks/GESTURE_BENCHMARK_004.md`.

### Fixed

- "Previous Short" at the first Short of a feed clicked a button YouTube hides without
  disabling it and failed after 3 s (all five failures of the Director's test); it is now
  refused at once ("already at the first Short").
- A gesture right after a navigation was refused with "no YouTube Shorts tab is active" or
  "the active Short changed" while the page switched Shorts; the page state is now re-reported
  at once and the dispatcher waits briefly (at most 1.2 s, one attempt) for a changing or
  loading Short. The Shorts session no longer ends and restarts around every navigation.
- Horizontal movements came out in the opposite direction: a newly tracked hand had to be
  still for 0.2 s, so in continuous motion the recognizer armed at the end of a stroke and
  confirmed the return (recorded sweeps 0/12 -> 9/12).
- Downward finger flicks were rejected because the curling finger reads as a fist (1/4 -> 4/4
  on the recordings); relaxing a pointing finger is still not a swipe.
- The stop pose's stillness check failed on small, jittering hands far from the camera.
- The evaluator's mirrored replay did not swap handedness labels.

### Changed

- Moving the finger up now shows the next Short (down: previous). Settings with the old
  default are migrated once with a notice; customised mappings are kept.
- Half-heart: the other fingers may curve with the index; hold 0.6 -> 0.5 s.
- Under a named preset the thresholds follow the current preset values; presets are shown as
  Relaxed / Balanced / Precise, plus Personal (calibration) and Custom.
- A gesture made while the previous action is still running waits for it (one at most,
  expires after 2.5 s) instead of being refused.
- Extension 0.4.0 (no new permissions).

### Added

- Structured rejection reasons with measured and required values, plain-language
  explanations, live recognizer state, positioning and low-frame-rate hints, and the final
  browser result on the video.
- Gesture Practice and Quick Calibration (personal swipe distances, half-heart template, stop
  tilt; bounded, reversible, derived numbers only).
- "Copy diagnostics": recognition and browser decisions without personal data; optional
  landmark-only recording of a practice session.
- Recorder session 4 (Brief 004, per hand) and an ordinary-use negatives session; evaluator
  strategy switches, semi-synthetic horizontal swipes, calibration simulation, classifier and
  filtering experiments.

## [0.3.0rc1] - release candidate (not released; Director acceptance pending)

### Added

- Four-direction index-finger swipes (one recognizer, either hand, diagonals rejected,
  settle-based return-movement suppression) and the single-hand half-heart like gesture.
- Browser tab navigation (next/previous tab of the focused window, no wrap-around, no new
  extension permissions); protocol version 2, extension 0.3.0.
- Content Creator Mode (always-on-top, non-activating overlay for OBS) with optional
  transparent background from local person segmentation; Background Mode (tray); visual
  customization; all modes share one runtime.
- Scrolling session accounting, Daily Activity Report, Gesture Performance Report, Doomscroll
  Index, optional Reality Checks, limits, break reminders and a reversible gesture-scrolling
  pause.
- Progressive Clown Transformation (procedural AR makeup from face landmarks) and optional
  passive eye analytics with calibration and a Visual Behavior Report.
- Doomscroll Wrapped (daily, session and co-op 1080x1920 PNG cards).
- Minimal two-person Co-op Doomscroll over a private network (authenticated, host-approved,
  shared next/previous/pause only).
- UI stall monitor with handler, GC and worker attribution; `--self-test`; Windows packaging
  with PyInstaller; recorder session 3 and per-gesture benchmark reports.

### Changed

- Gesture names and defaults (Brief 003): thumbs up and open-hand sweeps replaced; academic
  application switching removed. Settings files are migrated (with a backup) and version 0.2
  statistics are kept.

### Fixed

- ~13 ms UI-thread block every second from system-wide thread enumeration.
- False opposite swipe from a multi-part, overshooting return movement (HIGH preset).
- Reading a fresh statistics database reported an error until the first event.
- Two timing races in tests (browser reconnect, queued panel update).

## [0.2.0.dev0]


### Added

- Gesture recognition engine: pointing-hand swipes up/down, open-hand sweeps left/right,
  thumbs up and stop pose, with explicit lifecycles, return-movement suppression, cooldowns,
  control-hand selection and ambiguity suspension; thresholds calibrated on labeled recordings.
- Control modes (Tracking only, Gesture test, Live control), action dispatcher with stale-event
  rejection and one-action-at-a-time execution, emergency disable (button, Esc, Ctrl+Alt+D).
- YouTube Shorts control through a Manifest V3 companion extension and a loopback WebSocket
  bridge (origin pinning, pairing code, strict schema): next, previous, like (never unlike),
  pause/resume, each confirmed from page state.
- Local analytics (SQLite) with daily statistics, opt-out and clear.
- UI: control bar, gesture panel, gesture history, YouTube and statistics panels, gesture
  settings dialog with presets, on-video gesture feedback; settings persisted per user.
- Tools: guided gesture recording and replay evaluation; browser fixture and live-site tests.

### Fixed

- Bridge server thread error on shutdown (Windows), stale browser tab state after navigation,
  actions sent before the video loaded, clipped side-panel values, temporary file left by a
  failed settings write, unbounded bridge connections.

## 0.1.0.dev0

### Added

- Project foundation: `src/` package layout, pinned reproducible dependencies, MIT license,
  Windows setup/run/test scripts, GitHub Actions CI (format, lint, hardware-independent tests).
- Webcam acquisition with OpenCV (Media Foundation by default), resolution selection,
  user-initiated camera scan, graceful handling of unavailable, busy and disconnected cameras.
- Real-time hand tracking with the MediaPipe Hand Landmarker (VIDEO mode): up to two hands,
  21 landmarks each, handedness with score, one-time verified model download.
- Threaded pipeline with a latest-frame mailbox that drops stale frames instead of queuing.
- Motion engine: fingertip and palm displacement, velocity (px/s and palm lengths/s),
  8-way direction, time-constant smoothing, stationary hysteresis, loss/reacquisition handling,
  track association for two hands, motion trails.
- Desktop UI (PySide6 Widgets): live view with aligned skeleton, landmarks, bounding boxes,
  labels, trails and velocity arrows; tracking and motion panels; overlay toggles; mirror
  preview; diagnostics bar with measured FPS, latency, drops, CPU and memory; activity log.
- Opt-out of Windows execution-speed power throttling (`--allow-power-throttling` to keep it).
- Benchmark and GUI stability-session scripts with JSON reports.
- Documentation: architecture, decisions, engineering conventions, third-party notices,
  roadmap, project status, manual verification checklist, Integration Audit 001.
