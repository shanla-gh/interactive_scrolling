"""Tests against the physical webcam. Run with ``pytest --hardware``.

These verify acquisition, resource release and the full real pipeline. They cannot verify
that a hand is in front of the camera; see docs/milestones/M1_MANUAL_VERIFICATION.md.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from interactive_scrolling.config.settings import CameraSettings, TrackingSettings
from interactive_scrolling.core.pipeline import (
    CameraState,
    ProcessedFrame,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.vision.camera import OpenCVCamera, probe_cameras
from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
from tests.helpers import wait_until

pytestmark = pytest.mark.hardware

INDEX = 0


def measure(camera: OpenCVCamera, seconds: float) -> tuple[int, float]:
    frames = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        if camera.read() is not None:
            frames += 1
    return frames, frames / (time.perf_counter() - start)


@pytest.mark.parametrize("resolution", [(640, 480), (1280, 720)])
def test_webcam_delivers_frames(resolution: tuple[int, int]) -> None:
    camera = OpenCVCamera(CameraSettings(index=INDEX, width=resolution[0], height=resolution[1]))
    camera.open()
    try:
        frame = camera.read()
        assert frame is not None
        assert frame.image_bgr.ndim == 3 and frame.image_bgr.shape[2] == 3
        assert frame.image_bgr.std() > 0, "frame is uniform; is the lens covered?"
        _, fps = measure(camera, 2.0)
        print(f"\n{camera.actual_width}x{camera.actual_height}: {fps:.1f} FPS")
        assert fps >= 10
    finally:
        camera.close()


def test_webcam_open_close_cycles_release_the_device() -> None:
    timings = []
    for _ in range(5):
        camera = OpenCVCamera(CameraSettings(index=INDEX, width=640, height=480))
        start = time.perf_counter()
        camera.open()  # fails if the previous cycle did not release the device
        timings.append(time.perf_counter() - start)
        assert camera.read() is not None
        camera.close()
    print(f"\nopen times: {[f'{t:.2f}s' for t in timings]}")


def test_probe_finds_the_webcam() -> None:
    found = probe_cameras(max_index=2)
    assert any(c.index == INDEX for c in found)


def test_full_pipeline_with_real_camera_and_model(model_path: Path) -> None:
    frames: list[ProcessedFrame] = []
    lock = threading.Lock()

    class Listener:
        def on_frame(self, frame: ProcessedFrame) -> None:
            with lock:
                frames.append(frame)

        def on_camera_state(self, state, message, session) -> None:
            print(f"camera: {state.value} - {message}")

        def on_tracker_state(self, state, message) -> None:
            print(f"tracker: {state.value} - {message}")

    pipeline = VisionPipeline(
        Listener(),
        camera_factory=OpenCVCamera,
        tracker_factory=lambda: MediaPipeHandTracker(TrackingSettings(), model_path),
    )
    pipeline.launch()
    try:
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.READY, timeout_s=30)
        assert pipeline.start_camera(CameraSettings(index=INDEX, width=1280, height=720))
        assert wait_until(lambda: pipeline.camera_state is CameraState.RUNNING, timeout_s=15)
        time.sleep(5.0)
        metrics = pipeline.metrics()
        print(f"\n{metrics}")
        assert metrics.capture_fps >= 10
        assert metrics.processing_fps >= 10
        assert metrics.latency_ms is not None and metrics.latency_ms < 150
        with lock:
            processed = [f for f in frames if f.inference_ms is not None]
        assert len(processed) > 30
        pipeline.stop_camera()
        assert pipeline.wait_for_camera_stop(5)
        assert pipeline.camera_state is CameraState.STOPPED
        # The device is free again.
        camera = OpenCVCamera(CameraSettings(index=INDEX, width=640, height=480))
        camera.open()
        camera.close()
    finally:
        assert pipeline.shutdown(timeout_s=10)
