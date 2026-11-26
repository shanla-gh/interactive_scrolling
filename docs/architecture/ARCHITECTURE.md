# Architecture

Version 0.1.0.dev0 (Milestones 0 and 1).

## Data flow

```text
Physical webcam
    |  cv2.VideoCapture (Media Foundation)                 vision/camera.py
    v
Capture thread ── Frame(BGR, index, perf_counter_ns) ──>  core/mailbox.py
    |                     single-slot "latest value" mailbox (drops stale frames)
    v
Processing thread                                          core/pipeline.py
    |  BGR -> RGB (once)
    |  HandTracker.process(rgb, timestamp_ms)              vision/hand_tracker.py (MediaPipe VIDEO mode)
    v
TrackingResult(hands: HandObservation[21x3] + handedness)  vision/landmarks.py
    |
    v
MotionAnalyzer.update(tracking) -> MotionFrame             motion/analyzer.py
    |
    v
ProcessedFrame ──> PipelineListener (worker thread)
    |  PipelineBridge: coalesces frames, emits Qt signals  ui/bridge.py
    v
UI thread: MainWindow -> VideoView.paintEvent              ui/main_window.py, ui/video_view.py
    |  ViewTransform (letterbox + mirror)                  visualization/geometry.py
    v  OverlayRenderer (QPainter)                          visualization/overlay.py
Screen
```

## Packages and responsibilities

| Package | Responsibility | May depend on |
|---|---|---|
| `config` | Typed, validated settings dataclasses | standard library only |
| `core` | Clock/rate meters, mailbox, threaded pipeline, process diagnostics, OS tuning | `config`, `vision`, `motion` (no Qt, no MediaPipe) |
| `vision` | Camera acquisition, landmark data model, MediaPipe adapter, model assets | `config`, `core.timing` (no Qt) |
| `motion` | Timestamp-based displacement/velocity/direction, smoothing, trails | `config`, `vision.landmarks` (no Qt, no OpenCV) |
| `visualization` | Source-to-view geometry (pure) and QPainter overlay renderer | `vision`, `motion`, `config`, QtGui |
| `ui` | Qt Widgets window, panels, theme, worker-to-UI bridge | everything above |
| `app` | Argument parsing, logging, object wiring, entry point | everything |

These boundaries are enforced by `tests/unit/test_architecture.py`, which also asserts that
MediaPipe is imported only by `vision/hand_tracker.py`.

## Threads and ownership

| Thread | Lifetime | Owns |
|---|---|---|
| UI (main) | application | all Qt objects, `VideoView`, panels, timers |
| `vision-processing` | `VisionPipeline.launch()` .. `shutdown()` | `MotionAnalyzer`, the active `HandTracker` |
| `tracker-loader` | until the model is loaded | creates the `HandTracker`, then hands it to the processing thread |
| `camera-capture-N` | one per camera session | the `OpenCVCamera` (opened and released on this thread) |
| `camera-scan` | one per user-initiated scan | temporary capture devices |

Cross-thread communication uses only: the frame mailbox (capture -> processing), the
listener callbacks (processing/capture -> bridge), and Qt queued signals (bridge -> UI).
The bridge coalesces frames so the UI event queue never accumulates frames.

## Lifecycle

* **Start camera**: increments the session number, spawns a capture thread; the thread opens
  the device and reports `RUNNING`, or `ERROR` with a user-readable message.
* **Stop camera**: non-blocking. Sets the session's stop event; the capture thread releases
  the device and reports `STOPPED`. The UI clears the image and overlay and ignores late
  frames from the stopped session.
* **Shutdown** (window close): stops the camera, stops the processing thread, joins all
  threads (5 s timeout each) and closes the tracker.
* **Failures**: an unopenable camera, a camera that delivers no frames (30 consecutive read
  failures) and unexpected exceptions all end the session with `ERROR`; the user can retry.
  A missing model leaves the preview working with tracking marked unavailable. Ten
  consecutive inference failures disable tracking without stopping the preview.

## Coordinate systems

| Space | Definition | Used by |
|---|---|---|
| Normalized source | `x, y` in [0, 1] of the **unmirrored** frame, origin top-left, y down | `HandObservation.landmarks` |
| Source pixels | normalized x width/height | motion analysis (isotropic distances) |
| View | widget pixels after letterboxing and optional mirroring | rendering only |

Inference always runs on the unmirrored frame, so handedness is the user's real hand
(MediaPipe documents that mirrored input inverts handedness; this is verified by
`tests/integration/test_mediapipe_tracker.py`). Mirroring is applied only by
`ViewTransform` and, for direction labels, by `Direction.mirrored()`.

## Timestamps and units

* Timestamps: integer nanoseconds from `time.perf_counter_ns()` (QueryPerformanceCounter),
  taken immediately after each frame is read. `time.monotonic()` is not used because its
  resolution on Windows is 15.6 ms.
* MediaPipe receives `timestamp_ns // 1e6` (ms), forced strictly increasing.
* Velocities: px/s (source pixels) and palm lengths per second, where one palm length is the
  measured wrist to middle-finger-MCP distance. No metric (m/s) velocities are reported.
* Latency: capture timestamp to end of processing, in ms.

## Motion analysis

See the module docstring of `motion/analyzer.py`. Summary: time-constant exponential
smoothing of positions (tau = 40 ms) and velocities (tau = 60 ms); moving/stationary
classification with hysteresis (0.6 / 0.35 palms/s); greedy nearest-neighbour track
association by palm position with a handedness penalty; tracks discarded after 250 ms
without observations; jumps over 3 palm lengths restart a track. Eight-way direction
classification in 45-degree sectors.
