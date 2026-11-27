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
CREATE TABLE IF NOT EXISTS eye_stats (
    local_day TEXT NOT NULL,
    app_session TEXT NOT NULL,
    screen_s REAL NOT NULL DEFAULT 0,
    away_s REAL NOT NULL DEFAULT 0,
    unknown_s REAL NOT NULL DEFAULT 0,
    blinks INTEGER,
    longest_screen_s REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (local_day, app_session)
);
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
    SCROLL_ACTIVE_STARTED = "scroll_active_started"
    """Active scrolling began (Shorts playing in the focused browser; see wellbeing.sessions)."""
    SCROLL_ACTIVE_ENDED = "scroll_active_ended"
    SCROLL_HEARTBEAT = "scroll_heartbeat"
    """Written every 30 s of active scrolling, so a crash loses at most that much."""
    GESTURE_REJECTED = "gesture_rejected"
    """A gesture candidate that was not accepted: ``outcome`` = rejection code, ``reason`` =
    measured / required values (Brief 005: missed attempts must be visible afterwards)."""


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
class EyeAggregate:
    """Aggregated passive eye-analytics durations (no per-frame data is ever stored)."""

    ts: float
    screen_s: float
    away_s: float
    unknown_s: float
    blinks: int | None
    """``None`` when blinks could not be counted reliably (sampling rate too low)."""
    longest_screen_s: float


