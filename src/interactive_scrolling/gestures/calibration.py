"""Quick Calibration: measure a few demonstrations, check them, derive a personal profile.

Why the thresholds are personal (Brief 004 benchmark): the swipe distance that works is set by
the size of the user's *own* movements. A finger flick is preceded by a small wind-up in the
opposite direction (curling before flicking up); a distance below the wind-up turns the
wind-up into the opposite swipe and suppresses the real one as its "return" (0.5-0.6 palm
lengths: upward flicks 0/4 on the recordings), a distance above the flick misses it (1.0: 0/4).

Measurement
    Demonstrations are measured with a simple stroke segmenter on the smoothed fingertip
    (not with the recognizer, whose return handling would hide exactly the movements that
    matter here). A stroke runs from rest (speed below ``REST_SPEED``) through a movement
    faster than ``MOVE_SPEED`` until the fingertip stops or reverses. Strokes in the prompted
    direction are demonstrations; opposite strokes ending shortly before a demonstration are
    *wind-ups*; opposite strokes starting shortly after one are *returns* (ignored).
    Static poses are measured over still periods (net drift below the recognizer's limit).

Derivation (per axis, bounded)
    distance = the smaller of the current distance and 0.7 x the median demonstration length,
    raised above the largest wind-up (x 1.15) and kept below the smallest demonstration
    (x 0.9), within [``MIN_DISTANCE``, ``MAX_DISTANCE``]. It is raised above the current value
    only when the user's own wind-ups require it (calibrating on large swipes and later making
    small ones would otherwise fail: measured 0/8). Movements far larger than the typical
    demonstration (raising the hand into position) are not counted. If wind-ups and
    demonstrations overlap, the smallest demonstration wins and the user is told to make the
    swipe a little larger than the movement before it. A raise is limited to 15 %. Speed =
    0.5 x the slowest demonstration's peak, at least 1.2 and never above the current value; the
    maximum duration may only grow (up to 1.0 s). Every opposite stroke between two
    demonstrations is a return (however long the pause); only one right before the first
    demonstration can be a wind-up (version 0.4 also counted slow returns as wind-ups and
    raised the Director's distance to 1.34).
    The half-heart template is the median of the shape measurements of the held
    demonstrations (``pose.matches_personal_heart``); the stop pose's tilt tolerance may only
    grow (up to 70 degrees).

Only derived numbers are kept; no landmarks or images.
"""

from __future__ import annotations

import math
import statistics
import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime

