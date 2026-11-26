"""Minimal local event store for daily statistics (SQLite, standard library).

What is stored
--------------
Only event categories needed by the approved reporting features: confirmed gestures, action
lifecycle outcomes, live-control sessions and periods during which a supported YouTube Shorts
tab was visible. Each row holds a timestamp, the local calendar day, an application session id,
the gesture/action names, the outcome, an optional short reason produced by this application,
and a measured latency. **No** URLs, page titles, video ids, account data, landmarks or camera
data are stored.

Design
------
* Writes go through a bounded queue to a dedicated writer thread, so the camera, inference and
  UI threads never wait for disk I/O. If the queue is full, events are dropped and counted.
* Every event has a unique id (``INSERT OR IGNORE``), so a duplicate notification cannot
  inflate the statistics.
* The local calendar day is computed when the event happens, so the day boundary follows the
  user's clock; Shorts sessions spanning midnight are split between the two days.
* Database errors are logged and reported through :attr:`AnalyticsStore.error`; they never
  propagate into gesture control.
"""

from __future__ import annotations

import enum
import logging
import queue
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from interactive_scrolling.storage.paths import data_dir

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event_uid TEXT NOT NULL UNIQUE,
    ts REAL NOT NULL,
    local_day TEXT NOT NULL,
    app_session TEXT NOT NULL,
    kind TEXT NOT NULL,
    gesture TEXT,
    action TEXT,
    outcome TEXT,
    reason TEXT,
    latency_ms REAL
);
CREATE INDEX IF NOT EXISTS events_day ON events(local_day, kind);
"""


class EventKind(enum.Enum):
    GESTURE_CONFIRMED = "gesture_confirmed"
    ACTION_DISPATCHED = "action_dispatched"
    ACTION_RESULT = "action_result"
    """An action's final outcome (``outcome`` column: succeeded, no change, rejected, ...)."""
    CONTROL_SESSION_STARTED = "control_session_started"
    CONTROL_SESSION_ENDED = "control_session_ended"
    SHORTS_SESSION_STARTED = "shorts_session_started"
    SHORTS_SESSION_ENDED = "shorts_session_ended"


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    kind: EventKind
    ts: float
    gesture: str | None = None
    action: str | None = None
    outcome: str | None = None
    reason: str | None = None
    latency_ms: float | None = None
    event_uid: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True, slots=True)
class DailyStats:
    day: date
    gestures_confirmed: int = 0
    gestures: dict[str, int] = field(default_factory=dict)
    succeeded: dict[str, int] = field(default_factory=dict)
    """Successful actions by action name (confirmed effect)."""
    no_change: int = 0
    rejected: int = 0
    failed: int = 0
    unknown: int = 0
    not_executed: int = 0
    shorts_visible_s: float = 0.0
    """Total time a supported Shorts tab was visible and connected. Not watch or attention time."""
    live_control_s: float = 0.0


def local_day(ts: float) -> str:
    return datetime.fromtimestamp(ts).date().isoformat()


def _day_bounds(day: date) -> tuple[float, float]:
    start = datetime(day.year, day.month, day.day)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


