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

## Optional models (Brief 003)

| Item | Selfie Segmenter (landscape) | Face Landmarker |
|---|---|---|
| File | `selfie_segmenter_landscape.tflite` (float16, version 1) | `face_landmarker.task` (float16, version 1: BlazeFace short range, Face Mesh V2, Blendshape V2) |
| Source | `https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter_landscape/float16/1/selfie_segmenter_landscape.tflite` | `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task` |
| SHA-256 | `490e9ea734313e0de10fa0cd9e3c6133e36ea4db2b7a49bde9ef019f72796b8e` (250,177 bytes) | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` (3,758,596 bytes) |
| Publisher | Google (MediaPipe) | Google (MediaPipe) |
| License | Apache License 2.0 (model card on Google AI Edge / Hugging Face `litert-community`, Nov 2026) | Apache License 2.0 (same source) |
| Declared out of scope | surveillance and identity recognition | surveillance and identity recognition; the landmarks "do not provide facial recognition or identification" |

Use in this project: the segmenter only makes the background of the Content Creator overlay
transparent (presentation only); the face landmarker only drives the clown makeup and passive,
aggregated eye estimates. No identification, no stored images or landmarks. Both are optional,
downloaded with the hand model by `scripts/download_model.py`, and bundled in packaged builds
together with this notice and the Apache 2.0 license text.

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
