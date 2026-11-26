"""Typed, validated configuration objects.

Settings are plain dataclasses so they can be constructed in tests without any
framework. Every settings object validates itself on construction and raises
:class:`ConfigError` with a human-readable message when a value is invalid.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a configuration value is invalid."""


class CameraBackend(enum.Enum):
    """OpenCV capture backends supported on Windows."""

    MSMF = "msmf"
    """Media Foundation. Opens quickly and is the default on Windows."""

    DSHOW = "dshow"
    """DirectShow. Slower to open, but useful as a fallback for older drivers."""

    AUTO = "auto"
    """Let OpenCV choose."""


SUPPORTED_RESOLUTIONS: tuple[tuple[int, int], ...] = ((640, 480), (1280, 720), (1920, 1080))


@dataclass(frozen=True)
class CameraSettings:
    """Requested camera configuration. The device may negotiate different values."""

    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    backend: CameraBackend = CameraBackend.MSMF

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ConfigError(f"Camera index must be non-negative, got {self.index}.")
        if not (160 <= self.width <= 4096 and 120 <= self.height <= 4096):
            raise ConfigError(f"Unsupported camera resolution {self.width}x{self.height}.")
        if not 1 <= self.fps <= 240:
            raise ConfigError(f"Camera FPS must be between 1 and 240, got {self.fps}.")


@dataclass(frozen=True)
class TrackingSettings:
    """Hand landmarker configuration."""

    model_path: Path | None = None
    """Explicit model path. ``None`` uses the default location (see ``vision.model_assets``)."""

    num_hands: int = 2
    min_hand_detection_confidence: float = 0.5
    min_hand_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    inference_max_width: int | None = None
    """Downscale frames wider than this before inference. ``None`` uses the full frame."""

    def __post_init__(self) -> None:
        if self.inference_max_width is not None and self.inference_max_width < 160:
            raise ConfigError("inference_max_width must be at least 160 pixels.")
        if not 1 <= self.num_hands <= 4:
            raise ConfigError(f"num_hands must be between 1 and 4, got {self.num_hands}.")
        for name in (
            "min_hand_detection_confidence",
            "min_hand_presence_confidence",
            "min_tracking_confidence",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f"{name} must be within [0, 1], got {value}.")


@dataclass(frozen=True)
class MotionSettings:
    """Motion analysis parameters.

    Lengths expressed in *palm lengths* are relative to the measured distance between
    the wrist and the middle-finger MCP joint, which makes thresholds largely
    independent of how far the hand is from the camera.
    """

    position_time_constant_s: float = 0.04
    """Time constant of the exponential position smoother. ``0`` disables smoothing."""

    velocity_time_constant_s: float = 0.06
    """Time constant of the exponential velocity smoother. ``0`` disables smoothing."""

    moving_threshold_palms_per_s: float = 0.6
    """Speed above which a hand is classified as moving."""

    stationary_threshold_palms_per_s: float = 0.35
    """Speed below which a moving hand returns to stationary (hysteresis)."""

    max_observation_gap_s: float = 0.25
    """A track that is unobserved for longer than this restarts its velocity estimate."""

    max_jump_palms: float = 3.0
    """A single-observation jump larger than this is treated as a discontinuity."""

    association_max_distance_palms: float = 3.0
    """Maximum palm-centre distance for matching a detection to an existing track."""

    trail_duration_s: float = 0.7
    """Age of the oldest sample retained for motion trails."""

    displacement_window_s: float = 0.2
    """Window over which the net displacement vector is measured."""

    history_capacity: int = 120
    """Upper bound on the number of motion samples kept per hand."""

    def __post_init__(self) -> None:
        if self.position_time_constant_s < 0 or self.velocity_time_constant_s < 0:
            raise ConfigError("Smoothing time constants must be non-negative.")
        if self.stationary_threshold_palms_per_s < 0:
            raise ConfigError("Stationary threshold must be non-negative.")
        if self.moving_threshold_palms_per_s < self.stationary_threshold_palms_per_s:
            raise ConfigError("Moving threshold must be >= stationary threshold (hysteresis).")
        if self.max_observation_gap_s <= 0:
            raise ConfigError("max_observation_gap_s must be positive.")
        if self.max_jump_palms <= 0 or self.association_max_distance_palms <= 0:
            raise ConfigError("Jump and association distances must be positive.")
        if self.trail_duration_s <= 0 or self.displacement_window_s <= 0:
            raise ConfigError("Trail duration and displacement window must be positive.")
        if self.history_capacity < 2:
            raise ConfigError("history_capacity must be at least 2.")


@dataclass
class OverlaySettings:
    """Independently switchable overlay layers. Mutable so the UI can toggle them."""

    show_landmarks: bool = True
    show_skeleton: bool = True
    show_bounding_box: bool = True
    show_labels: bool = True
    show_fingertip_trail: bool = True
    show_palm_trail: bool = False
    show_vectors: bool = True


