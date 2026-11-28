"""Live Shorts preview: the latest frame from the browser, with measured rate and delay.

The extension captures the one tab the user chose in its popup, crops it to the Short's video
area and sends JPEG frames over the loopback ``/preview`` connection. Only the most recent
frame is kept (no queue): the display always shows the current picture and an old frame is
simply replaced. Decoding happens in the UI layer, only when a new frame is shown.

Measurements (all real):

* ``fps``: frames received per second over the last two seconds.
* ``transport_ms``: browser read time to arrival here (same computer, same wall clock):
  crop, JPEG encoding and the loopback transfer. It does not include the browser's own
  rendering before capture or the app's painting after arrival.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from interactive_scrolling.integrations.youtube.protocol import PreviewFrame

RATE_WINDOW_S = 2.0
STALE_AFTER_S = 1.5
"""No frame for this long while streaming: the preview shows that it is not live."""


@dataclass(frozen=True, slots=True)
class PreviewStatus:
    connected: bool
    state: str
    """``off`` (no preview connection), ``streaming``, ``hidden``, ``stopped``."""
    reason: str
    fps: float
    transport_ms: float | None
    frames: int
    frame_age_s: float | None
    skipped: int
    """Frame numbers that never arrived (the browser skipped them while the socket was busy)."""

    @property
    def live(self) -> bool:
        return (
            self.connected
            and self.state == "streaming"
            and self.frame_age_s is not None
            and self.frame_age_s <= STALE_AFTER_S
        )


class PreviewFeed:
    def __init__(self, wall_ms: Callable[[], float] | None = None) -> None:
        self._wall_ms = wall_ms or (lambda: time.time() * 1000.0)
        self._lock = threading.Lock()
        self._frame: PreviewFrame | None = None
        self._arrived_ms: float | None = None
        self._arrivals: deque[float] = deque()
        self._transport: deque[float] = deque(maxlen=60)
        self._connected = False
        self._state = "off"
        self._reason = ""
        self._frames = 0
        self._skipped = 0
        self._last_number: int | None = None
        self._stop: Callable[[], None] | None = None
        self.listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ bridge side

    def attach(self, stop: Callable[[], None]) -> None:
        with self._lock:
            self._connected = True
            self._state = "hidden"
            self._reason = "waiting for the first frame"
            self._stop = stop
            self._frame = None
            self._arrived_ms = None
            self._arrivals.clear()
            self._transport.clear()
            self._frames = 0
            self._skipped = 0
            self._last_number = None
        self._notify()

    def detach(self, reason: str) -> None:
        with self._lock:
            self._connected = False
            self._state = "off"
            self._reason = reason
            self._stop = None
            self._frame = None
        self._notify()

    def push(self, frame: PreviewFrame) -> None:
        now = self._wall_ms()
        with self._lock:
            if self._last_number is not None and frame.number > self._last_number + 1:
                self._skipped += frame.number - self._last_number - 1
            self._last_number = frame.number
            self._frame = frame
            self._arrived_ms = now
            self._frames += 1
            self._arrivals.append(now)
            while self._arrivals and now - self._arrivals[0] > RATE_WINDOW_S * 1000:
                self._arrivals.popleft()
            self._transport.append(max(0.0, now - frame.captured_ms))
            if self._state != "streaming":
                self._state = "streaming"
                self._reason = ""

    def set_state(self, state: str, reason: str) -> None:
        with self._lock:
            self._state = state
            self._reason = reason
            if state != "streaming":
                # Never keep showing a picture once the tab left Shorts.
                self._frame = None
        self._notify()

    # ------------------------------------------------------------------ app side

    def latest(self) -> PreviewFrame | None:
        """The current frame, or ``None`` when the preview must not show a picture."""
        with self._lock:
            return self._frame if self._state == "streaming" else None

    def status(self) -> PreviewStatus:
        now = self._wall_ms()
        with self._lock:
            while self._arrivals and now - self._arrivals[0] > RATE_WINDOW_S * 1000:
                self._arrivals.popleft()
            fps = len(self._arrivals) / RATE_WINDOW_S if self._arrivals else 0.0
            ordered = sorted(self._transport)
            transport = ordered[len(ordered) // 2] if ordered else None
            age = (now - self._arrived_ms) / 1000.0 if self._arrived_ms is not None else None
            return PreviewStatus(
                self._connected,
                self._state,
                self._reason,
                fps,
                transport,
                self._frames,
                age,
                self._skipped,
            )

    def request_stop(self) -> bool:
        """Ask the browser to end the capture (it revokes the preview tab's authorization)."""
        with self._lock:
            stop = self._stop
        if stop is None:
            return False
        stop()
        return True

    def _notify(self) -> None:
        for listener in list(self.listeners):
            listener()
