"""Control-mode selector, emergency disable and compact status chips."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from interactive_scrolling.actions.types import ControlMode

MODE_TIPS = {
    ControlMode.TRACKING_ONLY: "Camera and hand tracking only. Gestures are not recognized.",
    ControlMode.GESTURE_TEST: "Gestures are recognized and shown. Nothing is sent to the browser.",
    ControlMode.LIVE_CONTROL: "Confirmed gestures control YouTube Shorts and browser tabs.",
}


class ControlBar(QFrame):
    mode_requested = Signal(object)
    disable_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(8)
        label = QLabel("CONTROL")
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[ControlMode, QPushButton] = {}
        for mode in ControlMode:
            button = QPushButton(mode.label)
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("mode", mode.value)
            button.setToolTip(MODE_TIPS[mode])
            button.clicked.connect(lambda _=False, m=mode: self.mode_requested.emit(m))
            self.group.addButton(button)
            self.buttons[mode] = button
            layout.addWidget(button)
        self.disable_button = QPushButton("■  Disable control")
        self.disable_button.setObjectName("disableButton")
        self.disable_button.clicked.connect(self.disable_requested)
        layout.addWidget(self.disable_button)
        layout.addSpacing(12)
        self.youtube_chip = QLabel("YouTube: —")
        self.youtube_chip.setObjectName("chip")
        layout.addWidget(self.youtube_chip)
        self.last_chip = QLabel("Last gesture: —")
        self.last_chip.setObjectName("chip")
        layout.addWidget(self.last_chip, 1)
        self.set_mode(ControlMode.TRACKING_ONLY)

    def set_mode(self, mode: ControlMode) -> None:
        self.buttons[mode].setChecked(True)
        live = mode is ControlMode.LIVE_CONTROL
        self.disable_button.setEnabled(mode is not ControlMode.TRACKING_ONLY)
        self.setProperty("live", live)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_hotkey_hint(self, text: str) -> None:
        tip = "Immediately stop all gesture control."
        if text:
            tip += f" Global shortcut: {text}."
            self.disable_button.setText(f"■  Disable  ({text})")
        self.disable_button.setToolTip(tip)

    def set_youtube(self, text: str, ready: bool) -> None:
        self.youtube_chip.setText(text)
        self.youtube_chip.setProperty("state", "ok" if ready else "warn")
        self.youtube_chip.style().unpolish(self.youtube_chip)
        self.youtube_chip.style().polish(self.youtube_chip)

    def set_last(self, text: str) -> None:
        self.last_chip.setText(text)
