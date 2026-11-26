"""Control modes, actions, outcomes and the controller interface."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol

from interactive_scrolling.gestures.types import GestureEvent, GestureType


class ControlMode(enum.Enum):
    TRACKING_ONLY = "tracking_only"
    """Camera and tracking run; gestures are not recognized and nothing is executed."""
    GESTURE_TEST = "gesture_test"
    """Gestures are recognized, shown and logged; no external action is executed."""
    LIVE_CONTROL = "live_control"
    """Confirmed gestures may execute their mapped action after all safety checks."""

    @property
    def label(self) -> str:
        return {
            ControlMode.TRACKING_ONLY: "Tracking only",
            ControlMode.GESTURE_TEST: "Gesture test",
            ControlMode.LIVE_CONTROL: "Live control",
        }[self]


class ActionType(enum.Enum):
    NONE = "none"
    NEXT_SHORT = "next_short"
    PREVIOUS_SHORT = "previous_short"
    LIKE_SHORT = "like_short"
    TOGGLE_PLAYBACK = "toggle_playback"
    NEXT_BROWSER_TAB = "next_browser_tab"
    PREVIOUS_BROWSER_TAB = "previous_browser_tab"

    @property
    def label(self) -> str:
        return _ACTION_LABELS[self]

    @property
    def available(self) -> bool:
        """Whether this version can execute the action."""
        return self in AVAILABLE_ACTIONS


_ACTION_LABELS = {
    ActionType.NONE: "No action",
    ActionType.NEXT_SHORT: "Next Short",
    ActionType.PREVIOUS_SHORT: "Previous Short",
    ActionType.LIKE_SHORT: "Like Short",
    ActionType.TOGGLE_PLAYBACK: "Pause / resume",
    ActionType.NEXT_BROWSER_TAB: "Next browser tab",
    ActionType.PREVIOUS_BROWSER_TAB: "Previous browser tab",
}

SHORTS_ACTIONS = frozenset(
    {
        ActionType.NEXT_SHORT,
        ActionType.PREVIOUS_SHORT,
        ActionType.LIKE_SHORT,
        ActionType.TOGGLE_PLAYBACK,
    }
)
"""Actions that require a valid YouTube Shorts tab."""
TAB_ACTIONS = frozenset({ActionType.NEXT_BROWSER_TAB, ActionType.PREVIOUS_BROWSER_TAB})
"""Actions that require the supported browser to be the active application."""
AVAILABLE_ACTIONS = SHORTS_ACTIONS | TAB_ACTIONS
YOUTUBE_ACTIONS = SHORTS_ACTIONS

LEGACY_ACTION_NAMES = {
    # Version 0.2 reserved the hand sweeps for application switching, which Brief 003 removed.
    "switch_to_study_app": None,
    "return_to_social_app": None,
}
"""Stored action names of earlier versions; ``None`` means "use the current default"."""

CONFIGURABLE_GESTURES = tuple(GestureType)
"""Every gesture can be mapped to any available action (or to none)."""

DEFAULT_MAPPING: dict[GestureType, ActionType] = {
    GestureType.INDEX_SWIPE_DOWN: ActionType.NEXT_SHORT,
    GestureType.INDEX_SWIPE_UP: ActionType.PREVIOUS_SHORT,
    GestureType.INDEX_SWIPE_RIGHT: ActionType.NEXT_BROWSER_TAB,
    GestureType.INDEX_SWIPE_LEFT: ActionType.PREVIOUS_BROWSER_TAB,
    GestureType.HALF_HEART: ActionType.LIKE_SHORT,
    GestureType.STOP_GESTURE: ActionType.TOGGLE_PLAYBACK,
}


class MappingError(ValueError):
    pass


def validate_mapping(mapping: dict[GestureType, ActionType]) -> dict[GestureType, ActionType]:
    """Return a complete mapping; reject assignments outside the allowed action set."""
    result = dict(DEFAULT_MAPPING)
    for gesture, action in mapping.items():
        if action is not ActionType.NONE and action not in AVAILABLE_ACTIONS:
            raise MappingError(f"{gesture.label} cannot be mapped to {action.label}.")
        result[gesture] = action
    return result


class ActionStatus(enum.Enum):
    """Lifecycle and outcome of the action requested for one confirmed gesture."""

    NOT_EXECUTED = "not executed"
    """Recognized but intentionally not executed (mode, mapping, availability)."""
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    """Sent to the controller; outcome not known yet."""
    SUCCEEDED = "succeeded"
    """The controller confirmed the intended effect (e.g. the active Short changed)."""
    NO_CHANGE = "no change"
    """Valid request with nothing to do (e.g. the Short was already liked)."""
    REJECTED = "rejected"
    """Refused before execution (no valid context, stale, busy, disabled)."""
    FAILED = "failed"
    """Execution was attempted and the intended effect did not happen."""
    UNKNOWN = "outcome unknown"
    """The request may or may not have had an effect (e.g. timeout, disabled mid-flight)."""

    @property
    def final(self) -> bool:
        return self not in (ActionStatus.QUEUED, ActionStatus.DISPATCHED)


@dataclass(frozen=True, slots=True)
class ActionResult:
    status: ActionStatus
    reason: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ControllerCheck:
    ready: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """Snapshot of one gesture's journey through the dispatcher (immutable; one per update)."""

    record_id: str
    event: GestureEvent
    action: ActionType
    mode: ControlMode
    status: ActionStatus
    reason: str = ""
    detail: str = ""
    created_ns: int = 0
    dispatched_ns: int | None = None
    completed_ns: int | None = None
    wall_time: float = 0.0
    """Local wall-clock time (epoch seconds) when the gesture was confirmed, for display."""
    source: str = "local"
    """Who requested the action: "local" (this computer's gestures) or "guest" (co-op)."""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def action_latency_ms(self) -> float | None:
        """Time from dispatch to the controller's confirmed outcome."""
        if self.dispatched_ns is None or self.completed_ns is None:
            return None
        return (self.completed_ns - self.dispatched_ns) / 1e6

    @property
    def end_to_end_ms(self) -> float | None:
        """Time from the frame that confirmed the gesture to the confirmed outcome."""
        if self.completed_ns is None:
            return None
        return (self.completed_ns - self.event.timestamp_ns) / 1e6


class ActionController(Protocol):
    """Executes actions on one platform. Methods are called from the dispatcher thread."""

    def check(self, action: ActionType) -> ControllerCheck:
        """Whether ``action`` can be executed right now, and why not."""
        ...

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        """Execute and confirm ``action``; block at most ``timeout_s``."""
        ...

    def cancel_all(self) -> None:
        """Abandon any in-flight request (emergency disable)."""
        ...
