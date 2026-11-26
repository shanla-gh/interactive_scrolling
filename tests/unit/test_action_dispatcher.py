"""Safety rules of the action dispatcher."""

from __future__ import annotations

import threading
import time

import pytest

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    DEFAULT_MAPPING,
    ActionRecord,
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
    MappingError,
    validate_mapping,
)
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import wait_until

G = GestureType


class FakeController:
    def __init__(
        self,
        ready: bool = True,
        reason: str = "",
        delay_s: float = 0.0,
        result: ActionResult | None = None,
    ) -> None:
        self.ready = ready
        self.reason = reason
        self.delay_s = delay_s
        self.result = result or ActionResult(ActionStatus.SUCCEEDED, "", "active Short changed")
        self.executed: list[ActionType] = []
        self.cancelled = threading.Event()

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(self.ready, self.reason)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        self.executed.append(action)
        if self.cancelled.wait(self.delay_s):
            return ActionResult(ActionStatus.UNKNOWN, "cancelled")
        return self.result

    def cancel_all(self) -> None:
        self.cancelled.set()


def event(gesture: GestureType = G.FINGER_SWIPE_DOWN, age_s: float = 0.0) -> GestureEvent:
    return GestureEvent(gesture, time.perf_counter_ns() - int(age_s * 1e9), 1, Handedness.RIGHT)


@pytest.fixture
def records() -> list[ActionRecord]:
    return []


def make(controller, records, mode=ControlMode.LIVE_CONTROL, **kwargs) -> ActionDispatcher:
    dispatcher = ActionDispatcher(controller, **kwargs)
    dispatcher.add_record_listener(records.append)
    dispatcher.set_mode(mode)
    return dispatcher


def final(records: list[ActionRecord], record_id: str) -> ActionRecord | None:
    matching = [r for r in records if r.record_id == record_id and r.status.final]
    return matching[-1] if matching else None


def test_default_mode_is_tracking_only_and_never_executes(records) -> None:
    controller = FakeController()
    dispatcher = ActionDispatcher(controller)
    dispatcher.add_record_listener(records.append)
    assert dispatcher.mode is ControlMode.TRACKING_ONLY
    record = dispatcher.submit(event())
    assert record.status is ActionStatus.NOT_EXECUTED
    time.sleep(0.1)
    assert controller.executed == []
    dispatcher.shutdown()


def test_gesture_test_mode_records_but_never_executes(records) -> None:
    controller = FakeController()
    dispatcher = make(controller, records, ControlMode.GESTURE_TEST)
    record = dispatcher.submit(event())
    assert record.status is ActionStatus.NOT_EXECUTED
    assert record.reason == "Gesture test mode"
    assert record.action is ActionType.NEXT_SHORT
    time.sleep(0.1)
    assert controller.executed == []
    dispatcher.shutdown()


def test_live_control_executes_mapped_action_with_confirmation(records) -> None:
    controller = FakeController()
    dispatcher = make(controller, records)
    submitted = dispatcher.submit(event())
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    done = final(records, submitted.record_id)
    statuses = [r.status for r in records if r.record_id == submitted.record_id]
    assert statuses == [ActionStatus.QUEUED, ActionStatus.DISPATCHED, ActionStatus.SUCCEEDED]
    assert controller.executed == [ActionType.NEXT_SHORT]
    assert done.action_latency_ms is not None and done.end_to_end_ms is not None
    dispatcher.shutdown()


@pytest.mark.parametrize(
    ("gesture", "action"),
    [
        (G.FINGER_SWIPE_UP, ActionType.PREVIOUS_SHORT),
        (G.THUMBS_UP, ActionType.LIKE_SHORT),
        (G.STOP_GESTURE, ActionType.TOGGLE_PLAYBACK),
    ],
)
def test_default_mapping(records, gesture, action) -> None:
    controller = FakeController()
    dispatcher = make(controller, records)
    submitted = dispatcher.submit(event(gesture))
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    assert controller.executed == [action]
    dispatcher.shutdown()


def test_hand_sweeps_are_recognized_but_not_executed(records) -> None:
    controller = FakeController()
    dispatcher = make(controller, records)
    record = dispatcher.submit(event(G.HAND_SWIPE_RIGHT))
    assert record.status is ActionStatus.NOT_EXECUTED
    assert "not available" in record.reason
    time.sleep(0.1)
    assert controller.executed == []
    dispatcher.shutdown()


def test_controller_context_rejection_is_reported(records) -> None:
    controller = FakeController(
        ready=False, reason="no YouTube Shorts tab is active in the browser"
    )
    dispatcher = make(controller, records)
    submitted = dispatcher.submit(event())
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    done = final(records, submitted.record_id)
    assert done.status is ActionStatus.REJECTED
    assert "no YouTube Shorts tab" in done.reason
    assert controller.executed == []
    dispatcher.shutdown()


def test_stale_gesture_is_rejected(records) -> None:
    controller = FakeController()
    dispatcher = make(controller, records, max_event_age_s=0.5)
    submitted = dispatcher.submit(event(age_s=2.0))
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    assert final(records, submitted.record_id).status is ActionStatus.REJECTED
    assert "stale" in final(records, submitted.record_id).reason
    assert controller.executed == []
    dispatcher.shutdown()


