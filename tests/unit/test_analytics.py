"""Local analytics store: persistence, deduplication, day boundaries and failure handling."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from interactive_scrolling.storage.analytics import AnalyticsStore, EventKind

K = EventKind


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start.timestamp()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime(2026, 11, 26, 14, 0, 0))


def make(tmp_path: Path, clock: Clock, **kwargs) -> AnalyticsStore:
    return AnalyticsStore(tmp_path / "analytics.sqlite3", wall_clock=clock, **kwargs)


def test_counts_gestures_separately_from_successful_actions(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    for _ in range(3):
        store.record(K.GESTURE_CONFIRMED, gesture="finger_swipe_down")
    store.record(K.GESTURE_CONFIRMED, gesture="finger_swipe_up")
    store.record(K.ACTION_RESULT, action="next_short", outcome="succeeded", latency_ms=250)
    store.record(K.ACTION_RESULT, action="next_short", outcome="failed", reason="did not change")
    store.record(K.ACTION_RESULT, action="previous_short", outcome="rejected")
    store.record(K.ACTION_RESULT, action="like_short", outcome="no change")
    store.record(K.ACTION_RESULT, action="like_short", outcome="succeeded")
    store.record(K.ACTION_RESULT, action="toggle_playback", outcome="outcome unknown")
    store.flush()
    stats = store.daily_stats()
    assert stats.gestures_confirmed == 4
    assert stats.gestures == {"finger_swipe_down": 3, "finger_swipe_up": 1}
    assert stats.succeeded == {"next_short": 1, "like_short": 1}
    assert (stats.failed, stats.rejected, stats.no_change, stats.unknown) == (1, 1, 1, 1)
    store.close()


def test_statistics_survive_restart(tmp_path, clock) -> None:
    first = make(tmp_path, clock)
    first.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    first.close()
    second = make(tmp_path, clock)
    assert second.daily_stats().gestures_confirmed == 1
    second.close()


def test_duplicate_events_do_not_inflate_counts(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    for _ in range(3):
        store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up", event_uid="same-event")
    store.flush()
    assert store.daily_stats().gestures_confirmed == 1
    store.close()


def test_events_belong_to_the_local_day_they_happened(tmp_path) -> None:
    clock = Clock(datetime(2026, 11, 26, 23, 59, 30))
    store = make(tmp_path, clock)
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    clock.advance(60)  # 00:00:30 on the next day
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.flush()
    assert store.daily_stats(date(2026, 11, 26)).gestures_confirmed == 1
    assert store.daily_stats(date(2026, 11, 27)).gestures_confirmed == 2
    store.close()


def test_shorts_session_is_split_at_midnight(tmp_path) -> None:
    clock = Clock(datetime(2026, 11, 26, 23, 50))
    store = make(tmp_path, clock)
    store.record(K.SHORTS_SESSION_STARTED)
    clock.advance(20 * 60)  # until 00:10
    store.record(K.SHORTS_SESSION_ENDED)
    store.flush()
    assert store.daily_stats(date(2026, 11, 26)).shorts_visible_s == pytest.approx(600, abs=1)
    assert store.daily_stats(date(2026, 11, 27)).shorts_visible_s == pytest.approx(600, abs=1)
    store.close()


def test_open_session_counts_until_now(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    store.record(K.CONTROL_SESSION_STARTED)
    store.flush()
    clock.advance(90)
    assert store.daily_stats().live_control_s == pytest.approx(90, abs=0.5)
    store.close()


def test_session_left_open_by_a_crash_is_not_overestimated(tmp_path, clock) -> None:
    crashed = make(tmp_path, clock)
    crashed.record(K.SHORTS_SESSION_STARTED)
    clock.advance(30)
    crashed.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")  # last sign of life
    crashed.flush()
    clock.advance(3600)
    later = make(tmp_path, clock)
    assert later.daily_stats().shorts_visible_s == pytest.approx(30, abs=0.5)
    crashed.close()
    later.close()


def test_disabled_store_records_nothing(tmp_path, clock) -> None:
    store = make(tmp_path, clock, enabled=False)
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.flush()
    assert store.daily_stats().gestures_confirmed == 0
    store.close()


def test_clear_removes_all_analytics(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.flush()
    assert store.clear()
    assert store.daily_stats().gestures_confirmed == 0
    store.close()


def test_only_non_sensitive_columns_are_stored(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    store.record(K.ACTION_RESULT, action="like_short", outcome="rejected", reason="x" * 500)
    store.flush()
    with sqlite3.connect(store.path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(events)")]
        reason = connection.execute("SELECT reason FROM events").fetchone()[0]
    assert columns == [
        "id",
        "event_uid",
        "ts",
        "local_day",
        "app_session",
        "kind",
        "gesture",
        "action",
        "outcome",
        "reason",
        "latency_ms",
    ]
    assert len(reason) == 120
    store.close()


def test_database_errors_do_not_raise(tmp_path, clock) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    store = AnalyticsStore(blocker / "analytics.sqlite3", wall_clock=clock)
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")  # must not raise
    store.flush()
    assert store.error is not None
    assert store.daily_stats().gestures_confirmed == 0
    store.close()


def test_full_queue_drops_and_counts_instead_of_blocking(tmp_path, clock) -> None:
    store = make(tmp_path, clock, queue_size=1)
    for _ in range(500):
        store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.flush()
    stats = store.daily_stats()
    assert stats.gestures_confirmed + store.dropped == 500
    store.close()


def test_other_days_are_unaffected(tmp_path, clock) -> None:
    store = make(tmp_path, clock)
    store.record(K.GESTURE_CONFIRMED, gesture="thumbs_up")
    store.flush()
    yesterday = (datetime.fromtimestamp(clock.now) - timedelta(days=1)).date()
    assert store.daily_stats(yesterday).gestures_confirmed == 0
    store.close()
