"""Face landmarks for the Progressive Clown Transformation and passive eye analytics.

:class:`MediaPipeFaceTracker` adapts the MediaPipe Tasks ``FaceLandmarker``: 478 landmarks
(including 10 iris points), a few expression blendshapes and the head pose. It is used only for
the clown rendering and coarse, passive eye estimates. There is no face identification: no
embeddings or descriptors are computed and nothing is stored (the model card declares identity
recognition out of scope as well).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

INPUT_WIDTH = 640
"""Frames are downscaled to this width before face inference."""
BLENDSHAPES = (
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "jawOpen",
    "mouthSmileLeft",
    "mouthSmileRight",
)
"""The only blendshape scores kept (blinks and mouth shape for the clown makeup)."""


class FaceTrackerUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FaceObservation:
    landmarks: np.ndarray
    """(478, 3) float32, normalized coordinates of the unmirrored frame (like hand landmarks)."""
    blendshapes: dict[str, float] = field(default_factory=dict)
    yaw_deg: float | None = None
    """Head rotation to the side (positive: the person turns to their left), from the model's
    facial transformation matrix."""
    pitch_deg: float | None = None
    """Head rotation up/down (positive: looking up)."""


def head_angles(matrix: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) in degrees from a 4x4 facial transformation matrix."""
    r = matrix[:3, :3]
    yaw = math.degrees(math.atan2(-r[2, 0], math.hypot(r[2, 1], r[2, 2])))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    return yaw, pitch


class MediaPipeFaceTracker:
    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise FaceTrackerUnavailableError(
                f"Face landmark model not found at {model_path}. "
                "Run 'python scripts/download_model.py' once to download it."
            )
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        try:
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
        except (RuntimeError, ValueError) as exc:
            raise FaceTrackerUnavailableError(f"Could not load the face model: {exc}") from exc
        self._last_ms = -1
        log.info("Face landmarker loaded from %s", model_path)

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> FaceObservation | None:
        timestamp_ms = max(int(timestamp_ms), self._last_ms + 1)
        self._last_ms = timestamp_ms
        h, w = image_rgb.shape[:2]
        if w > INPUT_WIDTH:
            size = (INPUT_WIDTH, max(1, round(h * INPUT_WIDTH / w)))
            image_rgb = cv2.resize(image_rgb, size, interpolation=cv2.INTER_AREA)
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb)
        )
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return None
        points = result.face_landmarks[0]
        landmarks = np.array([(p.x, p.y, p.z) for p in points], dtype=np.float32)
        shapes: dict[str, float] = {}
        if result.face_blendshapes:
            for category in result.face_blendshapes[0]:
                if category.category_name in BLENDSHAPES:
                    shapes[category.category_name] = float(category.score)
        yaw = pitch = None
        if result.facial_transformation_matrixes:
            yaw, pitch = head_angles(np.asarray(result.facial_transformation_matrixes[0]))
        return FaceObservation(landmarks, shapes, yaw, pitch)

    def close(self) -> None:
        self._landmarker.close()