def test_gesture_during_running_action_is_rejected_not_queued(records) -> None:
    controller = FakeController(delay_s=0.4)
    dispatcher = make(controller, records)
    first = dispatcher.submit(event())
    assert wait_until(lambda: controller.executed)
    second = dispatcher.submit(event())
    assert second.status is ActionStatus.REJECTED
    assert "still running" in second.reason
    assert wait_until(lambda: final(records, first.record_id) is not None)
    assert controller.executed == [ActionType.NEXT_SHORT]
    dispatcher.shutdown()


def test_emergency_disable_prevents_new_actions_and_cancels_running_one(records) -> None:
    controller = FakeController(delay_s=5.0)
    dispatcher = make(controller, records)
    running = dispatcher.submit(event())
    assert wait_until(lambda: controller.executed)
    started = time.monotonic()
    dispatcher.emergency_disable()
    assert dispatcher.mode is ControlMode.TRACKING_ONLY
    assert controller.cancelled.is_set()
    assert wait_until(lambda: final(records, running.record_id) is not None, timeout_s=2)
    assert time.monotonic() - started < 1.0
    assert final(records, running.record_id).status is ActionStatus.UNKNOWN
    after = dispatcher.submit(event())
    assert after.status is ActionStatus.NOT_EXECUTED
    dispatcher.shutdown()


def test_reenabling_live_control_does_not_replay_old_gestures(records) -> None:
    controller = FakeController(delay_s=0.3)
    dispatcher = make(controller, records)
    dispatcher.submit(event())
    assert wait_until(lambda: controller.executed)
    queued_before_disable = dispatcher.submit(event())  # rejected: busy
    dispatcher.set_mode(ControlMode.GESTURE_TEST)
    dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    time.sleep(0.6)
    assert controller.executed == [ActionType.NEXT_SHORT]
    assert queued_before_disable.status is ActionStatus.REJECTED
    dispatcher.shutdown()


def test_unmapped_gesture_is_not_executed(records) -> None:
    controller = FakeController()
    mapping = validate_mapping({G.STOP_GESTURE: ActionType.NONE})
    dispatcher = make(controller, records, mapping=mapping)
    record = dispatcher.submit(event(G.STOP_GESTURE))
    assert record.status is ActionStatus.NOT_EXECUTED
    assert record.reason == "no action mapped"
    dispatcher.shutdown()


def test_custom_mapping_is_used(records) -> None:
    controller = FakeController()
    mapping = validate_mapping(
        {G.FINGER_SWIPE_DOWN: ActionType.PREVIOUS_SHORT, G.FINGER_SWIPE_UP: ActionType.NEXT_SHORT}
    )
    dispatcher = make(controller, records, mapping=mapping)
    submitted = dispatcher.submit(event(G.FINGER_SWIPE_DOWN))
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    assert controller.executed == [ActionType.PREVIOUS_SHORT]
    dispatcher.shutdown()


def test_invalid_mappings_are_refused() -> None:
    with pytest.raises(MappingError):
        validate_mapping({G.THUMBS_UP: ActionType.SWITCH_TO_STUDY_APP})
    with pytest.raises(MappingError):
        validate_mapping({G.HAND_SWIPE_LEFT: ActionType.NEXT_SHORT})
    assert validate_mapping({}) == DEFAULT_MAPPING


def test_failed_and_unknown_results_are_not_success(records) -> None:
    for status in (ActionStatus.FAILED, ActionStatus.UNKNOWN, ActionStatus.NO_CHANGE):
        controller = FakeController(result=ActionResult(status, "why"))
        dispatcher = make(controller, records)
        submitted = dispatcher.submit(event())
        assert wait_until(lambda s=submitted: final(records, s.record_id) is not None)
        assert final(records, submitted.record_id).status is status
        dispatcher.shutdown()


def test_controller_exception_is_reported_as_unknown(records) -> None:
    class Exploding(FakeController):
        def execute(self, action, request_id, timeout_s):
            raise RuntimeError("socket blew up")

    dispatcher = make(Exploding(), records)
    submitted = dispatcher.submit(event())
    assert wait_until(lambda: final(records, submitted.record_id) is not None)
    done = final(records, submitted.record_id)
    assert done.status is ActionStatus.UNKNOWN
    assert "socket blew up" in done.reason
    dispatcher.shutdown()


def test_mode_listeners_are_notified(records) -> None:
    changes = []
    dispatcher = ActionDispatcher(FakeController())
    dispatcher.add_mode_listener(lambda old, new, why: changes.append((old, new, why)))
    dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    dispatcher.emergency_disable()
    assert changes == [
        (ControlMode.TRACKING_ONLY, ControlMode.LIVE_CONTROL, ""),
        (ControlMode.LIVE_CONTROL, ControlMode.TRACKING_ONLY, "emergency disable"),
    ]
    dispatcher.shutdown()
