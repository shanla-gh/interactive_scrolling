"""The Doomscroll Index: a transparent 0-100 score of today's scrolling against your own goals.

Formula (deterministic, documented in docs/architecture/REPORTING.md)::

    D = today's active scrolling time (minutes)      B = your daily budget (minutes, > 0)
    L = today's longest scrolling session (minutes)  S = your session limit (minutes, > 0)

    budget_part  = min(1, D / (2 * B))     # 0.5 when you used exactly your budget
    session_part = min(1, L / (2 * S))     # 0.5 when your longest session hit your limit
    index = round(100 * (0.7 * budget_part + 0.3 * session_part))

So staying within both goals keeps the index at or below 50, and it reaches 100 only at twice
the budget *and* twice the session limit. No scrolling today gives 0. Without recorded data
(statistics switched off) the index is unavailable rather than 0.

It is an entertainment and self-awareness number, **not** a measure or diagnosis of addiction,
and lower is better: nothing in the application rewards a higher value.
"""

from __future__ import annotations

from dataclasses import dataclass

BUDGET_WEIGHT = 0.7
SESSION_WEIGHT = 0.3

_HUMOROUS = (
    (20, "Barely scrolled"),
    (40, "Casual scroller"),
    (60, "Getting comfortable"),
    (80, "Deep in the feed"),
    (101, "Certified clown"),
)
_PLAIN = (
    (20, "Low"),
    (40, "Moderate"),
    (60, "Elevated"),
    (80, "High"),
    (101, "Very high"),
)


@dataclass(frozen=True, slots=True)
class DoomscrollIndex:
    value: int
    budget_part: float
    session_part: float

    def label(self, humorous: bool = True) -> str:
        for limit, text in _HUMOROUS if humorous else _PLAIN:
            if self.value < limit:
                return text
        return _PLAIN[-1][1]


def doomscroll_index(
    scrolling_s: float | None,
    longest_session_s: float | None,
    daily_budget_min: float,
    session_limit_min: float,
) -> DoomscrollIndex | None:
    """Compute the index; ``None`` when no data is available."""
    if scrolling_s is None or longest_session_s is None:
        return None
    if daily_budget_min <= 0 or session_limit_min <= 0:
        raise ValueError("budget and session limit must be positive")
    budget_part = min(1.0, max(0.0, scrolling_s / 60) / (2 * daily_budget_min))
    session_part = min(1.0, max(0.0, longest_session_s / 60) / (2 * session_limit_min))
    value = round(100 * (BUDGET_WEIGHT * budget_part + SESSION_WEIGHT * session_part))
    return DoomscrollIndex(int(value), round(budget_part, 4), round(session_part, 4))
