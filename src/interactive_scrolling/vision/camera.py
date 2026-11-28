"""Webcam acquisition through OpenCV.

The camera object is deliberately synchronous and single-threaded; the pipeline
runs it on a dedicated capture thread. Frames are returned in OpenCV's native BGR
channel order and converted to RGB exactly once, by the processing stage.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np

from interactive_scrolling.config.settings import CameraBackend, CameraSettings
from interactive_scrolling.core.timing import Clock, now_ns

log = logging.getLogger(__name__)

_PRIVACY_HINT = (
    "Check that no other application is using the camera and that camera access is "
    "allowed for desktop apps in Windows Settings > Privacy & security > Camera."
)


class CameraError(RuntimeError):
    """Base class for camera failures. Messages are suitable for display to users."""


class CameraOpenError(CameraError):
    """The camera device could not be opened."""


class CameraReadError(CameraError):
    """The camera opened but did not deliver frames."""


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """A captured video frame.

    ``image_bgr`` is an ``(H, W, 3)`` ``uint8`` array in BGR order, exactly as
    delivered by OpenCV. ``timestamp_ns`` is taken from the shared monotonic clock
    immediately after the frame was read.
    """

    image_bgr: np.ndarray
    index: int
    timestamp_ns: int
    sample_ns: int | None = None
    """The driver's own sample time mapped onto the same clock (Media Foundation only), or
    ``None``. Recorded for analysis; recognition uses ``timestamp_ns`` (Brief 009: the engine
    is tuned on arrival times and regressed when replayed with periodic times)."""

    @property
    def width(self) -> int:
        return int(self.image_bgr.shape[1])

    @property
    def height(self) -> int:
        return int(self.image_bgr.shape[0])


class CaptureDevice(Protocol):
    """The subset of ``cv2.VideoCapture`` used by :class:`OpenCVCamera`."""

    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def set(self, prop_id: int, value: float) -> bool: ...
    def get(self, prop_id: int) -> float: ...
    def release(self) -> None: ...


CaptureFactory = Callable[[int, int], CaptureDevice]

_BACKEND_API: dict[CameraBackend, int] = {
    CameraBackend.MSMF: cv2.CAP_MSMF,
    CameraBackend.DSHOW: cv2.CAP_DSHOW,
    CameraBackend.AUTO: cv2.CAP_ANY,
}


def _default_capture_factory(index: int, api: int) -> CaptureDevice:
    return cv2.VideoCapture(index, api)


def normalize_frame_image(image: Any) -> np.ndarray | None:
    """Validate a raw frame and return a contiguous ``(H, W, 3)`` ``uint8`` BGR array.

    Grayscale and BGRA frames are converted to BGR. Returns ``None`` for frames that
    are empty or have an unsupported layout.
    """
    if not isinstance(image, np.ndarray) or image.size == 0 or image.dtype != np.uint8:
        return None
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3:
        return None
    channels = image.shape[2]
    if channels == 3:
        return image if image.flags.c_contiguous else np.ascontiguousarray(image)
    if channels == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if channels == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return None


class DriverClock:
    """Maps the driver's own frame times onto the application clock (Brief 009).

    Media Foundation reports a sample time per frame (``CAP_PROP_POS_MSEC``) that is exactly
    periodic, while the moment ``read()`` returns jitters by 5-7 ms (standard deviation,
    measured with ``scripts/probe_camera_modes.py``). Motion speeds use frame intervals, so the
    driver times give cleaner velocities. The mapping offset is the smallest observed
    ``arrival - sample`` time, so a mapped timestamp is never later than the frame's arrival;
    it creeps upwards by ``CREEP_NS`` per frame so drift between the two clocks cannot
    accumulate. Invalid driver values (missing, not increasing, gaps over a second) fall back
    to the arrival time and restart the mapping.
    """

    CREEP_NS = 10_000

    def __init__(self) -> None:
        self._offset_ns: int | None = None
        self._last_sample_ns: int | None = None
        self.driver_frames = 0
        self.fallback_frames = 0

    def reset(self) -> None:
        self._offset_ns = None
        self._last_sample_ns = None

    def map(self, sample_ms: float, arrival_ns: int) -> int:
        valid = sample_ms > 0
        sample_ns = int(sample_ms * 1_000_000)
        last = self._last_sample_ns
        if valid and last is not None and not (0 < sample_ns - last < 1_000_000_000):
            valid = False
        if not valid:
            self.reset()
            self.fallback_frames += 1
            return arrival_ns
        self._last_sample_ns = sample_ns
        delay = arrival_ns - sample_ns
        if self._offset_ns is None:
            self._offset_ns = delay
        else:
            self._offset_ns = min(self._offset_ns + self.CREEP_NS, delay)
        self.driver_frames += 1
        return min(arrival_ns, sample_ns + self._offset_ns)


class OpenCVCamera:
    """A webcam opened through ``cv2.VideoCapture``."""

    def __init__(
        self,
        settings: CameraSettings,
        capture_factory: CaptureFactory = _default_capture_factory,
        clock: Clock = now_ns,
        warmup_attempts: int = 20,
        use_driver_timestamps: bool = True,
    ) -> None:
        self._settings = settings
        self._factory = capture_factory
        self._clock = clock
        self._warmup_attempts = max(1, warmup_attempts)
        self._capture: CaptureDevice | None = None
        self._pending: np.ndarray | None = None
        self._next_index = 0
        self.actual_width = 0
        self.actual_height = 0
        self.reported_fps = 0.0
        self.driver_clock = DriverClock() if use_driver_timestamps else None
        """Maps driver sample times (Media Foundation only) into ``Frame.sample_ns``."""

    @property
    def settings(self) -> CameraSettings:
        return self._settings

    @property
    def is_open(self) -> bool:
        return self._capture is not None

    def open(self) -> None:
        """Open the device and wait for the first valid frame.

        Raises :class:`CameraOpenError` or :class:`CameraReadError`. On failure the
        device is always released.
        """
        if self._capture is not None:
            return
        s = self._settings
        api = _BACKEND_API[s.backend]
        try:
            capture = self._factory(s.index, api)
        except cv2.error as exc:
            raise CameraOpenError(f"Could not open camera {s.index}: {exc}") from exc
        if not capture.isOpened():
            capture.release()
            raise CameraOpenError(
                f"Could not open camera {s.index}. The device may not exist. {_PRIVACY_HINT}"
            )
        try:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(s.width))
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(s.height))
            capture.set(cv2.CAP_PROP_FPS, float(s.fps))
            first: np.ndarray | None = None
            for _ in range(self._warmup_attempts):
                ok, raw = capture.read()
                first = normalize_frame_image(raw) if ok else None
                if first is not None:
                    break
            if first is None:
                raise CameraReadError(
                    f"Camera {s.index} opened but did not deliver any frames. {_PRIVACY_HINT}"
                )
        except BaseException:
            capture.release()
            raise
        self._capture = capture
        self._pending = first
        self.actual_height, self.actual_width = first.shape[:2]
        try:
            self.reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
        except cv2.error:
            self.reported_fps = 0.0
        log.info(
            "Camera %d opened (%s): requested %dx%d, delivering %dx%d",
            s.index,
            s.backend.value,
            s.width,
            s.height,
            self.actual_width,
            self.actual_height,
        )

    def read(self) -> Frame | None:
        """Block until the next frame is available. Returns ``None`` if the read failed."""
        capture = self._capture
        if capture is None:
            raise CameraError("Camera is not open.")
        if self._pending is not None:
            image, self._pending = self._pending, None
        else:
            ok, raw = capture.read()
            image = normalize_frame_image(raw) if ok else None
        timestamp = self._clock()
        if image is None:
            return None
        sample_ns = None
        clock = self.driver_clock
        if clock is not None and self._settings.backend is CameraBackend.MSMF:
            try:
                sample_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC))
            except cv2.error:
                sample_ms = 0.0
            mapped = clock.map(sample_ms, timestamp)
            sample_ns = mapped if mapped != timestamp or sample_ms > 0 else None
        frame = Frame(
            image_bgr=image, index=self._next_index, timestamp_ns=timestamp, sample_ns=sample_ns
        )
        self._next_index += 1
        return frame

    def close(self) -> None:
        """Release the device. Safe to call repeatedly."""
        capture, self._capture = self._capture, None
        self._pending = None
        if capture is not None:
            capture.release()
            log.info("Camera %d released", self._settings.index)


@dataclass(frozen=True, slots=True)
class CameraInfo:
    """A camera found by :func:`probe_cameras`."""

    index: int
    width: int
    height: int

    @property
    def label(self) -> str:
        return f"Camera {self.index}  ({self.width}x{self.height})"


def probe_cameras(
    max_index: int = 4,
    backend: CameraBackend = CameraBackend.MSMF,
    capture_factory: CaptureFactory = _default_capture_factory,
) -> list[CameraInfo]:
    """Return the cameras that open and deliver a frame, checking indices ``0..max_index``.

    This briefly opens every device, so it must only run on explicit user request.
    """
    found: list[CameraInfo] = []
    api = _BACKEND_API[backend]
    for index in range(max_index + 1):
        try:
            capture = capture_factory(index, api)
        except cv2.error:
            continue
        try:
            if not capture.isOpened():
                continue
            ok, raw = capture.read()
            image = normalize_frame_image(raw) if ok else None
            if image is not None:
                found.append(CameraInfo(index, int(image.shape[1]), int(image.shape[0])))
        finally:
            capture.release()
    return found
