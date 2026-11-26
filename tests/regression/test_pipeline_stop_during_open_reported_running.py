"""Defect: stopping the camera while it was still opening could report RUNNING.

Found during CP 1.1 code review: the capture thread announced RUNNING after a slow open
even when a stop had been requested in the meantime. Fix: the state transition and the
stop check happen under the same lock.
"""

from __future__ import annotations

from interactive_scrolling.core.pipeline import CameraState
from tests.helpers import ScriptedTracker, SyntheticCamera
from tests.integration.test_pipeline import SETTINGS, RecordingListener, make_pipeline


def setup_function() -> None:
    SyntheticCamera.instances.clear()


def test_stop_during_slow_open_never_reports_running() -> None:
    listener = RecordingListener()
    pipeline = make_pipeline(listener, ScriptedTracker(), open_delay_s=0.3)
    try:
        pipeline.start_camera(SETTINGS)
        pipeline.stop_camera()
        assert pipeline.wait_for_camera_stop(5)
        assert CameraState.RUNNING not in listener.states()
        assert listener.states()[-1] is CameraState.STOPPED
        assert SyntheticCamera.instances[-1].close_calls == 1
    finally:
        pipeline.shutdown()
