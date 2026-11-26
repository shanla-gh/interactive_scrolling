"""The real-time vision pipeline: camera -> inference -> motion analysis -> listener.

Threading model
---------------
* **Capture thread** (one per camera session): opens the camera, reads frames as fast
  as the device delivers them and publishes each frame into a single-slot
  :class:`LatestValueMailbox`. Reading continuously keeps the driver's buffer empty, so
  the newest frame is always the one processed.
* **Processing thread** (one for the pipeline's lifetime): loads the hand landmarker once,
  then repeatedly takes the newest frame, converts BGR to RGB, runs inference and motion
  analysis, and hands a :class:`ProcessedFrame` to the listener. If inference is slower
  than capture, intermediate frames are dropped (and counted) rather than queued, which
  bounds both memory and latency.
* The listener is called from these worker threads (and, for camera state changes, from
  the thread calling ``start_camera``/``stop_camera``). Camera state notifications are
  issued while the state lock is held, so they always arrive in order. Listeners must
  return quickly; UI code marshals the calls onto its own thread (see ``ui.bridge``).

Each camera start begins a new *session*. Frames carry their session number so that
consumers can discard results that belong to a session that has already been stopped.
"""

from __future__ import annotations

import enum
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from interactive_scrolling.config.settings import CameraSettings, MotionSettings
from interactive_scrolling.core.mailbox import LatestValueMailbox
from interactive_scrolling.core.timing import NS_PER_MS, Clock, RateMeter, RollingStats, now_ns
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureEvent, GestureFrame
from interactive_scrolling.motion.analyzer import MotionAnalyzer, MotionFrame
from interactive_scrolling.vision.camera import CameraError, CameraReadError, Frame
from interactive_scrolling.vision.hand_tracker import HandTracker
from interactive_scrolling.vision.landmarks import HandObservation, TrackingResult

log = logging.getLogger(__name__)


