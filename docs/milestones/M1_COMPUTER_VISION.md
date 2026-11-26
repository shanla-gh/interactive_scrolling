# M1 - Computer Vision & Live Visualization

Overall status: **BLOCKED on owner visual sign-off.** All functionality is implemented and
verified with automated tests, the physical webcam and the real model; the only open
items are the criteria that need a person to judge visually in front of the camera
(see [M1_MANUAL_VERIFICATION.md](M1_MANUAL_VERIFICATION.md)).

## Test environment

Windows 11 Pro (10.0.26200), Intel Core i7-13700H (14 cores / 20 threads), 15.6 GB RAM,
integrated "HP HD Camera", mains power, Python 3.12.10, mediapipe 1.2.3,
opencv-contrib-python 4.12.0.88, numpy 2.2.6, PySide6 6.10.3. Measurements were taken
with other desktop applications running, as a user would.

## CP 1.1 - Real-time webcam acquisition: COMPLETED

* `vision/camera.py` (`OpenCVCamera`, `probe_cameras`), capture thread in `core/pipeline.py`.
* Camera selection (user-initiated scan), resolution selection, start/stop, mirrored
  preview, BGR->RGB conversion done once in the processing thread, bounded buffering
  (single-slot mailbox), readable errors for unavailable/busy/silent/disconnected cameras,
  release on stop, failure and window close.
* Evidence (hardware tests, `pytest --hardware`): 640x480 at 30.8 FPS, 1280x720 at
  30.4 FPS; five open/close cycles each re-acquired the device (0.26-0.30 s open time);
  probe found camera 0. Hardware-independent failure tests in `tests/unit/test_camera.py`
  and `tests/integration/test_pipeline.py` (open failure, disconnect, stop during open,
  10x start/stop, shutdown while running).
* Not exercised on hardware: another application holding the camera and a USB
  disconnect (the laptop camera is built in). Both paths are covered by simulated tests and
  are listed in the manual checklist.

## CP 1.2 - Real-time hand tracking: COMPLETED

* `vision/hand_tracker.py` (MediaPipe Hand Landmarker, VIDEO mode), `vision/landmarks.py`.
* 21 landmarks per hand, up to two hands, handedness and its score (no invented
  confidences: per-landmark visibility/presence are `None` for this model and are not shown),
  timestamped `TrackingResult`, UI-independent consumption.
* Model provenance: Google's official URL pinned to version 1, SHA-256 verified;
  Apache 2.0 per the official model card. Offline after the one-time download.
