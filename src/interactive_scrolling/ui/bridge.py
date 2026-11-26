"""Thread-safe bridges from worker threads to the Qt UI thread."""

from __future__ import annotations

import contextlib
import logging
import threading

from PySide6.QtCore import QObject, Signal

from interactive_scrolling.core.pipeline import CameraState, ProcessedFrame, TrackerState


class PipelineBridge(QObject):
    """Receives pipeline callbacks on worker threads and re-emits them as Qt signals.

    Frames are coalesced: at most one ``frame_ready`` notification is in flight, and the
    UI always takes the newest frame. If the UI is momentarily slower than the pipeline,
    intermediate frames are skipped instead of queuing up in the event loop.
    """

    frame_ready = Signal()
    camera_state_changed = Signal(object, str, int)
    tracker_state_changed = Signal(object, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._latest: ProcessedFrame | None = None
        self._pending = False
        self.skipped_frames = 0

    # PipelineListener ---------------------------------------------------------
    def on_frame(self, frame: ProcessedFrame) -> None:
        with self._lock:
            if self._latest is not None:
                self.skipped_frames += 1
            self._latest = frame
            if self._pending:
                return
            self._pending = True
        self.frame_ready.emit()

    def on_camera_state(self, state: CameraState, message: str, session: int) -> None:
        self.camera_state_changed.emit(state, message, session)

    def on_tracker_state(self, state: TrackerState, message: str) -> None:
        self.tracker_state_changed.emit(state, message)

    # UI side -----------------------------------------------------------------
    def take_latest(self) -> ProcessedFrame | None:
        with self._lock:
            frame, self._latest = self._latest, None
            self._pending = False
            return frame


class _LogEmitter(QObject):
    record = Signal(str, int)


class QtLogHandler(logging.Handler):
    """Forwards log records (from any thread) to the UI as a Qt signal."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.emitter = _LogEmitter()
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        # The emitter's C++ object may already be gone during interpreter shutdown.
        with contextlib.suppress(RuntimeError):
            self.emitter.record.emit(self.format(record), record.levelno)
