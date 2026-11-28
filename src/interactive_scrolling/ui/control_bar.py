"""Gesture control panel: Off / Test / Live, live feedback, quick controls, emergency stop.

Brief 010: a vertical block in the left camera column of the cinema workspace. Live control is
the only state in which gestures act on the browser; it is shown in red with a text label (never
colour alone), and Stop and the global shortcut return to Off at once. The feedback block says
what was recognized, which action was requested and - only after the browser confirmed it -
the outcome. Quick controls open the matching Unified Settings pages instead of duplicating
configuration.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ActionType, ControlMode
from interactive_scrolling.gestures.explain import event_label
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
OUTCOME_TEXT = {
    ActionStatus.SUCCEEDED: ("Successful", "ok"),
    ActionStatus.NO_CHANGE: ("No change needed", "ok"),
    ActionStatus.REJECTED: ("Not done", "warn"),
    ActionStatus.FAILED: ("Failed", "error"),
    ActionStatus.UNKNOWN: ("Not confirmed", "warn"),
    ActionStatus.NOT_EXECUTED: ("Not sent (test or off)", ""),
}


def reserve_bold_width(button: QPushButton) -> None:
    """A checked button is drawn bold; reserve that width so its text is never clipped."""
    font = QFont(button.font())
    font.setBold(True)
    text = QFontMetrics(font).horizontalAdvance(button.text())
    button.setMinimumWidth(text + 28)


class SegmentedControl(QFrame):
    """One rounded rectangle with exclusive segments (theme, presentation mode, gestures)."""

    selected = Signal(object)

    def __init__(
        self,
        options: list[tuple[object, str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[object, QPushButton] = {}
        for key, text, tip in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setToolTip(tip)
            # Keyboard focus only: a click must not leave a focus ring that looks like a
            # second selection.
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _=False, k=key: self.selected.emit(k))
            reserve_bold_width(button)
            self.group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button, 1)

    def set_value(self, key: object) -> None:
        button = self.buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)


class ControlBar(QFrame):
    mode_requested = Signal(object)
    disable_requested = Signal()
    settings_requested = Signal()
    practice_requested = Signal()
    camera_settings_requested = Signal()
    layer_toggled = Signal(str, bool)
    """Tracking-layer shortcut: overlay field name, enabled."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gestureStrip")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Gesture control")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.state = QLabel()
        self.state.setObjectName("gestureState")
        header.addWidget(self.state)
        root.addLayout(header)

        modes = list(ControlMode)
        self.segments = SegmentedControl([(m, SHORT_LABELS[m], MODE_TIPS[m]) for m in modes])
        self.buttons: dict[ControlMode, QPushButton] = {}
        for mode in modes:
            button = self.segments.buttons[mode]
            button.setProperty("mode", mode.value)
            button.setAccessibleName(mode.label)
            self.buttons[mode] = button
        self.segments.selected.connect(self.mode_requested)
        root.addWidget(self.segments)

        # Feedback: recognized gesture, requested action, verified outcome.
        feedback = QGridLayout()
        feedback.setHorizontalSpacing(10)
        feedback.setVerticalSpacing(2)
        self.feedback_labels: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate(
            (("gesture", "Gesture"), ("action", "Action"), ("outcome", "Outcome"))
        ):
            name = QLabel(caption)
            name.setObjectName("dimHint")
            value = QLabel("—")
            value.setObjectName("feedbackGesture" if key == "gesture" else "feedbackOutcome")
            value.setTextFormat(Qt.TextFormat.PlainText)
            feedback.addWidget(name, row, 0)
            feedback.addWidget(value, row, 1)
            self.feedback_labels[key] = value
        feedback.setColumnStretch(1, 1)
        root.addLayout(feedback)
        self.last_chip = QLabel("")
        self.last_chip.setObjectName("dimHint")
        self.last_chip.setWordWrap(True)
        self.last_chip.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.last_chip)

        self.quick_row = QWidget()
        quick = QHBoxLayout(self.quick_row)
        quick.setContentsMargins(0, 0, 0, 0)
        quick.setSpacing(16)
        caption = QLabel("Open")
        caption.setObjectName("dimHint")
        quick.addWidget(caption)
        self.practice_button = QPushButton("Practice")
        self.practice_button.setObjectName("linkButton")
        self.practice_button.setToolTip("Practice the gestures and calibrate your movements")
        self.practice_button.clicked.connect(self.practice_requested)
        self.settings_button = QPushButton("Gestures")
        self.settings_button.setObjectName("linkButton")
        self.settings_button.setToolTip("Settings - Gestures")
        self.settings_button.clicked.connect(self.settings_requested)
        self.camera_button = QPushButton("Camera")
        self.camera_button.setObjectName("linkButton")
        self.camera_button.setToolTip("Settings - Camera")
        self.camera_button.clicked.connect(self.camera_settings_requested)
        for button in (self.practice_button, self.settings_button, self.camera_button):
            quick.addWidget(button)
        quick.addStretch(1)
        root.addWidget(self.quick_row)

        self.layer_row = QWidget()
        layers = QHBoxLayout(self.layer_row)
        layers.setContentsMargins(0, 0, 0, 0)
        layers.setSpacing(4)
        caption = QLabel("Show")
        caption.setObjectName("dimHint")
        layers.addWidget(caption)
        self.layer_buttons: dict[str, QPushButton] = {}
        for field, text, tip in (
            ("show_skeleton", "Skeleton", "Hand skeleton on the camera image"),
            ("show_vectors", "Vectors", "Motion vectors on the camera image"),
            ("eyes", "Eyes", "Eye and gaze overlay (estimate, display only)"),
        ):
            button = QPushButton(text)
            button.setObjectName("layerButton")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.toggled.connect(lambda on, f=field: self.layer_toggled.emit(f, on))
            layers.addWidget(button)
            self.layer_buttons[field] = button
        layers.addStretch(1)
        root.addWidget(self.layer_row)

        self.disable_button = QPushButton("Stop gesture control")
        self.disable_button.setObjectName("disableButton")
        self.disable_button.clicked.connect(self.disable_requested)
        root.addWidget(self.disable_button)
        self.set_mode(ControlMode.TRACKING_ONLY)

    def set_mode(self, mode: ControlMode) -> None:
        self.segments.set_value(mode)
        live = mode is ControlMode.LIVE_CONTROL
        self.disable_button.setEnabled(mode is not ControlMode.TRACKING_ONLY)
        self.state.setText(STATE_TEXT[mode])
        self.setProperty("live", live)
        repolish(self)
        repolish(self.state)

    def secondary_widgets(self) -> list[QWidget]:
        """Hidden in Focus view; Off / Test / Live, feedback and Stop always stay."""
        return [self.last_chip, self.quick_row, self.layer_row]

    def set_layers(self, values: dict[str, bool]) -> None:
        for field, button in self.layer_buttons.items():
            if field in values and button.isChecked() != values[field]:
                button.blockSignals(True)
                button.setChecked(values[field])
                button.blockSignals(False)

    def set_hotkey_hint(self, text: str) -> None:
        tip = "Immediately stop all gesture control."
        if text:
            tip += f" Global shortcut: {text} (works in every window)."
            self.disable_button.setText(f"Stop gesture control   {text}")
        self.disable_button.setToolTip(tip)

    def show_record(self, record: ActionRecord) -> None:
        """Recognized gesture and requested action at once; the outcome only once final."""
        self.feedback_labels["gesture"].setText(
            event_label(record.event.gesture, record.event.detector).capitalize()
        )
        action = record.action.label if record.action is not ActionType.NONE else "None"
        self.feedback_labels["action"].setText(action)
        outcome = self.feedback_labels["outcome"]
        if record.status.final:
            text, state = OUTCOME_TEXT.get(record.status, (record.status.value, ""))
        else:
            text, state = "Waiting for the browser...", ""
        outcome.setText(text)
        outcome.setProperty("state", state)
        repolish(outcome)
        detail = f"{action}: {record.status.value}"
        if record.reason and record.status.final:
            detail += f" ({record.reason})"
        self.last_chip.setText(detail)
        self.last_chip.setToolTip(detail)

    def set_last(self, text: str) -> None:
        self.last_chip.setText(text)
        self.last_chip.setToolTip(text)