class AnalyticsStore:
    def __init__(
        self,
        path: Path | None = None,
        enabled: bool = True,
        wall_clock: Callable[[], float] = time.time,
        queue_size: int = 1000,
    ) -> None:
        self.path = path or data_dir() / "analytics.sqlite3"
        self.enabled = enabled
        self.app_session = uuid.uuid4().hex
        self._clock = wall_clock
        self._queue: queue.Queue[AnalyticsEvent | tuple[str, threading.Event] | None] = queue.Queue(
            maxsize=queue_size
        )
        self.dropped = 0
        self.error: str | None = None
        self._read_lock = threading.Lock()
        self._writer = threading.Thread(target=self._run, name="analytics-writer", daemon=True)
        self._writer.start()

    # ------------------------------------------------------------------ writing

    def record(
        self,
        kind: EventKind,
        gesture: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        latency_ms: float | None = None,
        event_uid: str | None = None,
    ) -> None:
        """Queue an event. Never blocks and never raises."""
        if not self.enabled:
            return
        event = AnalyticsEvent(
            kind=kind,
            ts=self._clock(),
            gesture=gesture,
            action=action,
            outcome=outcome,
            reason=(reason or None) and reason[:120],
            latency_ms=latency_ms,
            event_uid=event_uid or uuid.uuid4().hex,
        )
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1

    def flush(self, timeout_s: float = 5.0) -> bool:
        """Wait until all queued events are written (used by tests and shutdown)."""
        done = threading.Event()
        try:
            self._queue.put(("flush", done), timeout=timeout_s)
        except queue.Full:
            return False
        return done.wait(timeout_s)

    def clear(self) -> bool:
        """Delete all stored analytics. Returns False if the database could not be cleared."""
        done = threading.Event()
        self._queue.put(("clear", done))
        return done.wait(5.0) and self.error is None

    def close(self) -> None:
        self.flush()
        self._queue.put(None)
        self._writer.join(timeout=5)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA)
        return connection

    def _run(self) -> None:
        connection: sqlite3.Connection | None = None
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                if connection is None:
                    connection = self._connect()
                if isinstance(item, tuple):
                    command, done = item
                    if command == "clear":
                        connection.execute("DELETE FROM events")
                        connection.commit()
                        connection.execute("VACUUM")
                    done.set()
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO events (event_uid, ts, local_day, app_session, kind, "
                    "gesture, action, outcome, reason, latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.event_uid,
                        item.ts,
                        local_day(item.ts),
                        self.app_session,
                        item.kind.value,
                        item.gesture,
                        item.action,
                        item.outcome,
                        item.reason,
                        item.latency_ms,
                    ),
                )
                connection.commit()
                self.error = None
            except (sqlite3.Error, OSError) as exc:
                self.error = f"analytics database error: {exc}"
                log.error("%s", self.error)
                if connection is not None:
                    connection.close()
                connection = None
                if isinstance(item, tuple):
                    item[1].set()
        if connection is not None:
            connection.close()

    # ------------------------------------------------------------------ reading

    def daily_stats(self, day: date | None = None) -> DailyStats:
        """Statistics for one local calendar day (default: today). Never raises."""
        day = day or datetime.fromtimestamp(self._clock()).date()
        try:
            with self._read_lock, sqlite3.connect(self.path, timeout=5) as connection:
                return self._query(connection, day)
        except sqlite3.Error as exc:
            self.error = f"analytics database error: {exc}"
            return DailyStats(day)

    def _query(self, connection: sqlite3.Connection, day: date) -> DailyStats:
        rows = connection.execute(
            "SELECT kind, gesture, action, outcome, COUNT(*) FROM events WHERE local_day = ? "
            "GROUP BY kind, gesture, action, outcome",
            (day.isoformat(),),
        ).fetchall()
        gestures: dict[str, int] = {}
        succeeded: dict[str, int] = {}
        counts = {
            "no change": 0,
            "rejected": 0,
            "failed": 0,
            "outcome unknown": 0,
            "not executed": 0,
        }
        confirmed = 0
        for kind, gesture, action, outcome, n in rows:
            if kind == EventKind.GESTURE_CONFIRMED.value:
                confirmed += n
                gestures[gesture] = gestures.get(gesture, 0) + n
            elif kind == EventKind.ACTION_RESULT.value:
                if outcome == "succeeded":
                    succeeded[action] = succeeded.get(action, 0) + n
                elif outcome in counts:
                    counts[outcome] += n
        start, end = _day_bounds(day)
        return DailyStats(
            day=day,
            gestures_confirmed=confirmed,
            gestures=gestures,
            succeeded=succeeded,
            no_change=counts["no change"],
            rejected=counts["rejected"],
            failed=counts["failed"],
            unknown=counts["outcome unknown"],
            not_executed=counts["not executed"],
            shorts_visible_s=self._session_seconds(
                connection,
                EventKind.SHORTS_SESSION_STARTED,
                EventKind.SHORTS_SESSION_ENDED,
                start,
                end,
            ),
            live_control_s=self._session_seconds(
                connection,
                EventKind.CONTROL_SESSION_STARTED,
                EventKind.CONTROL_SESSION_ENDED,
                start,
                end,
            ),
        )

    def _session_seconds(
        self,
        connection: sqlite3.Connection,
        started: EventKind,
        ended: EventKind,
        day_start: float,
        day_end: float,
    ) -> float:
        """Total overlap of start/end intervals with the day, per application session.

        An interval still open in the current application session runs until now. An interval
        left open by an earlier session (e.g. a crash) is counted only up to that session's last
        recorded event, so durations are never overestimated.
        """
        rows = connection.execute(
            "SELECT app_session, kind, ts FROM events WHERE kind IN (?, ?) "
            "AND ts < ? ORDER BY app_session, ts",
            (started.value, ended.value, day_end),
        ).fetchall()
        last_event = dict(
            connection.execute(
                "SELECT app_session, MAX(ts) FROM events GROUP BY app_session"
            ).fetchall()
        )
        now = self._clock()
        total = 0.0
        open_since: dict[str, float] = {}
        for session, kind, ts in rows:
            if kind == started.value:
                open_since.setdefault(session, ts)
            elif session in open_since:
                begin = open_since.pop(session)
                total += max(0.0, min(ts, day_end) - max(begin, day_start))
        for session, begin in open_since.items():
            finish = now if session == self.app_session else last_event.get(session, begin)
            total += max(0.0, min(finish, day_end) - max(begin, day_start))
        return total
