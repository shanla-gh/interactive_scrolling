"""Static hand pose analysis from the 21 landmarks.

Finger extension is measured from joint angles of the 3D landmarks, using the normalized
landmarks with x/y scaled to pixels and z scaled like x (MediaPipe's relative depth has roughly
the scale of x). On labeled recordings of real hands these angles separated extended and curled
fingers much better than MediaPipe's metric world landmarks, whose depth estimates made
visibly straight fingers measure 55-100 degrees (see docs/architecture/GESTURES.md).

For each finger the *flexion* is the sum of the bend angles at its three joints (degrees):
about 0-40 for a straight finger and 180-300 for a finger folded into a fist.

Image-space directions (``thumb_up_alignment``, ``fingers_up_alignment``) use the unmirrored
frame with y pointing down; an alignment of 1.0 means pointing straight up.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

import numpy as np

from interactive_scrolling.vision.landmarks import HandLandmark as L
from interactive_scrolling.vision.landmarks import HandObservation

FINGER_CHAINS: dict[str, tuple[int, int, int, int]] = {
    "index": (L.INDEX_FINGER_MCP, L.INDEX_FINGER_PIP, L.INDEX_FINGER_DIP, L.INDEX_FINGER_TIP),
    "middle": (L.MIDDLE_FINGER_MCP, L.MIDDLE_FINGER_PIP, L.MIDDLE_FINGER_DIP, L.MIDDLE_FINGER_TIP),
    "ring": (L.RING_FINGER_MCP, L.RING_FINGER_PIP, L.RING_FINGER_DIP, L.RING_FINGER_TIP),
    "pinky": (L.PINKY_MCP, L.PINKY_PIP, L.PINKY_DIP, L.PINKY_TIP),
}
FINGERS = ("thumb", "index", "middle", "ring", "pinky")

# Flexion thresholds (degrees, sum over three joints), from a labeled recording of real hands:
# extended fingers measured 20-45, curled fingers 165-340, transitions 90-135 (uncertain).
FINGER_EXTENDED_MAX = 70.0
FINGER_CURLED_MIN = 140.0
THUMB_EXTENDED_MAX = 45.0
THUMB_CURLED_MIN = 80.0
# Pose direction requirements (cosine of the allowed angle from straight up).
THUMB_UP_MIN_ALIGNMENT = math.cos(math.radians(40))
FINGERS_UP_MIN_ALIGNMENT = math.cos(math.radians(40))


class FingerState(enum.Enum):
    EXTENDED = "extended"
    CURLED = "curled"
    UNCERTAIN = "uncertain"


class PoseLabel(enum.Enum):
    OPEN_PALM = "open palm"
    POINTING = "pointing"
    THUMBS_UP = "thumbs up"
    FIST = "fist"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class HandPose:
    flexion: dict[str, float]
    """Summed joint flexion per finger, degrees."""
    states: dict[str, FingerState]
    thumb_up_alignment: float
    """Cosine between the thumb (MCP -> tip) and image-up."""
    fingers_up_alignment: float
    """Cosine between the hand axis (wrist -> middle MCP) and image-up."""
    thumb_tip_highest: bool
    """The thumb tip is above every other landmark in the image."""
    label: PoseLabel

    def extended(self, *fingers: str) -> bool:
        return all(self.states[f] is FingerState.EXTENDED for f in fingers)

    def curled(self, *fingers: str) -> bool:
        return all(self.states[f] is FingerState.CURLED for f in fingers)

    @property
    def is_stop_pose(self) -> bool:
        """Open palm with the fingers pointing up."""
        return (
            self.label is PoseLabel.OPEN_PALM
            and self.fingers_up_alignment >= FINGERS_UP_MIN_ALIGNMENT
        )


def _bend(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Bend angle at ``b`` in degrees: 0 when a, b, c are collinear (straight)."""
    u = b - a
    v = c - b
    nu = np.linalg.norm(u)
    nv = np.linalg.norm(v)
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    cos = float(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))
    return math.degrees(math.acos(cos))


def _points_3d(obs: HandObservation, width: int, height: int) -> np.ndarray:
    scale = np.array([width, height, width], dtype=np.float64)
    return obs.landmarks.astype(np.float64) * scale


def _up_alignment(start: np.ndarray, end: np.ndarray) -> float:
    vector = end - start
    norm = float(np.linalg.norm(vector))
    if norm < 1e-9:
        return 0.0
    return float(-vector[1] / norm)  # image y points down


def _classify_finger(flexion: float, extended_max: float, curled_min: float) -> FingerState:
    if flexion <= extended_max:
        return FingerState.EXTENDED
    if flexion >= curled_min:
        return FingerState.CURLED
    return FingerState.UNCERTAIN


def analyze_pose(obs: HandObservation, width: int, height: int) -> HandPose:
    pts = _points_3d(obs, width, height)
    wrist = pts[L.WRIST]
    flexion: dict[str, float] = {}
    for name, (mcp, pip, dip, tip) in FINGER_CHAINS.items():
        flexion[name] = (
            _bend(wrist, pts[mcp], pts[pip])
            + _bend(pts[mcp], pts[pip], pts[dip])
            + _bend(pts[pip], pts[dip], pts[tip])
        )
    flexion["thumb"] = _bend(pts[L.THUMB_CMC], pts[L.THUMB_MCP], pts[L.THUMB_IP]) + _bend(
        pts[L.THUMB_MCP], pts[L.THUMB_IP], pts[L.THUMB_TIP]
    )
    states = {
        name: _classify_finger(flexion[name], FINGER_EXTENDED_MAX, FINGER_CURLED_MIN)
        for name in FINGER_CHAINS
    }
    states["thumb"] = _classify_finger(flexion["thumb"], THUMB_EXTENDED_MAX, THUMB_CURLED_MIN)

    image = obs.landmarks[:, :2].astype(np.float64) * (width, height)
    thumb_up = _up_alignment(image[L.THUMB_MCP], image[L.THUMB_TIP])
    fingers_up = _up_alignment(image[L.WRIST], image[L.MIDDLE_FINGER_MCP])
    others = np.delete(image[:, 1], L.THUMB_TIP)
    thumb_tip_highest = bool(image[L.THUMB_TIP, 1] < others.min())

    pose = HandPose(
        flexion=flexion,
        states=states,
        thumb_up_alignment=thumb_up,
        fingers_up_alignment=fingers_up,
        thumb_tip_highest=thumb_tip_highest,
        label=PoseLabel.OTHER,
    )
    return HandPose(
        flexion=flexion,
        states=states,
        thumb_up_alignment=thumb_up,
        fingers_up_alignment=fingers_up,
        thumb_tip_highest=thumb_tip_highest,
        label=_label(pose),
    )


def _label(pose: HandPose) -> PoseLabel:
    four = ("index", "middle", "ring", "pinky")
    if pose.extended(*four):
        return PoseLabel.OPEN_PALM
    if pose.extended("index") and pose.curled("middle", "ring", "pinky"):
        return PoseLabel.POINTING
    if (
        pose.curled(*four)
        and pose.extended("thumb")
        and pose.thumb_up_alignment >= THUMB_UP_MIN_ALIGNMENT
        and pose.thumb_tip_highest
    ):
        return PoseLabel.THUMBS_UP
    if pose.curled(*four):
        return PoseLabel.FIST
    return PoseLabel.OTHER
