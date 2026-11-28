"""Render the clown makeup stages on a synthetic face (development tool, Brief 008).

The face is drawn from MediaPipe's canonical face mesh (``scripts/canonical_face.py``): skin
with shading, hair, eyes, eyebrows, lips and stubble, so the renders show whether the makeup
keeps those visible. No real person's image is used. Output: one PNG per stage and opacity,
plus variants with an open mouth and a turned head, and a contact sheet.

Usage: python scripts/render_clown_stages.py --out screenshots/brief008/clown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_face import face_landmarks
from interactive_scrolling.visualization import clown as c
from interactive_scrolling.visualization.geometry import ViewTransform

W, H = 640, 720


def poly(points: np.ndarray, indices: tuple[int, ...]) -> QPainterPath:
    path = QPainterPath()
    for k, i in enumerate(indices):
        q = QPointF(points[i, 0] * W, points[i, 1] * H)
        path.moveTo(q) if k == 0 else path.lineTo(q)
    path.closeSubpath()
    return path


def draw_face(landmarks: np.ndarray) -> QImage:
    """A plain illustrated face on the landmarks (skin, hair, eyes, brows, lips, stubble)."""
    image = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(58, 62, 70))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    oval = poly(landmarks, c.FACE_OVAL)
    top = landmarks[c.FOREHEAD]
    # Hair: a dark cap above and beside the forehead.
    hair = QPainterPath()
    box = oval.boundingRect()
    hair.addEllipse(QRectF(box.x() - 18, box.y() - 50, box.width() + 36, box.height() * 0.62))
    p.fillPath(hair, QColor(62, 42, 30))
    skin = QRadialGradient(QPointF(top[0] * W, top[1] * H + box.height() * 0.45), box.width() * 0.7)
    skin.setColorAt(0.0, QColor(226, 184, 150))
    skin.setColorAt(1.0, QColor(186, 138, 106))
    p.fillPath(oval, QBrush(skin))
    # Skin texture: fine dots (to see whether makeup keeps texture visible).
    rng = np.random.default_rng(3)
    p.save()
    p.setClipPath(oval)
    for x, y in rng.uniform(0, 1, (2500, 2)):
        p.setPen(QColor(150, 100, 80, 60))
        p.drawPoint(QPointF(box.x() + x * box.width(), box.y() + y * box.height()))
    # Stubble on the lower face.
    chin_y = landmarks[c.CHIN, 1] * H
    for x, y in rng.uniform(0, 1, (1800, 2)):
        py = chin_y - y * box.height() * 0.32
        p.setPen(QColor(70, 50, 40, 110))
        p.drawPoint(QPointF(box.x() + x * box.width(), py))
    p.restore()
    for eye in (c.RIGHT_EYE, c.LEFT_EYE):
        p.fillPath(poly(landmarks, eye), QColor(245, 245, 240))
        centre = landmarks[list(eye), :2].mean(axis=0)
        p.setBrush(QColor(70, 90, 60))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(centre[0] * W, centre[1] * H), 7, 7)
        p.setBrush(QColor(15, 15, 15))
        p.drawEllipse(QPointF(centre[0] * W, centre[1] * H), 3, 3)
    for brow in (c.RIGHT_BROW, c.LEFT_BROW):
        p.fillPath(poly(landmarks, brow), QColor(70, 48, 34))
    p.fillPath(
        poly(landmarks, c.LIPS_OUTER).subtracted(poly(landmarks, c.LIPS_INNER)),
        QColor(176, 104, 98),
    )
    p.fillPath(poly(landmarks, c.LIPS_INNER), QColor(60, 25, 25))
    p.end()
    return image


def render(landmarks: np.ndarray, stage: int, opacity: float, label: str) -> QImage:
    image = draw_face(landmarks)
    effect = c.ClownEffect()
    effect.set_makeup_opacity(opacity)
    for i in range(60):
        effect.update(landmarks, int((1 + i / 30) * 1e9), stage)
    effect.jump_to_stage(stage)
    painter = QPainter(image)
    effect.paint(painter, ViewTransform.fit(W, H, W, H, False))
    painter.setPen(QPen(QColor(235, 235, 235)))
    font = QFont()
    font.setPointSize(13)
    painter.setFont(font)
    painter.drawText(QRectF(12, H - 36, W - 24, 28), Qt.AlignmentFlag.AlignLeft, label)
    painter.drawText(
        QRectF(12, 8, W - 24, 24), Qt.AlignmentFlag.AlignRight, "synthetic face (no person)"
    )
    painter.end()
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    neutral = face_landmarks(W, H, center=(0.5, 0.5), face_height=0.62)
    talking = face_landmarks(W, H, center=(0.5, 0.5), face_height=0.62, mouth_open=0.06)
    turned = face_landmarks(W, H, center=(0.5, 0.5), face_height=0.62, yaw_deg=25)
    shots = [
        ("clown_stage0", neutral, 0, 0.35, "Stage 0 - normal"),
        ("clown_stage1", neutral, 1, 0.35, "Stage 1 - red nose"),
        ("clown_stage2", neutral, 2, 0.35, "Stage 2 - nose and lips"),
        ("clown_stage3", neutral, 3, 0.35, "Stage 3 - full makeup (white 35 %, default)"),
        ("clown_stage3_white15", neutral, 3, 0.15, "Stage 3 - white 15 %"),
        ("clown_stage3_white55", neutral, 3, 0.55, "Stage 3 - white 55 %"),
        ("clown_stage3_white70", neutral, 3, 0.70, "Stage 3 - white 70 % (maximum)"),
        ("clown_stage3_talking", talking, 3, 0.35, "Stage 3 - mouth open"),
        ("clown_stage3_turned", turned, 3, 0.35, "Stage 3 - head turned 25 deg"),
    ]
    images = []
    for name, landmarks, stage, opacity, label in shots:
        image = render(landmarks, stage, opacity, label)
        path = args.out / f"{name}.png"
        image.save(str(path))
        images.append(image)
        print(path)
    sheet = QImage(W * 3, H * 3, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor(17, 18, 20))
    painter = QPainter(sheet)
    for k, image in enumerate(images):
        painter.drawImage((k % 3) * W, (k // 3) * H, image)
    painter.end()
    path = args.out / "clown_contact_sheet.png"
    sheet.save(str(path))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
