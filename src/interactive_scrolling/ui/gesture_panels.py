"""Gesture recognition panel and gesture history table."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ActionType
from interactive_scrolling.gestures.types import ControlStatus, GestureFrame
from interactive_scrolling.ui.panels import NO_DATA, Card
from interactive_scrolling.visualization import palette

STATUS_COLORS = {
    ActionStatus.SUCCEEDED: palette.ACCENT_GREEN,
    ActionStatus.NO_CHANGE: palette.ACCENT_CYAN,
    ActionStatus.NOT_EXECUTED: palette.TEXT_MUTED,
    ActionStatus.QUEUED: palette.ACCENT_AMBER,
    ActionStatus.DISPATCHED: palette.ACCENT_AMBER,
    ActionStatus.REJECTED: palette.ACCENT_AMBER,
    ActionStatus.FAILED: palette.ACCENT_RED,
    ActionStatus.UNKNOWN: palette.ACCENT_RED,
}


def describe(record: ActionRecord) -> str:
    text = record.status.value
    if record.reason:
        text += f" — {record.reason}"
    elif record.detail:
        text += f" — {record.detail}"
    return text


class GesturePanel(Card):
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Gesture recognition", parent)
        self.status = self.add_row("Control hand", accent=True)
        self.pose = self.add_row("Pose")
        self.phase = self.add_row("State")
        self.candidate = self.add_row("Candidate")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.add_widget(self.progress)
        self.last = self.add_row("Last confirmed", accent=True)
        self.action = self.add_row("Action")
        self.rejection = self.add_row("Last rejection")
        for label in (self.rejection, self.action, self.last):
            label.setWordWrap(True)
        button = QPushButton("Gesture settings...")
        button.clicked.connect(self.settings_requested)
        self.add_widget(button)
        self.show_frame(None, enabled=False)

    def show_frame(self, frame: GestureFrame | None, enabled: bool) -> None:
        if not enabled:
            self.status.setText("Recognition off (Tracking only)")
            for label in (self.pose, self.phase, self.candidate):
                label.setText(NO_DATA)
            self.progress.setValue(0)
            return
        if frame is None:
            self.status.setText("Waiting for frames")
            return
        if frame.status is ControlStatus.ACTIVE or frame.status is ControlStatus.STABILIZING:
            hand = frame.control_handedness.value if frame.control_handedness else "?"
            text = f"{hand} hand (track {frame.control_track_id})"
            if frame.status is ControlStatus.STABILIZING:
                text += " — stabilizing"
        else:
            text = (
                f"{frame.status.value}: {frame.status_detail}"
                if frame.status_detail
                else frame.status.value
            )
        self.status.setText(text)
        self.pose.setText(frame.pose or NO_DATA)
        phase = frame.phase.value
        if frame.blocked_until_ns is not None:
            remaining = (frame.blocked_until_ns - frame.timestamp_ns) / 1e9
            phase += f" (cooldown {remaining:.1f} s)"
        self.phase.setText(phase)
        if frame.candidates:
            best = max(frame.candidates, key=lambda c: c.progress)
            self.candidate.setText(f"{best.gesture.label}  {best.progress:.0%}")
            self.progress.setValue(int(best.progress * 100))
        else:
            self.candidate.setText(NO_DATA)
            self.progress.setValue(0)
        if frame.rejection is not None:
            self.rejection.setText(f"{frame.rejection.gesture.label}: {frame.rejection.reason}")

    def show_record(self, record: ActionRecord) -> None:
        self.last.setText(record.event.gesture.label)
        action = record.action.label if record.action is not ActionType.NONE else "none"
        self.action.setText(f"{action} — {describe(record)}")


class GestureHistory(QTableWidget):
    """Bounded table of confirmed gestures and their action outcomes (real records only)."""

    COLUMNS = ("Time", "Gesture", "Action", "Outcome")

    def __init__(self, capacity: int = 200, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.COLUMNS), parent)
        self.setObjectName("gestureHistory")
        self.capacity = capacity
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._rows: dict[str, QTableWidgetItem] = {}

    def update_record(self, record: ActionRecord) -> None:
        item = self._rows.get(record.record_id)
        if item is None:
            self.insertRow(0)
            stamp = datetime.fromtimestamp(record.wall_time).strftime("%H:%M:%S")
            values = (stamp, record.event.gesture.label, record.action.label, "")
            for column, value in enumerate(values):
                self.setItem(0, column, QTableWidgetItem(value))
            item = self.item(0, 3)
            self._rows[record.record_id] = item
            while self.rowCount() > self.capacity:
                last = self.rowCount() - 1
                gone = self.item(last, 3)
                self._rows = {k: v for k, v in self._rows.items() if v is not gone}
                self.removeRow(last)
        latency = record.action_latency_ms
        text = describe(record)
        if latency is not None and record.status in (
            ActionStatus.SUCCEEDED,
            ActionStatus.NO_CHANGE,
        ):
            text += f"  ({latency:.0f} ms)"
        item.setText(text)
        item.setForeground(QColor(STATUS_COLORS.get(record.status, palette.TEXT_MUTED)))

    def outcome_of(self, record_id: str) -> str | None:
        item = self._rows.get(record_id)
        return item.text() if item is not None else None
