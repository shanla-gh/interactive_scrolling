"""Location, verification and one-time download of the local MediaPipe models.

Model files are not stored in the repository. Each is downloaded once from Google's official
MediaPipe model storage, verified against a pinned SHA-256 digest, and then used fully offline.

* Hand Landmarker (``hand_landmarker.task``, float16, version 1) - required.
* Selfie Segmenter, landscape (``selfie_segmenter_landscape.tflite``, float16, version 1) -
  optional, only for the transparent background of the Content Creator overlay.
* Face Landmarker (``face_landmarker.task``, float16, version 1) - optional, only for the
  Progressive Clown Transformation and passive eye analytics.

All are published by Google under the Apache License 2.0 and declare surveillance and identity
recognition out of scope; see ``docs/THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

log = logging.getLogger(__name__)

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL_SIZE_BYTES = 7_819_105
MODEL_ENV_VAR = "INTERACTIVE_SCROLLING_MODEL"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
"""Repository root when running from a source checkout (``src/`` layout)."""


@dataclass(frozen=True, slots=True)
class ModelAsset:
    key: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    description: str
    env_var: str
    required: bool = False

    def path(self) -> Path:
        """``$<env_var>``, then ``<repository>/models/<file>``, ``./models/<file>``, and the
        folder of a packaged executable; the first existing file wins."""
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        candidates = [
            PROJECT_ROOT / "models" / self.filename,
            Path.cwd() / "models" / self.filename,
        ]
        frozen = getattr(sys, "_MEIPASS", None)
        if frozen:
            candidates.insert(0, Path(frozen) / "models" / self.filename)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def available(self) -> bool:
        return self.path().is_file()


HAND_MODEL = ModelAsset(
    "hand",
    MODEL_FILENAME,
    MODEL_URL,
    MODEL_SHA256,
    MODEL_SIZE_BYTES,
    "MediaPipe Hand Landmarker",
    MODEL_ENV_VAR,
    required=True,
)
SEGMENTER_MODEL = ModelAsset(
    "segmenter",
    "selfie_segmenter_landscape.tflite",
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter_landscape/float16/1/selfie_segmenter_landscape.tflite",
    "490e9ea734313e0de10fa0cd9e3c6133e36ea4db2b7a49bde9ef019f72796b8e",
    250_177,
    "MediaPipe Selfie Segmenter (landscape)",
    "INTERACTIVE_SCROLLING_SEGMENTER_MODEL",
)
FACE_MODEL = ModelAsset(
    "face",
    "face_landmarker.task",
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task",
    "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    3_758_596,
    "MediaPipe Face Landmarker",
    "INTERACTIVE_SCROLLING_FACE_MODEL",
)
MODELS = (HAND_MODEL, SEGMENTER_MODEL, FACE_MODEL)


class ModelDownloadError(RuntimeError):
    """The model could not be downloaded or failed verification."""


def default_model_path() -> Path:
    """Resolve the model location.

    Order: the ``INTERACTIVE_SCROLLING_MODEL`` environment variable, then
    ``<repository>/models/hand_landmarker.task``, then ``./models/hand_landmarker.task``.
    The first existing file wins; if none exists the repository location is returned so
    error messages and downloads point to the expected place.
    """
    return HAND_MODEL.path()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(path: Path, expected_sha256: str = MODEL_SHA256) -> bool:
    """Return ``True`` if ``path`` exists and matches the pinned digest."""
    return path.is_file() and sha256_of(path) == expected_sha256


Opener = Callable[[str], BinaryIO]


def _urlopen(url: str) -> BinaryIO:
    return urllib.request.urlopen(url, timeout=60)


def download_model(
    destination: Path,
    url: str = MODEL_URL,
    expected_sha256: str = MODEL_SHA256,
    opener: Opener = _urlopen,
) -> Path:
    """Download the model to ``destination`` and verify its SHA-256 digest.

    The file is written to a temporary file in the destination directory and only
    moved into place after verification, so a failed or interrupted download never
    leaves a corrupt model behind.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            try:
                with opener(url) as response:
                    for chunk in iter(lambda: response.read(1 << 16), b""):
                        digest.update(chunk)
                        out.write(chunk)
            except OSError as exc:
                raise ModelDownloadError(f"Download failed: {exc}") from exc
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise ModelDownloadError(
                f"Downloaded model failed verification (sha256 {actual}, expected "
                f"{expected_sha256})."
            )
        os.replace(tmp_path, destination)
        log.info("Model downloaded and verified: %s", destination)
        return destination
    finally:
        tmp_path.unlink(missing_ok=True)
