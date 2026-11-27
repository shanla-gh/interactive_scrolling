"""The gesture engine: control-hand selection, recognizer orchestration and conflict rules.

Input per frame: the :class:`TrackingResult` and :class:`MotionFrame` already produced by the
vision pipeline (no image data). Output: a :class:`GestureFrame` with the control-hand
status, active candidates, at most one confirmed :class:`GestureEvent` and rejections.

Safety rules
------------
* Only one *control hand* produces gestures (preference AUTO, LEFT or RIGHT). Other visible
  hands are tracked and drawn but never generate events.
* When the control hand is ambiguous (two candidates for the role, two hands overlapping)
  recognition is suspended. In LEFT/RIGHT mode the hand's handedness is the majority label
  of its recent frames, ignoring low-score labels.
* A newly acquired control hand must be tracked for ``min_track_age_s`` before candidates may
  start, and swipe recognizers additionally require it to be still first (re-arming), so a
  hand entering the frame cannot produce a swipe.
* Tracking loss cancels all candidates; gaps of up to ``RecognizerOptions.dropout_s`` (fast
  movements blur and MediaPipe drops a few frames) keep the current candidate.
* After any confirmed gesture, all recognizers are blocked for ``global_cooldown_s``; static
  pose candidates are cancelled while a swipe candidate is active.

The engine is not thread-safe; it is owned by the processing thread. Settings changes from
other threads go through :meth:`request_settings`, applied at the next update.
"""

from __future__ import annotations

import math
import threading
from collections import Counter, deque

from interactive_scrolling.config.settings import (
    CalibrationProfile,
    ControlHandPreference,
    GestureSettings,
)
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.gestures.pose import PoseLabel, analyze_pose, matches_personal_heart
from interactive_scrolling.gestures.recognizers import (
    DirectionalSwipeRecognizer,
    HandSample,
    RecognizerOptions,
    StaticPoseRecognizer,
    Step,
    half_heart,
    pointing,
    stop_pose,
)
from interactive_scrolling.gestures.types import (
    ControlStatus,
    GestureCandidate,
    GestureEvent,
    GestureFrame,
    GesturePhase,
    GestureRejection,
    GestureType,
    RejectCode,
)
from interactive_scrolling.motion.analyzer import HandMotion, MotionFrame
from interactive_scrolling.vision.landmarks import Handedness, TrackingResult

MIN_HANDEDNESS_SCORE = 0.7
"""Below this score the handedness of a hand is not trusted for LEFT/RIGHT selection."""
MIN_HAND_SEPARATION_PALMS = 1.2
"""Two hands closer than this (palm centres) make the control hand ambiguous."""
HANDEDNESS_WINDOW = 15
"""Frames over which a track's handedness label is smoothed (MediaPipe's per-frame label
flips occasionally during fast movement)."""
MIN_HAND_SCALE_FRACTION = 0.045
"""Below this hand size (fraction of the image width; ~58 px at 1280 px) landmark jitter
dominates small movements and the stop pose is often lost: the user is told to come closer."""
EDGE_MARGIN_FRACTION = 0.04
LOW_FPS = 20.0
"""Below this frame rate small finger flicks are undersampled (Brief 004: an upward flick
measured 0.53 instead of 0.82 hand lengths at 15 fps; hand movements still worked 8/8)."""


