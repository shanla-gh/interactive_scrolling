"""YouTube connection, setup and daily statistics panels."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

from interactive_scrolling.integrations.youtube.controller import YouTubeStatus
from interactive_scrolling.storage.analytics import DailyStats
from interactive_scrolling.ui.panels import NO_DATA, Card

EXTENSION_DIR = (
    Path(getattr(sys, "_MEIPASS", "")) / "browser_extension"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3] / "browser_extension"
)
"""The unpacked extension: next to the source tree, or inside a packaged build."""


def _bool(value: bool | None, yes: str, no: str) -> str:
    return NO_DATA if value is None else (yes if value else no)


class YouTubePanel(Card):
    def __init__(self, pairing_code: str, port: int, parent: QWidget | None = None) -> None:
        super().__init__("YouTube Shorts", parent)
        self.bridge = self.add_row("Bridge", accent=True)
        self.browser = self.add_row("Browser")
        self.context = self.add_row("Shorts", accent=True)
        self.signed_in = self.add_row("Signed in")
        self.playback = self.add_row("Playback")
        for label in (self.bridge, self.context):
            label.setWordWrap(True)
        self.add_heading("Pairing")
        self.pairing_code = pairing_code
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.code_label = QLabel("•" * 12)
        self.code_label.setObjectName("rowValue")
        layout.addWidget(self.code_label, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self.code_label.setText(self.pairing_code if on else "•" * 12)
        )
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.pairing_code))
        layout.addWidget(show)
        layout.addWidget(copy)
        self.add_widget(row)
        setup = QLabel(
            f"One-time setup: open edge://extensions (or chrome://extensions), enable "
            f"Developer mode, choose <b>Load unpacked</b> and select the folder "
            f"<b>{EXTENSION_DIR.name}</b> (copy its full path below). Then click the extension "
            f"icon, paste the pairing code and keep port {port}. After an update, press "
            f"<b>Reload</b> on the extension in the same page."
        )
        setup.setWordWrap(True)
        setup.setObjectName("rowKey")
        self.add_widget(setup)
        folder = QPushButton("Copy extension folder path")
        folder.setToolTip(str(EXTENSION_DIR))
        folder.clicked.connect(lambda: QGuiApplication.clipboard().setText(str(EXTENSION_DIR)))
        self.add_widget(folder)

    def show_status(self, status: YouTubeStatus | None) -> None:
        if status is None:
            self.bridge.setText("not available")
            return
        if not status.listening:
            self.bridge.setText(f"not running ({status.bridge_error or 'stopped'})")
        else:
            n = status.connections
            self.bridge.setText(f"listening, {n} browser{'s' if n != 1 else ''} connected")
        self.browser.setText(", ".join(status.browsers) or NO_DATA)
        self.context.setText(
            f"ready ({status.target_browser})" if status.ready else status.reason or NO_DATA
        )
        self.signed_in.setText(_bool(status.signed_in, "yes", "no (liking unavailable)"))
        self.playback.setText(_bool(status.paused, "paused", "playing"))


class StatsPanel(Card):
    clear_requested = Signal()
    enabled_changed = Signal(bool)

    def __init__(self, enabled: bool, parent: QWidget | None = None) -> None:
        super().__init__("Today", parent)
        self.gestures = self.add_row("Confirmed gestures", accent=True)
        self.swipes = self.add_row("Swipes down / up")
        self.navigation = self.add_row("Next / previous done")
        self.likes = self.add_row("Likes done")
        self.playback = self.add_row("Pause/resume done")
        self.problems = self.add_row("Rejected / failed")
        self.shorts = self.add_row(
            "Shorts tab visible",
            "Time a supported YouTube Shorts tab was visible and connected. "
            "This is not watch time or attention.",
        )
        self.enabled = QCheckBox("Keep local statistics")
        self.enabled.setChecked(enabled)
        self.enabled.setToolTip("Stored only on this computer. Contains no video or page data.")
        self.enabled.toggled.connect(self.enabled_changed)
        self.add_widget(self.enabled)
        clear = QPushButton("Clear statistics")
        clear.clicked.connect(self.clear_requested)
        self.add_widget(clear)
        self.error = QLabel("")
        self.error.setObjectName("rowKey")
        self.error.setWordWrap(True)
        self.add_widget(self.error)

    def show_stats(self, stats: DailyStats | None, error: str | None = None) -> None:
        self.error.setText(error or "")
        if stats is None:
            return
        g = stats.gestures
        s = stats.succeeded
        self.gestures.setText(str(stats.gestures_confirmed))
        down = g.get("index_swipe_down", 0) + g.get("finger_swipe_down", 0)
        up = g.get("index_swipe_up", 0) + g.get("finger_swipe_up", 0)
        self.swipes.setText(f"{down} / {up}")
        self.navigation.setText(f"{s.get('next_short', 0)} / {s.get('previous_short', 0)}")
        self.likes.setText(f"{s.get('like_short', 0)}  (already liked: {stats.no_change})")
        self.playback.setText(str(s.get("toggle_playback", 0)))
        self.problems.setText(f"{stats.rejected} / {stats.failed + stats.unknown}")
        minutes, seconds = divmod(int(stats.shorts_visible_s), 60)
        self.shorts.setText(f"{minutes} min {seconds:02d} s")
