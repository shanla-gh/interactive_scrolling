"""Synthetic camera scene for screenshots and demonstrations (no person, no webcam image).

A drawn room with a light figure, a scripted pointing hand that swipes up every 3 s, and the
figure's known outline as a stand-in segmentation mask.
"""

from __future__ import annotations

import math
import time

import numpy as np
from tests.gesture_helpers import POINTING, make_observation

from interactive_scrolling.config.settings import CameraSettings
from interactive_scrolling.vision.camera import Frame

W, H = 1280, 720


def figure_mask(w: int, h: int) -> np.ndarray:
    """A head-and-shoulders outline (float 0..1), the synthetic 'person'."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    head = ((xx - w * 0.5) / (w * 0.085)) ** 2 + ((yy - h * 0.36) / (h * 0.17)) ** 2 <= 1.0
    torso = ((xx - w * 0.5) / (w * 0.26)) ** 2 + ((yy - h * 1.02) / (h * 0.5)) ** 2 <= 1.0
    return (head | torso).astype(np.float32)


class SceneCamera:
    """30 fps generated frames: a dim room with a lighter figure (no real image)."""

    def __init__(self, settings: CameraSettings) -> None:
        self.settings = settings
        self.actual_width, self.actual_height = W, H
        self.opened = False
        self._n = 0
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        room = np.stack([40 + 30 * yy / H, 46 + 26 * xx / W, 58 + 20 * yy / H], axis=-1)
        room[int(H * 0.15) : int(H * 0.55), int(W * 0.72) : int(W * 0.9)] = (70, 92, 120)  # window
        mask = figure_mask(W, H)[..., None]
        person = np.empty_like(room)
        person[...] = (196, 200, 206)  # light shirt
        skin = (((xx - W * 0.5) / (W * 0.085)) ** 2 + ((yy - H * 0.36) / (H * 0.17)) ** 2) <= 1
        person[skin] = (150, 170, 205)
        self._image = (room * (1 - mask) + person * mask).astype(np.uint8)

    def open(self) -> None:
        self.opened = True

    def read(self) -> Frame | None:
        time.sleep(1 / 30)
        self._n += 1
        return Frame(
            image_bgr=self._image.copy(), index=self._n - 1, timestamp_ns=time.perf_counter_ns()
        )

    def close(self) -> None:
        self.opened = False


def failing_camera(settings: CameraSettings):  # type: ignore[no-untyped-def]
    from interactive_scrolling.vision.camera import CameraOpenError

    class Unavailable(SceneCamera):
        def open(self) -> None:
            raise CameraOpenError("Could not open camera 0 (it may be in use by another app).")

    return Unavailable(settings)


class ScriptedHand:
    """A pointing hand at the right side that rests and swipes up every 3 s."""

    def __init__(self) -> None:
        self.t0: int | None = None

    def process(self, image_rgb: np.ndarray, timestamp_ms: int):  # type: ignore[no-untyped-def]
        if self.t0 is None:
            self.t0 = timestamp_ms
        t = ((timestamp_ms - self.t0) / 1000.0) % 3.0
        y = 470.0 if t < 1.6 else 470.0 - min(1.0, (t - 1.6) / 0.25) * 160.0
        x = 900.0 + 6 * math.sin(timestamp_ms / 300.0)
        return (make_observation(POINTING, (x, y), palm_px=95.0),)

    def close(self) -> None:
        pass


class OutlineSegmenter:
    """Technical demonstration: returns the synthetic figure's outline as the mask."""

    def __init__(self) -> None:
        self._mask: np.ndarray | None = None

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> np.ndarray:
        h, w = image_rgb.shape[:2]
        if self._mask is None or self._mask.shape != (h, w):
            self._mask = figure_mask(w, h)
        return self._mask

    def close(self) -> None:
        pass
