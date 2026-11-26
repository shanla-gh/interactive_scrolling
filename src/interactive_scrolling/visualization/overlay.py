"""QPainter renderer for hand skeletons, landmarks and motion vectors.

Everything drawn here is derived from a :class:`TrackingResult` and the matching
:class:`MotionFrame`; nothing is animated independently of measured data. Positions are
mapped through a :class:`ViewTransform`, the same transform used to draw the video frame.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF

from interactive_scrolling.config.settings import OverlaySettings
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.motion.analyzer import HandMotion, MotionFrame, PointMotion, TrailPoint
from interactive_scrolling.vision.landmarks import (
    FINGERTIPS,
    HAND_CONNECTIONS,
    HandObservation,
    TrackingResult,
)
from interactive_scrolling.visualization import palette
from interactive_scrolling.visualization.geometry import ViewTransform

VECTOR_LOOKAHEAD_S = 0.15
"""Arrows show where the point would be after this time at its measured velocity."""

_MAX_ARROW_FRACTION = 0.35
_BBOX_MARGIN = 0.08


def _color(hex_value: str, alpha: int = 255) -> QColor:
    color = QColor(hex_value)
    color.setAlpha(max(0, min(255, alpha)))
    return color


class OverlayRenderer:
    """Stateless painter for the computer-vision overlay."""

    def __init__(self, trail_duration_s: float = 0.7) -> None:
        self.trail_duration_s = trail_duration_s
        self._label_font = QFont("Cascadia Mono")
        self._label_font.setStyleHint(QFont.StyleHint.Monospace)
        self._label_font.setPointSizeF(8.5)
        self._label_font.setBold(True)

    def paint(
        self,
        painter: QPainter,
        transform: ViewTransform,
        tracking: TrackingResult,
        motion: MotionFrame | None,
        options: OverlaySettings,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for index, hand in enumerate(tracking.hands):
            hand_motion = motion.for_observation(index) if motion else None
            self._paint_hand(painter, transform, hand, hand_motion, options, tracking.timestamp_ns)
        painter.restore()

    # ------------------------------------------------------------------ per hand

    def _paint_hand(
        self,
        painter: QPainter,
        transform: ViewTransform,
        hand: HandObservation,
        motion: HandMotion | None,
        options: OverlaySettings,
        timestamp_ns: int,
    ) -> None:
        color = palette.hand_color(hand.handedness)
        points = [
            QPointF(*transform.map_normalized(float(x), float(y))) for x, y, _ in hand.landmarks
        ]

        if motion is not None and options.show_palm_trail:
            self._paint_trail(painter, transform, motion.palm_trail, color, timestamp_ns, 2.0, 110)
        if motion is not None and options.show_fingertip_trail:
            self._paint_trail(
                painter, transform, motion.fingertip_trail, color, timestamp_ns, 3.0, 220
            )
        if options.show_bounding_box:
            self._paint_bounding_box(painter, transform, hand, color)
        if options.show_skeleton:
            self._paint_skeleton(painter, points, color)
        if options.show_landmarks:
            self._paint_landmarks(painter, points, color)
        if options.show_labels:
            self._paint_label(painter, transform, hand, color)
        if motion is not None and options.show_vectors:
            tip = points[8]
            self._paint_vector(painter, transform, tip, motion.fingertip, color, label=True)
            palm = QPointF(*transform.map_normalized(*hand.palm_center()))
            self._paint_vector(
                painter, transform, palm, motion.palm, palette.ACCENT_AMBER, label=False
            )

    def _paint_skeleton(self, painter: QPainter, points: Sequence[QPointF], color: str) -> None:
        glow = QPen(_color(color, 45), 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        core = QPen(_color(color, 230), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        for pen in (glow, core):
            painter.setPen(pen)
            for a, b in HAND_CONNECTIONS:
                painter.drawLine(points[a], points[b])

    def _paint_landmarks(self, painter: QPainter, points: Sequence[QPointF], color: str) -> None:
        painter.setPen(QPen(_color(palette.BACKGROUND, 220), 1.2))
        painter.setBrush(_color(color))
        for i, point in enumerate(points):
            radius = 4.6 if i in FINGERTIPS else 3.2
            painter.drawEllipse(point, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_color(color, 150), 1.2))
        for i in FINGERTIPS:
            painter.drawEllipse(points[i], 8.0, 8.0)

    def _hand_rect(self, transform: ViewTransform, hand: HandObservation) -> QRectF:
        x0, y0, x1, y1 = hand.bounding_box()
        ax, ay = transform.map_normalized(x0, y0)
        bx, by = transform.map_normalized(x1, y1)
        rect = QRectF(QPointF(min(ax, bx), min(ay, by)), QPointF(max(ax, bx), max(ay, by)))
        margin = _BBOX_MARGIN * max(rect.width(), rect.height())
        return rect.adjusted(-margin, -margin, margin, margin)

    def _paint_bounding_box(
        self, painter: QPainter, transform: ViewTransform, hand: HandObservation, color: str
    ) -> None:
        rect = self._hand_rect(transform, hand)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_color(color, 60), 1.0, Qt.PenStyle.DashLine))
        painter.drawRect(rect)
        corner = 0.18 * min(rect.width(), rect.height())
        painter.setPen(QPen(_color(color, 200), 2.0))
        path = QPainterPath()
        for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1),
        ):
            path.moveTo(cx + dx * corner, cy)
            path.lineTo(cx, cy)
            path.lineTo(cx, cy + dy * corner)
        painter.drawPath(path)

    def _paint_label(
        self, painter: QPainter, transform: ViewTransform, hand: HandObservation, color: str
    ) -> None:
        rect = self._hand_rect(transform, hand)
        text = hand.handedness.value.upper()
        if hand.handedness_score is not None:
            text += f"  {hand.handedness_score:.2f}"
        painter.setFont(self._label_font)
        metrics = QFontMetricsF(self._label_font)
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 14, metrics.height() + 6)
        box.moveBottomLeft(QPointF(rect.left(), rect.top() - 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color(palette.BACKGROUND, 200))
        painter.drawRoundedRect(box, 4, 4)
        painter.setBrush(_color(color))
        painter.drawRect(QRectF(box.left(), box.top(), 3, box.height()))
        painter.setPen(_color(color))
        painter.drawText(box.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_trail(
        self,
        painter: QPainter,
        transform: ViewTransform,
        trail: Sequence[TrailPoint],
        color: str,
        timestamp_ns: int,
        width: float,
        max_alpha: int,
    ) -> None:
        if len(trail) < 2:
            return
        duration_ns = self.trail_duration_s * NS_PER_S
        previous = QPointF(*transform.map_source_px(trail[0].x, trail[0].y))
        for point in trail[1:]:
            current = QPointF(*transform.map_source_px(point.x, point.y))
            freshness = 1.0 - min(1.0, (timestamp_ns - point.timestamp_ns) / duration_ns)
            pen = QPen(
                _color(color, int(max_alpha * freshness)),
                max(0.8, width * (0.35 + 0.65 * freshness)),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            painter.setPen(pen)
            painter.drawLine(previous, current)
            previous = current

    def _paint_vector(
        self,
        painter: QPainter,
        transform: ViewTransform,
        origin: QPointF,
        point_motion: PointMotion,
        color: str,
        label: bool,
    ) -> None:
        if not point_motion.is_moving:
            return
        vx, vy = point_motion.velocity_px_s
        dx, dy = transform.map_vector_px(vx * VECTOR_LOOKAHEAD_S, vy * VECTOR_LOOKAHEAD_S)
        length = math.hypot(dx, dy)
        max_length = _MAX_ARROW_FRACTION * min(transform.width, transform.height)
        if length < 2.0:
            return
        if length > max_length:
            dx, dy = dx * max_length / length, dy * max_length / length
            length = max_length
        tip = QPointF(origin.x() + dx, origin.y() + dy)
        painter.setPen(QPen(_color(color, 70), 7.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(origin, tip)
        painter.setPen(QPen(_color(color), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(origin, tip)
        ux, uy = dx / length, dy / length
        head = min(14.0, 0.4 * length + 6.0)
        left = QPointF(tip.x() - head * (ux - 0.5 * uy), tip.y() - head * (uy + 0.5 * ux))
        right = QPointF(tip.x() - head * (ux + 0.5 * uy), tip.y() - head * (uy - 0.5 * ux))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color(color))
        painter.drawPolygon(QPolygonF([tip, left, right]))
        if label:
            direction = point_motion.display_direction(transform.mirrored)
            text = f"{direction.arrow} {point_motion.speed_palms_s:.1f} palms/s"
            painter.setFont(self._label_font)
            painter.setPen(_color(color))
            painter.drawText(QPointF(tip.x() + 8 * ux + 6, tip.y() + 8 * uy + 4), text)
