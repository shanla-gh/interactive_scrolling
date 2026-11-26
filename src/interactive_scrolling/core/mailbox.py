"""A single-slot, latest-value mailbox used to hand frames between threads.

The producer never blocks and never accumulates a backlog: publishing a new value
replaces any value the consumer has not yet taken. This deliberately drops outdated
frames instead of letting latency build up when inference is slower than capture.
"""

from __future__ import annotations

import threading


class LatestValueMailbox[T]:
    """Thread-safe holder for the most recent value with "new value" signalling."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._value: T | None = None
        self._has_new = False
        self._dropped = 0
        self._published = 0

    def publish(self, value: T) -> None:
        """Store ``value``, replacing (and counting as dropped) any unconsumed value."""
        with self._condition:
            if self._has_new:
                self._dropped += 1
            self._value = value
            self._has_new = True
            self._published += 1
            self._condition.notify_all()

    def take(self, timeout: float | None = None) -> T | None:
        """Wait up to ``timeout`` seconds for a value that has not been taken yet.

        Returns ``None`` on timeout. Each published value is returned at most once.
        """
        with self._condition:
            if not self._has_new:
                self._condition.wait_for(lambda: self._has_new, timeout=timeout)
            if not self._has_new:
                return None
            value = self._value
            self._value = None
            self._has_new = False
            return value

    def clear(self) -> None:
        """Discard any pending value without counting it as dropped."""
        with self._condition:
            self._value = None
            self._has_new = False

    def wake(self) -> None:
        """Wake any waiting consumer (used during shutdown)."""
        with self._condition:
            self._condition.notify_all()

    @property
    def dropped(self) -> int:
        with self._condition:
            return self._dropped

    @property
    def published(self) -> int:
        with self._condition:
            return self._published
