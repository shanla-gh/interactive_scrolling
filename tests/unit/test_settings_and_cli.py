"""Configuration validation and command-line parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from interactive_scrolling.app import build_settings, parse_args
from interactive_scrolling.config.settings import (
    AppSettings,
    CameraBackend,
    ConfigError,
    OverlaySettings,
    TrackingSettings,
)


def test_defaults_are_valid() -> None:
    settings = AppSettings()
    assert settings.camera.index == 0
    assert (settings.camera.width, settings.camera.height) == (1280, 720)
    assert settings.camera.backend is CameraBackend.MSMF
    assert settings.mirror_preview
    overlay = OverlaySettings()
    assert overlay.show_skeleton and overlay.show_landmarks and overlay.show_vectors
    assert not overlay.show_palm_trail  # off by default to reduce clutter


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_hands": 0},
        {"num_hands": 5},
        {"min_hand_detection_confidence": 1.5},
        {"min_tracking_confidence": -0.1},
    ],
)
def test_invalid_tracking_settings(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigError):
        TrackingSettings(**kwargs)


def test_cli_builds_settings() -> None:
    args = parse_args(
        [
            "--camera",
            "1",
            "--resolution",
            "640x480",
            "--backend",
            "dshow",
            "--no-mirror",
            "--max-hands",
            "1",
            "--model",
            "m.task",
        ]
    )
    settings = build_settings(args)
    assert settings.camera.index == 1
    assert (settings.camera.width, settings.camera.height) == (640, 480)
    assert settings.camera.backend is CameraBackend.DSHOW
    assert not settings.mirror_preview
    assert settings.tracking.num_hands == 1
    assert settings.tracking.model_path == Path("m.task")


@pytest.mark.parametrize("resolution", ["640", "axb", "640x480x3"])
def test_cli_rejects_bad_resolution(resolution: str) -> None:
    with pytest.raises(ConfigError):
        build_settings(parse_args(["--resolution", resolution]))


def test_cli_rejects_invalid_camera_index() -> None:
    with pytest.raises(ConfigError):
        build_settings(parse_args(["--camera", "-3"]))


def test_main_reports_config_errors(capsys: pytest.CaptureFixture[str]) -> None:
    from interactive_scrolling.app import main

    assert main(["--resolution", "huge"]) == 2
    assert "Invalid resolution" in capsys.readouterr().err
