"""Broadcast Mode: a compact, always-on-top, frameless camera overlay for OBS.

The overlay is a *view* of the shared runtime: it receives the frames the main window already
gets from the one pipeline and never owns a camera, model or dispatcher. It does not take the
keyboard focus (``WindowDoesNotAcceptFocus``, ``WA_ShowWithoutActivating`` and, on Windows,
``WS_EX_NOACTIVATE``), so clicking or dragging it leaves the browser the active window.

Interaction: drag anywhere to move, drag the bottom-right corner to resize (16:9 kept),
right-click for layers, transparency, opacity, position and modes, double-click for Developer
Mode. A saved position that is no longer on any screen (a monitor was removed, the scaling
changed) is replaced by the bottom-right corner of the primary screen.

Display smoothing: the drawn skeleton is smoothed for presentation only
(``visualization.smoothing``); recognition and the Developer view use the raw landmarks.

Transparent background: when enabled the camera copy drawn here gets a person mask as its alpha
channel (see ``visualization.compositing``). If no fresh mask is available the camera image is
hidden and a notice is shown instead, so the room behind the user is never revealed by surprise.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QContextMenuEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from interactive_scrolling.actions.types import (
    ActionRecord,
    ActionStatus,
    ActionType,
    ControlMode,
)
from interactive_scrolling.config.settings import (
    AppearanceSettings,
    CreatorSettings,
    OverlayCorner,
    OverlaySettings,
)
from interactive_scrolling.core.auxiliary import AuxiliaryWorker
from interactive_scrolling.core.pipeline import ProcessedFrame
from interactive_scrolling.core.timing import now_ns
from interactive_scrolling.gestures.explain import event_label
from interactive_scrolling.ui.theme import mono_font
from interactive_scrolling.vision.compositing import MaskCompositor
from interactive_scrolling.visualization import palette
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.visualization.overlay import OverlayRenderer
from interactive_scrolling.visualization.smoothing import LandmarkSmoother

ExtraPainter = Callable[[QPainter, ViewTransform, ProcessedFrame], None]
CONTROL_CHIP = {
    ControlMode.TRACKING_ONLY: ("GESTURES OFF", palette.TEXT_MUTED),
    ControlMode.GESTURE_TEST: ("GESTURE TEST", palette.ACCENT_CYAN),
    ControlMode.LIVE_CONTROL: ("\u25cf LIVE CONTROL", palette.ACCENT_RED),
}
MIN_VISIBLE_SHARE = 0.25
"""A saved position is used only if at least this share of the overlay is on some screen."""

GRIP_PX = 18
FEEDBACK_S = 2.5
OUTCOME_TEXT = {
    ActionStatus.SUCCEEDED: ("Success", palette.ACCENT_GREEN),
    ActionStatus.NO_CHANGE: ("No change", palette.ACCENT_CYAN),
    ActionStatus.REJECTED: ("Rejected", palette.ACCENT_AMBER),
    ActionStatus.FAILED: ("Failed", palette.ACCENT_RED),
    ActionStatus.UNKNOWN: ("Unknown outcome", palette.ACCENT_RED),
    ActionStatus.NOT_EXECUTED: ("Not executed", palette.TEXT_MUTED),
}


def _no_activate(widget: QWidget) -> None:
    """Windows: mark the window WS_EX_NOACTIVATE so clicks never steal the focus."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        gwl_exstyle = -20
        ws_ex_noactivate = 0x08000000
        style = user32.GetWindowLongPtrW(hwnd, gwl_exstyle)
        user32.SetWindowLongPtrW(hwnd, gwl_exstyle, style | ws_ex_noactivate)
    except (AttributeError, OSError):
        pass


