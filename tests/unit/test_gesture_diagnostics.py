"""Recognition diagnostics, the opt-in landmark recorder and the diagnostics export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interactive_scrolling.gestures.diagnostics import GestureDiagnostics, LandmarkRecorder
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.services import offline_services
from interactive_scrolling.vision.landmarks import TrackingResult
from tests.gesture_helpers import Hand, make_observation, still, stroke

FPS = 30.0


def replay(hand: Hand, seconds: float, *taps) -> None:
    analyzer = MotionAnalyzer()
    engine = GestureEngine()
    for i in range(int(seconds * FPS)):
        t = i / FPS
        position = hand.position(t)
        observations = () if position is None else (make_observation(hand.pose(t), position),)
        tracking = TrackingResult(i, int(1e9 + t * 1e9), 1280, 720, observations)
        frame = engine.update(tracking, analyzer.update(tracking))
        for tap in taps:
            tap(tracking, frame)


def test_stages_are_counted_separately() -> None:
    diagnostics = GestureDiagnostics()
    replay(Hand(stroke((640, 300), (640, 450), 0.8, 0.3)), 2.0, diagnostics.observe)
    replay(Hand(stroke((640, 300), (640, 345), 0.8, 0.2)), 2.0, diagnostics.observe)
    snap = diagnostics.snapshot()
    down = snap["gestures"]["index_swipe_down"]
    assert down["confirmed"] == 1
    assert down["candidates"] >= 2
    assert down["rejected"].get("too_short", 0) >= 1
    assert 0.5 < snap["hand_tracked_fraction"] <= 1.0
    rejected = [e for e in snap["recent"] if e["kind"] == "rejected" and e["code"] == "too_short"]
    assert rejected and rejected[-1]["required"] == 0.8 and rejected[-1]["unit"] == "palms"


def test_action_outcomes_are_kept_with_the_reason() -> None:
    diagnostics = GestureDiagnostics()
    diagnostics.observe_action("index_swipe_up", "next_short", "rejected", "busy", None)
    snap = diagnostics.snapshot()
    assert snap["actions"] == {"next_short: rejected": 1}
    assert snap["recent"][-1]["reason"] == "busy"


def test_recording_replays_with_the_evaluator(tmp_path: Path) -> None:
    recorder = LandmarkRecorder()
    replay(Hand(still(640, 400)), 0.3, lambda tracking, frame: recorder.observe(tracking))
    assert recorder.stop() is None  # nothing is recorded unless started
    recorder.start()
    recorder.label("index_down_x4", 5.0, "swipe down")
    replay(
        Hand(stroke((640, 300), (640, 450), 0.8, 0.3)),
        2.0,
        lambda tracking, frame: recorder.observe(tracking),
    )
    content = recorder.stop()
    assert content["prompts"] == [["index_down_x4", 5.0, "swipe down"]]
    path = tmp_path / "gestures_test.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from evaluate_gestures import GestureSettings, Result, evaluate, load

    result = Result()
    evaluate(load(path), GestureSettings(), False, False, result, "t", False)
    row = result.rows["index swipe down"]
    assert (row.expected, row.detected, row.false_triggers) == (4, 1, 0)


def test_export_contains_no_pairing_code_or_page_data(tmp_path: Path) -> None:
    services = offline_services()
    services.diagnostics.observe_action("half_heart", "like_short", "rejected", "x", None)
    path = services.export_diagnostics(tmp_path, {"fps": 30.0})
    text = path.read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["performance"] == {"fps": 30.0}
    assert report["mapping"]["index_swipe_up"] == "next_short"
    assert services.user_settings.pairing_token not in text
    for forbidden in ("pairing", "video_id", "url", "title"):
        assert forbidden not in text.lower()
