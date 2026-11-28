"""Your session: the right-hand panel of the cinema workspace (Brief 010).

Expanded, it shows who is watching (you and, in Doomscroll Together, your friend), the
Together actions (Host / Join / Leave / End), the latest shared action, today's numbers and a
compact browser and preview line. Collapsed, it is a narrow strip with an expand button and
status dots, and the Short in the centre grows into the released space. Collapsing only hides
widgets: the session, its permissions and the browser capture keep running.

Detailed network configuration lives in Settings; diagnostics in the console.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.integrations.coop.session import CoopStatus
from interactive_scrolling.integrations.youtube.controller import YouTubeStatus
from interactive_scrolling.integrations.youtube.preview import PreviewStatus
from interactive_scrolling.ui.theme import repolish
from interactive_scrolling.ui.together import TogetherPanel

BROWSER_NAMES = {"edge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium"}
STRIP_WIDTH = 40
DEFAULT_WIDTH = 300
MIN_WIDTH = 250
MAX_WIDTH = 460


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def short_duration(seconds: float) -> str:
    seconds = int(max(0.0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def browser_summary(status: YouTubeStatus | None) -> tuple[str, str, str]:
    """(dot state, headline, detail) for the browser section."""
    if status is None:
        return "error", "Browser connection not available", "The local browser bridge is off."
    if not status.listening:
        return "error", "Browser connection stopped", status.bridge_error or ""
    if status.connections == 0:
        return "warn", "Browser not connected", "Set up the extension once, then open Shorts."
    names = ", ".join(BROWSER_NAMES.get(b, b) for b in status.browsers)
    if status.ready:
        detail = "Shorts ready"
        if status.via_preview:
            detail += " · controlled from the app"
        if status.signed_in is False:
            detail += " · not signed in (no likes)"
        return "ok", f"Connected · {names}", detail
    return "ok", f"Connected · {names}", status.reason.capitalize() if status.reason else ""


def participants(status: CoopStatus) -> list[tuple[str, str, str]]:
    """(dot state, name, state) rows: you first, then your friend if there is one."""
    if status.role == "off":
        return [("ok", "You", "Watching on this computer")]
    rows: list[tuple[str, str, str]] = []
    if status.role == "host":
        rows.append(("ok", "You", "Host · your browser plays"))
        if status.peer is None:
            rows.append(("", "Friend", "Not connected yet"))
        elif status.pending_approval:
            rows.append(("warn", status.peer, "Waiting for your approval"))
        elif status.approved:
            control = "can swipe" if status.shared_control else "watching (control off)"
            rows.append(("ok", status.peer, f"Guest · {control}"))
        else:
            rows.append(("warn", status.peer, "Connected"))
        return rows
    if status.reconnecting:
        rows.append(("warn", "You", "Guest · reconnecting"))
    elif status.approved:
        rows.append(("ok", "You", "Guest · your swipes go to the host"))
    else:
        rows.append(("warn", "You", "Guest · waiting for the host"))
    rows.append(("ok" if status.approved else "", status.peer or "Host", "Host · plays the feed"))
    return rows


def _dot(state: str = "") -> QLabel:
    dot = QLabel("●")
    dot.setObjectName("statusDot")
    dot.setProperty("state", state)
    return dot


class BrowserSection(QWidget):
    setup_requested = Signal()
    stop_preview_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel("Browser")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.dot = _dot()
        row.addWidget(self.dot)
        self.headline = QLabel()
        self.headline.setObjectName("sectionValue")
        row.addWidget(self.headline, 1)
        layout.addLayout(row)
        self.detail = QLabel()
        self.detail.setObjectName("hint")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.preview = QLabel()
        self.preview.setObjectName("dimHint")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        actions = QHBoxLayout()
        self.setup_button = QPushButton("Setup and pairing")
        self.setup_button.setObjectName("linkButton")
        self.setup_button.setToolTip("Settings - Browser")
        self.setup_button.clicked.connect(self.setup_requested)
        actions.addWidget(self.setup_button)
        self.stop_preview = QPushButton("Stop preview")
        self.stop_preview.setObjectName("linkButton")
        self.stop_preview.setToolTip("End the tab capture in the browser")
        self.stop_preview.clicked.connect(self.stop_preview_requested)
        actions.addSpacing(14)
        actions.addWidget(self.stop_preview)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.state = "error"
        self.show_status(None, None)

    def show_status(self, status: YouTubeStatus | None, preview: PreviewStatus | None) -> None:
        state, headline, detail = browser_summary(status)
        if self.dot.property("state") != state:
            self.dot.setProperty("state", state)
            repolish(self.dot)
        self.state = state
        self.headline.setText(headline)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        connected = preview is not None and preview.connected
        if connected:
            self.preview.setText(f"Live preview on · {preview.fps:.0f} fps")
        elif preview is not None and preview.reason:
            self.preview.setText(f"Live preview off ({preview.reason})")
        else:
            self.preview.setText("Live preview off")
        self.stop_preview.setVisible(connected)


class TodaySection(QWidget):
    report_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel("Today")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        details = QPushButton("Report")
        details.setObjectName("linkButton")
        details.setToolTip("Daily report, eye analytics and Doomscroll Wrapped")
        details.clicked.connect(self.report_requested)
        header.addWidget(details)
        layout.addLayout(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(0)
        self.values: dict[str, QLabel] = {}
        for column, (key, caption) in enumerate(
            (("session", "this session"), ("scrolling", "scrolling today"), ("shorts", "Shorts"))
        ):
            value = QLabel("—")
            value.setObjectName("bigNumber")
            label = QLabel(caption)
            label.setObjectName("numberCaption")
            grid.addWidget(value, 0, column)
            grid.addWidget(label, 1, column)
            self.values[key] = value
        layout.addLayout(grid)
        self.note = QLabel()
        self.note.setObjectName("dimHint")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def show_values(self, session_s: float, report, note: str = "") -> None:  # type: ignore[no-untyped-def]
        self.values["session"].setText(short_duration(session_s) if session_s > 0 else "—")
        if report is None:
            self.values["scrolling"].setText("—")
            self.values["shorts"].setText("—")
        else:
            self.values["scrolling"].setText(f"{int(report.scrolling_s // 60)} min")
            shorts = report.done("next_short") + report.done("previous_short")
            self.values["shorts"].setText(str(shorts))
        self.note.setText(note)
        self.note.setVisible(bool(note))


class ParticipantsSection(QWidget):
    """You and (in Doomscroll Together) your friend, one line each."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(3)
        self.rows: list[tuple[QLabel, QLabel, QLabel]] = []
        for index in range(2):
            dot = _dot()
            name = QLabel()
            name.setObjectName("sectionValue")
            name.setTextFormat(Qt.TextFormat.PlainText)
            state = QLabel()
            state.setObjectName("hint")
            state.setTextFormat(Qt.TextFormat.PlainText)
            self.grid.addWidget(dot, index * 2, 0)
            self.grid.addWidget(name, index * 2, 1)
            self.grid.addWidget(state, index * 2 + 1, 1)
            self.rows.append((dot, name, state))
        self.grid.setColumnStretch(1, 1)
        self.show_status(CoopStatus(role="off", state="no session"))

    def show_status(self, status: CoopStatus) -> None:
        rows = participants(status)
        for index, (dot, name, state) in enumerate(self.rows):
            visible = index < len(rows)
            for widget in (dot, name, state):
                widget.setVisible(visible)
            if not visible:
                continue
            dot_state, text, detail = rows[index]
            if dot.property("state") != dot_state:
                dot.setProperty("state", dot_state)
                repolish(dot)
            name.setText(text)
            state.setText(detail)


