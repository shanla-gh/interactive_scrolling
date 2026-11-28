"""Eye and gaze overlay: eye outlines, iris centres and estimated gaze vectors (Brief 009).

Visualization only, comparable to the hand motion vectors. The vectors show the *estimate*
of ``wellbeing/gaze.py`` (head orientation plus iris offset); their strength follows the
estimate's quality and they are hidden when the quality is too low (blink, strong head turn,
small eyes) - the outlines then turn grey and a short note says so. Display smoothing of the
direction (``SMOOTH_TAU_S``) never feeds back into analytics. Nothing here can trigger an
action.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from interactive_scrolling.vision.face_tracker import FaceObservation
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.wellbeing.gaze import LEFT_EYE, RIGHT_EYE, GazeEstimate, estimate_gaze

SMOOTH_TAU_S = 0.12
LOST_AFTER_S = 0.3
EYE_COLOR = "#e8eaed"
GAZE_COLOR = "#5fd3e6"
LOW_COLOR = "#8a9099"


class EyeOverlay:
    def __init__(self) -> None:
        self.estimate: GazeEstimate | None = None
        self.landmarks: np.ndarray | None = None
        self._yaw: float | None = None
        self._pitch: float | None = None
        self._last_ns: int | None = None

    def reset(self) -> None:
        self.estimate = None
        self.landmarks = None
        self._yaw = self._pitch = None
        self._last_ns = None

    def update(self, face: FaceObservation | None, timestamp_ns: int) -> None:
        estimate = estimate_gaze(face)
        if estimate is None:
            if self._last_ns is not None and (timestamp_ns - self._last_ns) / 1e9 > LOST_AFTER_S:
                self.reset()
            return
        dt = 0.033 if self._last_ns is None else max(0.0, (timestamp_ns - self._last_ns) / 1e9)
        alpha = 1.0 - math.exp(-dt / SMOOTH_TAU_S)
        if self._yaw is None or self._pitch is None:
            self._yaw, self._pitch = estimate.gaze_yaw_deg, estimate.gaze_pitch_deg
        else:
            self._yaw += alpha * (estimate.gaze_yaw_deg - self._yaw)
            self._pitch += alpha * (estimate.gaze_pitch_deg - self._pitch)
        self.estimate = estimate
        self.landmarks = face.landmarks if face is not None else None
        self._last_ns = timestamp_ns

    @property
    def display_angles(self) -> tuple[float, float] | None:
        if self._yaw is None or self._pitch is None:
            return None
        return self._yaw, self._pitch

    def paint(self, painter: QPainter, transform: ViewTransform) -> None:
        estimate, lm = self.estimate, self.landmarks
        if estimate is None or lm is None:
            return

        def p(x: float, y: float) -> QPointF:
            return QPointF(*transform.map_normalized(x, y))

        usable = estimate.usable
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outline = QColor(EYE_COLOR if usable else LOW_COLOR)
        outline.setAlphaF(0.55)
        painter.setPen(QPen(outline, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for contour in (RIGHT_EYE, LEFT_EYE):
            path = QPainterPath()
            for k, i in enumerate(contour):
                q = p(float(lm[i, 0]), float(lm[i, 1]))
                path.moveTo(q) if k == 0 else path.lineTo(q)
            path.closeSubpath()
            painter.drawPath(path)
        a = p(*estimate.right.center)
        b = p(*estimate.left.center)
        eye_distance = math.hypot(a.x() - b.x(), a.y() - b.y())
        iris_color = QColor(GAZE_COLOR if usable else LOW_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(iris_color)
        for eye in (estimate.right, estimate.left):
            painter.drawEllipse(p(*eye.iris), 2.6, 2.6)
        angles = self.display_angles
        if usable and angles is not None and eye_distance > 4:
            strength = max(0.35, min(1.0, estimate.quality))
            for eye in (estimate.right, estimate.left):
                yaw, pitch = estimate.eye_angles(eye)
                self._arrow(
                    painter,
                    p(*eye.iris),
                    yaw,
                    pitch,
                    eye_distance * 0.7,
                    strength * 0.6,
                    1.4,
                    transform.mirrored,
                    head=False,
                )
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            self._arrow(
                painter,
                mid,
                angles[0],
                angles[1],
                eye_distance * 1.6,
                strength,
                2.4,
                transform.mirrored,
                head=True,
            )
        elif not usable:
            painter.setPen(QColor(LOW_COLOR))
            font = QFont()
            font.setPointSizeF(8.5)
            painter.setFont(font)
            painter.drawText(
                QRectF(min(a.x(), b.x()) - 40, max(a.y(), b.y()) + 10, eye_distance + 80, 16),
                Qt.AlignmentFlag.AlignCenter,
                "gaze: low tracking quality",
            )
        painter.restore()

    @staticmethod
    def _arrow(
        painter: QPainter,
        origin: QPointF,
        yaw_deg: float,
        pitch_deg: float,
        length: float,
        strength: float,
        width: float,
        mirrored: bool,
        head: bool,
    ) -> None:
        # Positive yaw is towards the person's left = image +x (unmirrored); up is image -y.
        dx = math.sin(math.radians(yaw_deg)) * (-1.0 if mirrored else 1.0)
        dy = -math.sin(math.radians(pitch_deg))
        end = QPointF(origin.x() + dx * length, origin.y() + dy * length)
        color = QColor(GAZE_COLOR)
        color.setAlphaF(strength)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(origin, end)
        if head and math.hypot(dx, dy) > 0.05:
            angle = math.atan2(end.y() - origin.y(), end.x() - origin.x())
            size = 7.0
            for side in (-0.5, 0.5):
                painter.drawLine(
                    end,
                    QPointF(
                        end.x() - size * math.cos(angle + side),
                        end.y() - size * math.sin(angle + side),
                    ),
                )
