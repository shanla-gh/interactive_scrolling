"""Defect: camera state notifications could arrive out of order (STOPPED before STOPPING).

Found in Integration Audit 001: ``stop_camera`` notified STOPPING after releasing the
pipeline lock, so a capture thread that finished quickly could notify STOPPED first. The UI
then stayed in "STOPPING" with the start button disabled. Fix: state changes are notified
while the state lock is held, and the UI connects to the bridge with queued connections so
slots never run inside that lock.
"""

from __future__ import annotations

import time

from interactive_scrolling.config.settings import CameraSettings
from interactive_scrolling.core.pipeline import CameraState, VisionPipeline
from tests.helpers import ScriptedTracker, camera_factory, wait_until
from tests.integration.test_pipeline import RecordingListener


class PreemptedNotifier(VisionPipeline):
    """Simulates the thread calling stop_camera being descheduled before it notifies."""

    def _notify_camera(self, state: CameraState, message: str, session: int) -> None:
        if state is CameraState.STOPPING:
            time.sleep(0.3)
        super()._notify_camera(state, message, session)


def test_stopping_is_always_reported_before_stopped() -> None:
    listener = RecordingListener()
    pipeline = PreemptedNotifier(listener, camera_factory(fps=200), lambda: ScriptedTracker())
    pipeline.launch()
    try:
        for _ in range(3):
            listener.camera_states.clear()
            assert pipeline.start_camera(CameraSettings(width=320, height=240))
            assert wait_until(lambda: pipeline.camera_state is CameraState.RUNNING)
            pipeline.stop_camera()
            assert pipeline.wait_for_camera_stop(5)
            assert wait_until(lambda: len(listener.states()) >= 4)
            assert listener.states() == [
                CameraState.STARTING,
                CameraState.RUNNING,
                CameraState.STOPPING,
                CameraState.STOPPED,
            ]
    finally:
        pipeline.shutdown()
