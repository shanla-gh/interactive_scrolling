"""Passive gaze *estimate* from webcam face landmarks (Brief 009, visualization only).

Inputs are the face landmarker's eye contours, iris centres, blink blendshapes and head
angles. Measured: landmark positions (image coordinates). Estimated: head roll (from the eye
corners), per-eye iris offset, and a combined gaze direction = head orientation + an eyeball
rotation derived from the iris offset with a fixed eyeball-to-eye-width ratio. A webcam gives
no depth of the eye and no per-person eye model, so the direction is an approximation in
degrees, not a measured 3-D gaze ray; ``quality`` says how much to trust it and the overlay
hides it below ``MIN_QUALITY``.

Nothing here can trigger an action: the result is only drawn (and the existing analytics use
their own classification in ``eyes.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from interactive_scrolling.vision.face_tracker import FaceObservation

R_OUTER, R_INNER, R_IRIS, R_UPPER, R_LOWER = 33, 133, 468, 159, 145
L_OUTER, L_INNER, L_IRIS, L_UPPER, L_LOWER = 263, 362, 473, 386, 374
RIGHT_EYE = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)
LEFT_EYE = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466)
EYEBALL_RADIUS_EYE_WIDTHS = 0.42
"""Approximate eyeball radius in units of the visible eye width (anatomical average)."""
MIN_QUALITY = 0.35
HEAD_YAW_FULL = 30.0
HEAD_YAW_ZERO = 50.0
MIN_EYE_WIDTH = 0.018
"""Eye width (normalized image width) below which the iris offset is too coarse."""


@dataclass(frozen=True, slots=True)
class EyeEstimate:
    center: tuple[float, float]
    """Eye centre, normalized image coordinates (unmirrored)."""
    iris: tuple[float, float]
    offset_h: float
    """Iris offset from the eye centre along the eye axis, in eye widths; positive towards
    the person's left."""
    offset_v: float
    """Iris offset from the eyelid midpoint, in eye widths; positive downwards."""
    openness: float
    """1 - blink blendshape (0 closed, 1 open)."""


@dataclass(frozen=True, slots=True)
class GazeEstimate:
    right: EyeEstimate
    left: EyeEstimate
    head_yaw_deg: float
    head_pitch_deg: float
    head_roll_deg: float
    """Tilt of the eye-corner line (positive: the person's left eye lower in the image)."""
    gaze_yaw_deg: float
    """Estimated direction, positive towards the person's left."""
    gaze_pitch_deg: float
    """Estimated direction, positive upwards."""
    quality: float
    """0-1: eye openness, head turn and eye size combined."""

    @property
    def usable(self) -> bool:
        return self.quality >= MIN_QUALITY

    def eye_angles(self, eye: EyeEstimate) -> tuple[float, float]:
        """(yaw, pitch) estimate for one eye: head orientation plus its iris offset."""
        return (
            self.head_yaw_deg + _rotation(eye.offset_h),
            self.head_pitch_deg + _rotation(-eye.offset_v),
        )


def _rotation(offset_eye_widths: float) -> float:
    ratio = max(-1.0, min(1.0, offset_eye_widths / EYEBALL_RADIUS_EYE_WIDTHS))
    return math.degrees(math.asin(ratio))


def _eye(
    lm: np.ndarray,
    outer: int,
    inner: int,
    iris: int,
    upper: int,
    lower: int,
    sign: float,
    openness: float,
) -> tuple[EyeEstimate, float]:
    a, b = lm[outer, :2].astype(float), lm[inner, :2].astype(float)
    axis = b - a
    width = float(np.linalg.norm(axis))
    if width < 1e-6:
        raise ValueError("degenerate eye")
    unit = axis / width
    center = (a + b) / 2
    iris_pt = lm[iris, :2].astype(float)
    along = float(np.dot(iris_pt - center, unit)) / width
    lid_mid = (lm[upper, :2].astype(float) + lm[lower, :2].astype(float)) / 2
    normal = np.array([-unit[1], unit[0]])
    if normal[1] < 0:
        normal = -normal  # pointing down in the image
    across = float(np.dot(iris_pt - lid_mid, normal)) / width
    estimate = EyeEstimate(
        center=(float(center[0]), float(center[1])),
        iris=(float(iris_pt[0]), float(iris_pt[1])),
        offset_h=sign * along,
        offset_v=across,
        openness=openness,
    )
    return estimate, width


def estimate_gaze(face: FaceObservation | None) -> GazeEstimate | None:
    """The gaze estimate for one face, or ``None`` without landmarks or head angles."""
    if face is None or face.yaw_deg is None or face.pitch_deg is None:
        return None
    lm = face.landmarks
    if lm.shape[0] <= L_IRIS:
        return None
    shapes = face.blendshapes
    open_r = 1.0 - float(shapes.get("eyeBlinkRight", 0.0))
    open_l = 1.0 - float(shapes.get("eyeBlinkLeft", 0.0))
    try:
        # Right eye: outer corner on the image left, so "along" grows towards the person's left.
        right, w_r = _eye(lm, R_OUTER, R_INNER, R_IRIS, R_UPPER, R_LOWER, 1.0, open_r)
        left, w_l = _eye(lm, L_OUTER, L_INNER, L_IRIS, L_UPPER, L_LOWER, -1.0, open_l)
    except ValueError:
        return None
    corners = lm[L_OUTER, :2].astype(float) - lm[R_OUTER, :2].astype(float)
    roll = math.degrees(math.atan2(float(corners[1]), float(corners[0])))
    offset_h = (right.offset_h + left.offset_h) / 2
    offset_v = (right.offset_v + left.offset_v) / 2
    yaw = float(face.yaw_deg) + _rotation(offset_h)
    pitch = float(face.pitch_deg) + _rotation(-offset_v)
    turn = abs(float(face.yaw_deg))
    turn_q = 1.0 if turn <= HEAD_YAW_FULL else max(0.0, (HEAD_YAW_ZERO - turn) / 20.0)
    size_q = min(1.0, min(w_r, w_l) / MIN_EYE_WIDTH)
    open_q = max(0.0, min(1.0, (min(open_r, open_l) - 0.3) / 0.4))
    return GazeEstimate(
        right=right,
        left=left,
        head_yaw_deg=float(face.yaw_deg),
        head_pitch_deg=float(face.pitch_deg),
        head_roll_deg=roll,
        gaze_yaw_deg=yaw,
        gaze_pitch_deg=pitch,
        quality=round(turn_q * size_q * open_q, 3),
    )