class GestureEngine:
    def __init__(
        self,
        settings: GestureSettings | None = None,
        options: RecognizerOptions | None = None,
        profile: CalibrationProfile | None = None,
    ) -> None:
        self._settings = settings or GestureSettings()
        self.options = options or RecognizerOptions()
        self.profile: CalibrationProfile | None = profile
        self._pending_settings: GestureSettings | None = None
        self._lock = threading.Lock()
        self._build()
        self._control_track: int | None = None
        self._blocked_until_ns = 0
        self._labels: dict[int, deque[tuple[Handedness, float | None]]] = {}
        self._last_seen_ns: int | None = None
        self._frame_times: deque[int] = deque(maxlen=31)

    @property
    def settings(self) -> GestureSettings:
        return self._settings

    def request_settings(self, settings: GestureSettings) -> None:
        """Thread-safe: settings take effect at the next :meth:`update`."""
        with self._lock:
            self._pending_settings = settings

    def _build(self) -> None:
        s = self._settings
        o = self.options
        self.swipes = DirectionalSwipeRecognizer(s, pose_ok=pointing, pose_fraction=0.6, options=o)
        self.heart = StaticPoseRecognizer(
            GestureType.HALF_HEART,
            self._half_heart,
            lambda: self._settings.half_heart_hold_s,
            s,
            options=o,
            describe=unmet_heart_conditions,
        )
        self.stop = StaticPoseRecognizer(
            GestureType.STOP_GESTURE,
            self._stop_pose,
            lambda: self._settings.stop_hold_s,
            s,
            options=o,
            describe=unmet_stop_conditions,
        )
        self._apply_enabled()

    def _stop_pose(self, pose) -> bool:  # type: ignore[no-untyped-def]
        tilt = self._settings.stop_upright_deg
        if tilt == 40.0:
            return stop_pose(pose)
        return pose.label is PoseLabel.OPEN_PALM and pose.fingers_up_alignment >= math.cos(
            math.radians(tilt)
        )

    def _half_heart(self, pose) -> bool:  # type: ignore[no-untyped-def]
        if half_heart(pose):
            return True
        template = self.profile
        return (
            template is not None and template.has_heart and matches_personal_heart(pose, template)
        )

    def set_profile(self, profile: CalibrationProfile | None) -> None:
        """Personal calibration results (thread-safe enough: one reference assignment)."""
        self.profile = profile

    def frame_rate(self) -> float | None:
        """Frames per second over the last second of frames (``None`` until known)."""
        times = self._frame_times
        if len(times) < 10:
            return None
        span = (times[-1] - times[0]) / NS_PER_S
        return (len(times) - 1) / span if span > 0 else None

    def _apply_enabled(self) -> None:
        s = self._settings
        self.swipes.enabled = frozenset(
            gesture
            for gesture, on in (
                (GestureType.INDEX_SWIPE_DOWN, s.enable_swipe_down),
                (GestureType.INDEX_SWIPE_UP, s.enable_swipe_up),
                (GestureType.INDEX_SWIPE_LEFT, s.enable_swipe_left),
                (GestureType.INDEX_SWIPE_RIGHT, s.enable_swipe_right),
            )
            if on
        )

    def _enabled(self) -> list[DirectionalSwipeRecognizer | StaticPoseRecognizer]:
        s = self._settings
        out: list[DirectionalSwipeRecognizer | StaticPoseRecognizer] = []
        if self.swipes.enabled:
            # Disabled directions are followed but never confirm (see the recognizer), so a
            # movement in a disabled direction cannot be misread as another one.
            out.append(self.swipes)
        if s.enable_half_heart:
            out.append(self.heart)
        if s.enable_stop:
            out.append(self.stop)
        return out

    def _all(self) -> tuple[DirectionalSwipeRecognizer | StaticPoseRecognizer, ...]:
        return (self.swipes, self.heart, self.stop)

    def reset(self) -> None:
        """Forget the control hand and every candidate (camera restart, mode change)."""
        self._control_track = None
        self._labels.clear()
        self._last_seen_ns = None
        for recognizer in self._all():
            recognizer.reset(rearm=isinstance(recognizer, DirectionalSwipeRecognizer))

    # ------------------------------------------------------------------ control hand

    def _observe_labels(self, tracking: TrackingResult, motion: MotionFrame) -> None:
        present = set()
        for hand in motion.hands:
            obs = tracking.hands[hand.observation_index]
            history = self._labels.setdefault(hand.track_id, deque(maxlen=HANDEDNESS_WINDOW))
            if hand.reset:
                history.clear()
            history.append((obs.handedness, obs.handedness_score))
            present.add(hand.track_id)
        for track_id in list(self._labels):
            if track_id not in present and track_id != self._control_track:
                del self._labels[track_id]

    def handedness_of(self, track_id: int) -> Handedness:
        """Majority handedness of a track over recent frames, ignoring low-score labels."""
        votes = Counter(
            label
            for label, score in self._labels.get(track_id, ())
            if label is not Handedness.UNKNOWN and (score is None or score >= MIN_HANDEDNESS_SCORE)
        )
        if not votes:
            return Handedness.UNKNOWN
        (label, count), *rest = votes.most_common()
        if rest and rest[0][1] == count:
            return Handedness.UNKNOWN
        return label

    def _eligible(self, motion: HandMotion, tracking: TrackingResult) -> bool:
        preference = self._settings.control_hand
        if preference is ControlHandPreference.AUTO:
            return True
        wanted = Handedness.LEFT if preference is ControlHandPreference.LEFT else Handedness.RIGHT
        return self.handedness_of(motion.track_id) is wanted

    def _select(
        self, tracking: TrackingResult, motion: MotionFrame
    ) -> tuple[HandMotion | None, ControlStatus, str]:
        hands = list(motion.hands)
        if not hands:
            return None, ControlStatus.NO_HAND, "no hand in view"
        current = next((h for h in hands if h.track_id == self._control_track), None)
        if current is not None and not self._eligible(current, tracking):
            current = None
        if current is None:
            eligible = [h for h in hands if self._eligible(h, tracking)]
            if not eligible:
                wanted = self._settings.control_hand.value
                return None, ControlStatus.NO_HAND, f"{wanted} hand not in view"
            if len(eligible) > 1:
                return None, ControlStatus.AMBIGUOUS, "several possible control hands"
            current = eligible[0]
        for other in hands:
            if other is current:
                continue
            distance = math.dist(other.palm.position_px, current.palm.position_px)
            if distance < MIN_HAND_SEPARATION_PALMS * current.palm_length_px:
                return None, ControlStatus.AMBIGUOUS, "hands too close together"
        return current, ControlStatus.ACTIVE, ""

    # ------------------------------------------------------------------ update

    def update(self, tracking: TrackingResult, motion: MotionFrame) -> GestureFrame:
        with self._lock:
            pending, self._pending_settings = self._pending_settings, None
        if pending is not None:
            self._settings = pending
            for recognizer in self._all():
                recognizer.settings = pending
            self._apply_enabled()

        ts = tracking.timestamp_ns
        self._frame_times.append(ts)
        self._observe_labels(tracking, motion)
        hand, status, detail = self._select(tracking, motion)
        rejection: GestureRejection | None = None

        if hand is None:
            dropout = (
                status is ControlStatus.NO_HAND
                and self._last_seen_ns is not None
                and ts - self._last_seen_ns <= int(self.options.dropout_s * NS_PER_S)
            )
            if not dropout:
                lost = status is ControlStatus.NO_HAND
                rejection = self._cancel_all(
                    ts,
                    "tracking lost" if lost else "control hand ambiguous",
                    RejectCode.TRACKING_LOST if lost else RejectCode.AMBIGUOUS,
                )
            if status is ControlStatus.AMBIGUOUS:
                # Identity may have been swapped; require a fresh, settled hand afterwards.
                self._control_track = None
            return GestureFrame(
                timestamp_ns=ts,
                status=status,
                status_detail=detail,
                rejection=rejection,
                blocked_until_ns=self._blocked_until_ns if self._blocked_until_ns > ts else None,
            )

        # Identity comes from the motion tracker (position-based association). Handedness
        # label flips alone do not change identity; in LEFT/RIGHT mode a sustained flip makes
        # the hand ineligible through the smoothed label.
        if hand.track_id != self._control_track or hand.reset:
            rejection = self._cancel_all(ts, "control hand changed", RejectCode.HAND_CHANGED)
            for recognizer in self._all():
                recognizer.reset(rearm=isinstance(recognizer, DirectionalSwipeRecognizer))
            self._control_track = hand.track_id
        handedness = self.handedness_of(hand.track_id)

        self._last_seen_ns = ts
        observation = tracking.hands[hand.observation_index]
        pose = analyze_pose(observation, tracking.image_width, tracking.image_height)
        hint = positioning_hint(pose.scale_px, observation, tracking.image_width)
        if not hint and self.frame_rate() is not None and self.frame_rate() < LOW_FPS:
            hint = "Low camera frame rate: more light helps; move the hand, not only the finger"
        length = hand.palm_length_px
        sample = HandSample(
            timestamp_ns=ts,
            track_id=hand.track_id,
            handedness=handedness,
            pose=pose,
            fingertip=hand.fingertip.position_px,
            palm=hand.palm.position_px,
            fingertip_velocity=(
                hand.fingertip.velocity_px_s[0] / length,
                hand.fingertip.velocity_px_s[1] / length,
            ),
            palm_velocity=(
                hand.palm.velocity_px_s[0] / length,
                hand.palm.velocity_px_s[1] / length,
            ),
            palm_length_px=length,
            scale_px=pose.scale_px,
        )

        if hand.track_duration_s < self._settings.min_track_age_s:
            if self.options.static_while_stabilizing:
                # A held pose proves its own stability through the hold time, so static poses
                # may start their hold at once (the stop pose is often visible for only about
                # half a second at arm's length); swipes still wait.
                for recognizer in (self.heart, self.stop):
                    if recognizer in self._enabled():
                        recognizer.update(sample)
            return GestureFrame(
                timestamp_ns=ts,
                status=ControlStatus.STABILIZING,
                status_detail="waiting for stable tracking",
                control_track_id=hand.track_id,
                control_handedness=handedness,
                pose=pose.label.value,
                rejection=rejection,
                hint=hint,
                hand_scale_px=pose.scale_px,
            )

        steps: list[tuple[DirectionalSwipeRecognizer | StaticPoseRecognizer, Step]] = []
        enabled = self._enabled()
        for recognizer in enabled:
            steps.append((recognizer, recognizer.update(sample)))
        # Disabled recognizers keep running their release logic but never confirm.
        for recognizer in self._all():
            if recognizer not in enabled and recognizer.phase is not GesturePhase.IDLE:
                recognizer.reset(rearm=False)

        swipe_active = any(
            isinstance(r, DirectionalSwipeRecognizer) and r.phase is GesturePhase.CANDIDATE
            for r in enabled
        )
        event: GestureEvent | None = None
        candidates: list[GestureCandidate] = []
        for recognizer, step in steps:
            if step.rejection is not None:
                rejection = step.rejection
            if isinstance(recognizer, StaticPoseRecognizer) and swipe_active:
                cancelled = recognizer.cancel(ts, "hand started moving", RejectCode.HAND_MOVING)
                if cancelled.rejection is not None:
                    rejection = cancelled.rejection
                continue
            if step.event is not None and event is None and ts >= self._blocked_until_ns:
                event = step.event
            elif step.event is not None:
                rejection = GestureRejection(
                    step.event.gesture,
                    "blocked by a gesture just confirmed",
                    ts,
                    RejectCode.BLOCKED,
                )
            if step.candidate is not None and recognizer.phase is GesturePhase.CANDIDATE:
                candidates.append(step.candidate)

        if event is not None:
            self._blocked_until_ns = ts + int(self._settings.global_cooldown_s * NS_PER_S)
            for recognizer in self._all():
                if event.gesture not in recognizer.gestures:
                    recognizer.block_until(self._blocked_until_ns)
            candidates = []

        return GestureFrame(
            timestamp_ns=ts,
            status=ControlStatus.ACTIVE,
            control_track_id=hand.track_id,
            control_handedness=handedness,
            pose=pose.label.value,
            phase=self._overall_phase(event),
            candidates=tuple(candidates),
            events=(event,) if event is not None else (),
            rejection=rejection,
            blocked_until_ns=self._blocked_until_ns if self._blocked_until_ns > ts else None,
            hint=hint,
            hand_scale_px=pose.scale_px,
        )

    def _cancel_all(self, ts: int, reason: str, code: str) -> GestureRejection | None:
        rejection = None
        for recognizer in self._all():
            if recognizer.phase is GesturePhase.CANDIDATE:
                rejection = GestureRejection(recognizer.gestures[0], reason, ts, code)
                recognizer.reset(rearm=isinstance(recognizer, DirectionalSwipeRecognizer))
        return rejection

    def _overall_phase(self, event: GestureEvent | None) -> GesturePhase:
        if event is not None:
            return GesturePhase.CONFIRMED
        phases = {r.phase for r in self._enabled()}
        for phase in (
            GesturePhase.CANDIDATE,
            GesturePhase.COOLDOWN,
            GesturePhase.REARMING,
        ):
            if phase in phases:
                return phase
        return GesturePhase.IDLE


def positioning_hint(scale_px: float, observation, image_width: int) -> str:
    """A hint from measured tracking quality, or an empty string."""
    if image_width > 0 and scale_px < MIN_HAND_SCALE_FRACTION * image_width:
        return "Hand far from the camera: move it a little closer"
    x = observation.landmarks[:, 0]
    y = observation.landmarks[:, 1]
    margin = EDGE_MARGIN_FRACTION
    if x.min() < margin or x.max() > 1 - margin or y.min() < margin or y.max() > 1 - margin:
        return "Hand at the edge of the picture: move it towards the centre"
    return ""


def unmet_heart_conditions(pose) -> tuple[str, ...]:
    """Plain-language list of the half-heart conditions this pose does not meet."""
    from interactive_scrolling.gestures.pose import heart_checklist

    return tuple(text for text, ok in heart_checklist(pose) if not ok)


def unmet_stop_conditions(pose) -> tuple[str, ...]:
    from interactive_scrolling.gestures.pose import stop_checklist

    return tuple(text for text, ok in stop_checklist(pose) if not ok)
