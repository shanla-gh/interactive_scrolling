"""Qt-side attribution for UI stalls (diagnostic sessions only).

Installed as an application-wide event filter, it remembers the last event delivered on the UI
thread and whether the event dispatcher is currently waiting for events (``aboutToBlock`` /
``awake``). When the stall monitor detects a stall it asks :meth:`describe`, which tells apart
a UI thread that is *busy* delivering an event (and which one) from one that is *asleep* and
was not woken up in time. The filter costs a few microseconds per event, so the application
uses it only when diagnostics are requested (``--diagnose-stalls``, the stability session).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QAbstractEventDispatcher, QEvent, QObject


class EventProbe(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._last: tuple[str, str, int] = ("", "", 0)
        self._waiting = False
        self._since = time.perf_counter_ns()

    def attach(self, app: QObject) -> None:
        app.installEventFilter(self)
        dispatcher = QAbstractEventDispatcher.instance()
        if dispatcher is not None:
            dispatcher.aboutToBlock.connect(self._about_to_block)
            dispatcher.awake.connect(self._awake)

    def _about_to_block(self) -> None:
        self._waiting = True
        self._since = time.perf_counter_ns()

    def _awake(self) -> None:
        self._waiting = False
        self._since = time.perf_counter_ns()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        self._last = (event.type().name, type(watched).__name__, time.perf_counter_ns())
        return False

    def describe(self) -> str:
        kind, receiver, at = self._last
        now = time.perf_counter_ns()
        state = "event loop asleep" if self._waiting else "event loop busy"
        return (
            f"{state} for {(now - self._since) / 1e6:.0f} ms; last Qt event {kind} to "
            f"{receiver} {(now - at) / 1e6:.0f} ms ago"
        )
