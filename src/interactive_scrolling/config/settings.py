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
    """Shown as Precise (LOW sensitivity: larger, deliberate movements), Balanced and Relaxed
    (HIGH: smaller movements are enough). PERSONAL holds values from Quick Calibration and
    CUSTOM values edited by hand; both keep their stored values."""

    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"
    CUSTOM = "custom"
    PERSONAL = "personal"

    @property
    def keeps_values(self) -> bool:
        return self in (SensitivityPreset.CUSTOM, SensitivityPreset.PERSONAL)

    @property
    def display(self) -> str:
        return {
            SensitivityPreset.LOW: "Precise - larger, deliberate movements",
            SensitivityPreset.BALANCED: "Balanced (recommended)",
            SensitivityPreset.HIGH: "Relaxed - smaller movements are enough",
            SensitivityPreset.CUSTOM: "Custom",
            SensitivityPreset.PERSONAL: "Personal (from Quick Calibration)",
        }[self]


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
    "swipe_horizontal_distance_palms": (0.0, 3.0),
    "stop_upright_deg": (20.0, 75.0),
    "swipe_up_distance_palms": (0.0, 3.0),
    "swipe_down_distance_palms": (0.0, 3.0),
    "swipe_left_distance_palms": (0.0, 3.0),
    "swipe_right_distance_palms": (0.0, 3.0),
    "fist_swipe_distance_palms": (0.15, 3.0),
}
CONTROL_STYLES = ("finger", "fist", "hybrid")

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
    half_heart_hold_s: float = 0.5
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
    swipe_horizontal_distance_palms: float = 0.0
    """Distance for left/right swipes; 0 = the same as ``swipe_min_distance_palms``. Quick
    Calibration may set the two axes separately (comfortable ranges differ by person)."""
    stop_upright_deg: float = 40.0
    """How far the fingers of the stop pose may tilt from straight up."""
    swipe_up_distance_palms: float = 0.0
    swipe_down_distance_palms: float = 0.0
    swipe_left_distance_palms: float = 0.0
    swipe_right_distance_palms: float = 0.0
    """Per-direction finger-swipe distances from Quick Calibration; 0 = shared value."""
    control_style: str = "finger"
    """``finger`` (index swipes), ``fist`` (closed-hand swipes) or ``hybrid`` (both)."""
    fist_swipe_distance_palms: float = 0.5
    """Palm-centre travel of a fist (or palm) swipe."""
    enable_palm_swipes: bool = False
    """Experimental: open-hand swipes (conflict with the stop pose, see GESTURES.md)."""
    control_hand: ControlHandPreference = ControlHandPreference.AUTO
    enable_swipe_down: bool = True
    enable_swipe_up: bool = True
    enable_swipe_left: bool = True
    enable_swipe_right: bool = True
    enable_half_heart: bool = True
    enable_stop: bool = True

    def __post_init__(self) -> None:
        if self.control_style not in CONTROL_STYLES:
            raise ConfigError(f"control_style must be one of {CONTROL_STYLES}")
        for name, (low, high) in _RANGES.items():
            value = getattr(self, name)
            if not isinstance(value, int | float) or not low <= value <= high:
                raise ConfigError(f"{name} must be within [{low}, {high}], got {value!r}.")

    @classmethod
    def from_preset(cls, preset: SensitivityPreset, **overrides: object) -> GestureSettings:
        """Defaults scaled for ``preset``; other fields (hand, enabled gestures) via overrides."""
        if preset.keeps_values:
            raise ConfigError(f"{preset.value} is not a preset; edit individual values instead.")
        base = cls()
        scale = _PRESET_SCALES[preset]
        values: dict[str, object] = {name: getattr(base, name) * scale for name in _SCALED_FIELDS}
        values.update(overrides)
        values["preset"] = preset
        return replace(base, **values)  # type: ignore[arg-type]


_HEX_COLOR = "0123456789abcdefABCDEF"


def _valid_color(value: str) -> bool:
    return value == "auto" or (
        isinstance(value, str)
        and len(value) == 7
        and value[0] == "#"
        and all(c in _HEX_COLOR for c in value[1:])
    )


@dataclass(frozen=True)
class AppearanceSettings:
    """Visual customization of the overlays (Developer and Content Creator Mode)."""

    skeleton_color: str = "auto"
    """``auto`` colours each hand by handedness; otherwise ``#rrggbb``."""
    landmark_scale: float = 1.0
    line_scale: float = 1.0
    trail_length_s: float = 0.7
    show_gesture_feedback: bool = True
    """The confirmed-gesture banner and candidate progress bar on the video."""
    show_telemetry: bool = True
    """Status chips (tracking state, resolution) on the video."""

    def __post_init__(self) -> None:
        if not _valid_color(self.skeleton_color):
            raise ConfigError(
                f"skeleton_color must be 'auto' or #rrggbb, got {self.skeleton_color!r}."
            )
        for name, low, high in (
            ("landmark_scale", 0.3, 3.0),
            ("line_scale", 0.3, 3.0),
            ("trail_length_s", 0.1, 3.0),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not low <= value <= high
            ):
                raise ConfigError(f"{name} must be within [{low}, {high}], got {value!r}.")


