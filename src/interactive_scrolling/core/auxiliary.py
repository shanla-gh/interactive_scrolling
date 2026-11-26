"""Optional inference workers (segmentation, face landmarks) beside the primary pipeline.

The primary processing thread hands every processed frame to :meth:`AuxiliaryWorker.submit`,
which only stores a *read-only view* in a single-slot mailbox and returns immediately; it
costs the primary pipeline nothing measurable and can never slow it down. The worker thread
runs its model on the newest frame at most ``max_fps`` times per second and keeps the latest
result with the frame's timestamp and session, so consumers can reject stale results.

* Disabled workers neither load nor run their model; disabling closes the model again.
* The worker never modifies frames (the view it receives is read-only), so nothing it does can
  alter what the hand tracker or gesture engine see.
* Errors are logged and reported through ``state``; repeated failures disable the worker.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from interactive_scrolling.core.mailbox import LatestValueMailbox
from interactive_scrolling.core.timing import NS_PER_MS, RollingStats

log = logging.getLogger(__name__)


class Processor[R](Protocol):
    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> R: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AuxResult[R]:
    value: R
    timestamp_ns: int
    """Capture timestamp of the frame the result belongs to."""
    session: int
    completed_ns: int


@dataclass(frozen=True, slots=True, eq=False)
class _Job:
    image: np.ndarray
    timestamp_ns: int
    session: int


class AuxiliaryWorker[R]:
    MAX_FAILURES = 10

    def __init__(
        self,
        name: str,
        factory: Callable[[], Processor[R]],
        max_fps: float = 15.0,
        clock: Callable[[], int] = time.perf_counter_ns,
        on_result: Callable[[AuxResult[R]], None] | None = None,
    ) -> None:
        self.name = name
        self.on_result = on_result
        """Called on the worker thread with every new result (must return quickly)."""
        self._factory = factory
        self._interval_ns = int(1e9 / max_fps)
        self._clock = clock
        self._mailbox: LatestValueMailbox[_Job] = LatestValueMailbox()
        self._enabled = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: AuxResult[R] | None = None
        self.state = "off"
        """off, loading, running, unavailable (with ``message``)."""
        self.message = ""
        self.inference = RollingStats(60)
        self.processed = 0
        self._thread = threading.Thread(target=self._run, name=f"aux-{name}", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ control

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            if self.state == "unavailable":
                self.state = "off"  # allow a retry after the user re-enables the feature
            self._enabled.set()
        else:
            self._enabled.clear()
            self._mailbox.clear()
            with self._lock:
                self._latest = None
        self._mailbox.wake()

    def submit(self, image_rgb: np.ndarray, timestamp_ns: int, session: int) -> None:
        """Offer a frame (called from the processing thread; never blocks)."""
        if not self._enabled.is_set():
            return
        view = image_rgb.view()
        view.flags.writeable = False
        self._mailbox.publish(_Job(view, timestamp_ns, session))

    def latest(self) -> AuxResult[R] | None:
        with self._lock:
            return self._latest

    def shutdown(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._enabled.clear()
        self._mailbox.wake()
        self._thread.join(timeout_s)

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        processor: Processor[R] | None = None
        failures = 0
        last_ns = 0
        try:
            while not self._stop.is_set():
                if not self._enabled.is_set():
                    if processor is not None:
                        self._close(processor)
                        processor = None
                        self.state = "off"
                    self._enabled.wait(0.2)
                    continue
                if processor is None:
                    if self.state == "unavailable":
                        self._enabled.wait(0.5)
                        continue
                    self.state = "loading"
                    try:
                        processor = self._factory()
                    except Exception as exc:
                        log.error("%s unavailable: %s", self.name, exc)
                        self.state, self.message = "unavailable", str(exc)
                        continue
                    self.state, self.message, failures = "running", "", 0
                job = self._mailbox.take(timeout=0.2)
                if job is None or not self._enabled.is_set():
                    continue
                wait = self._interval_ns - (self._clock() - last_ns)
                if wait > 0:
                    # Rate limit; a newer frame may arrive meanwhile and is used instead.
                    self._stop.wait(wait / 1e9)
                    job = self._mailbox.take(timeout=0) or job
                last_ns = self._clock()
                try:
                    value = processor.process(job.image, job.timestamp_ns // NS_PER_MS)
                    failures = 0
                except Exception as exc:
                    failures += 1
                    log.exception("%s inference failed", self.name)
                    if failures >= self.MAX_FAILURES:
                        self._close(processor)
                        processor = None
                        self.state, self.message = "unavailable", f"repeated failures: {exc}"
                    continue
                done = self._clock()
                self.inference.add((done - last_ns) / NS_PER_MS)
                self.processed += 1
                if self._enabled.is_set():
                    result = AuxResult(value, job.timestamp_ns, job.session, done)
                    with self._lock:
                        self._latest = result
                    if self.on_result is not None:
                        try:
                            self.on_result(result)
                        except Exception:
                            log.exception("%s result listener failed", self.name)
        finally:
            if processor is not None:
                self._close(processor)

    def _close(self, processor: Processor[R]) -> None:
        try:
            processor.close()
        except Exception:
            log.exception("Closing %s failed", self.name)
