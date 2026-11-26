"""Framework-independent representation of hand tracking results.

Coordinate conventions
----------------------
* **Normalized source coordinates** (canonical): ``x`` and ``y`` in ``[0, 1]`` relative
  to the *unmirrored* camera image, origin top-left, ``x`` to the right, ``y`` down.
  Landmarks may lie slightly outside ``[0, 1]`` when a hand is partially out of frame.
* ``z`` is the model's relative depth with the wrist as origin (smaller is closer to the
  camera), on roughly the same scale as ``x``. It is not a metric distance.
* **Source pixel coordinates**: normalized coordinates multiplied by the source image
  width and height. Used for isotropic distance and motion measurements.
* Mirroring is a display concern; inference always runs on the unmirrored image so
  that handedness refers to the user's real left and right hands.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np

NUM_LANDMARKS = 21


class HandLandmark(enum.IntEnum):
    """Indices of the 21 hand landmarks (identical to MediaPipe's hand model)."""

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


_L = HandLandmark

PALM_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (_L.WRIST, _L.THUMB_CMC),
    (_L.WRIST, _L.INDEX_FINGER_MCP),
    (_L.INDEX_FINGER_MCP, _L.MIDDLE_FINGER_MCP),
    (_L.MIDDLE_FINGER_MCP, _L.RING_FINGER_MCP),
    (_L.RING_FINGER_MCP, _L.PINKY_MCP),
    (_L.WRIST, _L.PINKY_MCP),
)

FINGER_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (_L.THUMB_CMC, _L.THUMB_MCP),
    (_L.THUMB_MCP, _L.THUMB_IP),
    (_L.THUMB_IP, _L.THUMB_TIP),
    (_L.INDEX_FINGER_MCP, _L.INDEX_FINGER_PIP),
    (_L.INDEX_FINGER_PIP, _L.INDEX_FINGER_DIP),
    (_L.INDEX_FINGER_DIP, _L.INDEX_FINGER_TIP),
    (_L.MIDDLE_FINGER_MCP, _L.MIDDLE_FINGER_PIP),
    (_L.MIDDLE_FINGER_PIP, _L.MIDDLE_FINGER_DIP),
    (_L.MIDDLE_FINGER_DIP, _L.MIDDLE_FINGER_TIP),
    (_L.RING_FINGER_MCP, _L.RING_FINGER_PIP),
    (_L.RING_FINGER_PIP, _L.RING_FINGER_DIP),
    (_L.RING_FINGER_DIP, _L.RING_FINGER_TIP),
    (_L.PINKY_MCP, _L.PINKY_PIP),
    (_L.PINKY_PIP, _L.PINKY_DIP),
    (_L.PINKY_DIP, _L.PINKY_TIP),
)

HAND_CONNECTIONS: tuple[tuple[int, int], ...] = tuple(
    (int(a), int(b)) for a, b in PALM_CONNECTIONS + FINGER_CONNECTIONS
)
"""The 21 anatomical bones of the hand skeleton (palm outline plus finger chains)."""

FINGERTIPS: tuple[int, ...] = (
    _L.THUMB_TIP,
    _L.INDEX_FINGER_TIP,
    _L.MIDDLE_FINGER_TIP,
    _L.RING_FINGER_TIP,
    _L.PINKY_TIP,
)

PALM_LANDMARKS: tuple[int, ...] = (
    _L.WRIST,
    _L.INDEX_FINGER_MCP,
    _L.MIDDLE_FINGER_MCP,
    _L.RING_FINGER_MCP,
    _L.PINKY_MCP,
)


class Handedness(enum.Enum):
    """Which of the user's hands was detected."""

    LEFT = "Left"
    RIGHT = "Right"
    UNKNOWN = "Unknown"

    @classmethod
    def from_label(cls, label: str | None) -> Handedness:
        if label is None:
            return cls.UNKNOWN
        normalized = label.strip().lower()
        if normalized == "left":
            return cls.LEFT
        if normalized == "right":
            return cls.RIGHT
        return cls.UNKNOWN

    def swapped(self) -> Handedness:
        """The label a model would report for a horizontally mirrored image."""
        if self is Handedness.LEFT:
            return Handedness.RIGHT
        if self is Handedness.RIGHT:
            return Handedness.LEFT
        return self


@dataclass(frozen=True, slots=True, eq=False)
class HandObservation:
    """One detected hand in one frame.

    ``landmarks`` is a ``(21, 3)`` ``float32`` array of normalized source coordinates
    ``(x, y, z)``. ``handedness_score`` is the model's handedness classification score,
    or ``None`` when the model did not provide one. ``world_landmarks`` holds the model's
    metric 3D estimate (meters, origin at the hand's approximate geometric centre) when
    available.
    """

    landmarks: np.ndarray
    handedness: Handedness = Handedness.UNKNOWN
    handedness_score: float | None = None
    world_landmarks: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.landmarks.shape != (NUM_LANDMARKS, 3):
            raise ValueError(f"landmarks must have shape (21, 3), got {self.landmarks.shape}")
        if self.world_landmarks is not None and self.world_landmarks.shape != (NUM_LANDMARKS, 3):
            raise ValueError("world_landmarks must have shape (21, 3)")

    def pixel_points(self, width: int, height: int) -> np.ndarray:
        """Return a ``(21, 2)`` ``float64`` array of source pixel coordinates."""
        return to_pixels(self.landmarks[:, :2], width, height)

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Normalized ``(x_min, y_min, x_max, y_max)`` enclosing all landmarks."""
        xy = self.landmarks[:, :2]
        x_min, y_min = xy.min(axis=0)
        x_max, y_max = xy.max(axis=0)
        return float(x_min), float(y_min), float(x_max), float(y_max)

    def palm_center(self) -> np.ndarray:
        """Normalized ``(x, y)`` mean of the wrist and the four finger MCP joints."""
        return self.landmarks[list(PALM_LANDMARKS), :2].astype(np.float64).mean(axis=0)


@dataclass(frozen=True, slots=True, eq=False)
class TrackingResult:
    """All hands detected in one frame, with the frame's timing metadata."""

    frame_index: int
    timestamp_ns: int
    image_width: int
    image_height: int
    hands: tuple[HandObservation, ...] = ()
    inference_ms: float | None = None

    @property
    def hand_count(self) -> int:
        return len(self.hands)

    @property
    def landmark_count(self) -> int:
        return NUM_LANDMARKS * len(self.hands)


def to_pixels(points_xy: np.ndarray, width: int, height: int) -> np.ndarray:
    """Convert ``(N, 2)`` normalized coordinates to source pixel coordinates."""
    scale = np.array([width, height], dtype=np.float64)
    return np.asarray(points_xy, dtype=np.float64)[:, :2] * scale


def palm_length_px(landmarks: np.ndarray, width: int, height: int) -> float:
    """Distance in source pixels between the wrist and the middle-finger MCP joint.

    Used as the hand's size reference ("one palm length") for scale-invariant motion.
    """
    wrist = landmarks[HandLandmark.WRIST, :2] * (width, height)
    mcp = landmarks[HandLandmark.MIDDLE_FINGER_MCP, :2] * (width, height)
    return float(np.hypot(*(mcp - wrist)))
