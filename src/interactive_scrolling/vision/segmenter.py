"""Person segmentation for the transparent Content Creator background (presentation only).

:class:`MediaPipePersonSegmenter` adapts the MediaPipe Tasks ``ImageSegmenter`` with the
Selfie Segmenter (landscape) model. It returns a per-pixel *person confidence* mask in [0, 1]
at the resolution of the image it was given. The hand-tracking pipeline never sees its output:
the mask is only used to make the background of the overlay's copy of the frame transparent.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

INPUT_WIDTH = 320
"""Frames are downscaled to this width before segmentation (the model's input is 256x144)."""


class SegmenterUnavailableError(RuntimeError):
    pass


class MediaPipePersonSegmenter:
    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise SegmenterUnavailableError(
                f"Segmentation model not found at {model_path}. "
                "Run 'python scripts/download_model.py' once to download it."
            )
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        try:
            self._segmenter = vision.ImageSegmenter.create_from_options(options)
        except (RuntimeError, ValueError) as exc:
            raise SegmenterUnavailableError(
                f"Could not load the segmentation model: {exc}"
            ) from exc
        self._last_ms = -1
        log.info("Person segmenter loaded from %s", model_path)

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> np.ndarray:
        """Person confidence (float32, values 0-1) for a downscaled copy of ``image_rgb``."""
        timestamp_ms = max(int(timestamp_ms), self._last_ms + 1)
        self._last_ms = timestamp_ms
        h, w = image_rgb.shape[:2]
        small_w = min(w, INPUT_WIDTH)
        small_h = max(1, round(h * small_w / w))
        small = cv2.resize(image_rgb, (small_w, small_h), interpolation=cv2.INTER_AREA)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=small)
        result = self._segmenter.segment_for_video(image, timestamp_ms)
        masks = result.confidence_masks or []
        if not masks:
            return np.zeros((small_h, small_w), dtype=np.float32)
        # The landscape selfie model has one output: the person confidence.
        return np.array(masks[-1].numpy_view(), dtype=np.float32).reshape(small_h, small_w)

    def close(self) -> None:
        self._segmenter.close()
