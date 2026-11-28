"""Doomscroll Together: host or join a two-person session (Co-op Lite underneath).

The panel speaks in plain states ("Waiting for your friend", "Sam wants to join", "Playing
with Sam") and keeps addresses and ports in the invitation and the Host dialog. Network
details (round trip, confirmation time) live in the diagnostics console.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.actions.types import ActionType
from interactive_scrolling.integrations.coop.session import (
    DEFAULT_PORT,
    CoopStatus,
    invitation_text,
    network_choices,
    parse_invitation,
)
from interactive_scrolling.ui.report_panels import duration

ALL_NETWORKS = "0.0.0.0"
OUTCOME_WORDS = {
    "succeeded": "Success",
    "rejected": "Rejected",
    "failed": "Failed",
    "no change": "No change",
    "outcome unknown": "Unknown",
    "not executed": "Not executed",
}


class _JoinSignals(QObject):
    finished = Signal(str)
    """Empty on success, otherwise the message for the user."""


def describe_last(status: CoopStatus) -> str:
    last = status.last
    if last is None:
        return "No shared actions yet"
    try:
        action = ActionType(last.action).label
    except ValueError:
        action = last.action
    outcome = OUTCOME_WORDS.get(last.outcome, last.outcome.capitalize())
    return f"{last.by} → {action} → {outcome}"


def _label(text: str = "", name: str = "hint", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


class HostDialog(QDialog):
    """Name and network for a new session (the port is an advanced detail)."""

    def __init__(self, name: str, parent: QWidget | None = None, port: int = DEFAULT_PORT) -> None:
        super().__init__(parent)
        self.setWindowTitle("Host Doomscroll Together")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(
            _label(
                "Your browser plays the feed. Share it with your friend through Discord (or "
                "similar); you both control it with gestures."
            )
        )
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setMaxLength(24)
        form.addRow("Your name", self.name)
        self.network = QComboBox()
        for address, label in network_choices():
            self.network.addItem(f"{label}  ({address})", address)
        self.network.addItem("All private networks", ALL_NETWORKS)
        form.addRow("Friend joins from", self.network)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(port)
        form.addRow("Port", self.port)
        layout.addLayout(form)
        layout.addWidget(
            _label(
                "Same Wi-Fi: choose Local network. Different places: both of you join the same "
                "private VPN (for example Tailscale) and choose it here. Nothing is opened to "
                "the internet.",
                "dimHint",
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start session")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, int, str]:
        return self.name.text().strip(), self.port.value(), str(self.network.currentData())


class JoinDialog(QDialog):
    """Paste the invitation; address, port and code are filled in from it."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Join Doomscroll Together")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_label("Paste the invitation your friend sent you."))
        self.invitation = QPlainTextEdit()
        self.invitation.setPlaceholderText("Address: ...\nPort: ...\nCode: ...")
        self.invitation.setFixedHeight(84)
        self.invitation.textChanged.connect(self._parse)
        layout.addWidget(self.invitation)
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setMaxLength(24)
        form.addRow("Your name", self.name)
        self.address = QLineEdit()
        self.address.setPlaceholderText("e.g. 192.168.1.20")
        form.addRow("Address", self.address)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(DEFAULT_PORT)
        form.addRow("Port", self.port)
        self.code = QLineEdit()
        self.code.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        form.addRow("Code", self.code)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Join")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _parse(self) -> None:
        address, port, code = parse_invitation(self.invitation.toPlainText())
        if address:
            self.address.setText(address)
        if port:
            self.port.setValue(port)
        if code:
            self.code.setText(code)

    def values(self) -> tuple[str, str, int, str]:
        return (
            self.name.text().strip(),
            self.address.text().strip(),
            self.port.value(),
            self.code.text().strip(),
        )


