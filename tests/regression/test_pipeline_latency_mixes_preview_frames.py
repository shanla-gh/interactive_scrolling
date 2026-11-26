"""Defect: reported latency mixed preview-only frames with frames that include inference.

Found in Integration Audit 001 (UI review): right after the model finished loading, the
status bar showed ~0.3 ms latency while inference took ~15 ms, because the rolling window
still held frames processed before the tracker was ready. Fix: latency and processing
statistics restart when the tracker becomes available.
"""

from __future__ import annotations

import threading

from interactive_scrolling.config.settings import CameraSettings
from interactive_scrolling.core.pipeline import VisionPipeline
from tests.helpers import ScriptedTracker, camera_factory, wait_until
from tests.integration.test_pipeline import RecordingListener


def test_latency_statistics_restart_when_tracker_becomes_ready() -> None:
    release = threading.Event()
    tracker = ScriptedTracker(delay_s=0.03)

    def slow_factory() -> ScriptedTracker:
        release.wait(5)
        return tracker

    listener = RecordingListener()
    pipeline = VisionPipeline(listener, camera_factory(fps=60), slow_factory)
    pipeline.launch()
    try:
        pipeline.start_camera(CameraSettings(width=320, height=240))
        assert wait_until(lambda: len(listener.frames) >= 30)
        before = pipeline.metrics().latency_ms
        assert before is not None and before < 20  # preview frames only, no inference
        release.set()
        assert wait_until(lambda: tracker.calls >= 5)
        after = pipeline.metrics()
        assert after.latency_ms is not None and after.latency_ms >= 30
        assert after.latency_p95_ms is not None and after.latency_p95_ms >= 30
    finally:
        release.set()
        pipeline.shutdown()
