"""Clock and rate measurement utilities.

All timestamps in the application are integer nanoseconds from
:func:`time.perf_counter_ns`. On Windows ``time.monotonic`` is backed by
``GetTickCount64`` with a 15.6 ms resolution, which is too coarse for velocity
estimation at 30 FPS; ``perf_counter_ns`` uses ``QueryPerformanceCounter``.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

Clock = Callable[[], int]
"""A function returning a monotonic timestamp in nanoseconds."""

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000


def now_ns() -> int:
    """Return the current monotonic, high-resolution timestamp in nanoseconds."""
    return time.perf_counter_ns()


class RateMeter:
    """Measures an event rate (e.g. frames per second) over a sliding time window.

    Thread-safe: ``tick`` may be called from a worker thread while ``rate`` is read
    from the UI thread.
    """

    def __init__(self, window_s: float = 1.0, clock: Clock = now_ns) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be positive")
        self._window_ns = int(window_s * NS_PER_S)
        self._clock = clock
        self._events: deque[int] = deque()
        self._lock = threading.Lock()

    def tick(self, timestamp_ns: int | None = None) -> None:
        t = self._clock() if timestamp_ns is None else timestamp_ns
        with self._lock:
            self._events.append(t)
            self._prune(t)

    def rate(self) -> float:
        """Events per second over the window ending now. ``0.0`` with fewer than 2 events."""
        with self._lock:
            self._prune(self._clock())
            if len(self._events) < 2:
                return 0.0
            span = self._events[-1] - self._events[0]
            if span <= 0:
                return 0.0
            return (len(self._events) - 1) * NS_PER_S / span

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _prune(self, now: int) -> None:
        cutoff = now - self._window_ns
        while self._events and self._events[0] < cutoff:
            self._events.popleft()


class RollingStats:
    """Mean / max / percentile over the most recent ``capacity`` samples. Thread-safe."""

    def __init__(self, capacity: int = 120) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._values: deque[float] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def add(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._values)

    def mean(self) -> float | None:
        with self._lock:
            if not self._values:
                return None
            return sum(self._values) / len(self._values)

    def percentile(self, q: float) -> float | None:
        """Nearest-rank percentile, ``q`` in [0, 100]."""
        if not 0 <= q <= 100:
            raise ValueError("q must be within [0, 100]")
        with self._lock:
            if not self._values:
                return None
            ordered = sorted(self._values)
        rank = max(1, round(q / 100 * len(ordered)))
        return ordered[min(rank, len(ordered)) - 1]
