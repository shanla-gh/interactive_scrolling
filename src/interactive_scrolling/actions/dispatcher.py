"""The action dispatcher: the only path from a confirmed gesture to an external action.

Safety rules
------------
* Nothing is executed unless the mode is LIVE_CONTROL, both when the gesture is submitted and
  again immediately before execution.
* Every mode change starts a new *generation*. Requests from an older generation are never
  executed, so disabling and re-enabling live control cannot replay old gestures.
* Events older than ``max_event_age_s`` when they reach the front of the queue are rejected
  as stale.
* One action at a time: a gesture that arrives while another action is running is rejected
  rather than queued, so one gesture can never cause several navigations.
* The controller must confirm its context (``check``) right before execution.
* A result is only SUCCEEDED when the controller confirmed the effect; timeouts and
  cancellations are reported as UNKNOWN.

The dispatcher has its own worker thread, so slow browser round trips never block the camera
or inference threads. Listeners are called from the submitting thread and from the worker
thread; they must return quickly.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import replace

from interactive_scrolling.actions.types import (
    DEFAULT_MAPPING,
    ActionController,
    ActionRecord,
    ActionResult,
    ActionStatus,
    ActionType,
    ControlMode,
)
from interactive_scrolling.core.timing import NS_PER_S, Clock, now_ns
from interactive_scrolling.gestures.types import GestureEvent, GestureType

log = logging.getLogger(__name__)

RecordListener = Callable[[ActionRecord], None]
AdmissionCheck = Callable[[ActionRecord], str | None]
"""Returns a reason to refuse the action, or ``None`` (wellbeing pause, co-op arbitration)."""
ModeListener = Callable[[ControlMode, ControlMode, str], None]

TRANSIENT_WAIT_S = 1.2
"""Longest wait for a transient controller state (a Short changing or loading)."""
TRANSIENT_POLL_S = 0.03
ACTION_TIMEOUT_S = {
    ActionType.NEXT_SHORT: 3.0,
    ActionType.PREVIOUS_SHORT: 3.0,
    ActionType.LIKE_SHORT: 3.0,
    ActionType.TOGGLE_PLAYBACK: 2.0,
    ActionType.NEXT_BROWSER_TAB: 2.0,
    ActionType.PREVIOUS_BROWSER_TAB: 2.0,
}


class ActionDispatcher:
    def __init__(
        self,
        controller: ActionController | None,
        mapping: dict[GestureType, ActionType] | None = None,
        max_event_age_s: float = 0.6,
        clock: Clock = now_ns,
    ) -> None:
        self._controller = controller
        self._mapping = dict(mapping or DEFAULT_MAPPING)
        self._max_age_ns = int(max_event_age_s * NS_PER_S)
        self._clock = clock
        self._lock = threading.RLock()
        self._mode = ControlMode.TRACKING_ONLY
        self._generation = 0
        self._busy = False
        self._queue: queue.Queue[tuple[ActionRecord, int] | None] = queue.Queue(maxsize=1)
        self._record_listeners: list[RecordListener] = []
        self._mode_listeners: list[ModeListener] = []
        self._admission: list[AdmissionCheck] = []
        self._worker = threading.Thread(target=self._run, name="action-dispatcher", daemon=True)
        self._stopped = False
        self._worker.start()

    # ------------------------------------------------------------------ configuration

    def add_record_listener(self, listener: RecordListener) -> None:
        self._record_listeners.append(listener)

    def remove_record_listener(self, listener: RecordListener) -> None:
        if listener in self._record_listeners:
            self._record_listeners.remove(listener)

    def add_mode_listener(self, listener: ModeListener) -> None:
        self._mode_listeners.append(listener)

    def add_admission_check(self, check: AdmissionCheck) -> None:
        """Add a check run for every executable action before it is queued."""
        self._admission.append(check)

    @property
    def mode(self) -> ControlMode:
        return self._mode

    @property
    def mapping(self) -> dict[GestureType, ActionType]:
        with self._lock:
            return dict(self._mapping)

    def set_mapping(self, mapping: dict[GestureType, ActionType]) -> None:
        with self._lock:
            self._mapping = dict(mapping)

    def set_mode(self, mode: ControlMode, reason: str = "") -> None:
        """Switch the control mode. Any change invalidates queued and in-flight requests."""
        with self._lock:
            previous = self._mode
            if previous is mode:
                return
            self._mode = mode
            self._generation += 1
            self._drain_queue("control mode changed")
        if previous is ControlMode.LIVE_CONTROL and self._controller is not None:
            try:
                self._controller.cancel_all()
            except Exception:
                log.exception("Controller cancel failed")
        log.info("Control mode: %s%s", mode.label, f" ({reason})" if reason else "")
        for listener in list(self._mode_listeners):
            self._safe(listener, previous, mode, reason)

    def emergency_disable(self) -> None:
        """Stop all external control immediately."""
        self.set_mode(ControlMode.TRACKING_ONLY, "emergency disable")

    def shutdown(self, timeout_s: float = 3.0) -> None:
        self.set_mode(ControlMode.TRACKING_ONLY, "shutdown")
        self._stopped = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._drain_queue("shutdown")
            self._queue.put_nowait(None)
        self._worker.join(timeout_s)

    # ------------------------------------------------------------------ submission

    def set_controller(self, controller: ActionController | None) -> ActionController | None:
        """Replace the controller (co-op guest forwarding); returns the previous one. Pending
        requests are abandoned first so nothing runs against the wrong controller."""
        with self._lock:
            previous = self._controller
            self._generation += 1
            self._drain_queue("controller changed")
            self._controller = controller
        if previous is not None:
            try:
                previous.cancel_all()
            except Exception:
                log.exception("Controller cancel failed")
        return previous

    def submit(
        self, event: GestureEvent, action: ActionType | None = None, source: str = "local"
    ) -> ActionRecord:
        """Handle a confirmed gesture. Safe to call from any thread; never blocks.

        ``action`` overrides the gesture mapping (co-op requests carry their action) and
        ``source`` attributes the request; all other rules are identical."""
        with self._lock:
            mode = self._mode
            generation = self._generation
            if action is None:
                action = self._mapping.get(event.gesture, ActionType.NONE)
        record = ActionRecord(
            record_id=event.event_id,
            event=event,
            action=action,
            mode=mode,
            status=ActionStatus.QUEUED,
            created_ns=self._clock(),
            wall_time=time.time(),
            source=source,
        )
        if mode is not ControlMode.LIVE_CONTROL:
            return self._finish(record, ActionStatus.NOT_EXECUTED, f"{mode.label} mode")
        if action is ActionType.NONE:
            return self._finish(record, ActionStatus.NOT_EXECUTED, "no action mapped")
        if not action.available:
            return self._finish(
                record, ActionStatus.NOT_EXECUTED, "action not available in this version"
            )
        if self._controller is None:
            return self._finish(record, ActionStatus.REJECTED, "no controller available")
        for check in list(self._admission):
            try:
                refusal = check(record)
            except Exception:
                log.exception("Admission check failed; action refused")
                refusal = "internal error in an admission check"
            if refusal:
                return self._finish(record, ActionStatus.REJECTED, refusal)
        with self._lock:
            if self._busy:
                return self._finish(record, ActionStatus.REJECTED, "previous action still running")
            try:
                self._queue.put_nowait((record, generation))
            except queue.Full:
                return self._finish(record, ActionStatus.REJECTED, "previous action still queued")
            self._busy = True
        self._emit(record)
        return record

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            record, generation = item
            try:
                self._execute(record, generation)
            except Exception as exc:
                log.exception("Action execution crashed")
                self._finish(record, ActionStatus.FAILED, f"internal error: {exc}")
            finally:
                with self._lock:
                    self._busy = False

    def _execute(self, record: ActionRecord, generation: int) -> None:
        controller = self._controller
        assert controller is not None
        with self._lock:
            current_generation = self._generation
            mode = self._mode
        if generation != current_generation or mode is not ControlMode.LIVE_CONTROL:
            self._finish(record, ActionStatus.REJECTED, "live control was disabled")
            return
        age = self._clock() - record.event.timestamp_ns
        if age > self._max_age_ns:
            self._finish(record, ActionStatus.REJECTED, f"stale gesture ({age / 1e6:.0f} ms old)")
            return
        check = controller.check(record.action)
        # A transient state (the Short is changing or loading after the previous action) is
        # waited out for a bounded time; this is a single attempt, not a retry.
        deadline = self._clock() + int(TRANSIENT_WAIT_S * NS_PER_S)
        while not check.ready and check.transient and self._clock() < deadline:
            time.sleep(TRANSIENT_POLL_S)
            with self._lock:
                if generation != self._generation or self._mode is not ControlMode.LIVE_CONTROL:
                    self._finish(record, ActionStatus.REJECTED, "live control was disabled")
                    return
            check = controller.check(record.action)
        if not check.ready:
            self._finish(record, ActionStatus.REJECTED, check.reason)
            return
        dispatched = replace(record, status=ActionStatus.DISPATCHED, dispatched_ns=self._clock())
        self._emit(dispatched)
        timeout = ACTION_TIMEOUT_S.get(record.action, 3.0)
        try:
            result = controller.execute(record.action, record.record_id, timeout)
        except Exception as exc:
            log.exception("Controller raised during %s", record.action.value)
            result = ActionResult(ActionStatus.UNKNOWN, f"controller error: {exc}")
        with self._lock:
            disabled_meanwhile = generation != self._generation
        if disabled_meanwhile and result.status is ActionStatus.UNKNOWN:
            result = ActionResult(
                ActionStatus.UNKNOWN, "live control disabled while the action was running"
            )
        self._finish(dispatched, result.status, result.reason, result.detail)

    # ------------------------------------------------------------------ helpers

    def _finish(
        self, record: ActionRecord, status: ActionStatus, reason: str, detail: str = ""
    ) -> ActionRecord:
        final = replace(
            record, status=status, reason=reason, detail=detail, completed_ns=self._clock()
        )
        self._emit(final)
        return final

    def _drain_queue(self, reason: str) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is not None:
                self._busy = False
                self._finish(item[0], ActionStatus.REJECTED, reason)

    def _emit(self, record: ActionRecord) -> None:
        for listener in list(self._record_listeners):
            self._safe(listener, record)

    @staticmethod
    def _safe(callback: Callable[..., None], *args: object) -> None:
        try:
            callback(*args)
        except Exception:
            log.exception("Dispatcher listener failed")