class CameraState(enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TrackerState(enum.Enum):
    NOT_LOADED = "not loaded"
    LOADING = "loading"
    READY = "ready"
    UNAVAILABLE = "unavailable"


class CameraSource(Protocol):
    actual_width: int
    actual_height: int

    def open(self) -> None: ...
    def read(self) -> Frame | None: ...
    def close(self) -> None: ...


CameraFactory = Callable[[CameraSettings], CameraSource]
TrackerFactory = Callable[[], HandTracker]


@dataclass(frozen=True, slots=True, eq=False)
class ProcessedFrame:
    """A fully processed frame, ready for visualization."""

    session: int
    image_rgb: np.ndarray
    tracking: TrackingResult
    motion: MotionFrame
    capture_ns: int
    completed_ns: int
    inference_ms: float | None
    processing_ms: float
    gestures: GestureFrame | None = None
    gesture_ms: float | None = None
    """Time spent in gesture recognition for this frame."""

    @property
    def latency_ms(self) -> float:
        """Time from frame capture to the end of processing."""
        return (self.completed_ns - self.capture_ns) / NS_PER_MS


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    """A snapshot of measured pipeline performance. ``None`` means "no data yet"."""

    camera_state: CameraState
    tracker_state: TrackerState
    session: int
    frame_width: int
    frame_height: int
    capture_fps: float
    processing_fps: float
    inference_ms: float | None
    processing_ms: float | None
    latency_ms: float | None
    latency_p95_ms: float | None
    frames_captured: int
    frames_processed: int
    frames_dropped: int


class PipelineListener(Protocol):
    def on_frame(self, frame: ProcessedFrame) -> None: ...
    def on_camera_state(self, state: CameraState, message: str, session: int) -> None: ...
    def on_tracker_state(self, state: TrackerState, message: str) -> None: ...


@dataclass(frozen=True, slots=True, eq=False)
class _SessionFrame:
    session: int
    frame: Frame


class VisionPipeline:
    """Owns the capture and processing threads and their lifecycle."""

    def __init__(
        self,
        listener: PipelineListener,
        camera_factory: CameraFactory,
        tracker_factory: TrackerFactory | None,
        motion_settings: MotionSettings | None = None,
        max_consecutive_read_failures: int = 30,
        max_consecutive_inference_failures: int = 10,
        clock: Clock = now_ns,
        inference_max_width: int | None = None,
        gesture_engine: GestureEngine | None = None,
        on_gesture_event: Callable[[GestureEvent], None] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._listener = listener
        self._inference_max_width = inference_max_width
        self._camera_factory = camera_factory
        self._tracker_factory = tracker_factory
        self._analyzer = MotionAnalyzer(motion_settings)
        self._gesture_engine = gesture_engine
        self._on_gesture_event = on_gesture_event
        self._progress = progress or (lambda name: None)
        self._frame_taps: list[Callable[[np.ndarray, int, int], None]] = []
        """Called with "capture" / "processing" after every frame (stall attribution)."""
        self._gestures_enabled = False
        self._gesture_reset_requested = False
        self._gesture_stats = RollingStats(120)
        self._max_read_failures = max(1, max_consecutive_read_failures)
        self._max_inference_failures = max(1, max_consecutive_inference_failures)
        self._clock = clock

        # Re-entrant: camera-state notifications are emitted while it is held (to keep them
        # in order), so a listener that calls back into the pipeline must not deadlock.
        self._lock = threading.RLock()
        self._mailbox: LatestValueMailbox[_SessionFrame] = LatestValueMailbox()
        self._shutdown = threading.Event()
        self._processing_thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._capture_stop = threading.Event()

        self._camera_state = CameraState.STOPPED
        self._tracker_state = TrackerState.NOT_LOADED
        self._session = 0
        self._frame_size = (0, 0)
        self._frames_captured = 0
        self._frames_processed = 0

        self._capture_rate = RateMeter(1.0, clock)
        self._processing_rate = RateMeter(1.0, clock)
        self._inference_stats = RollingStats(60)
        self._processing_stats = RollingStats(60)
        self._latency_stats = RollingStats(120)

    # ------------------------------------------------------------------ lifecycle

    def launch(self) -> None:
        """Start the processing thread (and load the hand tracker). Idempotent."""
        with self._lock:
            if self._processing_thread is not None:
                return
            self._processing_thread = threading.Thread(
                target=self._processing_loop, name="vision-processing", daemon=True
            )
            self._processing_thread.start()

    def start_camera(self, settings: CameraSettings) -> bool:
        """Begin a new camera session. Returns ``False`` if a session is already active."""
        if self._shutdown.is_set():
            return False
        previous = self._capture_thread
        if previous is not None and previous.is_alive():
            # A session that has reported STOPPED/ERROR may still be returning.
            previous.join(timeout=0.5)
            if previous.is_alive():
                log.warning("Previous camera session is still shutting down.")
                return False
        with self._lock:
            if self._camera_state in (
                CameraState.STARTING,
                CameraState.RUNNING,
                CameraState.STOPPING,
            ):
                return False
            self._session += 1
            session = self._session
            self._capture_stop = threading.Event()
            self._frame_size = (0, 0)
            self._capture_rate.reset()
            self._processing_rate.reset()
            self._latency_stats.reset()
            self._camera_state = CameraState.STARTING
            thread = threading.Thread(
                target=self._capture_loop,
                args=(session, settings, self._capture_stop),
                name=f"camera-capture-{session}",
                daemon=True,
            )
            self._capture_thread = thread
            self._notify_camera(
                CameraState.STARTING, f"Opening camera {settings.index}...", session
            )
        thread.start()
        return True

    def stop_camera(self) -> None:
        """Request the active camera session to stop. Returns immediately."""
        with self._lock:
            if self._camera_state not in (CameraState.STARTING, CameraState.RUNNING):
                return
            self._camera_state = CameraState.STOPPING
            self._capture_stop.set()
            self._notify_camera(CameraState.STOPPING, "Stopping camera...", self._session)

    def shutdown(self, timeout_s: float = 5.0) -> bool:
        """Stop everything and release all resources. Returns ``True`` if all threads exited."""
        self.stop_camera()
        self._shutdown.set()
        self._mailbox.wake()
        clean = True
        for thread in (self._capture_thread, self._processing_thread):
            if thread is not None:
                thread.join(timeout=timeout_s)
                if thread.is_alive():
                    log.error("Thread %s did not exit within %.1f s", thread.name, timeout_s)
                    clean = False
        return clean

    def wait_for_camera_stop(self, timeout_s: float) -> bool:
        """Block until the current capture thread exits (used by tests and tools)."""
        thread = self._capture_thread
        if thread is None:
            return True
        thread.join(timeout=timeout_s)
        return not thread.is_alive()

    # ------------------------------------------------------------------ state

    @property
    def camera_state(self) -> CameraState:
        return self._camera_state

    @property
    def tracker_state(self) -> TrackerState:
        return self._tracker_state

    @property
    def session(self) -> int:
        return self._session

    def metrics(self) -> PipelineMetrics:
        running = self._camera_state is CameraState.RUNNING
        return PipelineMetrics(
            camera_state=self._camera_state,
            tracker_state=self._tracker_state,
            session=self._session,
            frame_width=self._frame_size[0],
            frame_height=self._frame_size[1],
            capture_fps=self._capture_rate.rate() if running else 0.0,
            processing_fps=self._processing_rate.rate() if running else 0.0,
            inference_ms=self._inference_stats.mean(),
            processing_ms=self._processing_stats.mean(),
            latency_ms=self._latency_stats.mean(),
            latency_p95_ms=self._latency_stats.percentile(95),
            frames_captured=self._frames_captured,
            frames_processed=self._frames_processed,
            frames_dropped=self._mailbox.dropped,
        )

    # ------------------------------------------------------------------ threads

    def _capture_loop(self, session: int, settings: CameraSettings, stop: threading.Event) -> None:
        camera: CameraSource | None = None
        error: str | None = None
        try:
            camera = self._camera_factory(settings)
            camera.open()
            with self._lock:
                # A stop requested while the device was opening wins.
                if stop.is_set() or self._camera_state is not CameraState.STARTING:
                    return
                self._frame_size = (camera.actual_width, camera.actual_height)
                self._camera_state = CameraState.RUNNING
                self._notify_camera(
                    CameraState.RUNNING,
                    f"Camera {settings.index} running at "
                    f"{camera.actual_width}x{camera.actual_height}",
                    session,
                )
            failures = 0
            while not stop.is_set():
                frame = camera.read()
                if frame is None:
                    failures += 1
                    if failures >= self._max_read_failures:
                        raise CameraReadError(
                            f"Camera {settings.index} stopped delivering frames. It may have "
                            "been disconnected or taken over by another application."
                        )
                    stop.wait(0.01)
                    continue
                failures = 0
                self._frames_captured += 1
                self._capture_rate.tick(frame.timestamp_ns)
                self._mailbox.publish(_SessionFrame(session, frame))
                self._progress("capture")
        except CameraError as exc:
            error = str(exc)
        except Exception as exc:
            log.exception("Unexpected error in camera session %d", session)
            error = f"Unexpected camera error: {exc}"
        finally:
            if camera is not None:
                try:
                    camera.close()
                except Exception:
                    log.exception("Error while releasing the camera")
            self._mailbox.clear()
            final = CameraState.ERROR if error else CameraState.STOPPED
            with self._lock:
                self._camera_state = final
                self._notify_camera(final, error or "Camera stopped", session)

    def _processing_loop(self) -> None:
        # The model loads on a helper thread so that the live preview is available
        # immediately; frames are passed through without inference until it is ready.
        loaded: list[HandTracker | None] = []
        loader: threading.Thread | None = None
        if self._tracker_factory is None:
            self._set_tracker_state(TrackerState.UNAVAILABLE, "Hand tracking is disabled.")
        else:
            loader = threading.Thread(
                target=lambda: loaded.append(self._load_tracker()),
                name="tracker-loader",
                daemon=True,
            )
            loader.start()
        tracker: HandTracker | None = None
        current_session: int | None = None
        inference_failures = 0
        try:
            while not self._shutdown.is_set():
                if loader is not None and not loader.is_alive():
                    tracker = loaded[0] if loaded else None
                    loader = None
                    # Statistics so far describe preview-only frames; start fresh so the
                    # reported latency reflects frames that include inference.
                    self._processing_stats.reset()
                    self._latency_stats.reset()
                item = self._mailbox.take(timeout=0.1)
                if item is None:
                    continue
                if item.session != current_session:
                    current_session = item.session
                    self._analyzer.reset()
                    if self._gesture_engine is not None:
                        self._gesture_engine.reset()
                frame = item.frame
                started = self._clock()
                image_rgb = cv2.cvtColor(frame.image_bgr, cv2.COLOR_BGR2RGB)
                hands: tuple[HandObservation, ...] = ()
                inference_ms: float | None = None
                if tracker is not None:
                    t0 = self._clock()
                    try:
                        hands = tracker.process(
                            self._inference_input(image_rgb), frame.timestamp_ns // NS_PER_MS
                        )
                        inference_failures = 0
                    except Exception as exc:
                        inference_failures += 1
                        log.exception("Hand inference failed")
                        if inference_failures >= self._max_inference_failures:
                            self._close_tracker(tracker)
                            tracker = None
                            self._set_tracker_state(
                                TrackerState.UNAVAILABLE,
                                f"Hand tracking stopped after repeated failures: {exc}",
                            )
                    inference_ms = (self._clock() - t0) / NS_PER_MS
                    self._inference_stats.add(inference_ms)
                tracking = TrackingResult(
                    frame_index=frame.index,
                    timestamp_ns=frame.timestamp_ns,
                    image_width=frame.width,
                    image_height=frame.height,
                    hands=hands,
                    inference_ms=inference_ms,
                )
                motion = self._analyzer.update(tracking)
                gestures, gesture_ms = self._recognize(tracking, motion)
                completed = self._clock()
                processed = ProcessedFrame(
                    session=item.session,
                    image_rgb=image_rgb,
                    tracking=tracking,
                    motion=motion,
                    capture_ns=frame.timestamp_ns,
                    completed_ns=completed,
                    inference_ms=inference_ms,
                    processing_ms=(completed - started) / NS_PER_MS,
                    gestures=gestures,
                    gesture_ms=gesture_ms,
                )
                self._frames_processed += 1
                self._processing_rate.tick(completed)
                self._processing_stats.add(processed.processing_ms)
                self._latency_stats.add(processed.latency_ms)
                self._safe_call(self._listener.on_frame, processed)
                for tap in self._frame_taps:
                    # Optional presentation/analytics workers get the frame only after hand
                    # tracking and gesture recognition are complete (read-only, non-blocking).
                    self._safe_call(tap, image_rgb, frame.timestamp_ns, item.session)
                self._progress("processing")
        finally:
            if loader is not None:
                loader.join(timeout=30.0)
                tracker = loaded[0] if loaded else None
            if tracker is not None:
                self._close_tracker(tracker)

    # ------------------------------------------------------------------ gestures

    def add_frame_tap(self, tap: Callable[[np.ndarray, int, int], None]) -> None:
        """Register ``tap(image_rgb, timestamp_ns, session)``, called for every processed frame
        on the processing thread. Taps must return immediately and must not modify the image.
        Register taps before ``launch``."""
        self._frame_taps.append(tap)

    def set_gestures_enabled(self, enabled: bool) -> None:
        """Turn gesture recognition on or off. Thread-safe; any change resets the engine so no
        half-finished candidate survives a mode switch."""
        with self._lock:
            if enabled != self._gestures_enabled:
                self._gestures_enabled = enabled
                self._gesture_reset_requested = True

    @property
    def gesture_ms_mean(self) -> float | None:
        return self._gesture_stats.mean()

    def _recognize(
        self, tracking: TrackingResult, motion: MotionFrame
    ) -> tuple[GestureFrame | None, float | None]:
        engine = self._gesture_engine
        if engine is None:
            return None, None
        with self._lock:
            enabled = self._gestures_enabled
            reset, self._gesture_reset_requested = self._gesture_reset_requested, False
        if reset:
            engine.reset()
        if not enabled:
            return None, None
        t0 = self._clock()
        try:
            frame = engine.update(tracking, motion)
        except Exception:
            log.exception("Gesture recognition failed; engine reset")
            engine.reset()
            return None, None
        elapsed = (self._clock() - t0) / NS_PER_MS
        self._gesture_stats.add(elapsed)
        if self._on_gesture_event is not None:
            for event in frame.events:
                self._safe_call(self._on_gesture_event, event)
        return frame, elapsed

    def _inference_input(self, image_rgb: np.ndarray) -> np.ndarray:
        """Optionally downscale the frame for inference (landmarks are normalized)."""
        limit = self._inference_max_width
        height, width = image_rgb.shape[:2]
        if limit is None or width <= limit:
            return image_rgb
        size = (limit, max(1, round(height * limit / width)))
        return cv2.resize(image_rgb, size, interpolation=cv2.INTER_AREA)

    def _load_tracker(self) -> HandTracker | None:
        assert self._tracker_factory is not None
        self._set_tracker_state(TrackerState.LOADING, "Loading hand landmark model...")
        try:
            tracker = self._tracker_factory()
        except Exception as exc:
            log.error("Hand tracker could not be loaded: %s", exc)
            self._set_tracker_state(TrackerState.UNAVAILABLE, str(exc))
            return None
        self._set_tracker_state(TrackerState.READY, "Hand landmark model ready")
        return tracker

    @staticmethod
    def _close_tracker(tracker: HandTracker) -> None:
        try:
            tracker.close()
        except Exception:
            log.exception("Error while closing the hand tracker")

    def _set_tracker_state(self, state: TrackerState, message: str) -> None:
        self._tracker_state = state
        self._safe_call(self._listener.on_tracker_state, state, message)

    def _notify_camera(self, state: CameraState, message: str, session: int) -> None:
        self._safe_call(self._listener.on_camera_state, state, message, session)

    @staticmethod
    def _safe_call(callback: Callable[..., None], *args: object) -> None:
        # A failing listener must not take down a worker thread; the error is logged.
        try:
            callback(*args)
        except Exception:
            log.exception("Pipeline listener raised an exception")
