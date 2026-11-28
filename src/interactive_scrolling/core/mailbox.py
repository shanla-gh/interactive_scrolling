"""A small bounded, latest-values mailbox used to hand frames between threads.

The producer never blocks and never accumulates a backlog: when the mailbox is full, the
oldest unconsumed value is discarded (and counted as dropped). With ``capacity=1`` it is a
single slot that always holds the newest value. The frame pipeline uses ``capacity=2``
(Brief 009): webcams deliver frames in bursts (two frames milliseconds apart), and a single
slot overwrote the first one before the ~10 ms processing could take it - about 5 % of the
frames in a 30-minute camera session, although processing had ample average capacity. Two
slots keep both frames of a burst (the older is processed first, at most one frame interval
late) while a third frame still evicts the oldest, so latency stays bounded.
"""

from __future__ import annotations

import threading
from collections import deque


class LatestValueMailbox[T]:
    """Thread-safe holder for the most recent value(s) with "new value" signalling."""

    def __init__(self, capacity: int = 1) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._condition = threading.Condition()
        self._values: deque[T] = deque()
        self._capacity = capacity
        self._dropped = 0
        self._published = 0

    def publish(self, value: T) -> None:
        """Store ``value``; if the mailbox is full, the oldest pending value is dropped."""
        with self._condition:
            if len(self._values) >= self._capacity:
                self._values.popleft()
                self._dropped += 1
            self._values.append(value)
            self._published += 1
            self._condition.notify_all()

    def take(self, timeout: float | None = None) -> T | None:
        """Wait up to ``timeout`` seconds for a value that has not been taken yet and return the
        oldest pending one. Returns ``None`` on timeout. Each value is returned at most once."""
        with self._condition:
            if not self._values:
                self._condition.wait_for(lambda: bool(self._values), timeout=timeout)
            if not self._values:
                return None
            return self._values.popleft()

    def clear(self) -> None:
        """Discard any pending values without counting them as dropped."""
        with self._condition:
            self._values.clear()

    def wake(self) -> None:
        """Wake any waiting consumer (used during shutdown)."""
        with self._condition:
            self._condition.notify_all()

    @property
    def pending(self) -> int:
        with self._condition:
            return len(self._values)

    @property
    def dropped(self) -> int:
        with self._condition:
            return self._dropped

    @property
    def published(self) -> int:
        with self._condition:
            return self._published
