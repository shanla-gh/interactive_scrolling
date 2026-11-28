"""Rate measurement, rolling statistics and the latest-value mailbox."""

from __future__ import annotations

import threading
import time

import pytest

from interactive_scrolling.core.mailbox import LatestValueMailbox
from interactive_scrolling.core.timing import NS_PER_S, RateMeter, RollingStats


class FakeClock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def test_rate_meter_measures_rate_from_timestamps() -> None:
    clock = FakeClock()
    meter = RateMeter(1.0, clock)
    for i in range(31):
        clock.now = i * NS_PER_S // 30
        meter.tick()
    assert meter.rate() == pytest.approx(30.0, rel=1e-3)


def test_rate_meter_window_drops_old_events() -> None:
    clock = FakeClock()
    meter = RateMeter(1.0, clock)
    for i in range(10):
        clock.now = i * NS_PER_S // 10
        meter.tick()
    clock.now = 5 * NS_PER_S
    assert meter.rate() == 0.0


def test_rate_meter_needs_two_events_and_resets() -> None:
    clock = FakeClock()
    meter = RateMeter(1.0, clock)
    assert meter.rate() == 0.0
    meter.tick()
    assert meter.rate() == 0.0
    clock.now = NS_PER_S // 2
    meter.tick()
    assert meter.rate() == pytest.approx(2.0)
    meter.reset()
    assert meter.rate() == 0.0


def test_rolling_stats() -> None:
    stats = RollingStats(capacity=4)
    assert stats.mean() is None and stats.percentile(95) is None
    for v in [1.0, 2.0, 3.0, 4.0, 100.0]:
        stats.add(v)
    assert stats.count() == 4  # oldest value evicted
    assert stats.mean() == pytest.approx(27.25)
    assert stats.percentile(50) == 3.0
    assert stats.percentile(100) == 100.0
    with pytest.raises(ValueError):
        stats.percentile(101)


def test_mailbox_returns_latest_and_counts_drops() -> None:
    box: LatestValueMailbox[int] = LatestValueMailbox()
    box.publish(1)
    box.publish(2)
    box.publish(3)
    assert box.take(timeout=0) == 3
    assert box.dropped == 2
    assert box.published == 3
    assert box.take(timeout=0) is None  # each value is delivered once


def test_mailbox_take_times_out() -> None:
    box: LatestValueMailbox[int] = LatestValueMailbox()
    start = time.perf_counter()
    assert box.take(timeout=0.05) is None
    assert time.perf_counter() - start >= 0.04


def test_mailbox_wakes_waiting_consumer() -> None:
    box: LatestValueMailbox[str] = LatestValueMailbox()
    received: list[str | None] = []
    consumer = threading.Thread(target=lambda: received.append(box.take(timeout=2.0)))
    consumer.start()
    time.sleep(0.05)
    box.publish("frame")
    consumer.join(timeout=2.0)
    assert received == ["frame"]


def test_mailbox_clear_discards_without_counting() -> None:
    box: LatestValueMailbox[int] = LatestValueMailbox()
    box.publish(1)
    box.clear()
    assert box.take(timeout=0) is None
    assert box.dropped == 0


def test_mailbox_never_holds_more_than_one_value_under_load() -> None:
    box: LatestValueMailbox[int] = LatestValueMailbox()
    for i in range(10_000):
        box.publish(i)
    assert box.take(timeout=0) == 9_999
    assert box.dropped == 9_999


def test_two_slot_mailbox_keeps_a_burst_and_stays_bounded() -> None:
    from interactive_scrolling.core.mailbox import LatestValueMailbox

    box = LatestValueMailbox(capacity=2)
    box.publish(1)
    box.publish(2)  # a burst: both frames are kept
    assert box.dropped == 0 and box.pending == 2
    assert box.take(0) == 1  # oldest first
    box.publish(3)
    box.publish(4)  # full again: the oldest pending (2) is dropped, never a backlog
    assert box.dropped == 1
    assert [box.take(0), box.take(0), box.take(0)] == [3, 4, None]
