"""Daily Activity Report and Gesture Performance Report from the local analytics store.

Gesture counts (what was *recognized*) and action counts (what was *executed and confirmed*)
are kept separate: a swipe recognized in Gesture test mode, rejected because no Shorts tab was
active, or refused by the page is a gesture but not an action.

Success rate (performance report): successful actions divided by actions *dispatched* to the
browser (requests that passed every safety check and reached the extension). Gestures that
were not executed (test mode, no mapping) or rejected before dispatch are excluded from the
denominator and reported separately. This is action-execution reliability, **not** gesture
recognition accuracy, which cannot be measured without knowing what the user intended (see the
recording benchmark in docs/architecture/GESTURES.md).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from interactive_scrolling.storage.analytics import AnalyticsStore, DailyStats
from interactive_scrolling.wellbeing.index import DoomscrollIndex, doomscroll_index
from interactive_scrolling.wellbeing.sessions import Session, sessions_from_intervals

LEGACY_SAME_GESTURE = {"finger_swipe_down": "index_swipe_down", "finger_swipe_up": "index_swipe_up"}
"""Version 0.2 names for exactly the same gesture (pointing-hand vertical swipes)."""


@dataclass(frozen=True, slots=True)
class DailyReport:
    day: date
    scrolling_s: float
    sessions: tuple[Session, ...]
    shorts_open_s: float
    """Time a Shorts tab was visible in a connected browser (focused or not, playing or not)."""
    gestures: dict[str, int]
    """Confirmed gestures by stored name (version 0.2 names of the same gesture merged)."""
    gestures_total: int
    succeeded: dict[str, int]
    """Successfully executed (confirmed) actions by action name."""
    no_change: int
    rejected: int
    failed: int
    unknown: int
    not_executed: int
    index: DoomscrollIndex | None

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    @property
    def longest_session_s(self) -> float:
        return max((s.active_s for s in self.sessions), default=0.0)

    def done(self, action: str) -> int:
        return self.succeeded.get(action, 0)


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    day: date
    gestures_total: int
    gestures: dict[str, int]
    dispatched: int
    succeeded: int
    no_change: int
    failed: int
    rejected: int
    unknown: int
    not_executed: int
    latency_ms_mean: float | None
    latency_ms_p95: float | None
    latency_samples: int
    by_action: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def success_rate(self) -> float | None:
        """Successful / dispatched actions; ``None`` when nothing was dispatched."""
        return self.succeeded / self.dispatched if self.dispatched else None


def _merge_legacy(gestures: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, count in gestures.items():
        key = LEGACY_SAME_GESTURE.get(name, name)
        out[key] = out.get(key, 0) + count
    return out


def daily_report(
    store: AnalyticsStore,
    daily_budget_min: float,
    session_limit_min: float,
    day: date | None = None,
) -> DailyReport | None:
    """Today's (or ``day``'s) report, or ``None`` if statistics are off or unreadable."""
    if not store.enabled:
        return None
    stats: DailyStats = store.daily_stats(day)
    intervals = store.scroll_intervals(stats.day)
    if intervals is None:
        return None
    sessions = tuple(sessions_from_intervals(intervals))
    scrolling = sum(b - a for a, b in intervals)
    longest = max((s.active_s for s in sessions), default=0.0)
    return DailyReport(
        day=stats.day,
        scrolling_s=scrolling,
        sessions=sessions,
        shorts_open_s=stats.shorts_visible_s,
        gestures=_merge_legacy(stats.gestures),
        gestures_total=stats.gestures_confirmed,
        succeeded=dict(stats.succeeded),
        no_change=stats.no_change,
        rejected=stats.rejected,
        failed=stats.failed,
        unknown=stats.unknown,
        not_executed=stats.not_executed,
        index=doomscroll_index(scrolling, longest, daily_budget_min, session_limit_min),
    )


def performance_report(store: AnalyticsStore, day: date | None = None) -> PerformanceReport | None:
    if not store.enabled:
        return None
    stats = store.daily_stats(day)
    outcomes = store.action_outcomes(stats.day)
    dispatched = store.dispatched_count(stats.day)
    latencies = store.success_latencies(stats.day)
    if outcomes is None or dispatched is None or latencies is None:
        return None
    by_action: dict[str, dict[str, int]] = {}
    for (action, outcome), count in outcomes.items():
        by_action.setdefault(action, {})[outcome] = count
    p95 = None
    if len(latencies) >= 2:
        p95 = statistics.quantiles(latencies, n=20, method="inclusive")[-1]
    elif latencies:
        p95 = latencies[0]
    return PerformanceReport(
        day=stats.day,
        gestures_total=stats.gestures_confirmed,
        gestures=_merge_legacy(stats.gestures),
        dispatched=dispatched,
        succeeded=sum(stats.succeeded.values()),
        no_change=stats.no_change,
        failed=stats.failed,
        rejected=stats.rejected,
        unknown=stats.unknown,
        not_executed=stats.not_executed,
        latency_ms_mean=statistics.fmean(latencies) if latencies else None,
        latency_ms_p95=p95,
        latency_samples=len(latencies),
        by_action=by_action,
    )
