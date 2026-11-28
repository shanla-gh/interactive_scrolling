"""The right-hand column of Normal Mode: browser connection, Doomscroll Together, today.

Each part is a few lines of plain text with one or two actions; details open in dialogs
(browser pairing and setup, the full daily report) or live in the diagnostics console.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
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

from interactive_scrolling.integrations.youtube.controller import YouTubeStatus
from interactive_scrolling.integrations.youtube.preview import PreviewStatus
from interactive_scrolling.ui.theme import repolish
from interactive_scrolling.ui.together import TogetherPanel

BROWSER_NAMES = {"edge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium"}


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
        self.dot = QLabel("●")
        self.dot.setObjectName("statusDot")
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
        self.show_status(None, None)

    def show_status(self, status: YouTubeStatus | None, preview: PreviewStatus | None) -> None:
        state, headline, detail = browser_summary(status)
        self.dot.setProperty("state", state)
        repolish(self.dot)
        self.headline.setText(headline)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        connected = preview is not None and preview.connected
        if connected:
            self.preview.setText("Live preview on")
        else:
            self.preview.setText("")
        self.preview.setVisible(connected)
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
        details.setToolTip("Daily report, limits and reminders, eye analytics, Wrapped")
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


class SessionPanel(QFrame):
    """Browser, Doomscroll Together and Today, stacked with thin separators."""

    def __init__(self, together: TogetherPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sessionPanel")
        self.browser = BrowserSection()
        self.together = together
        self.today = TodaySection()
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)
        layout.addWidget(self.browser)
        layout.addWidget(separator())
        layout.addWidget(self.together)
        layout.addWidget(separator())
        layout.addWidget(self.today)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


class PanelDialog(QDialog):
    """A non-modal dialog that hosts existing panels (setup, reports, recognition)."""

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
        self.resize(420, 560)
