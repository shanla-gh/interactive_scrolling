"""A gesture made while the previous navigation was settling was rejected (Brief 004).

The dispatcher now waits for a transient controller state (the Short changing or loading),
at most 1.2 s and in a single attempt.
"""

from __future__ import annotations

import time

import pytest

from interactive_scrolling.actions.types import ActionStatus, ActionType
from tests.helpers import wait_until
from tests.unit.test_action_dispatcher import (
    FakeController,
    TransientController,
    event,
    final,
    make,
)


@pytest.fixture
def records() -> list:
    return []


def test_transient_state_is_waited_out_once_not_rejected(records) -> None:
    """Regression (Director test, Nov 2026): a gesture made while the previous navigation was
    still settling was rejected with "no YouTube Shorts tab is active"."""
    controller = TransientController(transient_checks=5)
    dispatcher = make(controller, records)
    try:
        record = dispatcher.submit(event())
        assert wait_until(lambda: final(records, record.record_id) is not None, timeout_s=3)
        assert final(records, record.record_id).status is ActionStatus.SUCCEEDED
        assert controller.executed == [ActionType.NEXT_SHORT]
    finally:
        dispatcher.shutdown()


def test_transient_wait_is_bounded(records) -> None:
    controller = TransientController(transient_checks=10_000)
    dispatcher = make(controller, records)
    try:
        started = time.perf_counter()
        record = dispatcher.submit(event())
        assert wait_until(lambda: final(records, record.record_id) is not None, timeout_s=4)
        elapsed = time.perf_counter() - started
        result = final(records, record.record_id)
        assert result.status is ActionStatus.REJECTED
        assert result.reason == "the Short is changing"
        assert controller.executed == []
        assert 1.0 <= elapsed <= 2.5
    finally:
        dispatcher.shutdown()


def test_emergency_disable_ends_a_transient_wait(records) -> None:
    controller = TransientController(transient_checks=10_000)
    dispatcher = make(controller, records)
    try:
        record = dispatcher.submit(event())
        assert wait_until(lambda: controller.checks >= 2)
        dispatcher.emergency_disable()
        assert wait_until(lambda: final(records, record.record_id) is not None, timeout_s=3)
        assert final(records, record.record_id).status is ActionStatus.REJECTED
        assert controller.executed == []
    finally:
        dispatcher.shutdown()


def test_non_transient_refusal_is_not_waited_for(records) -> None:
    controller = FakeController(ready=False, reason="already at the first Short")
    dispatcher = make(controller, records)
    try:
        started = time.perf_counter()
        record = dispatcher.submit(event())
        assert wait_until(lambda: final(records, record.record_id) is not None, timeout_s=2)
        assert time.perf_counter() - started < 0.5
        assert final(records, record.record_id).reason == "already at the first Short"
    finally:
        dispatcher.shutdown()
