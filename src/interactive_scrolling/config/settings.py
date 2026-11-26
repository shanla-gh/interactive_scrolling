"""Typed, validated configuration objects.

Settings are plain dataclasses so they can be constructed in tests without any
framework. Every settings object validates itself on construction and raises
:class:`ConfigError` with a human-readable message when a value is invalid.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
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


@dataclass
class AppSettings:
    """Top-level application settings."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    motion: MotionSettings = field(default_factory=MotionSettings)
    overlay: OverlaySettings = field(default_factory=OverlaySettings)
    mirror_preview: bool = True
