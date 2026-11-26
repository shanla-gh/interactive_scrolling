"""Co-op panel: create or join a private two-person session and see who controlled what."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from interactive_scrolling.actions.types import ActionType
from interactive_scrolling.integrations.coop.session import DEFAULT_PORT, CoopStatus
from interactive_scrolling.ui.panels import NO_DATA, Card
from interactive_scrolling.ui.report_panels import duration


class _JoinSignals(QObject):
    finished = Signal(str)
    """Empty on success, otherwise the error message."""


def describe_last(status: CoopStatus) -> str:
    last = status.last
    if last is None:
        return NO_DATA
    try:
        action = ActionType(last.action).label
    except ValueError:
        action = last.action
    outcome = {"succeeded": "Success", "rejected": "Rejected", "failed": "Failed"}.get(
        last.outcome, last.outcome.capitalize()
    )
    return f"{last.by} → {action} → {outcome}"


class CoopPanel(Card):
    host_requested = Signal(str, int)
    end_requested = Signal()
    approve_requested = Signal(bool)
    shared_control_changed = Signal(bool)
    join_requested = Signal(str, str, int, str)
    """name, host address, port, code."""
    leave_requested = Signal()
    wrapped_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Co-op Doomscroll", parent)
        self.join_signals = _JoinSignals()
        intro = QLabel(
            "Two people, one feed: the Host's browser plays the Shorts (share it with Discord or "
            "similar); both players' next/previous/pause gestures control it. Same local or "
            "private network only. No video, camera or voice is sent."
        )
        intro.setWordWrap(True)
        intro.setObjectName("rowKey")
        self.add_widget(intro)
        self.name = QLineEdit("Player 1")
        self.name.setMaxLength(24)
        self.name.setPlaceholderText("Your name in the session")
        self.add_widget(self.name)

        self.add_heading("HOST")
        host_row = QWidget()
        row = QHBoxLayout(host_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(DEFAULT_PORT)
        self.port.setPrefix("port ")
        self.host_button = QPushButton("Create session")
        self.host_button.clicked.connect(
            lambda: self.host_requested.emit(self.name.text(), self.port.value())
        )
        row.addWidget(self.port)
        row.addWidget(self.host_button)
        self.add_widget(host_row)
        self.code = QLabel("")
        self.code.setObjectName("rowValue")
        self.code.setTextInteractionFlags(self.code.textInteractionFlags().TextSelectableByMouse)
        self.code.setWordWrap(True)
        self.add_widget(self.code)
        approve_row = QWidget()
        row = QHBoxLayout(approve_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.approve = QPushButton("Approve guest")
        self.approve.clicked.connect(lambda: self.approve_requested.emit(True))
        self.deny = QPushButton("Refuse")
        self.deny.clicked.connect(lambda: self.approve_requested.emit(False))
        row.addWidget(self.approve)
        row.addWidget(self.deny)
        self.add_widget(approve_row)
        self.shared = QCheckBox("Guest may control my feed")
        self.shared.setChecked(True)
        self.shared.toggled.connect(self.shared_control_changed)
        self.add_widget(self.shared)
        self.end_button = QPushButton("End session")
        self.end_button.clicked.connect(self.end_requested)
        self.add_widget(self.end_button)

        self.add_heading("GUEST")
        self.address = QLineEdit()
        self.address.setPlaceholderText("Host address, e.g. 192.168.1.20")
        self.guest_port = QSpinBox()
        self.guest_port.setRange(1024, 65535)
        self.guest_port.setValue(DEFAULT_PORT)
        self.guest_port.setPrefix("port ")
        self.join_code = QLineEdit()
        self.join_code.setPlaceholderText("Session code XXXX-XXXX-XXXX-XXXX")
        for widget in (self.address, self.guest_port, self.join_code):
            self.add_widget(widget)
        join_row = QWidget()
        row = QHBoxLayout(join_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.join_button = QPushButton("Join")
        self.join_button.clicked.connect(
            lambda: self.join_requested.emit(
                self.name.text(),
                self.address.text().strip(),
                self.guest_port.value(),
                self.join_code.text(),
            )
        )
        self.leave_button = QPushButton("Leave")
        self.leave_button.clicked.connect(self.leave_requested)
        row.addWidget(self.join_button)
        row.addWidget(self.leave_button)
        self.add_widget(join_row)

        self.add_heading("SESSION")
        self.state = self.add_row("Connection", accent=True)
        self.role = self.add_row("Role")
        self.peer = self.add_row("Other player")
        self.last = self.add_row("Last shared action", accent=True)
        self.duration = self.add_row("Session duration")
        self.counts = self.add_row("Successful actions by player")
        self.latency = self.add_row("Network round trip")
        for label in (self.state, self.last, self.counts):
            label.setWordWrap(True)
        wrapped = QPushButton("Duo Wrapped...")
        wrapped.clicked.connect(self.wrapped_requested)
        self.add_widget(wrapped)
        self.error = QLabel("")
        self.error.setObjectName("rowKey")
        self.error.setWordWrap(True)
        self.add_widget(self.error)
        self.show_status(CoopStatus(role="off", state="no session"))

    def show_error(self, text: str) -> None:
        self.error.setText(text)

    def show_status(self, status: CoopStatus) -> None:
        hosting = status.role == "host"
        guesting = status.role == "guest"
        self.host_button.setEnabled(not hosting and not guesting)
        self.end_button.setEnabled(hosting)
        self.approve.setEnabled(hosting and status.pending_approval)
        self.deny.setEnabled(hosting and status.peer is not None)
        self.shared.setEnabled(hosting)
        self.join_button.setEnabled(not hosting and not guesting)
        self.leave_button.setEnabled(guesting)
        if hosting and status.code:
            where = ", ".join(status.addresses) or "this computer's address"
            self.code.setText(
                f"Code: <b>{status.code}</b><br>Guest connects to {where}, port {status.port}"
            )
        else:
            self.code.setText("")
        self.state.setText(status.state + (f" ({status.error})" if status.error else ""))
        self.role.setText({"host": "Host", "guest": "Guest"}.get(status.role, NO_DATA))
        self.peer.setText(status.peer or NO_DATA)
        self.last.setText(describe_last(status))
        self.duration.setText(duration(status.session_s) if status.role != "off" else NO_DATA)
        if status.participants:
            self.counts.setText(", ".join(f"{n}: {c}" for n, _, c in status.participants))
        else:
            self.counts.setText(NO_DATA if not hosting else "none yet")
        self.latency.setText(f"{status.rtt_ms:.0f} ms" if status.rtt_ms is not None else NO_DATA)
