"""Diagnostics: the collapsible technical console at the bottom of Studio Mode.

Collapsed, it is one line: the live performance figures and the latest action. Expanded, it
shows the gesture history and log, the recognition state, performance and tracking figures,
and browser / preview / Doomscroll Together diagnostics. The application works the same in
both states; the gesture safety state is always visible in the strip under the camera.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

EXPANDED_HEIGHT = 230


def _scroll(widgets: list[QWidget], horizontal: bool = False) -> QScrollArea:
    page = QWidget()
    layout = QHBoxLayout(page) if horizontal else QVBoxLayout(page)
    layout.setContentsMargins(4, 6, 4, 6)
    layout.setSpacing(18)
    for widget in widgets:
        layout.addWidget(widget, 1 if horizontal else 0)
    layout.addStretch(0 if horizontal else 1)
    scroll = QScrollArea()
    scroll.setWidget(page)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    return scroll


class DiagnosticsConsole(QFrame):
    expanded_changed = Signal(bool)
    copy_requested = Signal()

    def __init__(
        self,
        stat_labels: list[QLabel],
        history: QWidget,
        recognition: QWidget,
        performance: list[QWidget],
        connections: list[QWidget],
        expanded: bool = False,
        camera: list[QWidget] | None = None,
        eyes: list[QWidget] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("console")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 4, 16, 6)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.toggle = QPushButton()
        self.toggle.setObjectName("flatButton")
        self.toggle.clicked.connect(lambda: self.set_expanded(not self.expanded))
        header.addWidget(self.toggle)
        stats = QWidget()
        stats.setObjectName("consoleStats")
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(14)
        for label in stat_labels:
            stats_layout.addWidget(label)
        stats_layout.addStretch(1)
        header.addWidget(stats, 1)
        self.copy_button = QPushButton("Copy diagnostics")
        self.copy_button.setObjectName("flatButton")
        self.copy_button.setToolTip(
            "Copy a report for a problem description (no images, URLs, codes or tokens)"
        )
        self.copy_button.clicked.connect(self.copy_requested)
        header.addWidget(self.copy_button)
        root.addLayout(header)

        self.activity_log = QPlainTextEdit()
        self.activity_log.setObjectName("activityLog")
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumBlockCount(500)
        activity = QSplitter(Qt.Orientation.Horizontal)
        activity.setChildrenCollapsible(False)
        activity.addWidget(history)
        activity.addWidget(self.activity_log)
        activity.setSizes([500, 500])

        self.tabs = QTabWidget()
        self.tabs.addTab(activity, "Activity")
        self.tabs.addTab(_scroll([recognition]), "Recognition")
        if camera:
            self.tabs.addTab(_scroll(camera), "Camera")
        self.tabs.addTab(_scroll(performance, horizontal=True), "Performance")
        if eyes:
            self.tabs.addTab(_scroll(eyes), "Eye tracking")
        self.tabs.addTab(_scroll(connections, horizontal=True), "Browser and Together")
        root.addWidget(self.tabs)
        self.expanded = not expanded
        self.set_expanded(expanded, notify=False)

    def set_expanded(self, expanded: bool, notify: bool = True) -> None:
        if expanded == self.expanded:
            return
        self.expanded = expanded
        self.tabs.setVisible(expanded)
        self.toggle.setText("▾  Diagnostics" if expanded else "▸  Diagnostics")
        self.toggle.setToolTip(
            "Hide the technical details"
            if expanded
            else "Show gesture history, log, recognition, performance and connection details"
        )
        self.setFixedHeight(EXPANDED_HEIGHT if expanded else self.sizeHint().height())
        if notify:
            self.expanded_changed.emit(expanded)

    @property
    def showing(self) -> bool:
        """Expanded and on screen: only then are the detail tabs refreshed."""
        return self.expanded and self.isVisible()

    def current_tab(self) -> str:
        return self.tabs.tabText(self.tabs.currentIndex())

    def sizeHint(self):  # type: ignore[no-untyped-def]
        hint = super().sizeHint()
        if not getattr(self, "expanded", True):
            margins = self.layout().contentsMargins()
            hint.setHeight(self.toggle.sizeHint().height() + margins.top() + margins.bottom())
        return hint