class TogetherPanel(QWidget):
    host_requested = Signal(str, int, str)
    """name, port, bind address."""
    end_requested = Signal()
    approve_requested = Signal(bool)
    shared_control_changed = Signal(bool)
    join_requested = Signal(str, str, int, str)
    """name, host address, port, code."""
    leave_requested = Signal()
    wrapped_requested = Signal()
    renew_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.join_signals = _JoinSignals()
        self.player_name = "Player 1"
        self.host_port = DEFAULT_PORT
        """Defaults for the Host dialog (Settings, Doomscroll Together)."""
        self._invitation = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        title = QLabel("Doomscroll Together")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        self.state = _label("", "sectionValue")
        root.addWidget(self.state)
        self.pages: list[QWidget] = []

        # -- off: invite or join
        off = QWidget()
        lay = QVBoxLayout(off)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_label("Scroll one feed with a friend. You both swipe; one browser plays."))
        row = QHBoxLayout()
        self.host_button = QPushButton("Host")
        self.host_button.setObjectName("primaryButton")
        self.host_button.clicked.connect(self._open_host)
        self.join_button = QPushButton("Join")
        self.join_button.clicked.connect(self._open_join)
        row.addWidget(self.host_button)
        row.addWidget(self.join_button)
        lay.addLayout(row)
        root.addWidget(off)
        self.pages.append(off)

        # -- host
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.code = _label("", "inviteCode", wrap=False)
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.code)
        self.where = _label("", "dimHint")
        lay.addWidget(self.where)
        row = QHBoxLayout()
        self.copy_button = QPushButton("Copy invitation")
        self.copy_button.clicked.connect(self._copy_invitation)
        self.renew_button = QPushButton("New code")
        self.renew_button.setObjectName("linkButton")
        self.renew_button.setToolTip("Make a new invitation; the old code stops working")
        self.renew_button.clicked.connect(self.renew_requested)
        row.addWidget(self.copy_button)
        row.addWidget(self.renew_button)
        lay.addLayout(row)
        approve_row = QHBoxLayout()
        self.approve = QPushButton("Let them in")
        self.approve.setObjectName("primaryButton")
        self.approve.clicked.connect(lambda: self.approve_requested.emit(True))
        self.deny = QPushButton("Decline")
        self.deny.clicked.connect(lambda: self.approve_requested.emit(False))
        approve_row.addWidget(self.approve)
        approve_row.addWidget(self.deny)
        approve_row.addStretch(1)
        lay.addLayout(approve_row)
        self.shared = QCheckBox("My friend can control the feed")
        self.shared.setChecked(True)
        self.shared.toggled.connect(self.shared_control_changed)
        lay.addWidget(self.shared)
        root.addWidget(host)
        self.pages.append(host)

        # -- guest
        guest = QWidget()
        lay = QVBoxLayout(guest)
        lay.setContentsMargins(0, 0, 0, 0)
        self.guest_hint = _label("")
        lay.addWidget(self.guest_hint)
        root.addWidget(guest)
        self.pages.append(guest)

        # -- shared session details
        self.last = _label("", "hint")
        root.addWidget(self.last)
        self.counts = _label("", "dimHint")
        root.addWidget(self.counts)
        row = QHBoxLayout()
        self.end_button = QPushButton("End session")
        self.end_button.clicked.connect(self.end_requested)
        self.leave_button = QPushButton("Leave")
        self.leave_button.clicked.connect(self.leave_requested)
        self.wrapped_button = QPushButton("Duo Wrapped")
        self.wrapped_button.setObjectName("linkButton")
        self.wrapped_button.clicked.connect(self.wrapped_requested)
        row.addWidget(self.end_button)
        row.addWidget(self.leave_button)
        row.addWidget(self.wrapped_button)
        row.addStretch(1)
        root.addLayout(row)
        self.error = _label("", "hint")
        self.error.setProperty("error", True)
        self.error.setVisible(False)
        root.addWidget(self.error)
        self.show_status(CoopStatus(role="off", state="no session"))

    # ------------------------------------------------------------------ dialogs

    def _open_host(self) -> None:
        dialog = HostDialog(self.player_name, self, self.host_port)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, port, bind = dialog.values()
            self.player_name = name or self.player_name
            self.host_requested.emit(name, port, bind)

    def _open_join(self) -> None:
        dialog = JoinDialog(self.player_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, address, port, code = dialog.values()
            self.player_name = name or self.player_name
            self.join_requested.emit(name, address, port, code)

    def _copy_invitation(self) -> None:
        if self._invitation:
            QGuiApplication.clipboard().setText(self._invitation)
            self.copy_button.setText("Copied")

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))

    # ------------------------------------------------------------------ state

    def show_status(self, status: CoopStatus) -> None:
        hosting = status.role == "host"
        guesting = status.role == "guest"
        current = 1 if hosting else 2 if guesting else 0
        for index, page in enumerate(self.pages):
            page.setVisible(index == current)
        self.end_button.setVisible(hosting)
        self.leave_button.setVisible(guesting)
        self.wrapped_button.setVisible(hosting and len(status.participants) > 1)
        session = hosting or guesting
        self.last.setVisible(session)
        self.counts.setVisible(hosting)
        self.state.setText(self._headline(status))
        if hosting:
            self._show_host(status)
        elif guesting:
            if status.reconnecting:
                hint = "The connection dropped; trying to resume."
            elif status.approved:
                hint = (
                    f"Your next, previous and pause gestures go to {status.peer}'s feed. "
                    "Watch it in your screen-sharing app."
                )
            else:
                hint = f"{status.peer or 'The host'} needs to let you in."
            self.guest_hint.setText(hint)
        self.last.setText(describe_last(status))
        if status.participants:
            self.counts.setText(
                "Successful actions: " + ", ".join(f"{n}: {c}" for n, _, c in status.participants)
            )
        else:
            self.counts.setText("")

    def _show_host(self, status: CoopStatus) -> None:
        waiting = status.peer is None
        self.code.setVisible(waiting)
        self.where.setVisible(waiting)
        self.copy_button.setVisible(waiting)
        self.renew_button.setVisible(waiting)
        self.approve.setVisible(status.pending_approval)
        self.deny.setVisible(status.peer is not None)
        self.approve.setEnabled(status.pending_approval)
        self.deny.setEnabled(status.peer is not None)
        self.deny.setText("Decline" if status.pending_approval else "Remove")
        self.shared.setVisible(status.peer is not None and not status.pending_approval)
        if status.code:
            self.code.setText(status.code)
            address = self._address(status)
            self.where.setText(f"{address}  ·  port {status.port}")
            invitation = invitation_text(self.player_name, address, status.port or 0, status.code)
            if invitation != self._invitation:
                self._invitation = invitation
                self.copy_button.setText("Copy invitation")
        else:
            self.code.setText("")

    @staticmethod
    def _address(status: CoopStatus) -> str:
        if status.bind and status.bind != ALL_NETWORKS:
            return status.bind
        return status.addresses[0] if status.addresses else "this computer's address"

    @staticmethod
    def _headline(status: CoopStatus) -> str:
        if status.role == "host":
            if status.invitation_expired:
                return "The invitation expired. Make a new code."
            if status.peer is None:
                return "Waiting for your friend"
            if status.pending_approval:
                return f"{status.peer} wants to join"
            if status.approved:
                text = f"Playing with {status.peer}"
                return text + f"  ·  {duration(status.session_s)}"
            return f"{status.peer} is connected"
        if status.role == "guest":
            if status.reconnecting:
                return "Reconnecting..."
            if status.approved:
                return f"Playing with {status.peer}"
            return f"Waiting for {status.peer or 'the host'}"
        if status.state.startswith("disconnected:"):
            return status.state.split(":", 1)[1].strip().capitalize()
        return "Not in a session"
