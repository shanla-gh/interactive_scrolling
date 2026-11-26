"""Scrolling sessions, reports, the Doomscroll Index and Anti-Doomscroll reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from interactive_scrolling.config.settings import ConfigError, WellbeingSettings
from interactive_scrolling.storage.analytics import AnalyticsStore, EventKind
from interactive_scrolling.wellbeing.index import doomscroll_index
from interactive_scrolling.wellbeing.monitor import WellbeingMonitor
from interactive_scrolling.wellbeing.report import daily_report, performance_report
from interactive_scrolling.wellbeing.sessions import (
    ActivityEvent,
    ActivityTracker,
    sessions_from_intervals,
)

K = EventKind


class Clock:
    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def noon() -> float:
    return datetime(2026, 11, 26, 12, 0, 0).timestamp()


# ---------------------------------------------------------------------- sessions


def test_short_gaps_join_sessions_long_gaps_split_them() -> None:
    sessions = sessions_from_intervals([(0, 100), (150, 300), (500, 560), (561, 600)])
    assert [(s.start, s.end, s.active_s) for s in sessions] == [
        (0, 300, 250),
        (500, 600, 99),
    ]


def test_tracker_emits_intervals_heartbeats_and_session_time() -> None:
    events: list[tuple[ActivityEvent, float]] = []
    tracker = ActivityTracker(lambda e, ts: events.append((e, ts)))
    for t in range(0, 100):
        tracker.update(float(t), active=True)
    assert tracker.current_session_s(99.0) == pytest.approx(99.0)
    for t in range(100, 160):  # paused for 60 s: same session, time not counted
        tracker.update(float(t), active=False)
    for t in range(160, 200):
        tracker.update(float(t), active=True)
    # The first interval ends at the first inactive sample (t = 100).
    assert tracker.current_session_s(199.0) == pytest.approx(100 + 39)
    kinds = [e for e, _ in events]
    assert kinds.count(ActivityEvent.STARTED) == 2
    assert kinds.count(ActivityEvent.ENDED) == 1
    assert ActivityEvent.HEARTBEAT in kinds
    for t in range(200, 400):  # more than the 2-minute gap: the session is over
        tracker.update(float(t), active=False)
    assert tracker.current_session_s(399.0) == 0.0 and not tracker.in_session


def test_tracker_restores_a_session_after_a_quick_restart() -> None:
    tracker = ActivityTracker()
    tracker.restore(sessions_from_intervals([(0, 600)]), now=650)
    tracker.update(650, active=True)
    tracker.update(700, active=True)
    assert tracker.current_session_s(700) == pytest.approx(650)


# ---------------------------------------------------------------------- index


@pytest.mark.parametrize(
    ("scroll_min", "longest_min", "expected"),
    [
        (0, 0, 0),
        (60, 20, 50),  # exactly at both goals
        (120, 40, 100),  # twice both goals
        (600, 600, 100),  # capped
        (30, 10, 25),
        (60, 0, 35),
    ],
)
def test_doomscroll_index_formula(scroll_min: float, longest_min: float, expected: int) -> None:
    index = doomscroll_index(scroll_min * 60, longest_min * 60, 60, 20)
    assert index is not None and index.value == expected
    assert 0 <= index.value <= 100


def test_doomscroll_index_missing_data_and_invalid_goals() -> None:
    assert doomscroll_index(None, None, 60, 20) is None
    with pytest.raises(ValueError):
        doomscroll_index(10, 10, 0, 20)


def test_doomscroll_labels_can_be_plain() -> None:
    index = doomscroll_index(120 * 60, 40 * 60, 60, 20)
    assert index.label(humorous=True) == "Certified clown"
    assert index.label(humorous=False) == "Very high"
    assert doomscroll_index(0, 0, 60, 20).label(False) == "Low"


# ---------------------------------------------------------------------- reminders


def test_reality_checks_limit_and_budget_are_shown_once() -> None:
    monitor = WellbeingMonitor(WellbeingSettings(enabled=True, reality_check_min=10))
    assert monitor.evaluate("d", 0.0, 9 * 60, 9 * 60) == []
    first = monitor.evaluate("d", 0.0, 10 * 60, 10 * 60)
    assert [n.title for n in first] == ["Reality Check"]
    assert monitor.evaluate("d", 0.0, 11 * 60, 11 * 60) == []
    at_limit = monitor.evaluate("d", 0.0, 20 * 60, 20 * 60)
    assert {n.title for n in at_limit} == {"Reality Check", "Session limit reached"}
    budget = monitor.evaluate("d", 0.0, 25 * 60, 60 * 60)
    assert [n.title for n in budget] == ["Daily scrolling budget reached"]
    assert not monitor.scrolling_paused  # automatic pause is off by default


def test_reminders_are_off_by_default() -> None:
    monitor = WellbeingMonitor(WellbeingSettings())
    assert monitor.evaluate("d", 0.0, 99 * 60, 999 * 60) == []
    assert not monitor.scrolling_paused


def test_automatic_pause_is_reversible_and_ends_with_the_session() -> None:
    monitor = WellbeingMonitor(WellbeingSettings(enabled=True, pause_at_limit=True))
    monitor.evaluate("d", 0.0, 21 * 60, 21 * 60)
    assert monitor.scrolling_paused and "session limit" in monitor.pause_reason
    monitor.resume()
    assert not monitor.scrolling_paused
    monitor.evaluate("d", 0.0, 22 * 60, 22 * 60)
    assert not monitor.scrolling_paused  # overridden for this session
    monitor.evaluate("d", 5000.0, 21 * 60, 50 * 60)  # a new session reaching the limit again
    assert monitor.scrolling_paused
    monitor.evaluate("d", None, 0, 50 * 60)  # session over
    assert not monitor.scrolling_paused


def test_manual_pause() -> None:
    monitor = WellbeingMonitor(WellbeingSettings())
    monitor.pause()
    assert monitor.scrolling_paused and monitor.pause_reason == "gesture scrolling paused by you"
    monitor.resume()
    assert not monitor.scrolling_paused


def test_invalid_wellbeing_settings() -> None:
    with pytest.raises(ConfigError):
        WellbeingSettings(session_limit_min=0)
    with pytest.raises(ConfigError):
        WellbeingSettings(daily_budget_min=True)


# ---------------------------------------------------------------------- reports from the store


def store_at(tmp_path, clock: Clock) -> AnalyticsStore:
    return AnalyticsStore(tmp_path / "analytics.sqlite3", wall_clock=clock)


def test_daily_report_from_recorded_activity(tmp_path) -> None:
    clock = Clock(noon())
    store = store_at(tmp_path, clock)

    def at(offset: float, kind: EventKind, **kw) -> None:
        clock.now = noon() + offset
        store.record(kind, **kw)

    at(0, K.SCROLL_ACTIVE_STARTED)
    at(600, K.SCROLL_ACTIVE_ENDED)  # 10 min
    at(660, K.SCROLL_ACTIVE_STARTED)  # 1 min gap: same session
    at(960, K.SCROLL_ACTIVE_ENDED)  # +5 min
    at(5000, K.SCROLL_ACTIVE_STARTED)  # new session
    at(5120, K.SCROLL_ACTIVE_ENDED)  # 2 min
    at(100, K.GESTURE_CONFIRMED, gesture="index_swipe_down")
    at(101, K.GESTURE_CONFIRMED, gesture="finger_swipe_down")  # v0.2 name, same gesture
    at(102, K.ACTION_RESULT, action="next_short", outcome="succeeded")
    at(103, K.GESTURE_CONFIRMED, gesture="index_swipe_right")
    at(104, K.ACTION_RESULT, action="next_browser_tab", outcome="succeeded")
    at(105, K.GESTURE_CONFIRMED, gesture="half_heart")
    at(106, K.ACTION_RESULT, action="like_short", outcome="no change")
    at(107, K.ACTION_RESULT, action="next_short", outcome="rejected")
    store.flush()
    clock.now = noon() + 6000
    report = daily_report(store, daily_budget_min=60, session_limit_min=20)
    assert report is not None
    assert report.scrolling_s == pytest.approx(600 + 300 + 120)
    assert report.session_count == 2
    assert report.longest_session_s == pytest.approx(900)
    assert report.gestures["index_swipe_down"] == 2
    assert report.gestures_total == 4
    assert report.done("next_short") == 1 and report.done("next_browser_tab") == 1
    assert report.done("like_short") == 0 and report.no_change == 1
    assert report.rejected == 1
    # D = 17 min of 60, L = 15 min of 20: round(100 * (0.7 * 17/120 + 0.3 * 15/40)) = 21
    assert report.index is not None and report.index.value == 21
    store.close()


def test_abnormal_shutdown_counts_until_the_last_heartbeat(tmp_path) -> None:
    clock = Clock(noon())
    crashed = store_at(tmp_path, clock)
    crashed.record(K.SCROLL_ACTIVE_STARTED)
    clock.now = noon() + 30
    crashed.record(K.SCROLL_HEARTBEAT)
    clock.now = noon() + 60
    crashed.record(K.SCROLL_HEARTBEAT)  # last sign of life, then the process died
    crashed.flush()
    clock.now = noon() + 3600
    restarted = store_at(tmp_path, clock)
    report = daily_report(restarted, 60, 20)
    assert report.scrolling_s == pytest.approx(60)
    crashed.close()
    restarted.close()


def test_session_across_midnight_is_split_between_days(tmp_path) -> None:
    late = datetime(2026, 11, 26, 23, 55).timestamp()
    clock = Clock(late)
    store = store_at(tmp_path, clock)
    store.record(K.SCROLL_ACTIVE_STARTED)
    clock.now = late + 600  # 00:05 next day
    store.record(K.SCROLL_ACTIVE_ENDED)
    store.flush()
    first = daily_report(store, 60, 20, day=datetime.fromtimestamp(late).date())
    second = daily_report(
        store, 60, 20, day=(datetime.fromtimestamp(late) + timedelta(days=1)).date()
    )
    assert first.scrolling_s == pytest.approx(300)
    assert second.scrolling_s == pytest.approx(300)
    store.close()


def test_report_unavailable_when_statistics_are_off(tmp_path) -> None:
    store = AnalyticsStore(tmp_path / "a.sqlite3", enabled=False)
    assert daily_report(store, 60, 20) is None
    assert performance_report(store) is None
    store.close()


def test_performance_report_uses_dispatched_actions_as_denominator(tmp_path) -> None:
    clock = Clock(noon())
    store = store_at(tmp_path, clock)
    for i, outcome in enumerate(["succeeded", "succeeded", "failed", "outcome unknown"]):
        store.record(K.GESTURE_CONFIRMED, gesture="index_swipe_down")
        store.record(K.ACTION_DISPATCHED, action="next_short", event_uid=f"d{i}")
        store.record(
            K.ACTION_RESULT, action="next_short", outcome=outcome, latency_ms=100.0 + i * 100
        )
    store.record(K.GESTURE_CONFIRMED, gesture="index_swipe_up")
    store.record(K.ACTION_RESULT, action="previous_short", outcome="not executed")
    store.flush()
    perf = performance_report(store)
    assert perf.dispatched == 4 and perf.succeeded == 2
    assert perf.success_rate == pytest.approx(0.5)
    assert perf.not_executed == 1 and perf.gestures_total == 5
    assert perf.latency_samples == 2 and perf.latency_ms_mean == pytest.approx(150)
    store.close()


def test_empty_day_has_zero_index_and_no_sessions(tmp_path) -> None:
    store = store_at(tmp_path, Clock(noon()))
    report = daily_report(store, 60, 20)
    assert report.session_count == 0 and report.scrolling_s == 0
    assert report.index.value == 0
    store.close()
