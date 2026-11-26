"""Progressive Clown Transformation: procedural AR clown makeup drawn from face landmarks.

All artwork is original and generated here with QPainter gradients and paths; no image assets
are used. Every element is anchored to MediaPipe face-mesh landmarks of the current frame, so
it follows head movement, rotation and expressions (mouth opening, smiling, blinking):

* Stage 1 - a glossy red nose on the nose tip, sized from the face width;
* Stage 2 - adds rosy cheeks, red lips following the lip contour and white diamonds around the
  eyes (drawn from the eye contours, so they close with the eyes);
* Stage 3 - adds a soft white face base inside the face oval, a wide red smile from the mouth
  corners, arched black eyebrows, blue diamond outlines and colourful hair tufts at the temples.

Landmarks are smoothed over time (exponential, ``SMOOTH_TAU_S``) to avoid jitter, the effect
fades in and out, and it disappears when the face has not been tracked for ``LOST_AFTER_S``.
Nothing is captured or stored.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from interactive_scrolling.visualization.geometry import ViewTransform

SMOOTH_TAU_S = 0.06
FADE_S = 0.35
LOST_AFTER_S = 0.25

FACE_OVAL = (
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
    152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
)  # fmt: skip
LIPS_OUTER = (
    61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185,
)  # fmt: skip
LIPS_INNER = (
    78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191,
)  # fmt: skip
RIGHT_EYE = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)
LEFT_EYE = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466)
RIGHT_BROW = (70, 63, 105, 66, 107)
LEFT_BROW = (300, 293, 334, 296, 336)
NOSE_TIP = 1
FACE_RIGHT, FACE_LEFT = 234, 454
FOREHEAD, CHIN = 10, 152
RIGHT_CHEEK, LEFT_CHEEK = 205, 425
MOUTH_RIGHT, MOUTH_LEFT = 61, 291
RIGHT_TEMPLE, LEFT_TEMPLE = 127, 356
RIGHT_WIG = (103, 54, 21, 162, 127, 234)
LEFT_WIG = (332, 284, 251, 389, 356, 454)
"""Face-oval points from the forehead down to the ears on each side (curly wig)."""
NUM_FACE_LANDMARKS = 478


def _color(hex_value: str, alpha: float) -> QColor:
    color = QColor(hex_value)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


class ClownEffect:
    """Holds the smoothed face and draws the current stage."""

    def __init__(self) -> None:
        self._points: np.ndarray | None = None
        self._last_ns: int | None = None
        self._visible = 0.0
        self._stage_level = 0.0
        """Continuous stage (fades between stages instead of switching)."""

    def reset(self) -> None:
        self._points = None
        self._last_ns = None
        self._visible = 0.0

    def update(self, landmarks: np.ndarray | None, timestamp_ns: int, stage: int) -> None:
        """Feed the newest face (normalized landmarks) or ``None`` if no face is tracked."""
        dt = 0.033 if self._last_ns is None else max(0.0, (timestamp_ns - self._last_ns) / 1e9)
        if landmarks is not None and landmarks.shape[0] >= NUM_FACE_LANDMARKS - 10:
            points = landmarks[:, :2].astype(np.float64)
            if self._points is None or self._points.shape != points.shape:
                self._points = points
            else:
                alpha = 1.0 - math.exp(-dt / SMOOTH_TAU_S)
                self._points = self._points + alpha * (points - self._points)
            self._last_ns = timestamp_ns
            self._visible = min(1.0, self._visible + dt / FADE_S)
        elif self._last_ns is not None and (timestamp_ns - self._last_ns) / 1e9 > LOST_AFTER_S:
            self._visible = max(0.0, self._visible - dt / FADE_S)
            if self._visible == 0.0:
                self._points = None
        target = float(max(0, min(3, stage)))
        step = dt / 1.5  # one stage per 1.5 s when the stage changes
        if self._stage_level < target:
            self._stage_level = min(target, self._stage_level + step)
        else:
            self._stage_level = max(target, self._stage_level - step)

    @property
    def visible(self) -> bool:
        return self._points is not None and self._visible > 0.0

    def stage_weight(self, stage: int) -> float:
        """0..1 visibility of the elements introduced at ``stage``."""
        return max(0.0, min(1.0, self._stage_level - (stage - 1)))

    # ------------------------------------------------------------------ drawing

    def paint(self, painter: QPainter, transform: ViewTransform) -> None:
        if not self.visible or self._stage_level <= 0.0:
            return
        pts = self._points
        assert pts is not None

        def p(index: int) -> QPointF:
            x, y = pts[index]
            return QPointF(*transform.map_normalized(float(x), float(y)))

        def path(indices: tuple[int, ...], scale: float = 1.0) -> QPainterPath:
            points = [p(i) for i in indices]
            cx = sum(q.x() for q in points) / len(points)
            cy = sum(q.y() for q in points) / len(points)
            out = QPainterPath()
            for k, q in enumerate(points):
                scaled = QPointF(cx + (q.x() - cx) * scale, cy + (q.y() - cy) * scale)
                if k == 0:
                    out.moveTo(scaled)
                else:
                    out.lineTo(scaled)
            out.closeSubpath()
            return out

        a, b = p(FACE_RIGHT), p(FACE_LEFT)
        face_w = math.hypot(a.x() - b.x(), a.y() - b.y())
        if face_w < 8:
            return
        fade = self._visible
        w1, w2, w3 = (self.stage_weight(s) * fade for s in (1, 2, 3))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if w3 > 0:
            self._paint_base(painter, path(FACE_OVAL, 0.97), p(NOSE_TIP), face_w, w3)
            self._paint_wig(painter, [p(i) for i in RIGHT_WIG + LEFT_WIG], p(NOSE_TIP), face_w, w3)
        if w2 > 0:
            for eye, brow in ((RIGHT_EYE, RIGHT_BROW), (LEFT_EYE, LEFT_BROW)):
                self._paint_eye(painter, [p(i) for i in eye], [p(i) for i in brow], face_w, w2, w3)
            for cheek in (RIGHT_CHEEK, LEFT_CHEEK):
                self._paint_cheek(painter, p(cheek), face_w, w2)
            if w3 > 0:
                self._paint_smile(painter, p(MOUTH_RIGHT), p(MOUTH_LEFT), p(CHIN), face_w, w3)
            self._paint_lips(painter, path(LIPS_OUTER, 1.12), path(LIPS_INNER), w2)
            if w3 > 0:
                for brow in (RIGHT_BROW, LEFT_BROW):
                    self._paint_brow(painter, [p(i) for i in brow], face_w, w3)
        if w1 > 0:
            self._paint_nose(painter, p(NOSE_TIP), face_w, w1)
        painter.restore()

    @staticmethod
    def _paint_base(
        painter: QPainter, oval: QPainterPath, center: QPointF, face_w: float, w: float
    ) -> None:
        gradient = QRadialGradient(center, face_w * 0.75)
        gradient.setColorAt(0.0, _color("#fbf7f0", 0.78 * w))
        gradient.setColorAt(0.75, _color("#f4efe6", 0.62 * w))
        gradient.setColorAt(1.0, _color("#f4efe6", 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(oval)

    @staticmethod
    def _paint_wig(
        painter: QPainter, anchors: list[QPointF], center: QPointF, face_w: float, w: float
    ) -> None:
        """Curly orange clown hair: overlapping shaded curls just outside the upper face oval."""
        radius = face_w * 0.075
        painter.setPen(Qt.PenStyle.NoPen)
        for k, anchor in enumerate(anchors):
            dx, dy = anchor.x() - center.x(), anchor.y() - center.y()
            norm = math.hypot(dx, dy) or 1.0
            ux, uy = dx / norm, dy / norm
            for j, (out, size) in enumerate(((0.35, 1.0), (1.25, 1.15), (2.1, 0.9))):
                offset = radius * out
                wobble = radius * 0.45 * (1 if (k + j) % 2 else -1)
                c = QPointF(
                    anchor.x() + ux * offset - uy * wobble,
                    anchor.y() + uy * offset + ux * wobble,
                )
                r = radius * size
                curl = QRadialGradient(c - QPointF(r * 0.3, r * 0.35), r * 1.3)
                curl.setColorAt(0.0, _color("#ffd08a", w))
                curl.setColorAt(0.35, _color("#ff7a1a", w))
                curl.setColorAt(0.85, _color("#d9400a", w))
                curl.setColorAt(1.0, _color("#a12a05", 0.0))
                painter.setBrush(QBrush(curl))
                painter.drawEllipse(c, r, r)

    @staticmethod
    def _paint_eye(
        painter: QPainter,
        eye: list[QPointF],
        brow: list[QPointF],
        face_w: float,
        w2: float,
        w3: float,
    ) -> None:
        cx = sum(q.x() for q in eye) / len(eye)
        cy = sum(q.y() for q in eye) / len(eye)
        eye_w = max(q.x() for q in eye) - min(q.x() for q in eye)
        brow_y = sum(q.y() for q in brow) / len(brow)
        top = min(brow_y, cy - eye_w * 0.6) - eye_w * 0.15
        bottom = cy + (cy - top) * 1.05
        half_w = eye_w * 0.62
        diamond = QPainterPath()
        diamond.moveTo(QPointF(cx, top))
        diamond.quadTo(
            QPointF(cx + half_w * 0.35, cy - (cy - top) * 0.35), QPointF(cx + half_w, cy)
        )
        diamond.quadTo(QPointF(cx + half_w * 0.35, cy + (bottom - cy) * 0.35), QPointF(cx, bottom))
        diamond.quadTo(
            QPointF(cx - half_w * 0.35, cy + (bottom - cy) * 0.35), QPointF(cx - half_w, cy)
        )
        diamond.quadTo(QPointF(cx - half_w * 0.35, cy - (cy - top) * 0.35), QPointF(cx, top))
        # Face paint, not a sticker: a soft gradient that lets skin texture show through.
        paint = QRadialGradient(QPointF(cx, cy), (bottom - top) * 0.6)
        paint.setColorAt(0.0, _color("#ffffff", 0.62 * w2))
        paint.setColorAt(0.8, _color("#fbfbf8", 0.5 * w2))
        paint.setColorAt(1.0, _color("#f5f5f0", 0.3 * w2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(paint))
        painter.drawPath(diamond)
        if w3 > 0:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_color("#1f6bff", 0.85 * w3), max(1.5, face_w * 0.012)))
            painter.drawPath(diamond)

    @staticmethod
    def _paint_cheek(painter: QPainter, center: QPointF, face_w: float, w: float) -> None:
        radius = face_w * 0.13
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, _color("#ff2d55", 0.55 * w))
        gradient.setColorAt(1.0, _color("#ff2d55", 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, radius, radius)

    @staticmethod
    def _paint_lips(painter: QPainter, outer: QPainterPath, inner: QPainterPath, w: float) -> None:
        lips = outer.subtracted(inner)  # the open mouth stays visible
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color("#e0102f", 0.82 * w))
        painter.drawPath(lips)

    @staticmethod
    def _paint_smile(
        painter: QPainter,
        right: QPointF,
        left: QPointF,
        chin: QPointF,
        face_w: float,
        w: float,
    ) -> None:
        mid = QPointF((right.x() + left.x()) / 2, (right.y() + left.y()) / 2)
        down = QPointF((chin.x() - mid.x()) * 0.45, (chin.y() - mid.y()) * 0.45)
        ux, uy = left.x() - right.x(), left.y() - right.y()
        norm = math.hypot(ux, uy) or 1.0
        ux, uy = ux / norm, uy / norm
        ext = face_w * 0.12
        up = QPointF(-down.x() * 0.9, -down.y() * 0.9)
        r_end = QPointF(right.x() - ux * ext + up.x(), right.y() - uy * ext + up.y())
        l_end = QPointF(left.x() + ux * ext + up.x(), left.y() + uy * ext + up.y())
        smile = QPainterPath(r_end)
        smile.quadTo(QPointF(mid.x() + down.x() * 1.6, mid.y() + down.y() * 1.6), l_end)
        smile.quadTo(QPointF(mid.x() + down.x() * 0.6, mid.y() + down.y() * 0.6), r_end)
        painter.setPen(QPen(_color("#c4001f", 0.85 * w), max(1.0, face_w * 0.008)))
        painter.setBrush(_color("#ff1f3d", 0.7 * w))
        painter.drawPath(smile)

    @staticmethod
    def _paint_brow(painter: QPainter, brow: list[QPointF], face_w: float, w: float) -> None:
        lift = face_w * 0.05
        arc = QPainterPath(QPointF(brow[0].x(), brow[0].y() - lift))
        middle = brow[len(brow) // 2]
        arc.quadTo(QPointF(middle.x(), middle.y() - lift * 3.0), brow[-1] - QPointF(0, lift))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(_color("#151515", 0.9 * w), max(2.0, face_w * 0.03))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(arc)

    @staticmethod
    def _paint_nose(painter: QPainter, tip: QPointF, face_w: float, w: float) -> None:
        radius = face_w * 0.095 * (0.6 + 0.4 * w)
        shadow = QRadialGradient(tip + QPointF(radius * 0.15, radius * 0.35), radius * 1.25)
        shadow.setColorAt(0.0, _color("#000000", 0.28 * w))
        shadow.setColorAt(1.0, _color("#000000", 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(tip + QPointF(radius * 0.15, radius * 0.35), radius * 1.2, radius * 1.2)
        ball = QRadialGradient(tip - QPointF(radius * 0.35, radius * 0.4), radius * 1.35)
        ball.setColorAt(0.0, _color("#ff9a9a", w))
        ball.setColorAt(0.18, _color("#ff2a2a", w))
        ball.setColorAt(0.75, _color("#c40012", w))
        ball.setColorAt(1.0, _color("#7a0008", w))
        painter.setBrush(QBrush(ball))
        painter.drawEllipse(tip, radius, radius)
        highlight = QRadialGradient(tip - QPointF(radius * 0.4, radius * 0.45), radius * 0.35)
        highlight.setColorAt(0.0, _color("#ffffff", 0.85 * w))
        highlight.setColorAt(1.0, _color("#ffffff", 0.0))
        painter.setBrush(QBrush(highlight))
        painter.drawEllipse(tip - QPointF(radius * 0.4, radius * 0.45), radius * 0.35, radius * 0.3)


def clown_stage(session_s: float, thresholds_min: tuple[float, float, float]) -> int:
    """Stage 0-3 for the current scrolling session's active time."""
    minutes = session_s / 60
    return sum(1 for limit in thresholds_min if minutes >= limit)
