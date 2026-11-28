"""Render the eye and gaze overlay on a synthetic face (development tool, Brief 009).

Uses the canonical-face drawing of ``render_clown_stages.py`` (no person). Variants: eyes
straight, irises turned to the person's left, head turned, looking up, a blink (vectors
hidden). Output is local (screenshots/ is not committed).

Usage: python scripts/render_gaze_overlay.py --out screenshots/brief009/gaze
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_face import face_landmarks
from interactive_scrolling.vision.face_tracker import FaceObservation
from interactive_scrolling.visualization.eye_overlay import EyeOverlay
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.wellbeing import gaze as g
from render_clown_stages import H, W, draw_face


def variant(iris_dx: float, iris_dy: float, yaw: float, pitch: float, blink: float):  # type: ignore[no-untyped-def]
    lm = face_landmarks(W, H, center=(0.5, 0.5), face_height=0.62, yaw_deg=yaw)
    for iris, outer, inner in ((g.R_IRIS, g.R_OUTER, g.R_INNER), (g.L_IRIS, g.L_OUTER, g.L_INNER)):
        width = abs(lm[inner, 0] - lm[outer, 0])
        centre = (lm[outer, :2] + lm[inner, :2]) / 2
        lm[iris, :2] = centre + np.array([iris_dx * width, iris_dy * width])
    return lm, FaceObservation(lm, {"eyeBlinkLeft": blink, "eyeBlinkRight": blink}, yaw, pitch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    shots = [
        ("gaze_straight", (0.0, 0.0, 0.0, 0.0, 0.0), "straight ahead"),
        ("gaze_eyes_left", (0.12, 0.0, 0.0, 0.0, 0.0), "eyes turned to the person's left"),
        ("gaze_head_turned", (0.0, 0.0, 25.0, 0.0, 0.0), "head turned 25 deg"),
        ("gaze_up", (0.0, -0.08, 0.0, 12.0, 0.0), "looking up"),
        ("gaze_blink", (0.0, 0.0, 0.0, 0.0, 0.9), "blink: vectors hidden"),
    ]
    for name, (dx, dy, yaw, pitch, blink), label in shots:
        lm, face = variant(dx, dy, yaw, pitch, blink)
        image = draw_face(lm)
        overlay = EyeOverlay()
        for i in range(15):
            overlay.update(face, int(1e9 + i * 33e6))
        painter = QPainter(image)
        overlay.paint(painter, ViewTransform.fit(W, H, W, H, False))
        painter.setPen(QColor(235, 235, 235))
        font = QFont()
        font.setPointSize(13)
        painter.setFont(font)
        estimate = overlay.estimate
        text = (
            f"{label} - estimate: yaw {estimate.gaze_yaw_deg:+.0f} deg, "
            f"pitch {estimate.gaze_pitch_deg:+.0f} deg, quality {estimate.quality:.2f}"
        )
        painter.drawText(QRectF(12, H - 36, W - 24, 28), Qt.AlignmentFlag.AlignLeft, text)
        painter.drawText(
            QRectF(12, 8, W - 24, 24),
            Qt.AlignmentFlag.AlignRight,
            "synthetic face, camera view (not mirrored)",
        )
        painter.end()
        path = args.out / f"{name}.png"
        image.save(str(path))
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