@dataclass(frozen=True, slots=True)
class EyeReport:
    screen_s: float
    away_s: float
    unknown_s: float
    blinks: int | None
    longest_screen_s: float


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
        self._queue: queue.Queue[
            AnalyticsEvent | EyeAggregate | tuple[str, threading.Event] | None
        ] = queue.Queue(maxsize=queue_size)
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

    def record_eyes(
        self,
        screen_s: float,
        away_s: float,
        unknown_s: float,
        blinks: int | None,
        longest_screen_s: float,
    ) -> None:
        """Add eye-analytics durations to today's aggregate. Never blocks or raises."""
        if not self.enabled:
            return
        item = EyeAggregate(self._clock(), screen_s, away_s, unknown_s, blinks, longest_screen_s)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    def eye_report(self, day: date | None = None) -> EyeReport | None:
        day = day or datetime.fromtimestamp(self._clock()).date()

        def query(connection: sqlite3.Connection) -> EyeReport | None:
            row = connection.execute(
                "SELECT SUM(screen_s), SUM(away_s), SUM(unknown_s), SUM(blinks), "
                "COUNT(blinks), COUNT(*), MAX(longest_screen_s) FROM eye_stats "
                "WHERE local_day = ?",
                (day.isoformat(),),
            ).fetchone()
            if row is None or row[5] == 0:
                return None
            screen, away, unknown, blinks, with_blinks, rows, longest = row
            return EyeReport(
                screen or 0.0,
                away or 0.0,
                unknown or 0.0,
                int(blinks) if with_blinks == rows and blinks is not None else None,
                longest or 0.0,
            )

        return self._read(query)  # type: ignore[return-value]

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

    def _reader(self) -> sqlite3.Connection:
        """A read connection; creates the (empty) schema if nothing has been written yet, so a
        fresh installation reads as "no data" instead of a database error."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.executescript(SCHEMA)
        return connection

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
                        connection.execute("DELETE FROM eye_stats")
                        connection.commit()
                        connection.execute("VACUUM")
                    done.set()
                    continue
                if isinstance(item, EyeAggregate):
                    self._write_eyes(connection, item)
                    connection.commit()
                    self.error = None
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

    def _write_eyes(self, connection: sqlite3.Connection, item: EyeAggregate) -> None:
        connection.execute(
            "INSERT INTO eye_stats (local_day, app_session, screen_s, away_s, unknown_s, blinks, "
            "longest_screen_s) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(local_day, app_session) DO UPDATE SET "
            "screen_s = screen_s + excluded.screen_s, away_s = away_s + excluded.away_s, "
            "unknown_s = unknown_s + excluded.unknown_s, "
            "blinks = CASE WHEN blinks IS NULL OR excluded.blinks IS NULL THEN NULL "
            "ELSE blinks + excluded.blinks END, "
            "longest_screen_s = MAX(longest_screen_s, excluded.longest_screen_s)",
            (
                local_day(item.ts),
                self.app_session,
                item.screen_s,
                item.away_s,
                item.unknown_s,
                item.blinks,
                item.longest_screen_s,
            ),
        )

    # ------------------------------------------------------------------ reading

    def daily_stats(self, day: date | None = None) -> DailyStats:
        """Statistics for one local calendar day (default: today). Never raises."""
        day = day or datetime.fromtimestamp(self._clock()).date()
        try:
            with self._read_lock, self._reader() as connection:
                return self._query(connection, day)
        except (sqlite3.Error, OSError) as exc:
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

    # ------------------------------------------------------------------ report queries

    def _read(self, query: Callable[[sqlite3.Connection], object]) -> object:
        try:
            with self._read_lock, self._reader() as connection:
                return query(connection)
        except (sqlite3.Error, OSError) as exc:
            self.error = f"analytics database error: {exc}"
            return None

    def scroll_intervals(self, day: date | None = None) -> list[tuple[float, float]] | None:
        """Active scrolling intervals overlapping ``day``, clipped to it (wall-clock seconds).

        An interval left open by an earlier application session (crash, power loss) ends at
        that session's last recorded event (at most one heartbeat late); one open in the
        current session runs until now. ``None`` if the database cannot be read.
        """
        day = day or datetime.fromtimestamp(self._clock()).date()
        start, end = _day_bounds(day)
        now = self._clock()
        kinds = (
            EventKind.SCROLL_ACTIVE_STARTED.value,
            EventKind.SCROLL_ACTIVE_ENDED.value,
            EventKind.SCROLL_HEARTBEAT.value,
        )

        def query(connection: sqlite3.Connection) -> list[tuple[float, float]]:
            rows = connection.execute(
                "SELECT app_session, kind, ts FROM events WHERE kind IN (?, ?, ?) "
                "AND ts >= ? AND ts < ? ORDER BY app_session, ts",
                (*kinds, start - 86400.0, end),
            ).fetchall()
            intervals: list[tuple[float, float]] = []
            open_at: dict[str, float] = {}
            last_seen: dict[str, float] = {}
            for session, kind, ts in rows:
                last_seen[session] = ts
                if kind == kinds[0]:
                    open_at.setdefault(session, ts)
                elif kind == kinds[1] and session in open_at:
                    intervals.append((open_at.pop(session), ts))
            for session, begin in open_at.items():
                finish = now if session == self.app_session else last_seen.get(session, begin)
                intervals.append((begin, finish))
            clipped = [(max(a, start), min(b, end)) for a, b in intervals]
            return [(a, b) for a, b in clipped if b > a]

        return self._read(query)  # type: ignore[return-value]

    def action_outcomes(self, day: date | None = None) -> dict[tuple[str, str], int] | None:
        """(action, outcome) -> count of final action outcomes on ``day``."""
        day = day or datetime.fromtimestamp(self._clock()).date()

        def query(connection: sqlite3.Connection) -> dict[tuple[str, str], int]:
            rows = connection.execute(
                "SELECT action, outcome, COUNT(*) FROM events WHERE local_day = ? AND kind = ? "
                "GROUP BY action, outcome",
                (day.isoformat(), EventKind.ACTION_RESULT.value),
            ).fetchall()
            return {(a or "", o or ""): n for a, o, n in rows}

        return self._read(query)  # type: ignore[return-value]

    def counts_between(self, start_ts: float, end_ts: float) -> tuple[int, dict[str, int]] | None:
        """(confirmed gestures, successful actions by name) between two wall-clock times."""

        def query(connection: sqlite3.Connection) -> tuple[int, dict[str, int]]:
            gestures = connection.execute(
                "SELECT COUNT(*) FROM events WHERE kind = ? AND ts >= ? AND ts <= ?",
                (EventKind.GESTURE_CONFIRMED.value, start_ts, end_ts),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT action, COUNT(*) FROM events WHERE kind = ? AND outcome = 'succeeded' "
                "AND ts >= ? AND ts <= ? GROUP BY action",
                (EventKind.ACTION_RESULT.value, start_ts, end_ts),
            ).fetchall()
            return gestures, {a: n for a, n in rows}

        return self._read(query)  # type: ignore[return-value]

    def rejection_summary(self, since_ts: float) -> dict[str, int]:
        """Stored gesture rejections since ``since_ts``: "gesture: code" -> count."""
        try:
            with self._reader() as conn:
                rows = conn.execute(
                    "SELECT gesture, outcome, COUNT(*) FROM events WHERE kind = ? AND ts >= ? "
                    "GROUP BY gesture, outcome ORDER BY COUNT(*) DESC",
                    (EventKind.GESTURE_REJECTED.value, since_ts),
                ).fetchall()
        except (sqlite3.Error, OSError):
            return {}
        return {f"{g}: {code}": n for g, code, n in rows}

    def dispatched_count(self, day: date | None = None) -> int | None:
        day = day or datetime.fromtimestamp(self._clock()).date()

        def query(connection: sqlite3.Connection) -> int:
            return connection.execute(
                "SELECT COUNT(*) FROM events WHERE local_day = ? AND kind = ?",
                (day.isoformat(), EventKind.ACTION_DISPATCHED.value),
            ).fetchone()[0]

        return self._read(query)  # type: ignore[return-value]

    def success_latencies(self, day: date | None = None) -> list[float] | None:
        """Dispatch-to-confirmation times (ms) of successful actions on ``day``."""
        day = day or datetime.fromtimestamp(self._clock()).date()

        def query(connection: sqlite3.Connection) -> list[float]:
            rows = connection.execute(
                "SELECT latency_ms FROM events WHERE local_day = ? AND kind = ? "
                "AND outcome = 'succeeded' AND latency_ms IS NOT NULL",
                (day.isoformat(), EventKind.ACTION_RESULT.value),
            ).fetchall()
            return [r[0] for r in rows]

        return self._read(query)  # type: ignore[return-value]

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
