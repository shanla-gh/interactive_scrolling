"""Detection and attribution of UI-thread stalls (no Qt dependency).

The UI owns a periodic heartbeat that calls :meth:`StallMonitor.beat`. A watchdog thread
notices when the heartbeat is overdue by more than ``threshold_ms`` and records a
:class:`Stall` with everything that helps to explain it:

* ``section``: the UI handler that was running when the stall was detected (handlers are
  wrapped in :meth:`section`), so a slow application handler is named directly;
* ``ui_stack``: the UI thread's Python stack at detection time;
* ``gc_ms``: garbage-collection time that overlapped the stall (from ``gc.callbacks``);
* ``worker_gaps_ms``: for each worker thread that reports progress (camera capture,
  processing), the longest pause in its progress that overlapped the stall. If the workers
  paused too, the whole process was descheduled or blocked (operating-system scheduling,
  paging, the GIL), not the UI code.

Measured per-section durations (``section_stats``) also show which handlers are expensive even
when they stay below the stall threshold. Nothing is written to disk; the owner decides what to
log or display.
"""

from __future__ import annotations

import contextlib
import gc
import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

NS_PER_MS = 1_000_000


@dataclass(frozen=True, slots=True)
class Stall:
    started_ns: int
    """Time of the last heartbeat before the stall."""
    duration_ms: float
    section: str | None
    ui_stack: tuple[str, ...]
    gc_ms: float
    worker_gaps_ms: dict[str, float] = field(default_factory=dict)
    context: str = ""
    """Extra attribution from ``context_provider`` (e.g. the Qt event being processed)."""

    def summary(self) -> str:
        where = self.section or "outside application handlers"
        workers = ", ".join(f"{k} {v:.0f} ms" for k, v in sorted(self.worker_gaps_ms.items()))
        top = self.ui_stack[-1].strip().splitlines()[0] if self.ui_stack else "no stack"
        extra = f"; {self.context}" if self.context else ""
        return (
            f"UI stalled {self.duration_ms:.0f} ms in {where}; GC {self.gc_ms:.0f} ms; "
            f"worker gaps: {workers or 'n/a'}; at {top}{extra}"
        )


@dataclass(slots=True)
class SectionStats:
    calls: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.calls if self.calls else 0.0


class StallMonitor:
    def __init__(
        self,
        threshold_ms: float = 150.0,
        poll_ms: float = 10.0,
        clock: Callable[[], int] = time.perf_counter_ns,
        capacity: int = 200,
        on_stall: Callable[[Stall], None] | None = None,
        context_provider: Callable[[], str] | None = None,
    ) -> None:
        self.threshold_ms = threshold_ms
        self._poll_s = poll_ms / 1000
        self._clock = clock
        self._on_stall = on_stall
        self.context_provider = context_provider
        self._lock = threading.Lock()
        self._ui_thread_id = threading.get_ident()
        self._last_beat = clock()
        self._section: str | None = None
        self._section_stats: dict[str, SectionStats] = {}
        self._workers: dict[str, int] = {}
        self._worker_gaps: deque[tuple[str, int, int]] = deque(maxlen=512)
        self._gc_intervals: deque[tuple[int, int]] = deque(maxlen=256)
        self._gc_start: int | None = None
        self.stalls: deque[Stall] = deque(maxlen=capacity)
        self.max_stall_ms = 0.0
        self.stall_count = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Start the watchdog. Call from the UI thread (it becomes the monitored thread)."""
        if self._thread is not None:
            return
        self._ui_thread_id = threading.get_ident()
        self._last_beat = self._clock()
        gc.callbacks.append(self._gc_callback)
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, name="stall-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        with contextlib.suppress(ValueError):
            gc.callbacks.remove(self._gc_callback)

    # ------------------------------------------------------------------ instrumentation

    def beat(self) -> None:
        """UI heartbeat (call from a periodic UI timer)."""
        self._last_beat = self._clock()

    WORKER_GAP_NS = 100 * NS_PER_MS

    def worker_progress(self, name: str) -> None:
        """A worker thread reports that it made progress (cheap, any thread)."""
        now = self._clock()
        previous = self._workers.get(name)
        if previous is not None and now - previous > self.WORKER_GAP_NS:
            self._worker_gaps.append((name, previous, now))
        self._workers[name] = now

    def _worker_overlap_ms(self, start: int, end: int) -> dict[str, float]:
        out: dict[str, float] = {name: 0.0 for name in self._workers}
        for name, a, b in list(self._worker_gaps):
            overlap = max(0, min(b, end) - max(a, start)) / NS_PER_MS
            out[name] = max(out.get(name, 0.0), overlap)
        for name, last in list(self._workers.items()):
            # A worker that has not reported since before the stall ended is still paused.
            if last < end:
                ongoing = max(0, end - max(last, start)) / NS_PER_MS
                if ongoing * NS_PER_MS > self.WORKER_GAP_NS:
                    out[name] = max(out[name], ongoing)
        return out

    @contextlib.contextmanager
    def section(self, name: str) -> Iterator[None]:
        """Time a UI handler and mark it as the running section."""
        outer = self._section
        self._section = name
        start = self._clock()
        try:
            yield
        finally:
            elapsed = (self._clock() - start) / NS_PER_MS
            self._section = outer
            with self._lock:
                stats = self._section_stats.setdefault(name, SectionStats())
                stats.calls += 1
                stats.total_ms += elapsed
                stats.max_ms = max(stats.max_ms, elapsed)

    def wrap(self, name: str, function: Callable[..., object]) -> Callable[..., object]:
        def wrapped(*args: object, **kwargs: object) -> object:
            with self.section(name):
                return function(*args, **kwargs)

        return wrapped

    def section_stats(self) -> dict[str, SectionStats]:
        with self._lock:
            return {
                k: SectionStats(v.calls, v.total_ms, v.max_ms)
                for k, v in self._section_stats.items()
            }

    # ------------------------------------------------------------------ watchdog

    def _gc_callback(self, phase: str, info: dict) -> None:
        now = self._clock()
        if phase == "start":
            self._gc_start = now
        elif self._gc_start is not None:
            self._gc_intervals.append((self._gc_start, now))
            self._gc_start = None

    def _gc_overlap_ms(self, start: int, end: int) -> float:
        total = 0
        for a, b in list(self._gc_intervals):
            total += max(0, min(b, end) - max(a, start))
        return total / NS_PER_MS

    def _watch(self) -> None:
        threshold_ns = int(self.threshold_ms * NS_PER_MS)
        while not self._stop.wait(self._poll_s):
            beat = self._last_beat
            if self._clock() - beat <= threshold_ns:
                continue
            # Stalled: capture where the UI thread is, then wait for it to recover.
            section = self._section
            context = ""
            if self.context_provider is not None:
                with contextlib.suppress(Exception):
                    context = self.context_provider()
            frame = sys._current_frames().get(self._ui_thread_id)
            stack = tuple(traceback.format_stack(frame)[-8:]) if frame is not None else ()
            while not self._stop.wait(self._poll_s) and self._last_beat == beat:
                pass
            end = self._last_beat if self._last_beat != beat else self._clock()
            duration = (end - beat) / NS_PER_MS
            workers = self._worker_overlap_ms(beat, end)
            stall = Stall(
                beat, duration, section, stack, self._gc_overlap_ms(beat, end), workers, context
            )
            self.stalls.append(stall)
            self.stall_count += 1
            self.max_stall_ms = max(self.max_stall_ms, duration)
            if self._on_stall is not None:
                with contextlib.suppress(Exception):
                    self._on_stall(stall)
