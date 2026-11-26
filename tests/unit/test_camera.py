"""OpenCVCamera behaviour with a fake capture device (no webcam required)."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import pytest

from interactive_scrolling.config.settings import CameraBackend, CameraSettings, ConfigError
from interactive_scrolling.vision.camera import (
    CameraError,
    CameraOpenError,
    CameraReadError,
    OpenCVCamera,
    normalize_frame_image,
    probe_cameras,
)


class FakeCapture:
    def __init__(
        self,
        opened: bool = True,
        frames: list[Any] | None = None,
        default_frame: Any = None,
    ) -> None:
        self.opened = opened
        self.frames = list(frames or [])
        self.default_frame = default_frame
        self.released = 0
        self.props: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.opened

    def read(self) -> tuple[bool, Any]:
        frame = self.frames.pop(0) if self.frames else self.default_frame
        return (frame is not None, frame)

    def set(self, prop_id: int, value: float) -> bool:
        self.props[prop_id] = value
        return True

    def get(self, prop_id: int) -> float:
        return self.props.get(prop_id, 0.0)

    def release(self) -> None:
        self.released += 1


def bgr(width: int = 64, height: int = 48) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 2] = 200  # red in BGR
    return image


def make_camera(capture: FakeCapture, **settings: Any) -> tuple[OpenCVCamera, list[tuple]]:
    calls: list[tuple] = []

    def factory(index: int, api: int) -> FakeCapture:
        calls.append((index, api))
        return capture

    clock_values = iter(range(1_000, 1_000_000, 1_000))
    camera = OpenCVCamera(
        CameraSettings(**settings),
        capture_factory=factory,
        clock=lambda: next(clock_values),
        warmup_attempts=3,
    )
    return camera, calls


def test_open_configures_device_and_reports_actual_size() -> None:
    capture = FakeCapture(default_frame=bgr(64, 48))
    camera, calls = make_camera(capture, index=2, width=1280, height=720, fps=30)
    camera.open()
    assert calls == [(2, cv2.CAP_MSMF)]
    assert capture.props[cv2.CAP_PROP_FRAME_WIDTH] == 1280
    assert capture.props[cv2.CAP_PROP_FRAME_HEIGHT] == 720
    assert capture.props[cv2.CAP_PROP_FPS] == 30
    # The device negotiated a different size; the camera reports the real one.
    assert (camera.actual_width, camera.actual_height) == (64, 48)
    assert camera.is_open


def test_backend_selection() -> None:
    capture = FakeCapture(default_frame=bgr())
    camera, calls = make_camera(capture, backend=CameraBackend.DSHOW)
    camera.open()
    assert calls[0][1] == cv2.CAP_DSHOW


def test_read_returns_bgr_frames_with_increasing_index_and_timestamp() -> None:
    capture = FakeCapture(default_frame=bgr())
    camera, _ = make_camera(capture)
    camera.open()
    frames = [camera.read() for _ in range(3)]
    assert all(f is not None for f in frames)
    assert [f.index for f in frames] == [0, 1, 2]
    assert frames[0].timestamp_ns < frames[1].timestamp_ns < frames[2].timestamp_ns
    assert frames[0].image_bgr[0, 0].tolist() == [0, 0, 200]  # BGR order untouched


def test_unavailable_camera_raises_open_error_and_releases() -> None:
    capture = FakeCapture(opened=False)
    camera, _ = make_camera(capture)
    with pytest.raises(CameraOpenError, match="Privacy"):
        camera.open()
    assert capture.released == 1
    assert not camera.is_open


def test_camera_that_never_delivers_frames_raises_read_error() -> None:
    capture = FakeCapture(default_frame=None)
    camera, _ = make_camera(capture)
    with pytest.raises(CameraReadError, match="did not deliver"):
        camera.open()
    assert capture.released == 1


def test_warmup_tolerates_initial_empty_frames() -> None:
    capture = FakeCapture(frames=[None, None], default_frame=bgr())
    camera, _ = make_camera(capture)
    camera.open()
    assert camera.read() is not None


def test_read_failure_returns_none() -> None:
    capture = FakeCapture(frames=[bgr()], default_frame=None)
    camera, _ = make_camera(capture)
    camera.open()
    assert camera.read() is not None  # the warm-up frame
    assert camera.read() is None


def test_factory_exception_becomes_open_error() -> None:
    def factory(index: int, api: int) -> FakeCapture:
        raise cv2.error("boom")

    camera = OpenCVCamera(CameraSettings(), capture_factory=factory)
    with pytest.raises(CameraOpenError):
        camera.open()


def test_close_is_idempotent_and_read_after_close_fails() -> None:
    capture = FakeCapture(default_frame=bgr())
    camera, _ = make_camera(capture)
    camera.open()
    camera.close()
    camera.close()
    assert capture.released == 1
    with pytest.raises(CameraError):
        camera.read()


@pytest.mark.parametrize(
    "kwargs",
    [{"index": -1}, {"width": 10}, {"height": 99999}, {"fps": 0}],
)
def test_invalid_camera_settings_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ConfigError):
        CameraSettings(**kwargs)


def test_normalize_frame_image_layouts() -> None:
    assert normalize_frame_image(None) is None
    assert normalize_frame_image(np.zeros((0, 0, 3), np.uint8)) is None
    assert normalize_frame_image(np.zeros((4, 4, 3), np.float32)) is None
    assert normalize_frame_image(np.zeros((4, 4, 2), np.uint8)) is None
    gray = normalize_frame_image(np.full((4, 5), 7, np.uint8))
    assert gray is not None and gray.shape == (4, 5, 3) and gray[0, 0].tolist() == [7, 7, 7]
    bgra = normalize_frame_image(np.full((4, 5, 4), 9, np.uint8))
    assert bgra is not None and bgra.shape == (4, 5, 3)
    strided = np.zeros((4, 10, 3), np.uint8)[:, ::2]
    out = normalize_frame_image(strided)
    assert out is not None and out.flags.c_contiguous


def test_probe_cameras_reports_working_devices_and_releases_all() -> None:
    captures = {
        0: FakeCapture(default_frame=bgr(640, 480)),
        1: FakeCapture(opened=False),
        2: FakeCapture(default_frame=None),
        3: FakeCapture(default_frame=bgr(1280, 720)),
    }
    found = probe_cameras(3, capture_factory=lambda index, api: captures[index])
    assert [(c.index, c.width, c.height) for c in found] == [(0, 640, 480), (3, 1280, 720)]
    assert all(c.released == 1 for c in captures.values())
    assert "1280x720" in found[1].label
