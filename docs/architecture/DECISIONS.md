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

## ADR-011 YouTube control through a companion extension and a loopback bridge

* **Decision**: a minimal Manifest V3 extension performs actions in the Shorts page and
  confirms them from page state; the app talks to it over a WebSocket on 127.0.0.1 that accepts
  only the extension's fixed origin and a pairing code.
* **Alternatives**: synthetic key presses (no context or outcome information, no reliable like
  shortcut), browser remote debugging (far too much control), native messaging (extra host
  executable and registry entries). Details: `YOUTUBE_INTEGRATION.md`.
* **Trade-off**: one-time manual extension installation; dependency on YouTube's markup,
  mitigated by honest failed/unknown outcomes.

## ADR-012 Rule-based gestures calibrated on labeled recordings

* **Decision**: transparent rules (pose flexion, distances and speeds in palm lengths, explicit
  lifecycles) instead of a trained classifier; thresholds from recordings of real gestures.
* **Why**: explainable rejection reasons, no confidence numbers that would be invented, easy
  tuning through presets, and no training data beyond a few minutes of recordings.

## ADR-013 Finger swipe = moving pointing hand, not a finger flick

* **Evidence**: in the recordings a flick and its return (or its preparation) were the same
  motion with the same speed and dwell, so no rule can tell an intended swipe from its return.
  Moving the pointing hand, with a return window measured from the end of the movement,
  recognized 8/8 intended swipes and no returns.

## ADR-014 Safety-first action dispatch

* **Decision**: start in Tracking only; explicit Live control; one action at a time; stale
  events and events from an earlier mode generation are never executed; success only when
  confirmed; system-wide emergency shortcut.

## ADR-015 Minimal local analytics in SQLite

* **Decision**: standard-library SQLite on a writer thread, one row per event category, local
  day stored with each event; no browsing or camera data. Enough for the approved daily
  statistics and future reports, without a reporting engine.

## ADR-016 One four-direction index-swipe recognizer with a settle-based return phase

* **Decision**: a single recognizer follows the pointing hand's index fingertip in 2D, commits
  the direction (dominant axis) at the stroke start, rejects movements between the axes and
  shares one threshold set for all directions. After a swipe, every opposite stroke is part of
  the return until the fingertip is back near the start *and has paused* (or 1.2 s passed).
* **Alternatives**: two axis recognizers (vertical finger, horizontal open hand) as in 0.2; a
  position-only return rule; a long fixed cooldown; a resting "arming dwell" before strokes.
* **Evidence**: replayed recordings - pointing swipes 8/8 at all presets and mirrored, 0 false
  triggers in 190 s of negatives. The position-only rule produced a false opposite swipe at the
  HIGH preset (multi-part, overshooting return; regression test). The arming dwell lost real
  swipes (up 4/4 -> 3/4 at 0.1 s) without fixing back-and-forth ambiguity.
* **Trade-off**: an opposite swipe right after a return needs a brief pause; preparation
  movements made while already pointing remain ambiguous (GESTURES.md, verification pending).

## ADR-017 Half-heart from image-space geometry, not a trained classifier

* **Decision**: a curved, downward-hooking index, a downward thumb, separated tips and an
  upright hand, held 0.6 s.
* **Why**: no labeled half-heart data exists; explicit geometry is explainable, separates the
  listed confusions (pointing, pinch, thumbs up, fist, sideways C) and can be tuned once the
  Director's recording exists. A neural network would need data that is not available and
  could not be validated.
* **Trade-off**: a vertical C-shaped hand that happens to match the heart's geometry is
  indistinguishable by construction; the hold and stillness requirements limit accidental use.

## ADR-018 Tab navigation through the existing extension, gated on browser focus

* **Decision**: tab switching is an extension command that activates the neighbouring tab of
  the focused window, available only while the browser is the active application, with no
  wrap-around and no new permissions.
* **Alternatives**: synthetic Ctrl+Tab key presses (could reach whatever application has focus,
  no confirmation), Windows application switching (removed from the product).
* **Trade-off**: a user who focuses the Interactive Scrolling window cannot switch browser tabs
  by gesture until the browser is focused again; this is intended.
