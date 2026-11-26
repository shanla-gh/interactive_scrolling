"""Synthetic hands with articulated fingers and scripted motion for gesture tests.

The hand is built in 3D (pixel units, x right, y down, z away from the camera) from finger
flexion angles, rotated in the image plane, and projected orthographically to normalized
landmarks (z scaled like x), which is how MediaPipe reports them. Motion patterns in the tests
mirror the behaviour observed in labeled recordings of real gestures (see
docs/architecture/GESTURES.md): strokes with fast returns, curled wind-ups before sweeps,
hands raised into view while already pointing, poses held between movements.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureEvent, GestureFrame
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.vision.landmarks import Handedness, HandObservation, TrackingResult

W, H = 1280, 720
FPS = 30.0

# Palm geometry in palm-length units (wrist at origin, fingers pointing up = -y).
_MCP = {
    "index": (-0.30, -1.0),
    "middle": (0.0, -1.0),
    "ring": (0.28, -0.95),
    "pinky": (0.52, -0.85),
}
_SEGMENTS = {
    "index": (0.40, 0.25, 0.22),
    "middle": (0.45, 0.27, 0.25),
    "ring": (0.40, 0.25, 0.22),
    "pinky": (0.30, 0.20, 0.18),
}
_THUMB_CMC = (-0.35, -0.20)
_THUMB_SEGMENTS = (0.32, 0.27, 0.25)
_ORDER = ("index", "middle", "ring", "pinky")

EXTENDED = (5.0, 5.0, 5.0)
CURLED = (80.0, 100.0, 60.0)


@dataclass(frozen=True)
class Pose:
    fingers: dict[str, tuple[float, float, float]]
    thumb_dir: tuple[float, float, float]
    thumb_bend: tuple[float, float]
    roll_deg: float = 0.0
    index_in_plane: bool = False
    """Curl the index finger sideways in the image plane (towards +x before roll and mirroring)
    instead of towards the camera, as in the half-heart."""


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


OPEN = Pose({f: EXTENDED for f in _ORDER}, (-0.6, -0.8, 0.0), (5.0, 5.0))
POINTING = Pose(
    {"index": EXTENDED, "middle": CURLED, "ring": CURLED, "pinky": CURLED},
    (0.6, -0.5, -0.6),
    (45.0, 50.0),
)
FIST = Pose({f: CURLED for f in _ORDER}, (0.6, -0.5, -0.6), (45.0, 50.0))
# Thumb extended sideways, then the whole hand is rolled so the thumb points up.
THUMBS_UP = Pose({f: CURLED for f in _ORDER}, (-1.0, 0.0, 0.0), (5.0, 5.0), roll_deg=90.0)
THUMBS_DOWN = Pose({f: CURLED for f in _ORDER}, (-1.0, 0.0, 0.0), (5.0, 5.0), roll_deg=-90.0)
# One half of a two-handed heart: hand upright, index curving over sideways with its tip hooking
# down, thumb pointing down towards the heart's bottom point, the other fingers folded.
HALF_HEART = Pose(
    {"index": (40.0, 70.0, 50.0), "middle": CURLED, "ring": CURLED, "pinky": CURLED},
    (0.55, 0.83, 0.0),
    (5.0, 5.0),
    index_in_plane=True,
)
# The same hand with the fingertips touching (a pinch) and a horizontal "C" (hand on its side).
PINCH = Pose(
    {"index": (40.0, 70.0, 50.0), "middle": CURLED, "ring": CURLED, "pinky": CURLED},
    (0.2, -0.98, 0.0),
    (5.0, 5.0),
    index_in_plane=True,
)
C_SIDEWAYS = Pose(HALF_HEART.fingers, HALF_HEART.thumb_dir, HALF_HEART.thumb_bend, 90.0, True)


def _chain(
    base: np.ndarray, direction: np.ndarray, lengths, bends, toward: np.ndarray | None = None
) -> list[np.ndarray]:
    """Joint positions along a finger; bends curl the finger towards ``toward`` (default: the
    camera, -z)."""
    toward = np.array([0.0, 0.0, -1.0]) if toward is None else toward
    points = []
    angle = 0.0
    position = base
    for length, bend in zip(lengths, bends, strict=True):
        angle += math.radians(bend)
        step = math.cos(angle) * direction + math.sin(angle) * toward
        position = position + length * _unit(step)
        points.append(position)
    return points


def hand_landmarks(pose: Pose, scale: float = 1.0) -> np.ndarray:
    """21 landmarks in palm-length units, wrist at the origin, before placement."""
    pts = np.zeros((21, 3))
    cmc = np.array([*_THUMB_CMC, 0.0])
    pts[1] = cmc
    thumb_dir = _unit(np.array(pose.thumb_dir))
    thumb = _chain(cmc, thumb_dir, _THUMB_SEGMENTS, (0.0, *pose.thumb_bend))
    pts[2:5] = thumb
    for i, name in enumerate(_ORDER):
        mcp = np.array([*_MCP[name], 0.0])
        base = 5 + 4 * i
        pts[base] = mcp
        direction = _unit(mcp)
        toward = None
        if name == "index" and pose.index_in_plane:
            toward = np.array([-direction[1], direction[0], 0.0])
        pts[base + 1 : base + 4] = _chain(
            mcp, direction, _SEGMENTS[name], pose.fingers[name], toward
        )
    roll = math.radians(pose.roll_deg)
    rot = np.array(
        [[math.cos(roll), -math.sin(roll), 0], [math.sin(roll), math.cos(roll), 0], [0, 0, 1]]
    )
    return pts @ rot.T * scale


def make_observation(
    pose: Pose,
    wrist_px: tuple[float, float],
    palm_px: float = 100.0,
    handedness: Handedness = Handedness.RIGHT,
    score: float | None = 0.95,
    mirror: bool = False,
) -> HandObservation:
    pts = hand_landmarks(pose, palm_px)
    if mirror:  # a left hand is the mirror image of a right hand
        pts[:, 0] = -pts[:, 0]
    pts[:, 0] += wrist_px[0]
    pts[:, 1] += wrist_px[1]
    landmarks = np.empty((21, 3), dtype=np.float32)
    landmarks[:, 0] = pts[:, 0] / W
    landmarks[:, 1] = pts[:, 1] / H
    landmarks[:, 2] = pts[:, 2] / W
    return HandObservation(landmarks=landmarks, handedness=handedness, handedness_score=score)


@dataclass
class Hand:
    """A scripted hand: position, pose and identity as functions of time (seconds)."""

    position: Callable[[float], tuple[float, float] | None]
    pose: Callable[[float], Pose] = lambda t: POINTING
    handedness: Handedness = Handedness.RIGHT
    label: Callable[[float], Handedness] | None = None
    """Optional per-frame handedness label (to simulate MediaPipe label flips)."""
    score: float | None = 0.95
    palm_px: float = 100.0


def still(x: float, y: float) -> Callable[[float], tuple[float, float]]:
    return lambda t: (x, y)


def stroke(
    start: tuple[float, float],
    end: tuple[float, float],
    t_start: float,
    duration: float,
    then: Callable[[float], tuple[float, float] | None] | None = None,
) -> Callable[[float], tuple[float, float] | None]:
    """Hold ``start`` until ``t_start``, move to ``end`` with a smooth (cosine) velocity profile
    over ``duration``, then follow ``then`` (or hold ``end``)."""

    def position(t: float) -> tuple[float, float] | None:
        if t < t_start:
            return start
        if t <= t_start + duration:
            u = (t - t_start) / duration
            s = (1 - math.cos(math.pi * u)) / 2
            return (start[0] + (end[0] - start[0]) * s, start[1] + (end[1] - start[1]) * s)
        return then(t) if then is not None else end

    return position


def chain(*segments: tuple[float, Callable[[float], tuple[float, float] | None]]):
    """Piecewise path: list of (t_begin, path) in increasing t_begin order."""

    def position(t: float) -> tuple[float, float] | None:
        current = segments[0][1]
        for begin, path in segments:
            if t >= begin:
                current = path
        return current(t)

    return position


def run(
    hands: Iterable[Hand],
    seconds: float,
    settings: GestureSettings | None = None,
    fps: float = FPS,
    engine: GestureEngine | None = None,
) -> tuple[list[GestureEvent], list[GestureFrame]]:
    """Feed the scripted hands through the motion analyzer and gesture engine."""
    hands = list(hands)
    analyzer = MotionAnalyzer()
    engine = engine or GestureEngine(settings or GestureSettings())
    events: list[GestureEvent] = []
    frames: list[GestureFrame] = []
    n = int(seconds * fps)
    for i in range(n):
        t = i / fps
        observations = []
        for hand in hands:
            position = hand.position(t)
            if position is None:
                continue
            observations.append(
                make_observation(
                    hand.pose(t),
                    position,
                    hand.palm_px,
                    hand.label(t) if hand.label is not None else hand.handedness,
                    hand.score,
                    mirror=hand.handedness is Handedness.LEFT,
                )
            )
        tracking = TrackingResult(i, int(1_000_000_000 + t * 1e9), W, H, tuple(observations))
        frame = engine.update(tracking, analyzer.update(tracking))
        frames.append(frame)
        events.extend(frame.events)
    return events, frames


def kinds(events: Iterable[GestureEvent]) -> list[str]:
    return [e.gesture.name for e in events]


def rejections(frames: Iterable[GestureFrame]) -> list[str]:
    return [f.rejection.reason for f in frames if f.rejection is not None]