class CollapsedStrip(QFrame):
    """The narrow strip shown instead of the panel: expand button and status dots."""

    expand_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionStrip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(12)
        self.expand_button = QPushButton("«")
        self.expand_button.setObjectName("flatButton")
        self.expand_button.setToolTip("Show Your session")
        self.expand_button.setAccessibleName("Show Your session")
        self.expand_button.clicked.connect(self.expand_requested)
        layout.addWidget(self.expand_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.together = _dot()
        self.together_count = QLabel("")
        self.together_count.setObjectName("dimHint")
        self.together_count.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.browser = _dot()
        for widget in (self.together, self.together_count, self.browser):
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def show_status(self, coop: CoopStatus, browser_state: str, browser_text: str) -> None:
        active = coop.role != "off"
        self.together.setVisible(active)
        self.together_count.setVisible(active)
        if active:
            state = "warn" if coop.reconnecting or coop.pending_approval else "ok"
            if not coop.approved and not coop.pending_approval and coop.role == "host":
                state = ""
            if self.together.property("state") != state:
                self.together.setProperty("state", state)
                repolish(self.together)
            people = 1 + (1 if coop.peer else 0)
            self.together_count.setText(str(people))
            tip = f"Doomscroll Together: {TogetherPanel._headline(coop)}"
            self.together.setToolTip(tip)
            self.together_count.setToolTip(tip)
        if self.browser.property("state") != browser_state:
            self.browser.setProperty("state", browser_state)
            repolish(self.browser)
        self.browser.setToolTip(f"Browser: {browser_text}")


class SessionPanel(QFrame):
    """Your session (expanded) or the collapsed strip; the window gives it its width."""

    expanded_changed = Signal(bool)

    def __init__(
        self, together: TogetherPanel, expanded: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sessionPanel")
        self.browser = BrowserSection()
        self.together = together
        self.today = TodaySection()
        self.people = ParticipantsSection()

        self.panel = QWidget()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(18, 12, 10, 4)
        title = QLabel("Your session")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.collapse_button = QPushButton("»")
        self.collapse_button.setObjectName("flatButton")
        self.collapse_button.setToolTip("Hide Your session (the session keeps running)")
        self.collapse_button.setAccessibleName("Hide Your session")
        self.collapse_button.clicked.connect(lambda: self.set_expanded(False))
        header.addWidget(self.collapse_button)
        panel_layout.addLayout(header)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 8, 18, 14)
        layout.setSpacing(14)
        layout.addWidget(self.people)
        layout.addWidget(separator())
        layout.addWidget(self.together)
        layout.addWidget(separator())
        layout.addWidget(self.today)
        layout.addWidget(separator())
        layout.addWidget(self.browser)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel_layout.addWidget(scroll, 1)

        self.strip = CollapsedStrip()
        self.strip.expand_requested.connect(lambda: self.set_expanded(True))
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.panel)
        outer.addWidget(self.strip)
        self.expanded = not expanded
        self.set_expanded(expanded, notify=False)

    def set_expanded(self, expanded: bool, notify: bool = True) -> None:
        if expanded == self.expanded:
            return
        self.expanded = expanded
        self.panel.setVisible(expanded)
        self.strip.setVisible(not expanded)
        if expanded:
            self.setMinimumWidth(MIN_WIDTH)
            self.setMaximumWidth(MAX_WIDTH)
        else:
            self.setFixedWidth(STRIP_WIDTH)
        if notify:
            self.expanded_changed.emit(expanded)

    def show_coop(self, status: CoopStatus) -> None:
        self.together.show_status(status)
        self.people.show_status(status)
        self.strip.show_status(status, self.browser.state, self.browser.headline.text())


class PanelDialog(QDialog):
    """A non-modal dialog that hosts existing panels (the daily report)."""

    def __init__(self, title: str, panels: list[QWidget], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        for panel in panels:
            layout.addWidget(panel)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.setContentsMargins(16, 0, 16, 12)
        row.addStretch(1)
        row.addWidget(close)
        outer.addLayout(row)
        self.resize(440, 600)
