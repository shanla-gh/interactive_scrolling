"""Transparent-background compositing for the Broadcast overlay (presentation only).

The overlay draws its own *downscaled copy* of the camera frame; the hand-tracking pipeline is
never affected. A person mask from the segmentation worker becomes the copy's alpha channel:

* small holes inside the person are filled (morphological closing of the confidence with a
  kernel of ``FILL_HOLES`` x the overlay width, 0 = off): light clothing against a dark
  background gets low confidence in patches, which showed the room through the shirt;
* the confidence is mapped through a soft ramp
  (``alpha = clip((confidence - LOW) / (HIGH - LOW), 0, 1)``), so edges fade instead of
  flickering between on and off;
* edges may follow the image (``GUIDED``: a guided filter with the camera image as guide);
* it is smoothed over time with separate weights for appearing (``RISE``) and disappearing
  (``FALL``) parts;
* a mask that is older than ``MAX_MASK_AGE_S`` relative to the frame, or from another camera
  session, is **not** used: the caller must then hide the camera image entirely, so the
  original background is never shown unexpectedly while transparency is on.

The defaults were chosen on a synthetic scenario (``scripts/experiment_mask_refinement.py``,
Brief 007); real image quality needs a visual check with a real person.
"""

from __future__ import annotations

import cv2
import numpy as np

LOW = 0.35
HIGH = 0.75
SMOOTHING = 0.5
"""Weight of the newest mask in the temporal average (version 0.6; see RISE/FALL)."""
RISE = 0.5
"""Weight of the newest mask where the person appears (alpha increases)."""
FALL = 0.5
"""Weight of the newest mask where the person disappears (alpha decreases)."""
FILL_HOLES = 0.0
"""Closing kernel as a share of the overlay width (0 = off)."""
ENCLOSED_FILL = 0.10
"""Fill low-confidence regions enclosed by the person on the left, right and top (a shirt
leaves the picture at the bottom) up to this share of the frame (0 = off)."""
ENCLOSED_WORK_WIDTH = 160
GUIDED = False
"""Refine the alpha edges with a guided filter (camera image as guide)."""
GUIDED_RADIUS = 4
GUIDED_EPS = 1e-3
MAX_MASK_AGE_S = 0.5


def _guided(guide: np.ndarray, src: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Grey-scale guided filter (He et al.) with box filters."""
    g = cv2.cvtColor(guide, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    k = (2 * radius + 1, 2 * radius + 1)
    mean_g = cv2.boxFilter(g, -1, k)
    mean_s = cv2.boxFilter(src, -1, k)
    cov = cv2.boxFilter(g * src, -1, k) - mean_g * mean_s
    var = cv2.boxFilter(g * g, -1, k) - mean_g * mean_g
    a = cov / (var + eps)
    b = mean_s - a * mean_g
    return cv2.boxFilter(a, -1, k) * g + cv2.boxFilter(b, -1, k)


def _fill_enclosed(confidence: np.ndarray, max_share: float) -> np.ndarray:
    """Raise the confidence of background regions that do not touch the left, right or top
    edge (holes in the person, also where the body leaves the picture at the bottom)."""
    h, w = confidence.shape
    work_w = min(w, ENCLOSED_WORK_WIDTH)
    work_h = max(1, round(h * work_w / w))
    small = cv2.resize(confidence, (work_w, work_h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (3, 3), 0)
    background = (small < 0.5).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(background, connectivity=4)
    fill = np.zeros_like(background)
    limit = max_share * work_w * work_h
    for label in range(1, count):
        x, y, bw, _bh, area = stats[label]
        if x == 0 or y == 0 or x + bw >= work_w or area > limit:
            continue  # touches the left, top or right edge, or too large: real background
        fill[labels == label] = 1
    if not fill.any():
        return confidence
    full = cv2.resize(fill, (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    out = confidence.copy()
    out[full] = np.maximum(out[full], 0.8)
    return out


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
        if FILL_HOLES > 0:
            k = max(3, int(FILL_HOLES * width) | 1)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            confidence = cv2.morphologyEx(confidence, cv2.MORPH_CLOSE, kernel)
        if ENCLOSED_FILL > 0:
            confidence = _fill_enclosed(confidence, ENCLOSED_FILL)
        alpha = np.clip((confidence - LOW) / (HIGH - LOW), 0.0, 1.0).astype(np.float32)
        if GUIDED:
            alpha = np.clip(_guided(small, alpha, GUIDED_RADIUS, GUIDED_EPS), 0.0, 1.0)
        previous = self._alpha
        if previous is not None and previous.shape == alpha.shape and mask_ts_ns != self._mask_ts:
            weight = np.where(alpha > previous, RISE, FALL).astype(np.float32)
            alpha = weight * alpha + (1 - weight) * previous
        elif previous is not None and previous.shape == alpha.shape:
            alpha = previous  # same mask as last time: keep the smoothed value
        self._alpha = alpha
        self._mask_ts = mask_ts_ns
        rgba = np.empty((height, width, 4), dtype=np.uint8)
        rgba[..., :3] = small
        rgba[..., 3] = (alpha * 255.0 + 0.5).astype(np.uint8)
        return rgba
