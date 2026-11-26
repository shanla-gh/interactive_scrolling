"""Transparent-background compositing for the Content Creator overlay (presentation only).

The overlay draws its own *downscaled copy* of the camera frame; the hand-tracking pipeline is
never affected. A person mask from the segmentation worker becomes the copy's alpha channel:

* the mask is resized to the copy's size and mapped through a soft ramp
  (``alpha = clip((confidence - LOW) / (HIGH - LOW), 0, 1)``), so edges fade instead of
  flickering between on and off;
* it is smoothed over time (exponential moving average) to suppress frame-to-frame noise;
* a mask that is older than ``MAX_MASK_AGE_S`` relative to the frame, or from another camera
  session, is **not** used: the caller must then hide the camera image entirely, so the
  original background is never shown unexpectedly while transparency is on.
"""

from __future__ import annotations

import cv2
import numpy as np

LOW = 0.35
HIGH = 0.75
SMOOTHING = 0.5
"""Weight of the newest mask in the temporal average."""
MAX_MASK_AGE_S = 0.5


class MaskCompositor:
    def __init__(self) -> None:
        self._alpha: np.ndarray | None = None
        self._mask_ts: int | None = None

    def reset(self) -> None:
        self._alpha = None
        self._mask_ts = None

    @staticmethod
    def usable(mask_ts_ns: int, mask_session: int, frame_ts_ns: int, frame_session: int) -> bool:
        return mask_session == frame_session and abs(frame_ts_ns - mask_ts_ns) <= int(
            MAX_MASK_AGE_S * 1e9
        )

    def compose(
        self, image_rgb: np.ndarray, mask: np.ndarray, mask_ts_ns: int, size: tuple[int, int]
    ) -> np.ndarray:
        """RGBA (``size`` = width, height) copy of ``image_rgb`` with the background removed."""
        width, height = size
        small = cv2.resize(image_rgb, (width, height), interpolation=cv2.INTER_AREA)
        confidence = cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)
        alpha = np.clip((confidence - LOW) / (HIGH - LOW), 0.0, 1.0)
        previous = self._alpha
        if previous is not None and previous.shape == alpha.shape and mask_ts_ns != self._mask_ts:
            alpha = SMOOTHING * alpha + (1 - SMOOTHING) * previous
        elif previous is not None and previous.shape == alpha.shape:
            alpha = previous  # same mask as last time: keep the smoothed value
        self._alpha = alpha
        self._mask_ts = mask_ts_ns
        rgba = np.empty((height, width, 4), dtype=np.uint8)
        rgba[..., :3] = small
        rgba[..., 3] = (alpha * 255.0 + 0.5).astype(np.uint8)
        return rgba