class CreatorOverlay(QWidget):
    developer_requested = Signal()
    background_requested = Signal()
    quit_requested = Signal()
    settings_changed = Signal(object)

    def __init__(
        self,
        settings: CreatorSettings,
        appearance: AppearanceSettings,
        segmenter: AuxiliaryWorker[np.ndarray] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Interactive Scrolling - Broadcast Mode")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(160, 90)
        self.settings = settings
        self.renderer = OverlayRenderer()
        self.renderer.set_style(appearance)
        self.segmenter = segmenter
        self.compositor = MaskCompositor()
        self.smoother = LandmarkSmoother()
        self._drawn_tracking = None
        self.control_mode = ControlMode.TRACKING_ONLY
        self.extra_painters: list[ExtraPainter] = []
        self.mirrored = True
        self.counters_text: str = ""
        self._frame: ProcessedFrame | None = None
        self._image: QImage | None = None
        self._image_buffer: np.ndarray | None = None
        self._last: tuple[str, ActionStatus | None, int] | None = None
        self._drag: QPoint | None = None
        self._resizing = False
        self._font = mono_font(9, bold=True)
        self._big_font = mono_font(13, bold=True)
        self.transparent_state = "off"
        """off / active / unavailable: what the transparent background is actually doing."""
        self.apply_settings(settings, reposition=True)

    # ------------------------------------------------------------------ settings

    def apply_settings(self, settings: CreatorSettings, reposition: bool = False) -> None:
        self.settings = settings
        self.resize(settings.width, settings.height)
        self.setWindowOpacity(settings.opacity)
        if self.segmenter is not None:
            self.segmenter.set_enabled(settings.transparent_background and self.isVisible())
        if reposition:
            self._place()
        self.update()

    def set_appearance(self, appearance: AppearanceSettings) -> None:
        self.renderer.set_style(appearance)
        self.update()

    def set_control_mode(self, mode: ControlMode) -> None:
        self.control_mode = mode
        self.update()

    @staticmethod
    def visible_share(rect: QRect) -> float:
        """Share of ``rect`` that lies on any screen's available area."""
        area = max(1, rect.width() * rect.height())
        covered = 0
        for screen in QApplication.screens():
            part = rect.intersected(screen.availableGeometry())
            if not part.isEmpty():
                covered += part.width() * part.height()
        return min(1.0, covered / area)

    def _place(self) -> None:
        s = self.settings
        if s.corner is OverlayCorner.CUSTOM and s.x is not None and s.y is not None:
            if self.visible_share(QRect(s.x, s.y, s.width, s.height)) >= MIN_VISIBLE_SHARE:
                self.move(s.x, s.y)
                return
            # Off-screen (monitor removed, scaling changed): back to a visible corner.
            self.settings = replace(s, corner=OverlayCorner.BOTTOM_RIGHT, x=None, y=None)
            s = self.settings
        screen = self.screen() if self.isVisible() else None
        screen = screen or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 24
        x = area.left() + margin
        y = area.top() + margin
        if s.corner in (OverlayCorner.TOP_RIGHT, OverlayCorner.BOTTOM_RIGHT, OverlayCorner.CUSTOM):
            x = area.right() - s.width - margin
        if s.corner in (
            OverlayCorner.BOTTOM_LEFT,
            OverlayCorner.BOTTOM_RIGHT,
            OverlayCorner.CUSTOM,
        ):
            y = area.bottom() - s.height - margin
        self.move(x, y)

    def _emit_settings(self, **changes: object) -> None:
        self.settings = replace(self.settings, **changes)  # type: ignore[arg-type]
        self.settings_changed.emit(self.settings)

    def overlay_layers(self) -> OverlaySettings:
        s = self.settings
        return OverlaySettings(
            show_landmarks=s.show_skeleton,
            show_skeleton=s.show_skeleton,
            show_bounding_box=False,
            show_labels=False,
            show_fingertip_trail=s.show_trails,
            show_palm_trail=False,
            show_vectors=s.show_vectors,
        )

    # ------------------------------------------------------------------ data

    def show_frame(self, frame: ProcessedFrame) -> None:
        self._frame = frame
        # Smoothed once per camera frame (repaints for fading feedback reuse it).
        self._drawn_tracking = (
            self.smoother.smooth(frame.tracking) if self.settings.smooth_skeleton else None
        )
        self.update()

    def clear(self) -> None:
        self._frame = None
        self._image = None
        self._drawn_tracking = None
        self.smoother.reset()
        self.compositor.reset()
        self.update()

    def show_record(self, record: ActionRecord) -> None:
        label = event_label(record.event.gesture, record.event.detector)
        if record.action is not ActionType.NONE:
            label += f" → {record.action.label}"
        status = record.status if record.status.final else None
        self._last = (label, status, now_ns())
        self.update()

    # ------------------------------------------------------------------ window events

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        _no_activate(self)
        if self.segmenter is not None:
            self.segmenter.set_enabled(self.settings.transparent_background)

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().hideEvent(event)
        if self.segmenter is not None:
            # The model does not run while nothing could display its result.
            self.segmenter.set_enabled(False)

    def _in_grip(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - GRIP_PX and pos.y() >= self.height() - GRIP_PX

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._resizing = self._in_grip(pos)
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
                if self._in_grip(event.position().toPoint())
                else Qt.CursorShape.OpenHandCursor
            )
            return
        if self._resizing:
            width = max(self.minimumWidth(), int(event.position().x()))
            self.resize(width, max(self.minimumHeight(), round(width * 9 / 16)))
        else:
            self.move(event.globalPosition().toPoint() - self._drag)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None:
            self._drag = None
            self._resizing = False
            pos = self.pos()
            self._emit_settings(
                width=self.width(),
                height=self.height(),
                x=pos.x(),
                y=pos.y(),
                corner=OverlayCorner.CUSTOM,
            )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.developer_requested.emit()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.build_menu().exec(event.globalPos())

    def build_menu(self) -> QMenu:
        menu = QMenu(self)
        s = self.settings
        for field_name, label in (
            ("show_skeleton", "Hand skeleton"),
            ("show_trails", "Motion trails"),
            ("show_vectors", "Motion vectors"),
            ("show_last_gesture", "Last gesture"),
            ("show_outcome", "Action outcome"),
            ("show_counters", "Session timer and counters"),
            ("show_control_state", "Gesture control status"),
            ("smooth_skeleton", "Smooth skeleton (display only)"),
            ("transparent_background", "Transparent background"),
        ):
            action = QAction(label, menu, checkable=True)
            action.setChecked(getattr(s, field_name))
            action.toggled.connect(lambda on, f=field_name: self._toggle(f, on))
            menu.addAction(action)
        opacity = menu.addMenu("Opacity")
        group = QActionGroup(opacity)
        for value in (1.0, 0.85, 0.7, 0.5):
            action = QAction(f"{value:.0%}", opacity, checkable=True)
            action.setChecked(abs(s.opacity - value) < 0.01)
            action.triggered.connect(lambda _=False, v=value: self._set_opacity(v))
            group.addAction(action)
            opacity.addAction(action)
        size = menu.addMenu("Size")
        for width in (320, 480, 640, 960):
            action = QAction(f"{width} x {width * 9 // 16}", size)
            action.triggered.connect(lambda _=False, w=width: self._set_size(w))
            size.addAction(action)
        position = menu.addMenu("Position")
        for corner, label in (
            (OverlayCorner.TOP_LEFT, "Top left"),
            (OverlayCorner.TOP_RIGHT, "Top right"),
            (OverlayCorner.BOTTOM_LEFT, "Bottom left"),
            (OverlayCorner.BOTTOM_RIGHT, "Bottom right (default)"),
        ):
            action = QAction(label, position)
            action.triggered.connect(lambda _=False, c=corner: self.move_to_corner(c))
            position.addAction(action)
        menu.addSeparator()
        menu.addAction("Developer Mode", self.developer_requested.emit)
        menu.addAction("Background Mode (tray)", self.background_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Interactive Scrolling", self.quit_requested.emit)
        return menu

    def _toggle(self, field_name: str, on: bool) -> None:
        self._emit_settings(**{field_name: on})
        self.apply_settings(self.settings)

    def _set_opacity(self, value: float) -> None:
        self._emit_settings(opacity=value)
        self.apply_settings(self.settings)

    def move_to_corner(self, corner: OverlayCorner) -> None:
        """Corner of the screen the overlay is on (or the primary screen)."""
        self._emit_settings(corner=corner, x=None, y=None)
        self.apply_settings(self.settings, reposition=True)

    def _set_size(self, width: int) -> None:
        self._emit_settings(width=width, height=width * 9 // 16)
        self.apply_settings(self.settings)

    # ------------------------------------------------------------------ painting

    def _transparent_image(self, frame: ProcessedFrame, w: int, h: int) -> QImage | None:
        worker = self.segmenter
        result = worker.latest() if worker is not None else None
        if result is None or not MaskCompositor.usable(
            result.timestamp_ns, result.session, frame.capture_ns, frame.session
        ):
            self.transparent_state = "unavailable"
            return None
        rgba = self.compositor.compose(frame.image_rgb, result.value, result.timestamp_ns, (w, h))
        self._image_buffer = rgba  # keeps the buffer alive while the QImage is used
        self.transparent_state = "active"
        return QImage(rgba.data, w, h, rgba.strides[0], QImage.Format.Format_RGBA8888)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        frame = self._frame
        if frame is None:
            self._paint_notice(painter, "Camera is off")
            painter.end()
            return
        h, w = frame.image_rgb.shape[:2]
        t = ViewTransform.fit(w, h, self.width(), self.height(), self.mirrored)
        target = QRectF(t.x, t.y, t.width, t.height)
        image: QImage | None
        if self.settings.transparent_background:
            image = self._transparent_image(frame, max(1, int(t.width)), max(1, int(t.height)))
        else:
            self.transparent_state = "off"
            image = QImage(
                frame.image_rgb.data, w, h, frame.image_rgb.strides[0], QImage.Format.Format_RGB888
            )
        if image is not None:
            painter.save()
            if not self.settings.transparent_background:
                clip = QPainterPath()
                clip.addRoundedRect(target, 10, 10)
                painter.setClipPath(clip)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            if t.mirrored:
                painter.translate(t.x + t.width, t.y)
                painter.scale(-1.0, 1.0)
                painter.drawImage(QRectF(0, 0, t.width, t.height), image)
            else:
                painter.drawImage(target, image)
            painter.restore()
        tracking = self._drawn_tracking if self._drawn_tracking is not None else frame.tracking
        self.renderer.paint(painter, t, tracking, frame.motion, self.overlay_layers())
        for paint_extra in self.extra_painters:
            paint_extra(painter, t, frame)
        if self.settings.transparent_background and image is None:
            self._paint_notice(painter, "Background removal unavailable - camera image hidden")
        self._paint_feedback(painter, target)
        if self.settings.show_control_state:
            self._paint_control_state(painter, target)
        self._paint_grip(painter)
        painter.end()

    def _paint_notice(self, painter: QPainter, text: str) -> None:
        painter.setFont(self._font)
        rect = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        painter.setPen(QColor(palette.ACCENT_AMBER))
        background = QColor(palette.BACKGROUND)
        background.setAlpha(200)
        box = painter.fontMetrics().boundingRect(
            rect.toRect(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text
        )
        painter.fillRect(QRectF(box).adjusted(-8, -6, 8, 6), background)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _paint_feedback(self, painter: QPainter, rect: QRectF) -> None:
        s = self.settings
        lines: list[tuple[str, str]] = []
        if self._last is not None and (now_ns() - self._last[2]) / 1e9 < FEEDBACK_S:
            label, status, _ = self._last
            if s.show_last_gesture:
                lines.append((label, palette.TEXT))
            if s.show_outcome and status is not None:
                text, color = OUTCOME_TEXT.get(status, (status.value, palette.TEXT_MUTED))
                lines.append((text, color))
            self.update()  # fade out even without new frames
        if s.show_counters and self.counters_text:
            lines.append((self.counters_text, palette.TEXT_MUTED))
        if not lines:
            return
        painter.setFont(self._big_font)
        metrics = painter.fontMetrics()
        y = rect.bottom() - 10
        for text, color in reversed(lines):
            width = metrics.horizontalAdvance(text) + 20
            box = QRectF(rect.left() + 10, y - metrics.height() - 6, width, metrics.height() + 6)
            background = QColor(palette.BACKGROUND)
            background.setAlpha(190)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(color))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
            y = box.top() - 4

    def _paint_control_state(self, painter: QPainter, rect: QRectF) -> None:
        text, color = CONTROL_CHIP[self.control_mode]
        painter.setFont(self._font)
        metrics = painter.fontMetrics()
        box = QRectF(
            rect.left() + 10,
            rect.top() + 10,
            metrics.horizontalAdvance(text) + 16,
            metrics.height() + 6,
        )
        background = QColor(palette.BACKGROUND)
        background.setAlpha(170)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor(color))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_grip(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 110), 1.5))
        r = QRect(self.width() - GRIP_PX, self.height() - GRIP_PX, GRIP_PX, GRIP_PX)
        for i in (4, 9, 14):
            painter.drawLine(
                QPointF(r.right() - i, r.bottom() - 1), QPointF(r.right() - 1, r.bottom() - i)
            )
