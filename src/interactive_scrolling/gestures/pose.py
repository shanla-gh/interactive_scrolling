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

Half-heart
----------
One half of the familiar two-handed heart, made with one hand held upright: the index finger
curves up and over towards the heart's centre line and its tip hooks downwards, the thumb
points down towards the heart's bottom point, the tips stay apart (the other hand would close
the gap), and the remaining fingers are folded or curved with the index. It is defined by
image-space geometry (relative to the measured palm length, independent of handedness):

* index curved (flexion within ``HEART_INDEX_FLEXION``), not straight as in pointing and not
  tucked into the palm as in a fist (tip at least ``HEART_MIN_INDEX_REACH`` from its knuckle);
* the index tip hooks down: at least ``HEART_MIN_HOOK`` below the highest index joint;
* the thumb is not curled and points downwards (``HEART_MIN_THUMB_DOWN``), its tip at least
  ``HEART_MIN_THUMB_BELOW`` below the index tip;
* the tips are apart (``HEART_GAP``): touching tips are a pinch, not a heart;
* index tip and thumb tip are on the same side of the hand axis (the heart's opening);
* middle, ring and little finger are not extended; the hand is upright.

The exact real-world geometry still needs labeled recordings of the gesture (see
docs/architecture/GESTURES.md); the thresholds are an engineering starting point.
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
# Half-heart geometry (palm lengths unless noted).
HEART_INDEX_FLEXION = (80.0, 230.0)
HEART_MIN_INDEX_REACH = 0.5
HEART_MIN_HOOK = 0.12
HEART_MIN_THUMB_DOWN = math.cos(math.radians(70))
HEART_MIN_THUMB_BELOW = 0.25
HEART_GAP = (0.3, 2.2)
HEART_MIN_UPRIGHT = math.cos(math.radians(65))


class FingerState(enum.Enum):
    EXTENDED = "extended"
    CURLED = "curled"
    UNCERTAIN = "uncertain"


class PoseLabel(enum.Enum):
    OPEN_PALM = "open palm"
    POINTING = "pointing"
    THUMBS_UP = "thumbs up"
    HALF_HEART = "half heart"
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
    heart: HeartGeometry | None = None

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


@dataclass(frozen=True, slots=True)
class HeartGeometry:
    """Image-space measurements used by the half-heart rule (palm lengths unless noted)."""

    index_reach: float
    """Distance from the index knuckle to its tip."""
    hook: float
    """How far the index tip lies below the highest index joint."""
    thumb_down_alignment: float
    """Cosine between the thumb (MCP -> tip) and image-down."""
    thumb_below_index: float
    """How far the thumb tip lies below the index tip."""
    gap: float
    """Distance between the thumb tip and the index tip."""
    same_side: bool
    """Index tip and thumb tip lie on the same side of the hand axis."""

    def matches(self, pose: HandPose) -> bool:
        low, high = HEART_INDEX_FLEXION
        return (
            low <= pose.flexion["index"] <= high
            and pose.states["thumb"] is not FingerState.CURLED
            and not any(pose.states[f] is FingerState.EXTENDED for f in ("middle", "ring", "pinky"))
            and pose.fingers_up_alignment >= HEART_MIN_UPRIGHT
            and self.index_reach >= HEART_MIN_INDEX_REACH
            and self.hook >= HEART_MIN_HOOK
            and self.thumb_down_alignment >= HEART_MIN_THUMB_DOWN
            and self.thumb_below_index >= HEART_MIN_THUMB_BELOW
            and HEART_GAP[0] <= self.gap <= HEART_GAP[1]
            and self.same_side
        )


def _heart_geometry(image: np.ndarray) -> HeartGeometry | None:
    palm = float(np.linalg.norm(image[L.MIDDLE_FINGER_MCP] - image[L.WRIST]))
    if palm < 1e-6:
        return None
    index_tip = image[L.INDEX_FINGER_TIP]
    thumb_tip = image[L.THUMB_TIP]
    top = min(image[L.INDEX_FINGER_PIP, 1], image[L.INDEX_FINGER_DIP, 1])
    thumb = thumb_tip - image[L.THUMB_MCP]
    thumb_norm = float(np.linalg.norm(thumb))
    axis = image[L.MIDDLE_FINGER_MCP] - image[L.WRIST]

    def side(point: np.ndarray) -> float:
        rel = point - image[L.WRIST]
        return float(axis[0] * rel[1] - axis[1] * rel[0])

    return HeartGeometry(
        index_reach=float(np.linalg.norm(index_tip - image[L.INDEX_FINGER_MCP])) / palm,
        hook=float(index_tip[1] - top) / palm,
        thumb_down_alignment=float(thumb[1] / thumb_norm) if thumb_norm > 1e-9 else 0.0,
        thumb_below_index=float(thumb_tip[1] - index_tip[1]) / palm,
        gap=float(np.linalg.norm(thumb_tip - index_tip)) / palm,
        same_side=side(index_tip) * side(thumb_tip) > 0,
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
        heart=_heart_geometry(image),
    )
    return HandPose(
        flexion=flexion,
        states=states,
        thumb_up_alignment=thumb_up,
        fingers_up_alignment=fingers_up,
        thumb_tip_highest=thumb_tip_highest,
        label=_label(pose),
        heart=pose.heart,
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
    if pose.heart is not None and pose.heart.matches(pose):
        return PoseLabel.HALF_HEART
    if pose.curled(*four):
        return PoseLabel.FIST
    return PoseLabel.OTHER
