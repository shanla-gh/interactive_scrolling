"""Hand landmark inference.

:class:`MediaPipeHandTracker` adapts the MediaPipe Tasks ``HandLandmarker`` to the
framework-independent :class:`~interactive_scrolling.vision.landmarks.HandObservation`
representation. It uses the ``VIDEO`` running mode: synchronous calls with strictly
increasing timestamps, which lets MediaPipe track hands between frames instead of
re-running palm detection on every frame. A tracker instance is not thread-safe: it may
be created on one thread and then used by another, but never concurrently.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from interactive_scrolling.config.settings import TrackingSettings
from interactive_scrolling.vision.landmarks import NUM_LANDMARKS, Handedness, HandObservation

log = logging.getLogger(__name__)


class HandTracker(Protocol):
    """Anything that turns an RGB frame into hand observations."""

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> tuple[HandObservation, ...]:
        """Detect hands in an ``(H, W, 3)`` ``uint8`` RGB image captured at ``timestamp_ms``."""
        ...

    def close(self) -> None: ...


class ModelNotFoundError(FileNotFoundError):
    """The hand landmarker model file is missing."""


class TrackerInitError(RuntimeError):
    """The inference engine could not be initialised."""


def _landmarks_to_array(points: Sequence[Any]) -> np.ndarray | None:
    if len(points) != NUM_LANDMARKS:
        return None
    return np.array(
        [(p.x or 0.0, p.y or 0.0, p.z or 0.0) for p in points],
        dtype=np.float32,
    )


def convert_result(result: Any) -> tuple[HandObservation, ...]:
    """Convert a MediaPipe ``HandLandmarkerResult`` into hand observations.

    Hands with an unexpected number of landmarks are discarded rather than padded.
    Handedness uses the highest-scoring category reported for each hand.
    """
    hands: list[HandObservation] = []
    handedness_lists = list(result.handedness or [])
    world_lists = list(result.hand_world_landmarks or [])
    for i, points in enumerate(result.hand_landmarks or []):
        landmarks = _landmarks_to_array(points)
        if landmarks is None:
            log.debug("Discarding hand %d with %d landmarks", i, len(points))
            continue
        handedness = Handedness.UNKNOWN
        score: float | None = None
        categories = handedness_lists[i] if i < len(handedness_lists) else []
        if categories:
            top = max(categories, key=lambda c: c.score if c.score is not None else -1.0)
            handedness = Handedness.from_label(top.category_name)
            score = float(top.score) if top.score is not None else None
        world = _landmarks_to_array(world_lists[i]) if i < len(world_lists) else None
        hands.append(
            HandObservation(
                landmarks=landmarks,
                handedness=handedness,
                handedness_score=score,
                world_landmarks=world,
            )
        )
    return tuple(hands)


class MediaPipeHandTracker:
    """MediaPipe Tasks hand landmarker running fully locally on the CPU."""

    def __init__(self, settings: TrackingSettings, model_path: Path) -> None:
        if not model_path.is_file():
            raise ModelNotFoundError(
                f"Hand landmarker model not found at {model_path}. "
                "Run 'python scripts/download_model.py' once to download it."
            )
        # Imported lazily: mediapipe is heavy and not needed by most unit tests.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=settings.num_hands,
            min_hand_detection_confidence=settings.min_hand_detection_confidence,
            min_hand_presence_confidence=settings.min_hand_presence_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )
        try:
            self._landmarker = vision.HandLandmarker.create_from_options(options)
        except (RuntimeError, ValueError) as exc:
            raise TrackerInitError(f"Could not initialise the hand landmarker: {exc}") from exc
        self._last_timestamp_ms = -1
        self._closed = False
        log.info("Hand landmarker loaded from %s (max %d hands)", model_path, settings.num_hands)

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> tuple[HandObservation, ...]:
        if self._closed:
            raise RuntimeError("Tracker is closed.")
        # VIDEO mode requires strictly increasing timestamps.
        timestamp_ms = max(int(timestamp_ms), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb)
        )
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        return convert_result(result)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._landmarker.close()
