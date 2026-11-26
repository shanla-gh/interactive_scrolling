"""The threaded pipeline with a synthetic camera and a scripted tracker."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from interactive_scrolling.config.settings import CameraSettings
from interactive_scrolling.core.pipeline import (
    CameraState,
    ProcessedFrame,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import ScriptedTracker, SyntheticCamera, camera_factory, make_hand, wait_until

SETTINGS = CameraSettings(width=320, height=240)


class RecordingListener:
    def __init__(self) -> None:
        self.frames: list[ProcessedFrame] = []
        self.camera_states: list[tuple[CameraState, str, int]] = []
        self.tracker_states: list[tuple[TrackerState, str]] = []
        self.lock = threading.Lock()

    def on_frame(self, frame: ProcessedFrame) -> None:
        with self.lock:
            self.frames.append(frame)

    def on_camera_state(self, state: CameraState, message: str, session: int) -> None:
        with self.lock:
            self.camera_states.append((state, message, session))

    def on_tracker_state(self, state: TrackerState, message: str) -> None:
        with self.lock:
            self.tracker_states.append((state, message))

    def states(self) -> list[CameraState]:
        with self.lock:
            return [s for s, _, _ in self.camera_states]


@pytest.fixture
def listener() -> RecordingListener:
    return RecordingListener()


@pytest.fixture(autouse=True)
def _reset_cameras() -> None:
    SyntheticCamera.instances.clear()


def moving_hand_script(ms: int):
    x = 50 + (ms % 2000) * 0.1  # 100 px/s to the right
    return (make_hand((x, 200), palm_px=40, width=320, height=240),)


def make_pipeline(
    listener: RecordingListener, tracker: ScriptedTracker | None, **camera
) -> VisionPipeline:
    pipeline = VisionPipeline(
        listener,
        camera_factory=camera_factory(**camera),
        tracker_factory=(lambda: tracker) if tracker is not None else None,
    )
    pipeline.launch()
    return pipeline


def test_frames_flow_through_tracking_and_motion(listener: RecordingListener) -> None:
    tracker = ScriptedTracker(moving_hand_script)
    pipeline = make_pipeline(listener, tracker, fps=60)
    try:
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.READY)
        assert pipeline.start_camera(SETTINGS)
        assert wait_until(
            lambda: len(listener.frames) >= 20 and listener.frames[-1].inference_ms is not None
        )
        frame = listener.frames[-1]
        # Colour conversion: the synthetic camera produces pure blue BGR frames.
        assert frame.image_rgb.shape == (240, 320, 3)
        assert frame.image_rgb[5, 5].tolist() == [0, 0, 255]
        assert frame.tracking.hand_count == 1
        assert frame.tracking.image_width == 320
        assert frame.motion.hands[0].handedness is Handedness.RIGHT
        assert frame.motion.hands[0].fingertip.velocity_px_s[0] > 0
        assert frame.latency_ms >= 0
        assert frame.completed_ns >= frame.capture_ns
        timestamps = [f.capture_ns for f in listener.frames]
        assert timestamps == sorted(timestamps)
        assert tracker.timestamps == sorted(tracker.timestamps)
        metrics = pipeline.metrics()
        assert metrics.camera_state is CameraState.RUNNING
        assert metrics.capture_fps > 10
        assert metrics.frame_width == 320
        assert metrics.inference_ms is not None
    finally:
        assert pipeline.shutdown(timeout_s=5)
    assert tracker.closed
    assert SyntheticCamera.instances[-1].close_calls == 1


def test_camera_preview_works_without_tracker(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, None)
    try:
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.UNAVAILABLE)
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 3)
        assert listener.frames[-1].tracking.hand_count == 0
        assert listener.frames[-1].inference_ms is None
    finally:
        pipeline.shutdown()


def test_tracker_load_failure_is_reported_and_preview_continues(
    listener: RecordingListener,
) -> None:
    def failing_factory():
        raise FileNotFoundError("model missing")

    pipeline = VisionPipeline(listener, camera_factory(), failing_factory)
    pipeline.launch()
    try:
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.UNAVAILABLE)
        assert any("model missing" in m for _, m in listener.tracker_states)
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 3)
    finally:
        pipeline.shutdown()


def test_camera_open_failure_reports_error(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker(), fail_open=True)
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: pipeline.camera_state is CameraState.ERROR)
        assert listener.states() == [CameraState.STARTING, CameraState.ERROR]
        assert "Could not open camera" in listener.camera_states[-1][1]
        assert listener.frames == []
        # The user can retry after an error.
        assert pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: pipeline.camera_state is CameraState.ERROR)
    finally:
        pipeline.shutdown()


def test_camera_disconnect_is_detected_and_released(listener: RecordingListener) -> None:
    pipeline = VisionPipeline(
        listener,
        camera_factory(fail_after=10),
        lambda: ScriptedTracker(),
        max_consecutive_read_failures=5,
    )
    pipeline.launch()
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: pipeline.camera_state is CameraState.ERROR)
        assert "stopped delivering frames" in listener.camera_states[-1][1]
        assert SyntheticCamera.instances[-1].close_calls == 1
    finally:
        pipeline.shutdown()


def test_repeated_start_stop_releases_every_session(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker(moving_hand_script))
    try:
        for session in range(1, 11):
            assert pipeline.start_camera(SETTINGS)
            assert wait_until(lambda s=session: any(f.session == s for f in listener.frames))
            pipeline.stop_camera()
            assert pipeline.wait_for_camera_stop(5)
            assert pipeline.camera_state is CameraState.STOPPED
        assert len(SyntheticCamera.instances) == 10
        assert all(c.close_calls == 1 and not c.opened for c in SyntheticCamera.instances)
    finally:
        pipeline.shutdown()


def test_motion_state_resets_between_sessions(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker(moving_hand_script))
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 5)
        pipeline.stop_camera()
        pipeline.wait_for_camera_stop(5)
        first_session_ids = {h.track_id for f in listener.frames for h in f.motion.hands}
        count = len(listener.frames)
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) > count + 2)
        new = [f for f in listener.frames if f.session == 2]
        assert new[0].motion.hands[0].reset
        assert new[0].motion.hands[0].track_id not in first_session_ids
    finally:
        pipeline.shutdown()


def test_start_while_running_is_rejected(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker())
    try:
        assert pipeline.start_camera(SETTINGS)
        assert not pipeline.start_camera(SETTINGS)
    finally:
        pipeline.shutdown()
    assert len(SyntheticCamera.instances) == 1


def test_slow_inference_drops_frames_instead_of_queuing(listener: RecordingListener) -> None:
    tracker = ScriptedTracker(delay_s=0.05)  # 20 inferences/s against a 100 FPS camera
    pipeline = make_pipeline(listener, tracker, fps=100)
    try:
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.READY)
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 15, timeout_s=10)
        metrics = pipeline.metrics()
        assert metrics.frames_dropped > metrics.frames_processed / 2
        # Latency stays bounded by roughly one inference plus one frame interval.
        recent = [f.latency_ms for f in listener.frames[-10:]]
        assert max(recent) < 200, recent
    finally:
        pipeline.shutdown()


def test_repeated_inference_failures_disable_tracking_but_keep_preview(
    listener: RecordingListener,
) -> None:
    tracker = ScriptedTracker(fail_with=RuntimeError("inference exploded"))
    pipeline = VisionPipeline(
        listener, camera_factory(), lambda: tracker, max_consecutive_inference_failures=3
    )
    pipeline.launch()
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: pipeline.tracker_state is TrackerState.UNAVAILABLE)
        assert tracker.closed
        count = len(listener.frames)
        assert wait_until(lambda: len(listener.frames) > count + 3)
        assert pipeline.camera_state is CameraState.RUNNING
    finally:
        pipeline.shutdown()


def test_listener_exception_does_not_kill_pipeline(listener: RecordingListener) -> None:
    calls = []

    class Faulty(RecordingListener):
        def on_frame(self, frame: ProcessedFrame) -> None:
            calls.append(frame)
            if len(calls) == 1:
                raise ValueError("ui bug")

    faulty = Faulty()
    pipeline = make_pipeline(faulty, ScriptedTracker())
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(calls) >= 5)
    finally:
        pipeline.shutdown()


def test_shutdown_while_running_releases_camera(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker())
    pipeline.start_camera(SETTINGS)
    assert wait_until(lambda: pipeline.camera_state is CameraState.RUNNING)
    assert pipeline.shutdown(timeout_s=5)
    camera = SyntheticCamera.instances[-1]
    assert camera.close_calls == 1 and not camera.opened
    assert not pipeline.start_camera(SETTINGS)  # no restart after shutdown


def test_processed_image_is_independent_copy(listener: RecordingListener) -> None:
    pipeline = make_pipeline(listener, ScriptedTracker())
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 2)
        a, b = listener.frames[0].image_rgb, listener.frames[1].image_rgb
        assert not np.shares_memory(a, b)
    finally:
        pipeline.shutdown()


@pytest.mark.parametrize(
    ("limit", "expected"), [(None, (240, 320, 3)), (160, (120, 160, 3)), (640, (240, 320, 3))]
)
def test_inference_input_downscaling(listener: RecordingListener, limit, expected) -> None:
    tracker = ScriptedTracker(moving_hand_script)
    pipeline = VisionPipeline(
        listener, camera_factory(), lambda: tracker, inference_max_width=limit
    )
    pipeline.launch()
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: tracker.calls >= 3)
        assert set(tracker.shapes) == {expected}
        # Display frames and tracking metadata keep the full camera resolution.
        assert wait_until(lambda: len(listener.frames) >= 3)
        assert listener.frames[-1].image_rgb.shape == (240, 320, 3)
        assert listener.frames[-1].tracking.image_width == 320
    finally:
        pipeline.shutdown()
