"""Plain-language texts for gesture instructions, live state and rejections.

Used by the live overlay, the gesture panel and the Practice mode, so a beginner never has to
interpret palm lengths, angles or recognizer phases. Every explanation is derived from the
measured values in a :class:`GestureRejection`; nothing here invents a confidence value.
"""

from __future__ import annotations

from interactive_scrolling.gestures.types import (
    ControlStatus,
    GestureFrame,
    GesturePhase,
    GestureRejection,
    GestureType,
    RejectCode,
)

G = GestureType

INSTRUCTIONS: dict[GestureType, tuple[str, str]] = {
    G.INDEX_SWIPE_UP: (
        "Move your finger UP",
        "Point with your index finger and move it up - a flick of the finger or a short "
        "movement of the hand. Then let it come back.",
    ),
    G.INDEX_SWIPE_DOWN: (
        "Move your finger DOWN",
        "Point with your index finger and move it down - flick the finger or move the hand a "
        "little. Then let it come back.",
    ),
    G.INDEX_SWIPE_RIGHT: (
        "Move your finger to YOUR RIGHT",
        "Point with your index finger and move it to your right (your own right, whatever "
        "the preview shows). Then let it come back.",
    ),
    G.INDEX_SWIPE_LEFT: (
        "Move your finger to YOUR LEFT",
        "Point with your index finger and move it to your left. Then let it come back.",
    ),
    G.HALF_HEART: (
        "Show a HALF-HEART",
        "One half of a two-handed heart: hand upright, index finger (or all fingers) curved "
        "over with the tip pointing down, thumb pointing down below it, a gap between them. "
        "Hold it still for a moment.",
    ),
    G.STOP_GESTURE: (
        "Show an OPEN PALM (stop)",
        "Open hand, fingers up, palm towards the camera, not too far away. Hold it still.",
    ),
}

_DIRECTION_WORD = {
    G.INDEX_SWIPE_UP: "up",
    G.INDEX_SWIPE_DOWN: "down",
    G.INDEX_SWIPE_RIGHT: "to your right",
    G.INDEX_SWIPE_LEFT: "to your left",
}


_FIST_WORD = {
    G.INDEX_SWIPE_UP: "UP",
    G.INDEX_SWIPE_DOWN: "DOWN",
    G.INDEX_SWIPE_RIGHT: "to YOUR RIGHT",
    G.INDEX_SWIPE_LEFT: "to YOUR LEFT",
}


def instruction(gesture: GestureType, detector: str = "finger") -> tuple[str, str]:
    """(short title, one-paragraph explanation) for ``gesture`` made with ``detector``."""
    if detector == "fist" and gesture in _FIST_WORD:
        word = _FIST_WORD[gesture]
        return (
            f"Move your FIST {word}",
            f"Close your hand into a fist, hold it still for a moment, then move it {word.lower()}"
            " with a small, quick movement of the wrist or hand. Then let it come back.",
        )
    return INSTRUCTIONS[gesture]


def event_label(gesture: GestureType, detector: str = "") -> str:
    """Display name of a recognized gesture, naming the detector for fist and palm swipes."""
    if detector in ("fist", "palm"):
        return f"{gesture.label} ({detector})"
    return gesture.label


def _short(gesture: GestureType) -> str:
    if gesture in _DIRECTION_WORD:
        return f"Finger {_DIRECTION_WORD[gesture]}"
    return gesture.label.capitalize()


def explain_rejection(rejection: GestureRejection) -> str:
    """One sentence: what was seen and what to do differently."""
    g = rejection.gesture
    name = _short(g)
    m, r = rejection.measured, rejection.required
    code = rejection.code
    if code == RejectCode.TOO_SHORT:
        if m is not None and r:
            return (
                f"{name}: movement too short ({m:.2f} of {r:.2f} hand lengths). "
                "Move a little further."
            )
        return f"{name}: movement too short. Move a little further."
    if code == RejectCode.TOO_SLOW:
        return f"{name}: movement too slow. Make it a little quicker."
    if code == RejectCode.TOO_LONG:
        return f"{name}: the movement took too long. Make one quick, short movement."
    if code == RejectCode.TOO_FAR:
        return f"{name}: the hand kept moving too far (that looks like moving the arm away)."
    if code == RejectCode.DIAGONAL:
        word = _DIRECTION_WORD.get(g, "straight")
        return f"{name}: direction unclear (diagonal). Move straight {word}."
    if code == RejectCode.POSE:
        if "curled" in rejection.reason:
            return f"{name}: the finger stayed curled. After a flick, straighten it again."
        return f"{name}: point with your index finger while moving."
    if code == RejectCode.RETURN:
        return "Ignored: this looked like your hand moving back after the previous swipe."
    if code == RejectCode.COOLDOWN:
        return "Ignored: too soon after the previous gesture."
    if code == RejectCode.NOT_ACTIVATED:
        return f"{name}: close the hand into a fist and hold it still briefly before moving."
    if code == RejectCode.NOT_ARMED:
        return "Ignored: the hand was already moving when it appeared. Hold it still briefly."
    if code == RejectCode.DISABLED:
        return f"{name} is switched off in the gesture settings."
    if code == RejectCode.HAND_MOVING:
        return f"{name}: keep your hand still while you hold the pose."
    if code == RejectCode.RELEASED:
        held = f" (held {m:.1f} of {r:.1f} s)" if m is not None and r else ""
        missing = f" Missing: {', '.join(rejection.details)}." if rejection.details else ""
        return f"{name}: pose not held long enough{held}.{missing}"
    if code == RejectCode.TRACKING_LOST:
        return "The camera lost your hand during the gesture."
    if code == RejectCode.AMBIGUOUS:
        return "Two hands are close together; use one hand."
    if code == RejectCode.HAND_CHANGED:
        return "A different hand took over; start again."
    if code == RejectCode.BLOCKED:
        return f"{name}: ignored right after another gesture."
    return f"{name}: {rejection.reason}"


def state_label(frame: GestureFrame | None) -> str:
    """Short live state for the overlay (READY, POINTING, MOVEMENT DETECTED, ...)."""
    if frame is None:
        return ""
    if frame.status is ControlStatus.NO_HAND:
        return "NO HAND"
    if frame.status is ControlStatus.AMBIGUOUS:
        return "USE ONE HAND"
    if frame.status is ControlStatus.STABILIZING:
        return "HAND FOUND"
    if frame.events:
        return frame.events[0].gesture.label
    if frame.candidates:
        best = max(frame.candidates, key=lambda c: c.progress)
        if best.gesture.is_dynamic:
            return f"MOVEMENT DETECTED: {best.gesture.label}"
        return f"{best.gesture.label} DETECTED - HOLD"
    if frame.phase is GesturePhase.COOLDOWN:
        return "WAIT"
    if frame.pose == "pointing":
        return "POINTING - READY"
    return "READY"
