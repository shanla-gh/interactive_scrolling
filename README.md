# interactive_scrolling

Control your computer with natural hand gestures, using nothing but a standard laptop webcam.
All computer vision runs locally on your machine.

> **Status: development build (v0.2.0.dev0).** Hand tracking, gesture recognition and
> YouTube Shorts control work and are tested; live use with a real YouTube account is awaiting
> the project owner's sign-off. Windows application switching, the content-creator overlay,
> Anti-Doomscroll features and reports are planned and **not implemented yet**.

## What it does today

* **Live webcam view** with an aligned hand skeleton, landmarks, bounding boxes, handedness
  labels, motion trails and velocity arrows; camera selection, resolution and mirroring.
* **Gesture recognition** (rule based, calibrated on recordings of real gestures):

  | Gesture | How | Action |
  |---|---|---|
  | Swipe down | point with your index finger and move the whole hand down | Next Short |
  | Swipe up | the same, upwards | Previous Short |
  | Thumbs up | hold still about half a second | Like the Short |
  | Stop | open hand, fingers up, palm to the camera, hold still | Pause / resume |
  | Hand sweep left / right | open hand, big fast sweep | recognized only (app switching is planned) |

* **Safe control modes**: *Tracking only* (default), *Gesture test* (gestures shown, nothing
  executed) and *Live control* (explicitly enabled). Emergency stop with the *Disable* button,
  Esc, or **Ctrl+Alt+D** anywhere in Windows.
* **YouTube Shorts control** in Microsoft Edge or Google Chrome through a small companion
  extension: next, previous, like (never unlikes) and pause/resume, each confirmed from the page
  and reported as succeeded, no change, rejected, failed or unknown.
* **Gesture history and daily statistics** (gestures, successful actions, rejections, time a
  Shorts tab was visible), stored only on your computer, with an opt-out and a clear button.
* **Settings**: sensitivity presets, thresholds, enabled gestures, control hand, gesture-to-action
  mapping; saved between sessions.
* **Diagnostics** from measured state: FPS, latency, dropped frames, CPU, memory, activity log.

## Requirements

* Windows 10/11 x64 with a webcam (developed and tested on Windows 11).
* Python 3.12 with the `py` launcher.
* For YouTube control: Microsoft Edge or Google Chrome.

## Installation

```powershell
git clone https://github.com/shanla-gh/interactive_scrolling.git
cd interactive_scrolling
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

The setup script creates `.venv\`, installs the pinned dependencies and downloads the hand
landmark model (~7.8 MB, verified by SHA-256). This is the only step that needs the internet.

### Browser extension (for YouTube control)

1. Start the app and open its **YouTube** tab; copy the pairing code.
2. Open `edge://extensions` (or `chrome://extensions`), enable **Developer mode**, choose
   **Load unpacked** and select the `browser_extension` folder of this repository.
3. Click the extension icon, paste the pairing code and choose **Save and connect**.

Details and the security model: [docs/architecture/YOUTUBE_INTEGRATION.md](docs/architecture/YOUTUBE_INTEGRATION.md).

## Usage

```powershell
scripts\run.ps1
```

Click **Start camera**, choose **Gesture test** to practise (see the gesture banner and the
history), then open a YouTube Shorts page and choose **Live control**. Gesture details and
limitations: [docs/architecture/GESTURES.md](docs/architecture/GESTURES.md).

Useful options: `--camera N`, `--resolution 1280x720`, `--no-mirror`, `--auto-start`,
`--max-hands 1`, `--backend dshow`, `--allow-power-throttling`.

## Development

```powershell
scripts\test.ps1                 # format check, lint, all hardware-independent tests
scripts\test.ps1 -Hardware       # additionally the physical webcam tests
.venv\Scripts\python.exe -m pytest --live-youtube tests\live          # real website (opt-in)
.venv\Scripts\python.exe scripts\stability_session.py --minutes 10
.venv\Scripts\python.exe scripts\record_gestures.py      # labeled calibration recording
.venv\Scripts\python.exe scripts\evaluate_gestures.py recordings\<file>.json
```

Read [docs/ENGINEERING_CONVENTIONS.md](docs/ENGINEERING_CONVENTIONS.md) first. Architecture:
[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md). Current state:
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Technology

Python 3.12 · MediaPipe Tasks 1.2.3 · OpenCV 4.12 · NumPy 2.2 · PySide6 / Qt 6.10 · websockets
15 · SQLite · psutil · Manifest V3 browser extension · pytest, pytest-qt, ruff.

## Privacy

* Video is processed in memory on your computer and discarded frame by frame; nothing is
  recorded, uploaded or sent anywhere, and there is no telemetry.
* The camera opens only when you click *Start camera* or *Scan*.
* The browser connection is local only (127.0.0.1), restricted to this project's extension and a
  pairing code; the extension can only see youtube.com pages and only performs four actions.
* Statistics contain event types, outcomes and timings only: no page addresses, titles, video
  ids, account data or camera data. They can be disabled and cleared.
* No account credentials are used; the extension acts in your normal browser session.

## Known limitations

* Tested on one Windows 11 laptop and one built-in webcam; gestures calibrated on one person.
* Hand sweeps are recognized unreliably for small movements; holding an open hand still for
  0.8 s counts as a stop gesture.
* YouTube control depends on YouTube's current page structure; if it changes, actions are
  reported as failed or unknown rather than successful.
* Chrome needs the extension loaded manually; Firefox is not supported.
* Cameras are listed by index, not by name.

## License

MIT, see [LICENSE](LICENSE). Third-party components and the MediaPipe model (Apache 2.0):
[docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md).