class OverlayCorner(enum.Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CUSTOM = "custom"


@dataclass(frozen=True)
class CreatorSettings:
    """The always-on-top Content Creator overlay."""

    width: int = 480
    height: int = 270
    x: int | None = None
    """Window position in screen pixels; ``None`` places it in ``corner``."""
    y: int | None = None
    corner: OverlayCorner = OverlayCorner.BOTTOM_RIGHT
    opacity: float = 1.0
    show_skeleton: bool = True
    show_vectors: bool = False
    show_trails: bool = True
    show_last_gesture: bool = True
    show_outcome: bool = True
    show_counters: bool = False
    transparent_background: bool = False
    """Remove the background around the person (local segmentation, presentation only)."""

    def __post_init__(self) -> None:
        if not (160 <= self.width <= 3840 and 90 <= self.height <= 2160):
            raise ConfigError(f"Overlay size {self.width}x{self.height} is out of range.")
        if isinstance(self.opacity, bool) or not 0.3 <= self.opacity <= 1.0:
            raise ConfigError(f"Overlay opacity must be within [0.3, 1.0], got {self.opacity!r}.")
        for name in ("x", "y"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not -20000 <= value <= 20000):
                raise ConfigError(f"Overlay {name} position {value!r} is out of range.")


@dataclass(frozen=True)
class WellbeingSettings:
    """Anti-Doomscroll options (all optional; reminders are off until the user enables them)."""

    enabled: bool = False
    """Show Reality Checks and limit notices."""
    session_limit_min: float = 20.0
    daily_budget_min: float = 60.0
    reality_check_min: float = 15.0
    """Interval of Reality Check notices during a session (0 = none)."""
    break_reminders: bool = True
    pause_at_limit: bool = False
    """Pause gesture scrolling automatically at the session limit or daily budget."""
    humorous_labels: bool = True
    """Playful wording for the Doomscroll Index and Wrapped titles."""

    def __post_init__(self) -> None:
        for name, low, high in (
            ("session_limit_min", 1.0, 600.0),
            ("daily_budget_min", 1.0, 1440.0),
            ("reality_check_min", 0.0, 240.0),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not low <= value <= high
            ):
                raise ConfigError(f"{name} must be within [{low}, {high}], got {value!r}.")


@dataclass(frozen=True)
class EffectsSettings:
    """Face-based features. Both are off by default; face inference runs only when one is on."""

    clown_enabled: bool = False
    clown_stage1_min: float = 10.0
    clown_stage2_min: float = 20.0
    clown_stage3_min: float = 30.0
    clown_preview_stage: int | None = None
    """Show this stage regardless of the session (for trying the effect); ``None`` = off."""
    eye_analytics_enabled: bool = False
    eye_baseline_yaw: float | None = None
    """Result of the optional one-point calibration (``None``: not calibrated)."""
    eye_baseline_pitch: float | None = None
    eye_baseline_gaze: float | None = None

    def __post_init__(self) -> None:
        stages = (self.clown_stage1_min, self.clown_stage2_min, self.clown_stage3_min)
        for value in stages:
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not 0 <= value <= 600
            ):
                raise ConfigError(
                    f"Clown thresholds must be within [0, 600] minutes, got {value!r}."
                )
        if not stages[0] <= stages[1] <= stages[2]:
            raise ConfigError("Clown stage thresholds must not decrease.")
        if self.clown_preview_stage is not None and self.clown_preview_stage not in (0, 1, 2, 3):
            raise ConfigError("clown_preview_stage must be 0-3 or None.")

    @property
    def clown_thresholds(self) -> tuple[float, float, float]:
        return (self.clown_stage1_min, self.clown_stage2_min, self.clown_stage3_min)


@dataclass
class AppSettings:
    """Top-level application settings."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    motion: MotionSettings = field(default_factory=MotionSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    gestures: GestureSettings = field(default_factory=GestureSettings)
    mirror_preview: bool = True


@dataclass(frozen=True)
class CalibrationProfile:
    """Derived results of Quick Calibration (no images, no landmark sequences).

    The swipe thresholds it produced live in :class:`GestureSettings` (preset PERSONAL); this
    section keeps the personal half-heart template - the median shape measurements of the
    user's own demonstrations - and when and with which hand the calibration was made.
    ``None`` means "not calibrated" for that gesture."""

    created: str = ""
    hand: str = ""
    method: int = 0
    """Derivation version: 0 = version 0.4 (could raise thresholds too far), 2 = version 0.5."""
    heart_index_flexion: float | None = None
    heart_index_reach: float | None = None
    heart_hook: float | None = None
    heart_thumb_down: float | None = None
    heart_thumb_below: float | None = None
    heart_gap: float | None = None
    heart_upright: float | None = None

    @property
    def has_heart(self) -> bool:
        return self.heart_hook is not None
