"""Neutral synthetic face landmarks from MediaPipe's canonical face mesh (development tool).

The face landmarker bundle (``models/face_landmarker.task``, downloaded, not committed)
contains the canonical face geometry used by MediaPipe. Projecting its 468 vertices gives a
neutral, non-personal face in the 478-landmark layout (the 10 iris points are placed at the
eye centres), so face effects can be previewed and tested without any real person's image.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import numpy as np

MODEL = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"


def _varint(data: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[i]
        i += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return result, i


def canonical_vertices(model: Path = MODEL) -> np.ndarray:
    """(468, 3) canonical mesh vertices in centimetres (x right, y up)."""
    blob = zipfile.ZipFile(model).read("geometry_pipeline_metadata_landmarks.binarypb")
    _, i = _varint(blob, 0)
    length, i = _varint(blob, i)
    mesh = blob[i : i + length]
    floats: list[float] = []
    j = 0
    while j < len(mesh):
        key, j = _varint(mesh, j)
        field, wire = key >> 3, key & 7
        if wire == 0:
            _, j = _varint(mesh, j)
        elif wire == 5:
            if field == 3:
                floats.append(struct.unpack_from("<f", mesh, j)[0])
            j += 4
        elif wire == 2:
            n, j = _varint(mesh, j)
            j += n
        else:
            raise ValueError("unexpected wire type")
    vertex = np.array(floats, dtype=np.float64).reshape(-1, 5)
    return vertex[:, :3]


def face_landmarks(
    image_w: int,
    image_h: int,
    center: tuple[float, float] = (0.5, 0.45),
    face_height: float = 0.5,
    yaw_deg: float = 0.0,
    mouth_open: float = 0.0,
) -> np.ndarray:
    """(478, 3) normalized landmarks of the neutral face at ``center`` (fraction of the image),
    ``face_height`` of the image height, optionally turned (``yaw_deg``) and with the lower lip
    and chin lowered by ``mouth_open`` (fraction of the face height)."""
    v = canonical_vertices().copy()
    yaw = np.radians(yaw_deg)
    x, z = (
        v[:, 0] * np.cos(yaw) + v[:, 2] * np.sin(yaw),
        -v[:, 0] * np.sin(yaw) + v[:, 2] * np.cos(yaw),
    )
    v[:, 0], v[:, 2] = x, z
    height = v[:, 1].max() - v[:, 1].min()
    if mouth_open:
        lower = (14, 87, 178, 88, 95, 317, 402, 318, 324, 17, 84, 181, 91, 146, 314, 405, 321, 375)
        chin = v[:, 1] < v[14, 1]
        drop = mouth_open * height
        v[chin, 1] -= drop * 0.6
        v[list(lower), 1] -= drop * 0.4
    scale_px = face_height * image_h / height
    cx, cy = center[0] * image_w, center[1] * image_h
    mid = (v[:, :2].max(axis=0) + v[:, :2].min(axis=0)) / 2
    px = cx + (v[:, 0] - mid[0]) * scale_px
    py = cy - (v[:, 1] - mid[1]) * scale_px
    pts = np.zeros((478, 3))
    pts[:468, 0] = px / image_w
    pts[:468, 1] = py / image_h
    pts[:468, 2] = -v[:, 2] * scale_px / image_w
    right_eye = pts[[33, 133, 159, 145], :].mean(axis=0)
    left_eye = pts[[263, 362, 386, 374], :].mean(axis=0)
    pts[468:473] = right_eye
    pts[473:478] = left_eye
    return pts
