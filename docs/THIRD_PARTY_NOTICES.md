# Third-party notices

Interactive Scrolling is released under the MIT License (see `LICENSE`). It depends on the
third-party components below. None of them are copied into this repository; they are
installed from PyPI (or, for the model, downloaded from Google) by the setup process.

## Hand landmark model

| Item | Value |
|---|---|
| File | `hand_landmarker.task` (MediaPipe Hand Landmarker, float16, version 1) |
| Source | `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` |
| SHA-256 | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` (7,819,105 bytes) |
| Publisher | Google (MediaPipe) |
| License | Apache License 2.0. The official model card *"Model Card Hand Tracking (Lite_Full) with Fairness, Oct 2021"* states "LICENSED UNDER Apache License, Version 2.0". |

The model is **not** stored in this repository. `scripts/download_model.py` downloads it once,
verifies the SHA-256 digest and places it in `models/` (ignored by Git). If you redistribute
the model (for example in a packaged release), include the Apache 2.0 license text and
Google's attribution.

The model card lists the intended uses as *mobile AR, gesture recognition and hand control*
and declares surveillance and identity recognition out of scope. This project uses the model
only for local hand-control interaction, consistent with those terms.

## Python packages (direct dependencies)

| Package | Version | License |
|---|---|---|
| mediapipe | 1.2.3 | Apache-2.0 |
| opencv-contrib-python | 4.12.0.88 | Apache-2.0 (OpenCV); wheels bundle FFmpeg and other components under their own licenses |
| numpy | 2.2.6 | BSD-3-Clause |
| PySide6 (Qt for Python) | 6.10.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| psutil | 7.2.2 | BSD-3-Clause |
| websockets | 15.0.1 | BSD-3-Clause |

Notable transitive dependencies (pulled in by mediapipe): matplotlib (PSF-based Matplotlib
license), sounddevice (MIT), absl-py (Apache-2.0), flatbuffers (Apache-2.0), certifi
(MPL-2.0), pillow (MIT-CMU). The full pinned set is in `requirements.txt`.

### Qt / PySide6 (LGPL)

PySide6 is used under the LGPL-3.0 as an unmodified, dynamically loaded package installed by
pip. A future bundled Windows release (milestone M6) must keep the Qt libraries replaceable by
the user and ship the LGPL license text and a notice of where to obtain the Qt source.

## Test assets

The integration tests download MediaPipe's public example photo
`https://storage.googleapis.com/mediapipe-assets/woman_hands.jpg` into `tests/.cache/`
(ignored by Git) and verify its SHA-256 digest. Its licence is not documented by the
MediaPipe documentation, so it is never committed or redistributed by this project.
