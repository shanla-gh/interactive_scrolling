# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased] - 0.1.0.dev0

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
