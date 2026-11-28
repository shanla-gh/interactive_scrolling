"""The desktop window driven through Qt with a synthetic camera and a scripted tracker."""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import Qt

from interactive_scrolling.config.settings import AppSettings, CameraSettings
from interactive_scrolling.core.pipeline import CameraState, TrackerState
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.vision.camera import CameraInfo
from tests.helpers import ScriptedTracker, SyntheticCamera, camera_factory, make_hand


def fps_value(text: str) -> float:
    match = re.search(r"([0-9]+\.[0-9]) FPS", text)
    assert match, text
    return float(match.group(1))


def hand_script(ms: int):
    x = 100 + (ms % 3000) * 0.15
    return (make_hand((x, 380), palm_px=80),)


@pytest.fixture(autouse=True)
def _reset_cameras() -> None:
    SyntheticCamera.instances.clear()


def make_window(qtbot, **camera) -> MainWindow:
    settings = AppSettings(camera=CameraSettings(width=640, height=480))
    window = MainWindow(
        settings,
        camera_factory=camera_factory(fps=60, **camera),
        tracker_factory=lambda: ScriptedTracker(hand_script),
        probe_cameras=lambda: [CameraInfo(0, 640, 480), CameraInfo(2, 1280, 720)],
    )
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.pipeline.tracker_state is TrackerState.READY, timeout=5000)
    return window


def start(qtbot, window: MainWindow) -> None:
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.video.frame is not None, timeout=5000)


def test_initial_state(qtbot) -> None:
    window = make_window(qtbot)
    assert window.status_pill.text() == "●  Camera off"
    assert window.start_button.text() == "Start camera"
    assert window.video.frame is None
    assert window.resolution_combo.currentText() == "640x480"
    assert window.tracking_panel.state.text() == "Inactive"


def test_live_frames_update_view_and_panels(qtbot) -> None:
    window = make_window(qtbot)
    # Brief 010: the detail panels refresh only while the diagnostics console shows them.
    window.console.set_expanded(True)
    start(qtbot, window)
    assert window.status_pill.text() == "●  Camera on"
    assert window.start_button.text() == "Stop camera"
    assert not window.camera_combo.isEnabled() and not window.resolution_combo.isEnabled()
    qtbot.waitUntil(lambda: window.tracking_panel.hands.text() == "1", timeout=3000)
    assert window.tracking_panel.landmarks.text().startswith("21")
    assert "Right" in window.tracking_panel.handedness.text()
    qtbot.waitUntil(
        lambda: "palms/s" in window.motion_panel.blocks[0].tip_speed.text(), timeout=3000
    )
    qtbot.waitUntil(lambda: fps_value(window.capture_fps_label.text()) > 10, timeout=3000)
    qtbot.waitUntil(lambda: fps_value(window.processing_fps_label.text()) > 10, timeout=3000)
    assert (
        window.latency_label.text().startswith("LATENCY ") and "ms" in window.latency_label.text()
    )


def test_overlay_and_mirror_controls_change_state(qtbot) -> None:
    window = make_window(qtbot)
    panel = window.overlay_panel
    panel.checkboxes["show_skeleton"].setChecked(False)
    assert window.settings.overlay.show_skeleton is False
    assert window.video.overlay.show_skeleton is False
    panel.checkboxes["show_palm_trail"].setChecked(True)
    assert window.video.overlay.show_palm_trail is True
    assert window.video.mirrored
    panel.mirror.setChecked(False)
    assert not window.video.mirrored and not window.settings.mirror_preview


def test_stop_clears_view_and_releases_camera(qtbot) -> None:
    window = make_window(qtbot)
    start(qtbot, window)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.pipeline.camera_state is CameraState.STOPPED, timeout=5000)
    qtbot.waitUntil(lambda: window.status_pill.text() == "●  Camera off", timeout=2000)
    assert window.video.frame is None
    assert window.tracking_panel.state.text() == "Inactive"
    assert SyntheticCamera.instances[-1].close_calls == 1
    # Late frames from the stopped session must not reappear.
    qtbot.wait(150)
    assert window.video.frame is None


def test_repeated_start_stop_from_ui(qtbot) -> None:
    window = make_window(qtbot)
    for _ in range(5):
        start(qtbot, window)
        qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.status_pill.text() == "●  Camera off", timeout=5000)
    assert len(SyntheticCamera.instances) == 5
    assert all(c.close_calls == 1 for c in SyntheticCamera.instances)


def test_camera_error_is_shown_and_recoverable(qtbot) -> None:
    window = make_window(qtbot, fail_open=True)
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.status_pill.text() == "●  Camera error", timeout=5000)
    assert window.start_button.isEnabled() and window.start_button.text() == "Start camera"
    assert window.camera_combo.isEnabled()
    qtbot.waitUntil(
        lambda: "Could not open camera" in window.activity_log.toPlainText(), timeout=2000
    )


def test_scan_populates_camera_list(qtbot) -> None:
    window = make_window(qtbot)
    qtbot.mouseClick(window.scan_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.camera_combo.count() == 2, timeout=3000)
    assert window.camera_combo.itemData(1) == 2
    assert "1280x720" in window.camera_combo.itemText(1)
    window.camera_combo.setCurrentIndex(1)
    assert window.requested_camera_settings().index == 2


def test_resizing_keeps_video_aspect_ratio(qtbot) -> None:
    window = make_window(qtbot)
    start(qtbot, window)
    for size in [(1000, 660), (1700, 1000), (1200, 700)]:
        window.resize(*size)
        qtbot.wait(50)
        t = window.video.current_transform()
        assert t is not None
        assert t.width / t.height == pytest.approx(640 / 480)
        assert t.width <= window.video.width() + 1e-6 and t.height <= window.video.height() + 1e-6


def test_missing_model_keeps_preview_and_reports(qtbot) -> None:
    def failing():
        raise FileNotFoundError("Hand landmarker model not found")

    window = MainWindow(
        AppSettings(camera=CameraSettings(width=640, height=480)),
        camera_factory=camera_factory(),
        tracker_factory=failing,
    )
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.pipeline.tracker_state is TrackerState.UNAVAILABLE, timeout=3000)
    # The panel is updated through a queued signal after the worker changed its state.
    qtbot.waitUntil(lambda: window.tracking_panel.model.text() == "Unavailable", timeout=3000)
    start(qtbot, window)
    assert window.video.frame.tracking.hand_count == 0


def test_close_shuts_down_pipeline(qtbot) -> None:
    window = make_window(qtbot)
    start(qtbot, window)
    window.close()
    camera = SyntheticCamera.instances[-1]
    assert camera.close_calls == 1 and not camera.opened
    assert window.pipeline.camera_state is CameraState.STOPPED
