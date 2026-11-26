# Architecture decision records

Each record states the decision, the alternatives considered and the trade-offs.

## ADR-001 Python 3.12 in a project-local virtual environment

* **Decision**: Python 3.12, `.venv/` inside the repository, exact pins in
  `requirements.txt` / `requirements-dev.txt`, compatible ranges in `pyproject.toml`.
* **Why**: 3.12 is installed on the target machine and supported by every dependency. A
  local venv avoids system-wide installs. Exact pins make installations reproducible.
* **Trade-off**: pins must be refreshed deliberately. Only Windows x64 / CPython 3.12 is tested.

## ADR-002 MediaPipe Tasks Hand Landmarker 1.2.3 in VIDEO mode

* **Decision**: `mediapipe==1.2.3` (Tasks API; the legacy `solutions` API no longer
  ships), `hand_landmarker.task` float16 v1, `RunningMode.VIDEO`.
* **Alternatives**: `LIVE_STREAM` mode (asynchronous callbacks) or `IMAGE` mode.
* **Why**: VIDEO mode is synchronous, which keeps frame/result pairing and timestamps
  trivial, and it reuses the previous frame's hand region instead of running palm detection
  on every frame. Our own capture/processing threads already provide asynchrony.
* **Trade-off**: inference blocks the processing thread; mitigated by dropping stale frames.

## ADR-003 opencv-contrib-python 4.12 (not opencv-python, not 5.x)

* **Decision**: depend on `opencv-contrib-python==4.12.0.88`.
* **Why**: mediapipe 1.2.3 already requires `opencv-contrib-python`; installing
  `opencv-python` as well would install two packages providing `cv2`. The 4.x line was
  chosen over the new 5.x major release to stay on the series mediapipe has been used with;
  4.12 also constrains numpy to `<2.3`, giving numpy 2.2.6.

## ADR-004 Two worker threads and a latest-value mailbox

* **Decision**: a capture thread reads continuously and publishes into a single-slot
  mailbox; a processing thread always takes the newest frame.
* **Alternatives**: single thread read-then-infer; unbounded `queue.Queue`.
* **Why**: read-then-infer lets frames pile up in the driver buffer (latency grows) and
  halves the frame rate when inference approaches the frame interval. An unbounded queue
  grows without limit. The mailbox bounds both memory and latency; drops are counted and shown.
* **Trade-off**: under heavy load the processed frame rate is lower than the capture rate.

## ADR-005 Qt Widgets with QPainter rendering (not QML, not OpenCV drawing)

* **Decision**: Qt Widgets; the overlay is drawn with QPainter in `VideoView.paintEvent`
  using the same `ViewTransform` as the video image.
* **Alternatives**: QML/Qt Quick; drawing the overlay into the frame with OpenCV.
* **Why**: Widgets keep the whole UI in one language with straightforward testing
  (pytest-qt, offscreen rendering). QPainter gives anti-aliased lines and fonts at the
  display resolution, so the overlay stays crisp at any window size, and overlay toggles
  apply instantly without reprocessing. OpenCV drawing would scale with the image (blurry
  lines) and has poor text rendering. QML would add a second language and a scene graph
  this milestone does not need.
* **Trade-off**: painting happens on the UI thread (measured: ~30 FPS display with spare
  capacity on the development machine).

## ADR-006 Framework-free core

* **Decision**: `config`, `core`, `vision` and `motion` do not import Qt; the pipeline
  reports through a plain listener protocol and `ui/bridge.py` adapts it to Qt signals.
* **Why**: the future gesture engine and platform controllers can consume tracking and
  motion data without a GUI, and the logic is testable without Qt.

## ADR-007 Motion in source pixels with palm-length normalization

* **Decision**: positions in source pixels; speeds also reported in palm lengths per second.
* **Why**: pixels are isotropic (normalized coordinates are not when the frame is not square).
  Palm-length units make thresholds roughly independent of distance to the camera. Metric
  velocities would need calibration and depth, so they are deliberately not reported.

## ADR-008 Opt out of Windows execution-speed power throttling

* **Decision**: at startup the application calls
  `SetProcessInformation(ProcessPowerThrottling)` to opt out of execution-speed throttling
  (EcoQoS). `--allow-power-throttling` keeps the Windows default.
* **Evidence**: three alternating A/B pairs of the headless benchmark at 1280x720
  (10 s each, same machine, plugged in):

  | Throttling | Inference median (ms) | Processing FPS | Latency mean (ms) |
  |---|---|---|---|
  | Windows default | 28.7 / 26.0 / 27.7 | 27.5 / 28.1 / 26.0 | 37.3 / 37.3 / 37.7 |
  | Opted out | 21.7 / 17.5 / 8.7 | 30.2 / 30.3 / 29.9 | 20.5 / 19.9 / 11.1 |

  The same model needs ~15 ms in a tight loop, so the default-mode slowdown was not compute
  bound: CPU use was only ~5 % of the machine.
* **Trade-off**: somewhat higher power use while the application runs. This only affects
  this process and is reversible by the flag.
* **Rejected alternative**: downscaling frames before inference. Benchmarks showed no
  consistent gain (MediaPipe resizes internally to 192/224 px), so it is available as the
  `inference_max_width` setting but disabled by default.

## ADR-009 Model downloaded on setup, not committed

* **Decision**: the model is fetched once by `scripts/download_model.py` from a pinned,
  versioned Google URL and verified by SHA-256; `models/` is ignored by Git.
* **Why**: keeps binary artifacts out of the repository while guaranteeing integrity and
  fully offline operation afterwards. Apache-2.0 would allow redistribution, but that is
  unnecessary for a source repository.

## ADR-010 Camera discovery only on explicit user action

* **Decision**: the camera list is populated by a "Scan" button that probes indices 0-4
  through OpenCV. Nothing opens a camera before the user asks.
* **Why**: OpenCV cannot list device names, and Qt Multimedia returned no devices on the
  target machine. Probing opens each device briefly, which must be user-initiated for privacy.
* **Trade-off**: entries are labelled "Camera N (WxH)" rather than with device names.
