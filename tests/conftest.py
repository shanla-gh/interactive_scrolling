"""Shared pytest configuration.

Test categories
---------------
* ``tests/unit``         fast, hardware-independent tests of individual modules.
* ``tests/integration``  several modules together (pipeline, UI, real model on still images).
* ``tests/regression``   one test per fixed defect, named after the defect.
* ``tests/hardware``     require a physical webcam; skipped unless ``--hardware`` is given.

Markers: ``hardware`` (physical webcam), ``model`` (downloaded model file), ``network``
(public test image download), ``browser`` (Microsoft Edge with the extension, offline fixture
pages), ``live_youtube`` (the real YouTube website; opt in with ``--live-youtube``). Missing
prerequisites skip with an explicit reason.
"""

from __future__ import annotations

import os

# Qt must use the offscreen platform in headless test runs (CI, terminals).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import hashlib
import urllib.request
from pathlib import Path

import pytest

from interactive_scrolling.vision.model_assets import default_model_path, verify_model

CACHE_DIR = Path(__file__).parent / ".cache"

# Public sample image published by the MediaPipe project for its hand landmarker examples.
# It is downloaded on demand and never committed to the repository.
SAMPLE_HANDS_URL = "https://storage.googleapis.com/mediapipe-assets/woman_hands.jpg"
SAMPLE_HANDS_SHA256 = "70cbeb38e198c9862202e0979c21a99b40ca980d3e7b250176c85b1636a40f12"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="run tests that need a physical webcam",
    )
    parser.addoption(
        "--live-youtube",
        action="store_true",
        default=False,
        help="run tests against the real YouTube website (signed-out throw-away profile)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_hw = pytest.mark.skip(reason="needs a physical webcam; run with --hardware")
    skip_live = pytest.mark.skip(reason="uses the real YouTube website; run with --live-youtube")
    for item in items:
        if "hardware" in item.keywords and not config.getoption("--hardware"):
            item.add_marker(skip_hw)
        if "live_youtube" in item.keywords and not config.getoption("--live-youtube"):
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def model_path() -> Path:
    path = default_model_path()
    if not verify_model(path):
        pytest.skip(f"hand landmarker model not available at {path}; run scripts/download_model.py")
    return path


@pytest.fixture(scope="session")
def sample_hands_image_path() -> Path:
    """Path to MediaPipe's public two-hands sample photo, downloaded once and cached."""
    CACHE_DIR.mkdir(exist_ok=True)
    target = CACHE_DIR / "woman_hands.jpg"
    if not target.is_file():
        try:
            with urllib.request.urlopen(SAMPLE_HANDS_URL, timeout=30) as response:
                data = response.read()
        except OSError as exc:
            pytest.skip(f"sample image could not be downloaded (offline?): {exc}")
        if hashlib.sha256(data).hexdigest() != SAMPLE_HANDS_SHA256:
            pytest.fail("downloaded sample image does not match the pinned SHA-256 digest")
        target.write_bytes(data)
    return target
