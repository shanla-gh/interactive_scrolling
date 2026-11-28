"""Gesture control strip: Off / Test / Live, emergency stop and the latest result.

It sits directly under the camera so the gesture state is always in view, while the top bar
stays reserved for the camera and the presentation mode (Brief 008). Live control is the only
state in which gestures act on the browser; it is shown in red, and the Stop button and the
global shortcut return to Off at once.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.ui.theme import repolish

SHORT_LABELS = {
    ControlMode.TRACKING_ONLY: "Off",
    ControlMode.GESTURE_TEST: "Test",
    ControlMode.LIVE_CONTROL: "Live",
}
MODE_TIPS = {
    ControlMode.TRACKING_ONLY: "Gestures off: the camera shows your hand; nothing is recognized.",
    ControlMode.GESTURE_TEST: "Gesture test: gestures are recognized and shown. Nothing is sent "
    "to the browser.",
    ControlMode.LIVE_CONTROL: "Live control: confirmed gestures control YouTube Shorts and "
    "browser tabs.",
}
STATE_TEXT = {
    ControlMode.TRACKING_ONLY: "Gestures do nothing",
    ControlMode.GESTURE_TEST: "Recognized, not sent",
    ControlMode.LIVE_CONTROL: "Gestures control YouTube",
}


def reserve_bold_width(button: QPushButton) -> None:
    """A checked mode button is drawn bold; reserve that width so its text is never clipped
    (Brief 007: "Tracking only" was clipped at 125 % display scaling)."""
    font = QFont(button.font())
    font.setBold(True)
    text = QFontMetrics(font).horizontalAdvance(button.text())
    button.setMinimumWidth(text + 28)


class ControlBar(QFrame):
    mode_requested = Signal(object)
    disable_requested = Signal()
    settings_requested = Signal()
    practice_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gestureStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(0)
        label = QLabel("Gestures")
        label.setObjectName("gestureStripLabel")
        layout.addWidget(label)
        layout.addSpacing(10)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[ControlMode, QPushButton] = {}
        modes = list(ControlMode)
        for index, mode in enumerate(modes):
            button = QPushButton(SHORT_LABELS[mode])
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("mode", mode.value)
            button.setProperty("first", index == 0)
            button.setProperty("last", index == len(modes) - 1)
            button.setToolTip(MODE_TIPS[mode])
            button.setAccessibleName(mode.label)
            button.clicked.connect(lambda _=False, m=mode: self.mode_requested.emit(m))
            reserve_bold_width(button)
            self.group.addButton(button)
            self.buttons[mode] = button
            layout.addWidget(button)
        layout.addSpacing(10)
        self.state = QLabel()
        self.state.setObjectName("gestureState")
        layout.addWidget(self.state)
        layout.addSpacing(12)
        self.last_chip = QLabel("")
        self.last_chip.setObjectName("dimHint")
        self.last_chip.setTextFormat(Qt.TextFormat.PlainText)
        self.last_chip.setMinimumWidth(40)
        layout.addWidget(self.last_chip, 1)
        layout.addSpacing(8)
        self.practice_button = QPushButton("Practice")
        self.practice_button.setObjectName("flatButton")
        self.practice_button.setToolTip("Practice the gestures and calibrate your movements")
        self.practice_button.clicked.connect(self.practice_requested)
        layout.addWidget(self.practice_button)
        self.settings_button = QPushButton("Gesture settings")
        self.settings_button.setObjectName("flatButton")
        self.settings_button.clicked.connect(self.settings_requested)
        layout.addWidget(self.settings_button)
        layout.addSpacing(6)
        self.disable_button = QPushButton("Stop")
        self.disable_button.setObjectName("disableButton")
        self.disable_button.clicked.connect(self.disable_requested)
        layout.addWidget(self.disable_button)
        self.set_mode(ControlMode.TRACKING_ONLY)

    def set_mode(self, mode: ControlMode) -> None:
        self.buttons[mode].setChecked(True)
        live = mode is ControlMode.LIVE_CONTROL
        self.disable_button.setEnabled(mode is not ControlMode.TRACKING_ONLY)
        self.state.setText(STATE_TEXT[mode])
        self.setProperty("live", live)
        repolish(self)
        repolish(self.state)

    def set_hotkey_hint(self, text: str) -> None:
        tip = "Immediately stop all gesture control."
        if text:
            tip += f" Global shortcut: {text} (works in every window)."
            self.disable_button.setText(f"Stop  {text}")
        self.disable_button.setToolTip(tip)

    def set_last(self, text: str) -> None:
        self.last_chip.setText(text)
        self.last_chip.setToolTip(text)
