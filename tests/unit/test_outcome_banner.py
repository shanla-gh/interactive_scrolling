"""Banner texts for finished browser actions."""

from __future__ import annotations

import time

from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ActionType, ControlMode
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.ui.gesture_panels import outcome_banner
from interactive_scrolling.vision.landmarks import Handedness


def record(status: ActionStatus, reason: str = "") -> ActionRecord:
    event = GestureEvent(GestureType.INDEX_SWIPE_DOWN, time.perf_counter_ns(), 1, Handedness.RIGHT)
    return ActionRecord(
        record_id="r",
        event=event,
        action=ActionType.PREVIOUS_SHORT,
        mode=ControlMode.LIVE_CONTROL,
        status=status,
        created_ns=0,
        wall_time=0.0,
        reason=reason,
    )


def test_first_short_refusal_says_the_gesture_was_recognized() -> None:
    """Brief 005: 7 of the Director's 13 downward swipes were refused at the first Short;
    the banner must not look like a recognition failure."""
    text, _ = outcome_banner(record(ActionStatus.REJECTED, "already at the first Short"))
    assert "gesture recognized" in text and "already at the first Short" in text


def test_success_banner() -> None:
    text, _ = outcome_banner(record(ActionStatus.SUCCEEDED))
    assert text == "\u2713 Previous Short"
