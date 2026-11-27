"""Defect: the diagnostics bar was empty until the first timer tick after launch.

Found during CP 1.5 UI testing. Fix: diagnostics are rendered once at construction.
"""

from __future__ import annotations

from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.ui.main_window import MainWindow
from tests.helpers import camera_factory


def test_diagnostics_are_populated_immediately(qtbot) -> None:
    window = MainWindow(AppSettings(), camera_factory=camera_factory(), tracker_factory=None)
    qtbot.addWidget(window)
    assert window.capture_fps_label.text().startswith("CAM")
    assert window.processing_fps_label.text().startswith("PROC")
    assert window.latency_label.text().startswith("LATENCY")
    assert window.resources_label.text().startswith("CPU")