from interactive_scrolling.config.settings import (
    CalibrationProfile,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.gestures.engine import MIN_HAND_SCALE_FRACTION
from interactive_scrolling.gestures.pose import (
    FINGER_EXTENDED_MAX,
    FingerState,
    PoseLabel,
    analyze_pose,
    heart_features,
)
from interactive_scrolling.gestures.recognizers import (
    STATIC_MAX_DRIFT_PALMS,
    STATIC_WINDOW_S,
    SWIPE_DIRECTIONS,
    swipe_distance,
    to_user,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.vision.landmarks import TrackingResult

G = GestureType
DEMOS_PER_GESTURE = 3
REST_SPEED = 0.4
MOVE_SPEED = 0.8
MIN_STROKE_PALMS = 0.3
WINDUP_GAP_S = 0.45
RETURN_GAP_S = 0.6
MIN_DISTANCE = 0.5
MAX_DISTANCE = 1.4
MIN_HOLD_S = 0.4
OUTLIER_FACTOR = 2.5
CALIBRATION_METHOD = 2
MAX_RAISE = 1.15
FIST_MIN_DISTANCE = 0.3
FIST_MAX_DISTANCE = 0.8
"""Calibration may raise a distance by at most 15 % (only when wind-ups require it)."""
WINDUP_OUTLIER_FACTOR = 1.5
AXES = {
    "vertical": (G.INDEX_SWIPE_UP, G.INDEX_SWIPE_DOWN),
    "horizontal": (G.INDEX_SWIPE_LEFT, G.INDEX_SWIPE_RIGHT),
}
SWIPES = frozenset(SWIPE_DIRECTIONS)


@dataclass(frozen=True)
class Stroke:
    direction: GestureType
    length_palms: float
    peak_palms_s: float
    duration_s: float
    start_ns: int
    end_ns: int
    pointing_before: bool
    pointing_after: bool
    diagonal: bool


@dataclass(frozen=True)
class HeldPose:
    duration_s: float
    features: dict[str, float] | None
    upright_deg: float
    four_extended: bool
    label: str


@dataclass
class PromptResult:
    """Measurements of one prompt (e.g. "move your finger up, 3 times")."""

    gesture: GestureType
    detector: str = "finger"
    """``finger`` (index fingertip) or ``fist`` (palm centre of a closed hand)."""
    demos: list[Stroke] = field(default_factory=list)
    windups: list[Stroke] = field(default_factory=list)
    returns: list[Stroke] = field(default_factory=list)
    holds: list[HeldPose] = field(default_factory=list)
    other: list[Stroke] = field(default_factory=list)
    frames: int = 0
    tracked: int = 0
    scales: list[float] = field(default_factory=list)
    image_width: int = 0

    @property
    def valid_demos(self) -> int:
        if self.gesture in SWIPES:
            return len(self.demos)
        return sum(1 for hold in self.holds if self._hold_ok(hold))

    def _hold_ok(self, hold: HeldPose) -> bool:
        if self.gesture is G.HALF_HEART:
            return heart_essentials(hold.features)
        return hold.four_extended

    def feedback(self) -> list[str]:
        """Measured problems in plain language, most important first (empty = fine)."""
        out: list[str] = []
        if self.frames and self.tracked / self.frames < 0.5:
            out.append("Your hand was not visible most of the time: keep it in the picture.")
        if (
            self.scales
            and self.image_width
            and statistics.median(self.scales) < MIN_HAND_SCALE_FRACTION * self.image_width
        ):
            out.append("Your hand is far from the camera: move it a little closer.")
        if self.gesture in SWIPES:
            if not self.demos:
                opposite = [s for s in self.other if s.direction is _opposite(self.gesture)]
                short = [s for s in self.other if s.direction is self.gesture]
                diagonal = [s for s in self.other if s.diagonal]
                if short:
                    out.append("Movement too short: move a little further.")
                elif diagonal:
                    out.append("The movement was diagonal: move straight.")
                elif opposite:
                    out.append(
                        f"That went {_word(opposite[0].direction)} - "
                        f"please move {_word(self.gesture)}."
                    )
                else:
                    out.append("No movement detected.")
            elif any(not (s.pointing_before or s.pointing_after) for s in self.demos):
                out.append(
                    "Close your hand into a fist, hold it still briefly, then move it."
                    if self.detector == "fist"
                    else "Point with your index finger while you move."
                )
        else:
            if not self.holds:
                out.append("Hold the pose still for a moment.")
            elif not self.valid_demos:
                out.append(
                    "Hold the heart shape: thumb pointing down below the curved index finger, "
                    "with a gap between them."
                    if self.gesture is G.HALF_HEART
                    else "Open your hand fully, fingers up, palm to the camera."
                )
        return out


def _opposite(gesture: GestureType) -> GestureType:
    return {
        G.INDEX_SWIPE_UP: G.INDEX_SWIPE_DOWN,
        G.INDEX_SWIPE_DOWN: G.INDEX_SWIPE_UP,
        G.INDEX_SWIPE_LEFT: G.INDEX_SWIPE_RIGHT,
        G.INDEX_SWIPE_RIGHT: G.INDEX_SWIPE_LEFT,
    }[gesture]


def _word(gesture: GestureType) -> str:
    return {
        G.INDEX_SWIPE_UP: "up",
        G.INDEX_SWIPE_DOWN: "down",
        G.INDEX_SWIPE_LEFT: "to your left",
        G.INDEX_SWIPE_RIGHT: "to your right",
    }[gesture]


def heart_essentials(features: dict[str, float] | None) -> bool:
    """The parts of a half-heart that a personal template may not relax."""
    return (
        features is not None
        and features["index_flexion"] >= FINGER_EXTENDED_MAX
        and features["gap"] >= 0.25
        and features["thumb_below"] >= 0.1
        and features["thumb_down"] > 0.0
    )


class _Segmenter:
    """Fingertip stroke segmentation for one prompt (see the module documentation)."""

    def __init__(self) -> None:
        self.strokes: list[Stroke] = []
        self._rest: tuple[tuple[float, float], int, float] | None = None
        self._move: dict | None = None
        self._pointing: deque[tuple[int, bool]] = deque(maxlen=12)

    def add(self, ts: int, tip, v_px, scale: float, pointing: bool) -> None:  # type: ignore[no-untyped-def]
        self._pointing.append((ts, pointing))
        vx, vy = to_user((v_px[0] / scale, v_px[1] / scale))
        speed = math.hypot(vx, vy)
        if self._move is None:
            if speed < REST_SPEED or self._rest is None:
                self._rest = (tip, ts, scale)
            if speed >= MOVE_SPEED:
                origin, start, rest_scale = self._rest
                self._move = {
                    "origin": origin,
                    "start": start,
                    "scale": rest_scale,
                    "peak": speed,
                    "far": 0.0,
                    "far_tip": tip,
                    "pointing_before": sum(p for _, p in self._pointing) >= 3,
                }
            return
        m = self._move
        m["peak"] = max(m["peak"], speed)
        d = to_user(
            ((tip[0] - m["origin"][0]) / m["scale"], (tip[1] - m["origin"][1]) / m["scale"])
        )
        far = math.hypot(*d)
        if far >= m["far"]:
            m["far"], m["far_tip"], m["vector"] = far, tip, d
        back = math.hypot(
            (tip[0] - m["far_tip"][0]) / m["scale"], (tip[1] - m["far_tip"][1]) / m["scale"]
        )
        if speed < REST_SPEED or back > 0.25:
            self._finish(ts, pointing)
            self._rest = (tip, ts, scale)

    def _finish(self, ts: int, pointing: bool) -> None:
        m, self._move = self._move, None
        if m is None or m["far"] < 0.15 or "vector" not in m:
            return
        x, y = m["vector"]
        if abs(y) >= abs(x):
            direction = G.INDEX_SWIPE_DOWN if y > 0 else G.INDEX_SWIPE_UP
            along, across = abs(y), abs(x)
        else:
            direction = G.INDEX_SWIPE_RIGHT if x > 0 else G.INDEX_SWIPE_LEFT
            along, across = abs(x), abs(y)
        self.strokes.append(
            Stroke(
                direction=direction,
                length_palms=round(along, 3),
                peak_palms_s=round(m["peak"], 3),
                duration_s=round((ts - m["start"]) / NS_PER_S, 3),
                start_ns=m["start"],
                end_ns=ts,
                pointing_before=m["pointing_before"],
                pointing_after=pointing,
                diagonal=across * 1.8 > along,
            )
        )


class _Holds:
    def __init__(self) -> None:
        self.holds: list[HeldPose] = []
        self._run: list = []
        self._window: deque = deque()

    def add(self, ts: int, palm, scale: float, pose) -> None:  # type: ignore[no-untyped-def]
        self._window.append((ts, palm))
        while self._window and self._window[0][0] < ts - int(STATIC_WINDOW_S * NS_PER_S):
            self._window.popleft()
        xs = [p[0] for _, p in self._window]
        ys = [p[1] for _, p in self._window]
        drift = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / scale
        if drift <= STATIC_MAX_DRIFT_PALMS:
            self._run.append((ts, pose))
        else:
            self.close()

    def snapshot(self) -> list[HeldPose]:
        """The finished holds plus the current one if it is already long enough."""
        current = self._summarize(self._run)
        return self.holds + ([current] if current is not None else [])

    def close(self) -> None:
        run, self._run = self._run, []
        held = self._summarize(run)
        if held is not None:
            self.holds.append(held)

    @staticmethod
    def _summarize(run: list) -> HeldPose | None:  # type: ignore[type-arg]
        if len(run) < 2:
            return None
        duration = (run[-1][0] - run[0][0]) / NS_PER_S
        if duration < MIN_HOLD_S:
            return None
        poses = [pose for _, pose in run]
        features = [heart_features(p) for p in poses]
        features = [f for f in features if f is not None]
        median = (
            {k: statistics.median(f[k] for f in features) for k in features[0]}
            if features
            else None
        )
        upright = statistics.median(
            math.degrees(math.acos(max(-1.0, min(1.0, p.fingers_up_alignment)))) for p in poses
        )
        extended = sum(
            all(p.states[f] is FingerState.EXTENDED for f in ("index", "middle", "ring", "pinky"))
            for p in poses
        )
        labels = [p.label.value for p in poses]
        return HeldPose(
            duration_s=round(duration, 2),
            features=median,
            upright_deg=round(upright, 1),
            four_extended=extended >= len(poses) / 2,
            label=max(set(labels), key=labels.count),
        )


class CalibrationCollector:
    """Feeds prompts' frames to the measurement (processing thread: ``observe``; UI thread:
    ``begin``/``end``/``progress``)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._analyzer = MotionAnalyzer()
        self._gesture: GestureType | None = None
        self._result: PromptResult | None = None
        self._segmenter = _Segmenter()
        self._holds = _Holds()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._gesture is not None

    def begin(self, gesture: GestureType, detector: str = "finger") -> None:
        with self._lock:
            self._gesture = gesture
            self._result = PromptResult(gesture, detector)
            self._segmenter = _Segmenter()
            self._holds = _Holds()

    def end(self) -> PromptResult | None:
        with self._lock:
            result, self._result, self._gesture = self._result, None, None
            if result is None:
                return None
            self._holds.close()
            _classify(result, self._segmenter.strokes, self._holds.holds)
            return result

    def progress(self) -> PromptResult | None:
        """A classified copy of the measurements so far (for live feedback)."""
        with self._lock:
            if self._result is None:
                return None
            copy = replace(self._result, scales=list(self._result.scales))
            _classify(copy, list(self._segmenter.strokes), self._holds.snapshot())
            return copy

    def observe(self, tracking: TrackingResult) -> None:
        with self._lock:
            motion = self._analyzer.update(tracking)
            result = self._result
            if result is None:
                return
            result.frames += 1
            result.image_width = tracking.image_width
            if len(motion.hands) != 1:
                return
            hand = motion.hands[0]
            obs = tracking.hands[hand.observation_index]
            pose = analyze_pose(obs, tracking.image_width, tracking.image_height)
            result.tracked += 1
            result.scales.append(pose.scale_px)
            if result.gesture in SWIPES and result.detector == "fist":
                self._segmenter.add(
                    tracking.timestamp_ns,
                    hand.palm.position_px,
                    hand.palm.velocity_px_s,
                    pose.scale_px,
                    pose.label is PoseLabel.FIST,
                )
            elif result.gesture in SWIPES:
                self._segmenter.add(
                    tracking.timestamp_ns,
                    hand.fingertip.position_px,
                    hand.fingertip.velocity_px_s,
                    pose.scale_px,
                    pose.label is PoseLabel.POINTING,
                )
            else:
                self._holds.add(tracking.timestamp_ns, hand.palm.position_px, pose.scale_px, pose)


def _classify(result: PromptResult, strokes: list[Stroke], holds: list[HeldPose]) -> None:
    result.demos, result.windups, result.other, result.returns = [], [], [], []
    result.holds = list(holds)
    if result.gesture not in SWIPES:
        return
    target = result.gesture
    opposite = _opposite(target)
    demos = [
        s
        for s in strokes
        if s.direction is target and s.length_palms >= MIN_STROKE_PALMS and not s.diagonal
    ]
    result.demos = demos
    gap_w = int(WINDUP_GAP_S * NS_PER_S)
    first_demo = min((d.start_ns for d in demos), default=None)
    for s in strokes:
        if s in demos:
            continue
        if s.direction is opposite:
            # Between two demonstrations the hand must come back: every opposite stroke there
            # is a return, however long the user paused (a held swipe followed by a slow return
            # was taken for a wind-up and raised the distance - Director, Brief 004 beta).
            # Only a stroke right before the first demonstration can be a wind-up.
            after_a_demo = any(s.start_ns >= d.end_ns for d in demos)
            if after_a_demo:
                result.returns.append(s)
                continue
            if first_demo is not None and 0 <= first_demo - s.end_ns <= gap_w:
                result.windups.append(s)
                continue
        result.other.append(s)


@dataclass(frozen=True)
class Derived:
    settings: GestureSettings
    profile: CalibrationProfile
    notes: list[str]
    """What was changed or why something was kept (plain language)."""


def _direction_distance(
    direction: GestureType,
    results: dict[GestureType, PromptResult],
    current: float,
    notes: list[str],
    label: str,
) -> tuple[float, list[Stroke]] | None:
    """Personal distance for one direction, or ``None`` without enough demonstrations."""
    result = results.get(direction)
    if result is None or len(result.demos) < 2:
        return None
    typical = statistics.median(s.length_palms for s in result.demos)
    # Raising the hand into position or lowering it is not a demonstration (or a wind-up).
    demos = [s for s in result.demos if s.length_palms <= OUTLIER_FACTOR * typical]
    lengths = [s.length_palms for s in demos]
    # Movements in this direction that must NOT trigger it: wind-ups before the demonstrations
    # of this direction and of the opposite one (a downward curl before an upward flick moves
    # like a downward flick). Returns are not used: the recognizer suppresses them anyway, and
    # whole-hand returns (as large as the swipe) raised the distance so far that small flicks
    # failed in the cross-session simulation (0/8).
    opposite = results.get(_opposite(direction))
    unwanted = list(result.windups)
    if opposite is not None:
        unwanted += [s for s in opposite.windups if s.direction is direction]
    unwanted = [s for s in unwanted if s.length_palms <= WINDUP_OUTLIER_FACTOR * typical]
    # Lower the distance for small movements; raise it only as far as unwanted movements
    # require and at most by MAX_RAISE (a higher distance punishes any later change of style).
    distance = min(0.7 * statistics.median(lengths), current)
    ceiling = min(0.9 * min(lengths), MAX_RAISE * current)
    floor = 1.15 * max((s.length_palms for s in unwanted), default=0.0)
    if floor > ceiling:
        notes.append(
            f"{label}: the movement back is about as large as your swipe; make the swipe a "
            "little larger than the movement back."
        )
        distance = ceiling
    else:
        distance = min(max(distance, floor), ceiling)
    if distance < MIN_DISTANCE:
        notes.append(
            f"{label}: your movements are very small; the distance stays at the safe minimum "
            f"of {MIN_DISTANCE:.2f} hand lengths - move a little further."
        )
    distance = round(min(max(distance, MIN_DISTANCE), MAX_DISTANCE), 2)
    notes.append(
        f"{label}: distance {distance:.2f} hand lengths "
        f"(your swipes {min(lengths):.2f}-{max(lengths):.2f})."
    )
    return distance, demos


DIRECTION_FIELDS = {
    G.INDEX_SWIPE_UP: ("swipe_up_distance_palms", "Finger up"),
    G.INDEX_SWIPE_DOWN: ("swipe_down_distance_palms", "Finger down"),
    G.INDEX_SWIPE_LEFT: ("swipe_left_distance_palms", "Finger left"),
    G.INDEX_SWIPE_RIGHT: ("swipe_right_distance_palms", "Finger right"),
}


def derive(
    results: dict[GestureType, PromptResult],
    base: GestureSettings,
    hand: str = "",
    fist_results: dict[GestureType, PromptResult] | None = None,
) -> Derived:
    """Bounded personal settings from the measured prompts (see the module documentation).

    Finger distances are derived per direction (Brief 005: up and down need not be alike);
    a direction with fewer than two usable demonstrations keeps its current value."""
    notes: list[str] = []
    changes: dict[str, object] = {}
    peaks: list[float] = []
    durations: list[float] = []
    for direction, (field_name, label) in DIRECTION_FIELDS.items():
        derived = _direction_distance(
            direction, results, swipe_distance(base, direction), notes, label
        )
        if derived is None:
            if direction in results:
                notes.append(f"{label}: not enough demonstrations, unchanged.")
            continue
        changes[field_name], demos = derived
        peaks += [s.peak_palms_s for s in demos]
        durations += [s.duration_s for s in demos]
    fist_distances = []
    for direction in DIRECTION_FIELDS:
        label = f"Fist {direction.value.rsplit('_', 1)[1]}"
        derived = _direction_distance(
            direction, fist_results or {}, base.fist_swipe_distance_palms, notes, label
        )
        if derived is not None:
            fist_distances.append(derived[0])
    if fist_distances:
        # One shared fist distance (palm-centre travel); the most demanding direction decides
        # so that no direction becomes easier than its own movements allow.
        changes["fist_swipe_distance_palms"] = round(
            min(max(max(fist_distances), FIST_MIN_DISTANCE), FIST_MAX_DISTANCE), 2
        )
    settings = base
    if changes:
        if peaks:
            # The speed is only ever lowered (fast demonstrations must not make slower
            # everyday swipes fail).
            changes["swipe_min_speed_palms_s"] = round(
                min(max(0.5 * min(peaks), 1.2), base.swipe_min_speed_palms_s), 2
            )
            changes["swipe_max_duration_s"] = round(
                min(max(1.3 * max(durations), base.swipe_max_duration_s), 1.0), 2
            )
        settings = replace(settings, preset=SensitivityPreset.PERSONAL, **changes)
    profile = CalibrationProfile(
        created=datetime.now().isoformat(timespec="minutes"), hand=hand, method=CALIBRATION_METHOD
    )
    heart = results.get(G.HALF_HEART)
    if heart is not None:
        good = [h.features for h in heart.holds if heart_essentials(h.features)]
        if good:
            template = {k: statistics.median(f[k] for f in good) for k in good[0]}  # type: ignore[index]
            profile = replace(
                profile,
                heart_index_flexion=round(template["index_flexion"], 1),
                heart_index_reach=round(template["index_reach"], 3),
                heart_hook=round(template["hook"], 3),
                heart_thumb_down=round(template["thumb_down"], 3),
                heart_thumb_below=round(template["thumb_below"], 3),
                heart_gap=round(template["gap"], 3),
                heart_upright=round(template["upright"], 3),
            )
            notes.append(f"Half-heart: your shape learned from {len(good)} demonstration(s).")
        else:
            notes.append("Half-heart: no usable demonstration, the standard shape is used.")
    stop = results.get(G.STOP_GESTURE)
    if stop is not None:
        tilts = [h.upright_deg for h in stop.holds if h.four_extended]
        if tilts:
            tilt = statistics.median(tilts)
            if tilt + 10 > settings.stop_upright_deg:
                allowed = round(min(70.0, tilt + 10), 1)
                settings = replace(settings, stop_upright_deg=allowed)
                if settings.preset is not SensitivityPreset.PERSONAL:
                    settings = replace(settings, preset=SensitivityPreset.PERSONAL)
                notes.append(f"Stop pose: fingers may tilt up to {allowed:.0f} degrees.")
            else:
                notes.append("Stop pose: your open palm already fits the standard pose.")
        else:
            notes.append("Stop pose: no open palm was held; unchanged.")
    return Derived(settings, profile, notes)
