"""First-use guide: what the app does and the four steps to control YouTube Shorts (Brief 007).

Shown once on the first start (and from the Help button). It explains only what a new user
needs - camera, browser extension and pairing, optional practice, Live control and how to stop
it - and links to the existing actions instead of duplicating them. Calibration is optional.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.ui.youtube_panel import EXTENSION_DIR

GESTURES = (
    ("Move your hand UP", "next Short"),
    ("Move your hand DOWN", "previous Short"),
    ("Move to YOUR RIGHT / LEFT", "next / previous browser tab"),
    ("Half-heart (one hand)", "like the Short"),
    ("Open palm, held still", "pause / play"),
)


class GettingStartedDialog(QDialog):
    start_camera_requested = Signal()
    practice_requested = Signal()
    browser_tab_requested = Signal()

    def __init__(self, pairing_code: str, hotkey: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Getting started")
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        intro = QLabel(
            "<b>Interactive Scrolling</b> lets you scroll YouTube Shorts with hand movements in "
            "front of your webcam. The camera image is processed on this computer only; no "
            "frames leave it."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        stop = "the Stop control button or Esc" + (f", or {hotkey} anywhere" if hotkey else "")
        steps = (
            (
                "1  Start the camera",
                "The camera is needed to see your hand. Nothing is recorded.",
                "Start camera",
                self.start_camera_requested,
            ),
            (
                "2  Connect the browser",
                "Microsoft Edge (or Chrome): open edge://extensions, switch on Developer mode, "
                f"choose Load unpacked and select the folder {EXTENSION_DIR.name} (the Browser tab "
                "copies its full path). Click the extension "
                "icon and paste the pairing code. The Browser tab shows when it is connected.",
                "Copy pairing code",
                None,
            ),
            (
                "3  Practice (optional, about a minute)",
                "Swipe in front of the camera; Practice tells you after each try whether it was "
                "recognized and why not. Nothing is sent to the browser while you practise.",
                "Open Practice",
                self.practice_requested,
            ),
            (
                "4  Switch on Live control",
                "Open YouTube Shorts in the browser and choose Live control at the top. To stop "
                f"at once: {stop}.",
                None,
                None,
            ),
        )
        for title, text, button_text, signal in steps:
            card = QFrame()
            card.setObjectName("card")
            layout = QHBoxLayout(card)
            texts = QVBoxLayout()
            heading = QLabel(title)
            heading.setObjectName("cardTitle")
            body = QLabel(text)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            texts.addWidget(heading)
            texts.addWidget(body)
            layout.addLayout(texts, 1)
            if button_text:
                button = QPushButton(button_text)
                if signal is not None:
                    button.clicked.connect(signal.emit)
                else:
                    button.clicked.connect(
                        lambda _=False, code=pairing_code: QApplication.clipboard().setText(code)
                    )
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
            root.addWidget(card)

        table = QLabel(
            "<b>Gestures</b> (any hand shape; hold the hand still for a moment, move, then let "
            "it come back):<br>"
            + "<br>".join(f"{move} &rarr; {action}" for move, action in GESTURES)
            + "<br><span style='color:#8b949e'>A pointing-finger flick works too. If swipes "
            "happen by accident while you use your hands for other things, choose Gesture "
            "settings &gt; Swipe with &gt; Pointing finger only.</span>"
        )
        table.setWordWrap(True)
        root.addWidget(table)

        bottom = QHBoxLayout()
        self.dont_show = QCheckBox("Don't show this at start")
        self.dont_show.setChecked(True)
        bottom.addWidget(self.dont_show, 1)
        close = QPushButton("Close")
        close.setObjectName("primaryButton")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        root.addLayout(bottom)