* Evidence: on MediaPipe's public two-hand photo the tracker finds both hands with correct
  handedness (subject's right hand = `Right`); mirrored input mirrors x and swaps handedness
  (the reason mirroring is display-only); blank frames give no hands; a hand that disappears
  produces no stale landmarks. In the 10-minute live session hands were detected through
  the webcam in 373 of 600 one-second samples.

## CP 1.3 - Hand skeleton and landmark visualization: COMPLETED (visual sign-off pending)

* `visualization/geometry.py` (`ViewTransform`), `visualization/overlay.py`, `ui/video_view.py`.
* 21 landmarks, 21 anatomical bones (identical to MediaPipe's definition, tested),
  corner-bracket bounding boxes, handedness labels, right hand green / left hand cyan,
  tracking status HUD, all layers individually switchable.
* Evidence: pixel-level tests render the view offscreen at 4 sizes, mirrored and not, and
  find landmark colours exactly where the transform maps them and the video marker exactly
  under the same transform; disabled layers draw nothing; lost hands leave no overlay.
  Screenshots of the real UI with real MediaPipe landmarks (sample photo fed as a camera)
  showed the skeleton on the fingers in both mirror modes.
* Pending: the owner's visual confirmation on their own hands (manual checklist).

## CP 1.4 - Motion analysis and vector engine: COMPLETED

* `motion/analyzer.py`. Fingertip and palm displacement, velocity (px/s and palms/s),
  direction, magnitude, time-constant smoothing, history and trails, stationary hysteresis,
  loss/reacquisition handling, jump protection, two-hand association. Units and coordinate
  conventions are documented in the module and in `docs/architecture/ARCHITECTURE.md`.
* Evidence: 37 unit tests (including parametrized cases) with controlled synthetic sequences (exact velocities for
  constant and irregular frame intervals, convergence with smoothing, direction sectors,
  scale invariance at 50/100/150 px palm sizes, jitter of 0.8 px never classified as moving,
  no spike after loss or jumps, crossing hands keep identity). With the real model tracking
  a photo moving at 86.7 px/s, the measured speed was 87-88 px/s for both hands.
  Arrow direction is pixel-tested in both mirror modes.

## CP 1.5 - Desktop application and visual identity: COMPLETED (visual sign-off pending)

* Qt Widgets (ADR-005): header with status pill and camera controls, central live view,
  tracking, motion and overlay panels, activity log, diagnostics bar, dark theme with
  green/cyan accents. Every displayed value comes from measured state.
* Evidence: 10 pytest-qt UI tests (start/stop, error display and recovery, scan, overlay and
  mirror controls, resizing keeps aspect ratio, close releases the camera), plus the GUI
  stability session below. Defects found and fixed while verifying the UI: default
  resolution ignored, preview blocked while the model loaded, empty diagnostics at startup,
  empty activity log at a quiet console level, misleading latency right after model load,
  unreadable velocity labels (all with regression tests).

## CP 1.6 - Stability and performance verification: COMPLETED

Commands: `scripts/benchmark_pipeline.py`, `scripts/stability_session.py --minutes 10`.

### 10-minute GUI stability session (real window, webcam and model)

The session starts the camera, restarts it every 2 minutes, resizes the window every
30 s, toggles mirroring and an overlay layer, and finally closes the window.

| Metric | Result |
|---|---|
| Duration | 600.4 s |
| Capture FPS (mean / min) | 30.2 / 27.2 |
| Processing FPS (mean / min) | 30.3 / 27.4 |
| Display FPS (mean / min) | 30.3 / 23.4 |
| Capture-to-result latency (mean / p95 / max of 1 s means) | 15.5 / 19.3 / 22.5 ms |
| Inference time (mean of 1 s means) | 14.9 ms |
| Dropped (stale) frames | 5 in 10 minutes |
| Process CPU (share of all 20 logical cores, mean / max) | 4.1 % / 9.5 % |
| Resident memory (mean / max) | 357 / 374 MB; first-minute mean 365 MB, last-minute mean 336 MB (no growth) |
| Threads | 95-116, stable |
| UI event-loop heartbeat lateness (p99 / max) | 14.3 / 222 ms (one stall, cause not identified) |
| Camera restarts | 4 / 4 successful (stop and restart each observed within the 1 s sampling interval) |
| Warnings / errors logged | none |
| Window close | 0.30 s, camera stopped, no worker thread alive |

This session ran before audit fixes D-1, D-5 and D-9. A second 10-minute session after
the audit fixes gave the same results (30.3 FPS, 16.2 ms mean latency, no UI stall above
40 ms); both are tabulated in `PROJECT_STATUS.md`.

### Camera start and model load

Camera open: 0.24-0.30 s (Media Foundation; DirectShow took 4.3 s, hence the default).
Model load: 0.4-0.6 s warm, 3.3 s cold; the first launch after a reboot was observed to
take up to ~9 s. The preview is live during loading.

### Bottleneck investigation

* Windows execution-speed power throttling roughly doubled inference time and latency
  (ADR-008, three paired runs). The application opts out; with the default, processing ran
  at 26-28 FPS with ~37 ms latency.
* Downscaling frames before inference gave no consistent gain and is off by default.
* Run-to-run variance on this machine is high when other applications are active
  (inference medians of 9-29 ms across runs); results above are from typical desktop use.
