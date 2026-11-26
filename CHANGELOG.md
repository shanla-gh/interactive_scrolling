# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased] - 0.2.0.dev0

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
