"""In-memory recognition diagnostics and the opt-in landmark recorder.

:class:`GestureDiagnostics` follows every processed frame on the processing thread and keeps
(bounded, in memory only) what the user needs to understand why a gesture did or did not
work: how often a control hand was tracked, which candidates formed, which were confirmed and
every rejection with its measured and required value, plus the outcome of the resulting
browser actions. Nothing is written to disk unless the user exports it; no images, page
addresses, titles or video ids are kept.

The stages it separates (Brief 004, CP A2): hand tracked -> candidate formed -> confirmed ->
action dispatched -> browser outcome. Whether the user *attempted* a gesture cannot be known
from the camera; the Practice mode supplies that by prompting.

:class:`LandmarkRecorder` records the normalized hand landmarks of a short session (only when
the user starts it) in the format of ``scripts/record_gestures.py``, so a problematic gesture
can be replayed with ``scripts/evaluate_gestures.py``.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field

from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.gestures.types import ControlStatus, GestureFrame, GestureType
from interactive_scrolling.vision.landmarks import TrackingResult

ATTEMPT_CAPACITY = 300


@dataclass(slots=True)
class _Counts:
    candidates: Counter = field(default_factory=Counter)
    confirmed: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)
    """(gesture value, code) -> count."""
    status_frames: Counter = field(default_factory=Counter)
    hints: Counter = field(default_factory=Counter)
    actions: Counter = field(default_factory=Counter)
    """(action, status) -> count."""


class GestureDiagnostics:
    """Thread-safe: ``observe`` runs on the processing thread, readers on the UI thread."""

    def __init__(self, capacity: int = ATTEMPT_CAPACITY) -> None:
        self._lock = threading.Lock()
        self._capacity = capacity
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._entries: deque[dict] = deque(maxlen=self._capacity)
            self._counts = _Counts()
            self._active: set[GestureType] = set()
            self._scales: deque[float] = deque(maxlen=900)
            self._started = time.time()

    # ------------------------------------------------------------------ input

    def observe(self, tracking: TrackingResult, frame: GestureFrame) -> None:
        with self._lock:
            c = self._counts
            c.status_frames[frame.status.value] += 1
            if frame.hint:
                c.hints[frame.hint] += 1
            if frame.hand_scale_px is not None and frame.status is ControlStatus.ACTIVE:
                self._scales.append(frame.hand_scale_px)
            current = {candidate.gesture for candidate in frame.candidates}
            for gesture in current - self._active:
                c.candidates[gesture.value] += 1
            self._active = current
            for event in frame.events:
                c.confirmed[event.gesture.value] += 1
                self._entries.append(
                    {
                        "t": _wall(),
                        "kind": "confirmed",
                        "gesture": event.gesture.value,
                        "hand": event.handedness.value,
                        "movement_palms": event.magnitude_palms,
                        "peak_speed_palms_s": event.peak_speed_palms_s,
                        "duration_s": event.duration_s,
                        "decision_delay_s": event.decision_delay_s,
                    }
                )
            r = frame.rejection
            if r is not None:
                c.rejected[(r.gesture.value, r.code or "other")] += 1
                self._entries.append(
                    {
                        "t": _wall(),
                        "kind": "rejected",
                        "gesture": r.gesture.value,
                        "code": r.code,
                        "reason": r.reason,
                        "measured": r.measured,
                        "required": r.required,
                        "unit": r.unit,
                        "details": list(r.details),
                    }
                )

    def observe_action(
        self, gesture: str, action: str, status: str, reason: str, latency_ms: float | None
    ) -> None:
        """A final action outcome (called by the services with plain values)."""
        with self._lock:
            self._counts.actions[(action, status)] += 1
            self._entries.append(
                {
                    "t": _wall(),
                    "kind": "action",
                    "gesture": gesture,
                    "action": action,
                    "status": status,
                    "reason": reason,
                    "latency_ms": None if latency_ms is None else round(latency_ms, 1),
                }
            )

    # ------------------------------------------------------------------ output

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return list(self._entries)[-limit:]

    def snapshot(self) -> dict:
        with self._lock:
            c = self._counts
            frames = sum(c.status_frames.values())
            scales = sorted(self._scales)
            per_gesture = {}
            for gesture in GestureType:
                g = gesture.value
                rejected = {code: n for (name, code), n in c.rejected.items() if name == g}
                per_gesture[g] = {
                    "candidates": c.candidates[g],
                    "confirmed": c.confirmed[g],
                    "rejected": rejected,
                }
            return {
                "since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._started)),
                "frames": frames,
                "control_hand_status": dict(c.status_frames),
                "hand_tracked_fraction": round(
                    c.status_frames[ControlStatus.ACTIVE.value] / frames, 3
                )
                if frames
                else None,
                "median_hand_size_px": round(scales[len(scales) // 2], 1) if scales else None,
                "positioning_hints": dict(c.hints),
                "gestures": per_gesture,
                "actions": {f"{a}: {s}": n for (a, s), n in c.actions.items()},
                "recent": list(self._entries),
            }


def _wall() -> str:
    return time.strftime("%H:%M:%S")


class LandmarkRecorder:
    """Records normalized landmarks of the processed frames for a limited time (opt in).

    Thread-safe: frames arrive on the processing thread; ``start``/``stop``/``label`` on the UI
    thread. The output is the ``record_gestures.py`` format (``prompts`` and ``frames``)."""

    def __init__(self, max_seconds: float = 120.0) -> None:
        self._lock = threading.Lock()
        self._max_ns = int(max_seconds * NS_PER_S)
        self._frames: list[dict] | None = None
        self._prompts: list[list] = []
        self._label = "unlabeled"
        self._segment = 0
        self._start_ns: int | None = None

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._frames is not None

    def start(self) -> None:
        with self._lock:
            self._frames = []
            self._prompts = []
            self._label = "unlabeled"
            self._segment = 0
            self._start_ns = None

    def label(self, label: str, seconds: float = 0.0, text: str = "") -> None:
        """Mark the following frames with ``label`` (one prompt segment)."""
        with self._lock:
            if self._frames is None:
                return
            self._label = label
            self._segment += 1
            self._prompts.append([label, seconds, text])

    def observe(self, tracking: TrackingResult) -> None:
        with self._lock:
            if self._frames is None:
                return
            if self._start_ns is None:
                self._start_ns = tracking.timestamp_ns
            if tracking.timestamp_ns - self._start_ns > self._max_ns:
                return
            self._frames.append(
                {
                    "t_ns": tracking.timestamp_ns,
                    "label": self._label,
                    "segment": self._segment,
                    "w": tracking.image_width,
                    "h": tracking.image_height,
                    "hands": [
                        {
                            "lm": [[round(float(v), 5) for v in point] for point in hand.landmarks],
                            "handedness": hand.handedness.value,
                            "score": None
                            if hand.handedness_score is None
                            else round(hand.handedness_score, 3),
                        }
                        for hand in tracking.hands
                    ],
                }
            )

    def stop(self) -> dict | None:
        """End the recording and return its content (``None`` if none was running)."""
        with self._lock:
            frames, self._frames = self._frames, None
            if frames is None:
                return None
            return {"prompts": self._prompts, "frames": frames}
