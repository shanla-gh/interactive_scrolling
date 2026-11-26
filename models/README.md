# models

Downloaded model files live here and are not committed to Git.

Run `python scripts/download_model.py` to fetch `hand_landmarker.task` (MediaPipe Hand
Landmarker, Apache 2.0) and verify its SHA-256 digest. Details and the pinned URL are in
[docs/THIRD_PARTY_NOTICES.md](../docs/THIRD_PARTY_NOTICES.md).

To use a model stored elsewhere, pass `--model PATH` or set `INTERACTIVE_SCROLLING_MODEL`.
