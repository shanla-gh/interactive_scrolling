"""Defect: the activity log stayed empty when the console log level was above INFO.

Found during CP 1.5 visual review: INFO records were filtered by the logger level before
reaching the UI handler. Fix: the window ensures the package logger passes INFO records;
console handlers apply the requested console level themselves.
"""

from __future__ import annotations

import logging

from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.ui.main_window import MainWindow
from tests.helpers import camera_factory


def test_activity_log_receives_info_with_quiet_console(qtbot) -> None:
    package = logging.getLogger("interactive_scrolling")
    root = logging.getLogger()
    saved = (package.level, root.level)
    package.setLevel(logging.NOTSET)
    root.setLevel(logging.WARNING)
    try:
        window = MainWindow(AppSettings(), camera_factory=camera_factory(), tracker_factory=None)
        qtbot.addWidget(window)
        qtbot.waitUntil(lambda: "started" in window.activity_log.toPlainText(), timeout=2000)
        logging.getLogger("interactive_scrolling.test").info("visible in activity log")
        qtbot.waitUntil(
            lambda: "visible in activity log" in window.activity_log.toPlainText(), timeout=2000
        )
    finally:
        package.setLevel(saved[0])
        root.setLevel(saved[1])
