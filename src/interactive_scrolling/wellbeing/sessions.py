"""Scrolling activity and session accounting (pure logic, wall-clock seconds).

Definitions (documented in docs/architecture/REPORTING.md)
---------------------------------------------------------
* **Shorts page open**: a connected browser's active tab in its last focused window is a
  YouTube Shorts page (recorded since 0.2 as ``shorts_session`` events).
* **Active scrolling**: additionally, that browser window has the operating-system focus, the
  page is visible, the Short has loaded and is *playing*. Paused videos, background tabs and an
  unfocused browser do not count. This is a measure of Shorts playing in the foreground, **not**
  of attention: estimated viewing time is a separate, optional eye-analytics measure.
* **Scrolling session**: active intervals separated by gaps of at most ``SESSION_GAP_S``
  (2 minutes) belong to one session, so briefly pausing a video or checking another tab does
  not split it. The session's duration is its *active* time; the gaps are not counted.
* **Day**: intervals are split at local midnight; a session crossing midnight contributes to
  both days.

:class:`ActivityTracker` turns once-per-second activity samples into interval start/end
events (with heartbeats so an abnormal shutdown loses at most ``HEARTBEAT_S``) and knows the
current session's active time live. :func:`sessions_from_intervals` rebuilds sessions from the
persisted intervals for the reports.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable
from dataclasses import dataclass

SESSION_GAP_S = 120.0
HEARTBEAT_S = 30.0


class ActivityEvent(enum.Enum):
    STARTED = "scroll_active_started"
    ENDED = "scroll_active_ended"
    HEARTBEAT = "scroll_heartbeat"


@dataclass(frozen=True, slots=True)
class Session:
    start: float
    end: float
    active_s: float
    """Sum of the active intervals (gaps excluded)."""


def sessions_from_intervals(
    intervals: Iterable[tuple[float, float]], gap_s: float = SESSION_GAP_S
) -> list[Session]:
    """Merge active intervals into sessions (gaps <= ``gap_s`` join intervals)."""
    sessions: list[Session] = []
    for start, end in sorted(i for i in intervals if i[1] > i[0]):
        if sessions and start - sessions[-1].end <= gap_s:
            last = sessions[-1]
            sessions[-1] = Session(last.start, max(last.end, end), last.active_s + (end - start))
        else:
            sessions.append(Session(start, end, end - start))
    return sessions


class ActivityTracker:
    """Feed :meth:`update` about once per second; it emits interval events through ``emit``."""

    def __init__(
        self,
        emit: Callable[[ActivityEvent, float], None] | None = None,
        gap_s: float = SESSION_GAP_S,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self._emit = emit or (lambda event, ts: None)
        self.gap_s = gap_s
        self.heartbeat_s = heartbeat_s
        self._active_since: float | None = None
        self._last_heartbeat = 0.0
        self._session_start: float | None = None
        self._session_active_s = 0.0
        """Active time of the current session in closed intervals."""
        self._last_active_end: float | None = None
        self.last_update: float | None = None

    @property
    def active(self) -> bool:
        return self._active_since is not None

    def restore(self, sessions: list[Session], now: float) -> None:
        """Continue a session recorded before a restart if it ended less than a gap ago."""
        if sessions and now - sessions[-1].end <= self.gap_s:
            last = sessions[-1]
            self._session_start = last.start
            self._session_active_s = last.active_s
            self._last_active_end = last.end

    def update(self, now: float, active: bool) -> None:
        self.last_update = now
        if active and self._active_since is None:
            if self._last_active_end is None or now - self._last_active_end > self.gap_s:
                self._session_start = now
                self._session_active_s = 0.0
            self._active_since = now
            self._last_heartbeat = now
            self._emit(ActivityEvent.STARTED, now)
        elif not active and self._active_since is not None:
            self._close(now)
        elif active and now - self._last_heartbeat >= self.heartbeat_s:
            self._last_heartbeat = now
            self._emit(ActivityEvent.HEARTBEAT, now)
        if (
            not active
            and self._last_active_end is not None
            and now - self._last_active_end > self.gap_s
        ):
            self._session_start = None
            self._session_active_s = 0.0
            self._last_active_end = None

    def _close(self, now: float) -> None:
        assert self._active_since is not None
        self._session_active_s += max(0.0, now - self._active_since)
        self._active_since = None
        self._last_active_end = now
        self._emit(ActivityEvent.ENDED, now)

    def stop(self, now: float) -> None:
        """Close an open interval (application shutdown)."""
        if self._active_since is not None:
            self._close(now)

    def current_session_s(self, now: float) -> float:
        """Active seconds of the session in progress (0 when there is none)."""
        if self._session_start is None:
            return 0.0
        running = now - self._active_since if self._active_since is not None else 0.0
        return self._session_active_s + max(0.0, running)

    @property
    def in_session(self) -> bool:
        return self._session_start is not None
