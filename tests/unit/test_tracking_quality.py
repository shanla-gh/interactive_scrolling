"""Brief 006 diagnostics: measured frame timing, duplicate-hand count and the trajectory."""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from tests.gesture_helpers import Hand, run, stroke


def test_tracking_quality_reports_measured_frame_intervals() -> None:
    engine = GestureEngine(GestureSettings())
    run([Hand(stroke((640, 300), (640, 420), 1.0, 0.2))], 2.0, engine=engine)
    q = engine.tracking_quality()
    assert q["frames"] == 60 and q["frames_with_control_hand"] > 0
    assert abs(q["frame_interval_ms"]["median"] - 33.3) < 0.5
    assert q["frame_interval_ms"]["share_over_50ms"] == 0
    assert q["duplicate_hand_frames_ignored"] == 0


def test_motion_trace_carries_the_observed_trajectory() -> None:
    _, frames = run([Hand(stroke((640, 300), (640, 420), 1.0, 0.3))], 1.2)
    traces = [f.motion for f in frames if f.motion is not None and f.motion.phase == "moving"]
    assert traces and len(traces[-1].path_px) >= 3
    ys = [p[1] for p in traces[-1].path_px]
    assert ys == sorted(ys)  # the recorded points follow the downward movement
