# Architecture

Version 0.3.0rc1 (Milestones 0-11, Engineering Brief 003).

## Data flow

```text
Physical webcam
    |  cv2.VideoCapture (Media Foundation)                 vision/camera.py
    v
Capture thread ── Frame(BGR, index, perf_counter_ns) ──>  core/mailbox.py (latest value)
    v
Processing thread                                          core/pipeline.py
    |  BGR -> RGB (once); HandTracker.process (original, unmodified frame)
    |  MotionAnalyzer -> GestureEngine (four index swipes, half-heart, stop)
    |      confirmed GestureEvent -> ActionDispatcher (own thread)        actions/
    |          admission checks (Anti-Doomscroll pause, co-op shared cooldown)
    |          -> controller: browser extension bridge (Shorts, tabs)     integrations/youtube/
    |             or, as co-op Guest, the Host over the co-op link        integrations/coop/
    |  frame taps (after tracking, read-only view, never blocking):
    |      segmentation worker (creator transparency)   vision/segmenter.py  core/auxiliary.py
    |      face worker (clown, eye analytics)           vision/face_tracker.py
    v
ProcessedFrame ──> PipelineBridge (coalescing) ──> UI thread                ui/
    Developer window (VideoView), Content Creator overlay, tray icon: views of one runtime
Services activity thread (1 Hz)                                            services.py
    scrolling activity -> sessions (wellbeing/), reminders, cached reports, eye aggregates
    -> SQLite writer thread                                                storage/analytics.py
```

## Packages and responsibilities

| Package | Responsibility | May depend on |
|---|---|---|
| `config` | Typed, validated settings dataclasses | standard library only |
| `core` | Timing, mailbox, pipeline, optional inference workers, stall monitor, diagnostics | `config`, `vision`, `motion`, `gestures` (no Qt, no MediaPipe) |
| `vision` | Camera, landmark model, MediaPipe adapters (hands, segmentation, face), model assets, transparency compositing | `config`, `core.timing` (no Qt) |
| `motion` | Displacement/velocity/direction, smoothing, trails | `config`, `vision.landmarks` |
| `visualization` | View geometry and QPainter renderers (overlay, clown) | `vision`, `motion`, `config`, QtGui (no OpenCV) |
| `gestures` | Pose analysis, recognizers, gesture engine | `config`, `core.timing`, `vision`, `motion` |
| `actions` | Control modes, mapping, dispatcher, controller interface | `gestures`, `config`, `core.timing` |
| `integrations/youtube` | Extension bridge, protocol, browser controller | `actions`, `core.timing` |
| `integrations/coop` | Co-op protocol, host, guest | `actions`, `gestures`, `vision.landmarks` |
| `storage` | Settings store (with migration), analytics store | `config`, `actions`, `gestures` |
| `wellbeing` | Sessions, reports, Doomscroll Index, reminders, eye analytics (pure logic) | `config`, `storage`, `vision.face_tracker` data types |
| `services` | Composition of engine, dispatcher, bridge, analytics, wellbeing, co-op | all non-UI packages |
| `ui` | Qt windows, panels, overlay, tray, dialogs, Wrapped | everything above |
| `app` | Argument parsing, logging, object wiring, entry point | everything |

Boundaries are enforced by `tests/unit/test_architecture.py`; MediaPipe is imported only by the
three adapters in `vision/` (`hand_tracker.py`, `segmenter.py`, `face_tracker.py`).

## Threads and ownership

| Thread | Lifetime | Owns |
|---|---|---|
| UI (main) | application | Qt objects, both windows, tray, timers |
| `vision-processing` | application | motion analyzer, hand tracker, gesture engine |
| `tracker-loader` | until loaded | creates the hand tracker |
| `camera-capture-N` | one per camera session | the camera device |
| `aux-segmentation`, `aux-face landmarks` | application (idle while disabled) | their model, loaded only while enabled |
| `action-dispatcher` | application | queued action, controller calls |
| `browser-bridge` + connection threads | application | extension WebSocket server |
| `coop-host` / `coop-guest`, `coop-ping` | while a co-op session exists | co-op connection |
| `activity` | application | activity tracker, reminders, cached reports |
| `analytics-writer` | application | SQLite connection |
| `stall-monitor` | application | UI stall watchdog |

Cross-thread data: immutable records, lock-protected state, single-slot mailboxes and Qt queued
signals. Presentation modes (Developer, Content Creator, Background) only show or hide windows;
they never start or stop the camera, the models, the dispatcher or the bridge, and the global
emergency shortcut works in every mode.

## Lifecycle

* Start / stop camera: as in 0.2 (non-blocking stop, session numbers discard late frames).
* Optional workers: enabled when their feature is on and visible (transparent overlay shown,
  clown or eye analytics enabled); disabling closes the model.
* Shutdown (main window close, tray or overlay *Quit*): emergency disable, overlay and tray
  closed, workers shut down, pipeline shut down (camera released), co-op left/ended, activity
  interval closed, eye aggregates flushed, analytics closed, then the process exits.

## Coordinates and timestamps

Unchanged: landmarks in normalized coordinates of the unmirrored frame; mirroring is display
only (`ViewTransform`); timestamps are `perf_counter_ns`; reports use wall-clock seconds.

## Related documents

[GESTURES.md](GESTURES.md), [YOUTUBE_INTEGRATION.md](YOUTUBE_INTEGRATION.md),
[REPORTING.md](REPORTING.md), [COOP.md](COOP.md), [UI_AND_EFFECTS.md](UI_AND_EFFECTS.md),
[DECISIONS.md](DECISIONS.md).
