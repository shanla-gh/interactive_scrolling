"""Defect: the configured default resolution (1280x720) was ignored; 640x480 was requested.

Found during CP 1.5 live verification. ``QComboBox.findData`` cannot match Python tuples,
so the lookup returned -1 and the first entry was selected. Fix: select by list position.
"""

from __future__ import annotations

from interactive_scrolling.config.settings import AppSettings, CameraSettings
from interactive_scrolling.ui.main_window import MainWindow
from tests.helpers import camera_factory


def test_default_resolution_is_preselected(qtbot) -> None:
    window = MainWindow(
        AppSettings(),
        camera_factory=camera_factory(),
        tracker_factory=None,
    )
    qtbot.addWidget(window)
    assert window.resolution_combo.currentText() == "1280x720"
    assert (
        window.requested_camera_settings().width,
        window.requested_camera_settings().height,
    ) == (
        1280,
        720,
    )


def test_non_standard_resolution_is_added_and_selected(qtbot) -> None:
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=800, height=600)),
        camera_factory=camera_factory(),
        tracker_factory=None,
    )
    qtbot.addWidget(window)
    assert window.resolution_combo.currentText() == "800x600"
    assert window.requested_camera_settings().width == 800
