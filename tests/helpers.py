"""Test doubles and synthetic data generators.

These exist only for controlled, repeatable testing. Production code never uses them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import ClassVar

import numpy as np

from interactive_scrolling.config.settings import CameraSettings
from interactive_scrolling.vision.camera import CameraOpenError, Frame
from interactive_scrolling.vision.landmarks import Handedness, HandObservation, TrackingResult

# An open right hand (palm facing the camera, unmirrored image), in palm-length units
# relative to the wrist, x to the right and y down. Wrist -> middle MCP is exactly 1.0.
_TEMPLATE = np.array(
    [
        (0.00, 0.00),  # wrist
        (-0.35, -0.20),  # thumb cmc
        (-0.60, -0.45),  # thumb mcp
        (-0.80, -0.65),  # thumb ip
        (-0.95, -0.85),  # thumb tip
        (-0.30, -1.00),  # index mcp
        (-0.35, -1.40),
        (-0.38, -1.65),
        (-0.40, -1.90),  # index tip
        (0.00, -1.00),  # middle mcp
        (0.00, -1.45),
        (0.00, -1.72),
        (0.00, -2.00),  # middle tip
        (0.28, -0.95),  # ring mcp
        (0.32, -1.35),
        (0.34, -1.60),
        (0.36, -1.85),  # ring tip
        (0.52, -0.85),  # pinky mcp
        (0.60, -1.15),
        (0.64, -1.35),
        (0.68, -1.55),  # pinky tip
    ],
    dtype=np.float64,
)

INDEX_TIP_OFFSET = _TEMPLATE[8]
PALM_CENTER_OFFSET = _TEMPLATE[[0, 5, 9, 13, 17]].mean(axis=0)


def make_hand(
    wrist_px: tuple[float, float],
    palm_px: float = 100.0,
    width: int = 640,
    height: int = 480,
    handedness: Handedness = Handedness.RIGHT,
    score: float | None = 0.95,
) -> HandObservation:
    """Build a synthetic hand whose wrist is at ``wrist_px`` (source pixels)."""
    xy = np.asarray(wrist_px, dtype=np.float64) + _TEMPLATE * palm_px
    if handedness is Handedness.LEFT:
        xy[:, 0] = 2 * wrist_px[0] - xy[:, 0]
    landmarks = np.zeros((21, 3), dtype=np.float32)
    landmarks[:, 0] = xy[:, 0] / width
    landmarks[:, 1] = xy[:, 1] / height
    return HandObservation(landmarks=landmarks, handedness=handedness, handedness_score=score)


def tracking(
    t_ns: int,
    hands: tuple[HandObservation, ...] = (),
    width: int = 640,
    height: int = 480,
    index: int = 0,
) -> TrackingResult:
    return TrackingResult(
        frame_index=index, timestamp_ns=t_ns, image_width=width, image_height=height, hands=hands
    )


class ScriptedTracker:
    """A hand tracker that returns observations from a function of the timestamp."""

    def __init__(
        self,
        script: Callable[[int], tuple[HandObservation, ...]] | None = None,
        delay_s: float = 0.0,
        fail_with: Exception | None = None,
    ) -> None:
        self.script = script or (lambda _ms: ())
        self.delay_s = delay_s
        self.fail_with = fail_with
        self.calls = 0
        self.timestamps: list[int] = []
        self.shapes: list[tuple[int, ...]] = []
        self.closed = False
        self.thread_ids: set[int] = set()

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> tuple[HandObservation, ...]:
        assert image_rgb.ndim == 3 and image_rgb.shape[2] == 3 and image_rgb.dtype == np.uint8
        self.calls += 1
        self.shapes.append(image_rgb.shape)
        self.timestamps.append(timestamp_ms)
        self.thread_ids.add(threading.get_ident())
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail_with is not None:
            raise self.fail_with
        return self.script(timestamp_ms)

    def close(self) -> None:
        self.closed = True


class SyntheticCamera:
    """A camera producing generated BGR frames at a fixed rate, with injectable failures."""

    instances: ClassVar[list[SyntheticCamera]] = []

    def __init__(
        self,
        settings: CameraSettings,
        fps: float = 100.0,
        fail_open: bool = False,
        fail_after: int | None = None,
        open_delay_s: float = 0.0,
    ) -> None:
        self.settings = settings
        self.interval = 1.0 / fps
        self.fail_open = fail_open
        self.fail_after = fail_after
        self.open_delay_s = open_delay_s
        self.actual_width = settings.width
        self.actual_height = settings.height
        self.opened = False
        self.open_calls = 0
        self.close_calls = 0
        self.reads = 0
        SyntheticCamera.instances.append(self)

    def open(self) -> None:
        self.open_calls += 1
        if self.open_delay_s:
            time.sleep(self.open_delay_s)
        if self.fail_open:
            raise CameraOpenError(f"Could not open camera {self.settings.index} (synthetic).")
        self.opened = True

    def read(self) -> Frame | None:
        assert self.opened, "read() on a closed camera"
        time.sleep(self.interval)
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            return None
        image = np.zeros((self.actual_height, self.actual_width, 3), dtype=np.uint8)
        image[:, :, 0] = 255  # pure blue in BGR order
        image[0, 0, 1] = self.reads % 256
        return Frame(image_bgr=image, index=self.reads - 1, timestamp_ns=time.perf_counter_ns())

    def close(self) -> None:
        self.close_calls += 1
        self.opened = False


def camera_factory(**kwargs: object) -> Callable[[CameraSettings], SyntheticCamera]:
    def factory(settings: CameraSettings) -> SyntheticCamera:
        return SyntheticCamera(settings, **kwargs)  # type: ignore[arg-type]

    return factory


def wait_until(predicate: Callable[[], bool], timeout_s: float = 5.0, step_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return predicate()
