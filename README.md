# interactive_scrolling

Control your computer with natural hand gestures, using nothing but a standard laptop webcam.
All computer vision runs locally on your machine.

> **Status: early development (v0.1.0.dev0).** The computer vision foundation is working:
> live webcam capture, real-time hand tracking, skeleton visualization and measured motion
> vectors. Gesture recognition and app control (YouTube Shorts, Windows) are planned and
> **not implemented yet**.

## What it does today

* **Live webcam view** with start/stop control, camera selection (user-initiated scan),
  resolution choice and an optional mirrored preview.
* **Real-time hand tracking** with Google's MediaPipe Hand Landmarker: up to two hands,
  21 landmarks per hand, left/right handedness with the model's score.
* **Hand skeleton overlay** aligned to your hand at any window size: landmarks, anatomical
  bone connections, bounding boxes, handedness labels, separate colours per hand.
* **Motion analysis** computed from timestamped observations: index-fingertip and palm
  displacement, velocity, speed and 8-way direction, smoothed and noise-filtered, with
  fading motion trails and velocity arrows drawn on the video.
* **Diagnostics** from measured state: capture, processing and display FPS, inference time,
  capture-to-result latency, dropped frames, CPU and memory use, and an activity log.
* Every overlay layer can be switched on and off.

## Planned (not yet implemented)

* Gesture recognition engine (swipes, thumbs-up, pinch, ...).
* YouTube Shorts control: next/previous video, like, play/pause.
* Switching between applications with directional swipes.
* Floating webcam overlay for content creators; customizable gesture mappings.

See [ROADMAP.md](ROADMAP.md).

## Requirements

* Windows 10/11 x64 with a webcam (development and testing happen on Windows 11).
* Python 3.12 (python.org or Microsoft Store) with the `py` launcher.
* No GPU required. About 1 GB of disk space for the virtual environment.

## Installation

```powershell
git clone https://github.com/shanla-gh/interactive_scrolling.git
cd interactive_scrolling
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

The setup script creates `.venv\`, installs the exact tested dependency versions from
`requirements-dev.txt`, installs the project in editable mode and downloads the hand
landmark model (~7.8 MB, verified by SHA-256) into `models\`. This is the only step that
needs the internet. Manual equivalent:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe scripts\download_model.py
```

## Usage

```powershell
scripts\run.ps1
# or
.venv\Scripts\python.exe -m interactive_scrolling
```

Click **Start camera**. Useful options:

| Option | Meaning |
|---|---|
| `--camera N` | camera index (default 0) |
| `--resolution 1280x720` | requested capture resolution |
| `--no-mirror` | start with an unmirrored preview |
| `--auto-start` | start the camera immediately |
| `--max-hands 1` | track at most one hand |
| `--backend dshow` | use DirectShow instead of Media Foundation |
| `--allow-power-throttling` | keep Windows' default power throttling (see below) |

On Windows the application opts its own process out of *execution-speed power throttling*,
which otherwise roughly doubled tracking latency on the development machine
([ADR-008](docs/architecture/DECISIONS.md)).

If the camera cannot be opened, the application shows the reason. Check that no other
app is using the camera and that desktop apps are allowed to use it under
*Settings > Privacy & security > Camera*.

## Development

```powershell
scripts\test.ps1             # ruff format check, ruff lint, all hardware-independent tests
scripts\test.ps1 -Hardware   # additionally run tests that use the physical webcam
.venv\Scripts\python.exe scripts\benchmark_pipeline.py --duration 30
.venv\Scripts\python.exe scripts\stability_session.py --minutes 10 --output reports\stability.json
```

Read [docs/ENGINEERING_CONVENTIONS.md](docs/ENGINEERING_CONVENTIONS.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) before contributing. Architecture:
[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md). Current state:
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Technology

Python 3.12 · MediaPipe Tasks 1.2.3 (Hand Landmarker) · OpenCV 4.12 · NumPy 2.2 ·
PySide6 / Qt 6.10 (Widgets) · psutil · pytest, pytest-qt, ruff.

## Privacy

* Video is processed in memory on your computer and discarded frame by frame.
* Nothing is recorded, saved, uploaded or sent anywhere. There is no telemetry.
* The camera is only opened when you click *Start camera* or *Scan*.
* The only network access is the one-time model download during setup.

## Known limitations

* Tested only on Windows 11 with one integrated laptop webcam.
* OpenCV cannot read camera names, so cameras are listed by index.
* Tracking quality depends on lighting and on the hand being clearly visible; gloves and heavy
  occlusion reduce accuracy (as documented in the model card).
* Speeds are reported in pixels and palm lengths per second, not physical units.
* Settings are not yet saved between sessions.
* No gesture-driven actions exist yet.

## License

MIT, see [LICENSE](LICENSE). Third-party components and the MediaPipe model (Apache 2.0)
are listed in [docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md).
