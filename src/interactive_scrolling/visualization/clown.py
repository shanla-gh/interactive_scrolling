"""Progressive Clown Transformation: subtle clown makeup drawn from face landmarks.

Redesigned in Brief 008 as makeup on the person's own face rather than a mask. Every element is
anchored to the MediaPipe face-mesh landmarks of the current frame and blended with the camera
image, so the eyes, eyebrows, facial hair, skin texture, expressions and the person's own hair
stay visible:

* Stage 1 - a red clown nose on the nose tip, sized from the face width;
* Stage 2 - adds red lip makeup that follows the lip contour (multiplied onto the lips, so their
  texture shows through; an open mouth stays open);
* Stage 3 - adds light, semi-transparent white makeup on the face with feathered edges, leaving
  the eyes, eyebrows and lips uncovered. Its strength is adjustable (``makeup_opacity``).

No hair, wig, eye shapes or opaque face mask are drawn. All artwork is procedural (QPainter);
no image assets are used. Landmarks are smoothed over time for display only
(``SMOOTH_TAU_S``), the effect fades in and out, and it disappears when the face has not been
tracked for ``LOST_AFTER_S``. Nothing is captured or stored.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QRadialGradient

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
RIGHT_BROW = (70, 63, 105, 66, 107, 55, 65, 52, 53, 46)
LEFT_BROW = (300, 293, 334, 296, 336, 285, 295, 282, 283, 276)
"""Upper and lower eyebrow contours (kept free of white makeup)."""
NOSE_TIP = 1
FACE_RIGHT, FACE_LEFT = 234, 454
FOREHEAD, CHIN = 10, 152
NUM_FACE_LANDMARKS = 478

DEFAULT_MAKEUP_OPACITY = 0.35
MIN_MAKEUP_OPACITY = 0.1
MAX_MAKEUP_OPACITY = 0.7
"""The white makeup never covers the face completely (the face must stay recognizable)."""
FEATHER_LAYERS = 10
FEATHER_DEPTH = 0.22
"""The white base fades out over the outer 22 % of the face outline."""


def _color(hex_value: str, alpha: float) -> QColor:
    color = QColor(hex_value)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def _path(points: list[QPointF], scale: float = 1.0) -> QPainterPath:
    """Closed polygon through ``points``, scaled about their centroid."""
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


class ClownEffect:
    """Holds the smoothed face and draws the current stage."""

    def __init__(self) -> None:
        self._points: np.ndarray | None = None
        self._last_ns: int | None = None
        self._visible = 0.0
        self._stage_level = 0.0
        """Continuous stage (fades between stages instead of switching)."""
        self.makeup_opacity = DEFAULT_MAKEUP_OPACITY
        """Strength of the stage 3 white makeup at the centre of the face."""

    def set_makeup_opacity(self, value: float) -> None:
        self.makeup_opacity = max(MIN_MAKEUP_OPACITY, min(MAX_MAKEUP_OPACITY, float(value)))

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

    def jump_to_stage(self, stage: int) -> None:
        """Show ``stage`` at once (previews; a session stage still fades in)."""
        self._stage_level = float(max(0, min(3, stage)))

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

        a, b = p(FACE_RIGHT), p(FACE_LEFT)
        face_w = math.hypot(a.x() - b.x(), a.y() - b.y())
        if face_w < 8:
            return
        fade = self._visible
        w1, w2, w3 = (self.stage_weight(s) * fade for s in (1, 2, 3))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if w3 > 0:
            features = [
                ([p(i) for i in RIGHT_EYE], 1.0),
                ([p(i) for i in LEFT_EYE], 1.0),
                ([p(i) for i in RIGHT_BROW], 0.8),
                ([p(i) for i in LEFT_BROW], 0.8),
                ([p(i) for i in LIPS_OUTER], 0.35),
            ]
            self._paint_base(painter, [p(i) for i in FACE_OVAL], features, w3 * self.makeup_opacity)
        if w2 > 0:
            outer = _path([p(i) for i in LIPS_OUTER])
            inner = _path([p(i) for i in LIPS_INNER])
            self._paint_lips(painter, outer, inner, w2)
        if w1 > 0:
            self._paint_nose(painter, p(NOSE_TIP), face_w, w1)
        painter.restore()

    @staticmethod
    def _paint_base(
        painter: QPainter,
        oval: list[QPointF],
        features: list[tuple[list[QPointF], float]],
        strength: float,
    ) -> None:
        """Translucent white base, feathered both towards the face outline and towards the
        eyes, eyebrows and lips: each layer is a slightly smaller face region with slightly
        smaller cut-outs, so the makeup fades out instead of ending in a hard edge."""
        if strength <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        brush = _color("#fbfaf7", strength / FEATHER_LAYERS)
        for k in range(FEATHER_LAYERS):
            inner = k / (FEATHER_LAYERS - 1)  # 0 = outermost layer, 1 = innermost
            region = _path(oval, 1.0 - inner * FEATHER_DEPTH)
            for points, margin in features:
                # Outer layers keep a wide margin around a feature, inner layers a tight one.
                scale = 1.08 + margin * (1.0 - inner) * 0.9
                region = region.subtracted(_path(points, scale))
            painter.setBrush(brush)
            painter.drawPath(region)

    @staticmethod
    def _paint_lips(painter: QPainter, outer: QPainterPath, inner: QPainterPath, w: float) -> None:
        lips = outer.subtracted(inner)  # an open mouth stays open
        painter.setPen(Qt.PenStyle.NoPen)
        painter.save()
        # Multiply keeps the lips' own light and texture; a thin normal layer adds colour to
        # very dark or very light lips.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        painter.setBrush(_color("#e3394a", 0.85 * w))
        painter.drawPath(lips)
        painter.restore()
        painter.setBrush(_color("#c8102e", 0.22 * w))
        painter.drawPath(lips)

    @staticmethod
    def _paint_nose(painter: QPainter, tip: QPointF, face_w: float, w: float) -> None:
        radius = face_w * 0.085 * (0.6 + 0.4 * w)
        offset = QPointF(radius * 0.1, radius * 0.3)
        shadow = QRadialGradient(tip + offset, radius * 1.2)
        shadow.setColorAt(0.0, _color("#000000", 0.22 * w))
        shadow.setColorAt(1.0, _color("#000000", 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(tip + offset, radius * 1.15, radius * 1.15)
        ball = QRadialGradient(tip - QPointF(radius * 0.3, radius * 0.35), radius * 1.3)
        ball.setColorAt(0.0, _color("#ff8f8f", w))
        ball.setColorAt(0.2, _color("#f0262b", w))
        ball.setColorAt(0.8, _color("#b5000f", w))
        ball.setColorAt(1.0, _color("#7a0008", 0.9 * w))
        painter.setBrush(QBrush(ball))
        painter.drawEllipse(tip, radius, radius)
        spot = tip - QPointF(radius * 0.38, radius * 0.42)
        highlight = QRadialGradient(spot, radius * 0.32)
        highlight.setColorAt(0.0, _color("#ffffff", 0.7 * w))
        highlight.setColorAt(1.0, _color("#ffffff", 0.0))
        painter.setBrush(QBrush(highlight))
        painter.drawEllipse(spot, radius * 0.3, radius * 0.26)


def clown_stage(session_s: float, thresholds_min: tuple[float, float, float]) -> int:
    """Stage 0-3 for the current scrolling session's active time."""
    minutes = session_s / 60
    return sum(1 for limit in thresholds_min if minutes >= limit)
