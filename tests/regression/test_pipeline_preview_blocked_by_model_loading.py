"""Defect: no video was shown until the hand landmark model finished loading.

Found during CP 1.5 live verification: loading the model took ~9 s on first launch and the
processing thread did not pass frames through meanwhile, so the preview stayed empty and
158 frames were dropped. Fix: the tracker loads on a helper thread and frames are shown
without inference until it is ready.
"""

from __future__ import annotations

import threading

from interactive_scrolling.core.pipeline import TrackerState, VisionPipeline
from tests.helpers import ScriptedTracker, SyntheticCamera, camera_factory, wait_until
from tests.integration.test_pipeline import SETTINGS, RecordingListener


def setup_function() -> None:
    SyntheticCamera.instances.clear()


def test_preview_starts_before_slow_model_finishes_loading() -> None:
    listener = RecordingListener()
    release = threading.Event()
    tracker = ScriptedTracker()

    def slow_factory() -> ScriptedTracker:
        release.wait(5)
        return tracker

    pipeline = VisionPipeline(listener, camera_factory(), slow_factory)
    pipeline.launch()
    try:
        pipeline.start_camera(SETTINGS)
        assert wait_until(lambda: len(listener.frames) >= 3)
        assert pipeline.tracker_state is TrackerState.LOADING
        assert tracker.calls == 0
        release.set()
        assert wait_until(lambda: tracker.calls > 0)
    finally:
        release.set()
        pipeline.shutdown()
    assert tracker.closed