class ControlHandPreference(enum.Enum):
    """Which hand may issue gesture commands."""

    AUTO = "auto"
    """The first hand that is alone in view becomes the control hand and keeps that role."""
    LEFT = "left"
    RIGHT = "right"


class SensitivityPreset(enum.Enum):
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"
    CUSTOM = "custom"


# Thresholds scaled by a preset: lower sensitivity needs larger, faster, longer gestures.
_PRESET_SCALES = {
    SensitivityPreset.LOW: 1.25,
    SensitivityPreset.BALANCED: 1.0,
    SensitivityPreset.HIGH: 0.8,
}
_SCALED_FIELDS = (
    "swipe_min_distance_palms",
    "swipe_min_speed_palms_s",
    "half_heart_hold_s",
    "stop_hold_s",
)

_RANGES: dict[str, tuple[float, float]] = {
    "swipe_min_distance_palms": (0.3, 3.0),
    "swipe_min_speed_palms_s": (0.5, 10.0),
    "swipe_max_duration_s": (0.2, 2.0),
    "direction_ratio": (1.0, 5.0),
    "half_heart_hold_s": (0.1, 3.0),
    "stop_hold_s": (0.1, 3.0),
    "static_max_speed_palms_s": (0.1, 3.0),
    "cooldown_s": (0.0, 5.0),
    "return_window_s": (0.0, 3.0),
    "global_cooldown_s": (0.0, 5.0),
    "rearm_still_s": (0.0, 2.0),
    "rearm_max_speed_palms_s": (0.1, 3.0),
    "min_track_age_s": (0.0, 2.0),
}

GESTURE_ENABLE_FIELDS = (
    "enable_swipe_down",
    "enable_swipe_up",
    "enable_swipe_left",
    "enable_swipe_right",
    "enable_half_heart",
    "enable_stop",
)


@dataclass(frozen=True)
class GestureSettings:
    """Gesture recognition thresholds. Distances and speeds are in palm lengths.

    One palm length is the measured wrist to middle-finger-MCP distance, so thresholds do not
    depend on how far the hand is from the camera. The four index swipes share one set of
    thresholds (see docs/architecture/GESTURES.md for why).
    """

    preset: SensitivityPreset = SensitivityPreset.BALANCED
    swipe_min_distance_palms: float = 0.8
    """Fingertip travel along the swipe direction."""
    swipe_min_speed_palms_s: float = 2.0
    """Peak fingertip speed along the swipe direction."""
    swipe_max_duration_s: float = 0.7
    direction_ratio: float = 1.8
    """The main axis must exceed the cross axis by this factor (1.8 = within ~29 degrees);
    movements between the axes are rejected rather than assigned to a direction."""
    half_heart_hold_s: float = 0.6
    stop_hold_s: float = 0.8
    static_max_speed_palms_s: float = 0.6
    cooldown_s: float = 0.5
    """Minimum time after a swipe before the next swipe can be confirmed."""
    return_window_s: float = 1.2
    """After a swipe, an opposite stroke that starts within this time after the swipe's
    movement ended, while the hand is still away from where the swipe started, is the hand's
    return movement and is ignored."""
    global_cooldown_s: float = 0.4
    """After any confirmed gesture, no other gesture is confirmed for this time."""
    rearm_still_s: float = 0.0
    """How long the hand must stay below ``rearm_max_speed_palms_s`` before a new swipe can
    start. 0 means one slow frame is enough: a stroke must begin from (near) rest, so a hand
    that is already moving when it is acquired cannot trigger a swipe."""
    rearm_max_speed_palms_s: float = 1.0
    min_track_age_s: float = 0.3
    control_hand: ControlHandPreference = ControlHandPreference.AUTO
    enable_swipe_down: bool = True
    enable_swipe_up: bool = True
    enable_swipe_left: bool = True
    enable_swipe_right: bool = True
    enable_half_heart: bool = True
    enable_stop: bool = True

    def __post_init__(self) -> None:
        for name, (low, high) in _RANGES.items():
            value = getattr(self, name)
            if not isinstance(value, int | float) or not low <= value <= high:
                raise ConfigError(f"{name} must be within [{low}, {high}], got {value!r}.")

    @classmethod
    def from_preset(cls, preset: SensitivityPreset, **overrides: object) -> GestureSettings:
        """Defaults scaled for ``preset``; other fields (hand, enabled gestures) via overrides."""
        if preset is SensitivityPreset.CUSTOM:
            raise ConfigError("CUSTOM is not a preset; edit individual values instead.")
        base = cls()
        scale = _PRESET_SCALES[preset]
        values: dict[str, object] = {name: getattr(base, name) * scale for name in _SCALED_FIELDS}
        values.update(overrides)
        values["preset"] = preset
        return replace(base, **values)  # type: ignore[arg-type]


@dataclass
class AppSettings:
    """Top-level application settings."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    motion: MotionSettings = field(default_factory=MotionSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    gestures: GestureSettings = field(default_factory=GestureSettings)
    mirror_preview: bool = True
