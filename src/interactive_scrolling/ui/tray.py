"""Background Mode: a system-tray icon that always shows what the camera and control are doing.

The icon is visible for the whole lifetime of the application (in every UI mode), so the
camera can never be active without a visible indicator. Its colour shows the state:
grey camera off, green camera on (tracking only), amber gesture test, red live control. The
menu offers start/stop camera, emergency disable, the three UI modes and Quit.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.visualization import palette

STATE_COLORS = {
    "off": palette.TEXT_DIM,
    ControlMode.TRACKING_ONLY: palette.ACCENT_GREEN,
    ControlMode.GESTURE_TEST: palette.ACCENT_AMBER,
    ControlMode.LIVE_CONTROL: palette.ACCENT_RED,
}


def state_icon(color: str, camera_on: bool) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(palette.BACKGROUND))
    painter.drawEllipse(2, 2, 60, 60)
    painter.setBrush(QColor(color))
    if camera_on:
        painter.drawEllipse(14, 14, 36, 36)
    else:
        painter.drawEllipse(22, 22, 20, 20)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    start_camera = Signal()
    stop_camera = Signal()
    disable_control = Signal()
    mode_requested = Signal(str)
    """"developer", "creator" or "background"."""
    quit_requested = Signal()
    broadcast_settings_requested = Signal()

    def __init__(self, hotkey_label: str = "", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.icon = QSystemTrayIcon(self)
        self.menu = QMenu()
        self.camera_status = QAction("Camera: off", self.menu)
        self.camera_status.setEnabled(False)
        self.control_status = QAction("Gestures: off", self.menu)
        self.control_status.setEnabled(False)
        self.menu.addAction(self.camera_status)
        self.menu.addAction(self.control_status)
        self.menu.addSeparator()
        self.camera_action = self.menu.addAction("Start camera", self._toggle_camera)
        disable_text = "Stop gesture control" + (f"  ({hotkey_label})" if hotkey_label else "")
        self.disable_action = self.menu.addAction(disable_text, self.disable_control.emit)
        self.menu.addSeparator()
        self.menu.addAction("Studio Mode", lambda: self.mode_requested.emit("developer"))
        self.menu.addAction("Broadcast Mode", lambda: self.mode_requested.emit("creator"))
        self.menu.addAction("Broadcast settings...", self.broadcast_settings_requested.emit)
        self.menu.addAction("Background Mode", lambda: self.mode_requested.emit("background"))
        self.menu.addSeparator()
        self.menu.addAction("Quit Interactive Scrolling", self.quit_requested.emit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self._camera_on = False
        self.update_state(False, ControlMode.TRACKING_ONLY)

    def show(self) -> None:
        if self.available:
            self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def update_state(self, camera_on: bool, mode: ControlMode) -> None:
        self._camera_on = camera_on
        self.camera_status.setText(f"Camera: {'ON' if camera_on else 'off'}")
        self.control_status.setText(f"Gestures: {mode.label}")
        self.camera_action.setText("Stop camera" if camera_on else "Start camera")
        self.disable_action.setEnabled(mode is not ControlMode.TRACKING_ONLY)
        color = STATE_COLORS[mode] if camera_on else STATE_COLORS["off"]
        self.icon.setIcon(state_icon(color, camera_on))
        self.icon.setToolTip(
            f"Interactive Scrolling - camera {'on' if camera_on else 'off'}, {mode.label}"
        )

    def notify(self, title: str, text: str) -> None:
        if self.available and self.icon.isVisible():
            self.icon.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 8000)

    def _toggle_camera(self) -> None:
        (self.stop_camera if self._camera_on else self.start_camera).emit()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.mode_requested.emit("developer")
