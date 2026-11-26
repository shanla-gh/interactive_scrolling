"""The live webcam view with the computer-vision overlay and HUD."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from interactive_scrolling.config.settings import OverlaySettings
from interactive_scrolling.core.pipeline import ProcessedFrame
from interactive_scrolling.core.timing import RateMeter, now_ns
from interactive_scrolling.ui.theme import mono_font
from interactive_scrolling.visualization import palette
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.visualization.overlay import OverlayRenderer


class VideoView(QWidget):
    """Draws the latest processed frame, letterboxed, with overlays aligned to it."""

    def __init__(self, overlay: OverlaySettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("videoView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.overlay = overlay
        self.mirrored = True
        self.renderer = OverlayRenderer()
        self.display_rate = RateMeter(1.0)
        self._frame: ProcessedFrame | None = None
        self._image: QImage | None = None
        self._placeholder = "Camera is off. Press Start camera to begin."
        self._status_text = ""
        self._banner: tuple[str, str, int] | None = None  # text, colour, shown-at (ns)
        self._banner_font = mono_font(15, bold=True)
        self._hud_font = mono_font(8.5, bold=True)
        self._placeholder_font = mono_font(10.5)

    # ------------------------------------------------------------------ state

    @property
    def frame(self) -> ProcessedFrame | None:
        return self._frame

    def set_frame(self, frame: ProcessedFrame) -> None:
        image = frame.image_rgb
        height, width = image.shape[:2]
        # QImage references the numpy buffer; keeping ``frame`` alive keeps the buffer valid.
        self._image = QImage(
            image.data, width, height, image.strides[0], QImage.Format.Format_RGB888
        )
        self._frame = frame
        self.display_rate.tick()
        self.update()

    def clear(self, message: str) -> None:
        """Remove the current frame and overlay and show ``message`` instead."""
        self._frame = None
        self._image = None
        self._placeholder = message
        self.display_rate.reset()
        self.update()

    BANNER_S = 1.3

    def show_gesture(self, text: str, color: str = palette.ACCENT_GREEN) -> None:
        """Briefly show a confirmed gesture at the top of the image (never over the hand)."""
        self._banner = (text, color, now_ns())
        self.update()

    def set_status_text(self, text: str) -> None:
        self._status_text = text
        self.update()

    def set_mirrored(self, mirrored: bool) -> None:
        self.mirrored = mirrored
        self.update()

    def current_transform(self) -> ViewTransform | None:
        if self._frame is None:
            return None
        h, w = self._frame.image_rgb.shape[:2]
        return ViewTransform.fit(w, h, self.width(), self.height(), self.mirrored)

    def sizeHint(self) -> QSize:
        return QSize(960, 540)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(palette.BACKGROUND))
        transform = self.current_transform()
        if transform is None or self._image is None or self._frame is None:
            self._paint_placeholder(painter)
        else:
            self._paint_frame(painter, transform, self._image)
            self.renderer.paint(
                painter, transform, self._frame.tracking, self._frame.motion, self.overlay
            )
            self._paint_hud(painter, transform, self._frame)
            self._paint_gesture_feedback(painter, transform, self._frame)
        painter.end()

    def _paint_frame(self, painter: QPainter, t: ViewTransform, image: QImage) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if t.mirrored:
            painter.translate(t.x + t.width, t.y)
            painter.scale(-1.0, 1.0)
            painter.drawImage(QRectF(0.0, 0.0, t.width, t.height), image)
        else:
            painter.drawImage(QRectF(t.x, t.y, t.width, t.height), image)
        painter.restore()

    def _paint_placeholder(self, painter: QPainter) -> None:
        painter.save()
        grid = QColor(palette.BORDER)
        grid.setAlpha(90)
        painter.setPen(QPen(grid, 1.0))
        step = 32
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)
        self._paint_brackets(
            painter, QRectF(self.rect()).adjusted(16, 16, -16, -16), palette.TEXT_DIM
        )
        painter.setFont(self._placeholder_font)
        painter.setPen(QColor(palette.TEXT_MUTED))
        painter.drawText(
            QRectF(self.rect()).adjusted(40, 40, -40, -40),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self._placeholder,
        )
        painter.restore()

    def _paint_brackets(self, painter: QPainter, rect: QRectF, color: str) -> None:
        length = min(28.0, rect.width() / 6, rect.height() / 6)
        painter.setPen(QPen(QColor(color), 2.0))
        for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1),
        ):
            painter.drawLine(QPointF(cx, cy), QPointF(cx + dx * length, cy))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * length))

    def _paint_gesture_feedback(
        self, painter: QPainter, t: ViewTransform, frame: ProcessedFrame
    ) -> None:
        painter.save()
        rect = QRectF(t.x, t.y, t.width, t.height)
        gestures = frame.gestures
        if gestures is not None and gestures.candidates:
            best = max(gestures.candidates, key=lambda c: c.progress)
            width = min(260.0, rect.width() * 0.4)
            bar = QRectF(rect.center().x() - width / 2, rect.bottom() - 30, width, 6)
            painter.setPen(Qt.PenStyle.NoPen)
            track = QColor(palette.BACKGROUND)
            track.setAlpha(180)
            painter.setBrush(track)
            painter.drawRoundedRect(bar.adjusted(-2, -2, 2, 2), 4, 4)
            painter.setBrush(QColor(palette.ACCENT_AMBER))
            painter.drawRoundedRect(QRectF(bar.x(), bar.y(), width * best.progress, 6), 3, 3)
            painter.setFont(self._hud_font)
            painter.setPen(QColor(palette.ACCENT_AMBER))
            painter.drawText(
                QRectF(bar.x(), bar.y() - 22, width, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{best.gesture.label}  {best.progress:.0%}",
            )
        if self._banner is not None:
            text, color, shown = self._banner
            age = (now_ns() - shown) / 1e9
            if age > self.BANNER_S:
                self._banner = None
            else:
                alpha = 1.0 if age < 0.8 else max(0.0, 1 - (age - 0.8) / (self.BANNER_S - 0.8))
                painter.setFont(self._banner_font)
                metrics = painter.fontMetrics()
                box = QRectF(0, 0, metrics.horizontalAdvance(text) + 48, metrics.height() + 18)
                box.moveCenter(QPointF(rect.center().x(), rect.top() + 26 + box.height() / 2))
                background = QColor(palette.BACKGROUND)
                background.setAlphaF(0.82 * alpha)
                accent = QColor(color)
                accent.setAlphaF(alpha)
                painter.setPen(QPen(accent, 1.5))
                painter.setBrush(background)
                painter.drawRoundedRect(box, 8, 8)
                painter.setPen(accent)
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
                self.update()  # keep fading even if frames stop
        painter.restore()

    def _paint_hud(self, painter: QPainter, t: ViewTransform, frame: ProcessedFrame) -> None:
        painter.save()
        rect = QRectF(t.x, t.y, t.width, t.height)
        self._paint_brackets(painter, rect.adjusted(8, 8, -8, -8), palette.ACCENT_GREEN)
        painter.setFont(self._hud_font)
        tracking = frame.tracking
        hands = tracking.hand_count
        if hands:
            status = f"TRACKING  {hands} HAND{'S' if hands > 1 else ''}"
            color = palette.ACCENT_GREEN
        else:
            status = "NO HAND DETECTED"
            color = palette.TEXT_MUTED
        if self._status_text:
            status, color = self._status_text, palette.ACCENT_AMBER
        source = (
            f"{tracking.image_width}x{tracking.image_height}{'  MIRRORED' if t.mirrored else ''}"
        )
        self._paint_chip(painter, QPointF(rect.left() + 20, rect.top() + 20), status, color)
        self._paint_chip(
            painter,
            QPointF(rect.left() + 20, rect.bottom() - 20),
            f"LIVE  {source}",
            palette.TEXT_MUTED,
            anchor_bottom=True,
        )
        painter.restore()

    def _paint_chip(
        self,
        painter: QPainter,
        origin: QPointF,
        text: str,
        color: str,
        anchor_bottom: bool = False,
    ) -> None:
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 26
        height = metrics.height() + 8
        top = origin.y() - height if anchor_bottom else origin.y()
        box = QRectF(origin.x(), top, width, height)
        background = QColor(palette.BACKGROUND)
        background.setAlpha(190)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(box, 4, 4)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(box.left() + 10, box.center().y()), 3.0, 3.0)
        painter.setPen(QColor(color))
        painter.drawText(box.adjusted(18, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
