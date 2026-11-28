"""Gesture control in the desktop window: modes, live feedback, history, settings, statistics."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
)
from interactive_scrolling.config.settings import AppSettings, CameraSettings, SensitivityPreset
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.services import ControlServices
from interactive_scrolling.storage.analytics import AnalyticsStore
from interactive_scrolling.storage.settings_store import SettingsStore
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog
from tests.gesture_helpers import POINTING, make_observation
from tests.helpers import ScriptedTracker, SyntheticCamera, camera_factory

W, H = 640, 480


class SwipeScript:
    """A pointing hand that rests, swipes up (next Short), rests, and repeats every 3 s."""

    def __init__(self) -> None:
        self.t0: int | None = None

    def __call__(self, ms: int):
        if self.t0 is None:
            self.t0 = ms
        t = ((ms - self.t0) / 1000.0) % 3.0
        y = 300.0 if t < 1.2 else 300.0 - min(1.0, (t - 1.2) / 0.25) * 120.0
        return (make_observation_scaled((320.0, y)),)


def make_observation_scaled(wrist):
    obs = make_observation(POINTING, wrist, palm_px=80.0)
    # make_observation normalizes for 1280x720; rescale to the 640x480 synthetic camera.
    obs.landmarks[:, 0] *= 1280 / W
    obs.landmarks[:, 1] *= 720 / H
    obs.landmarks[:, 2] *= 1280 / W
    return obs


class FakeController:
    def __init__(self) -> None:
        self.executed: list[ActionType] = []

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(True)

    def execute(self, action, request_id, timeout_s) -> ActionResult:
        self.executed.append(action)
        return ActionResult(ActionStatus.SUCCEEDED, "", "active Short changed")

    def cancel_all(self) -> None:
        pass

    def status(self):
        return None


@pytest.fixture(autouse=True)
def _reset_cameras() -> None:
    SyntheticCamera.instances.clear()


def make_window(qtbot, tmp_path: Path, controller=None) -> tuple[MainWindow, ControlServices]:
    store = SettingsStore(tmp_path / "settings.json")
    user = store.load()
    services = ControlServices(
        engine=GestureEngine(user.gestures),
        dispatcher=ActionDispatcher(controller, user.mapping),
        user_settings=user,
        store=store,
        analytics=AnalyticsStore(tmp_path / "analytics.sqlite3"),
    )
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=W, height=H)),
        camera_factory=camera_factory(fps=60),
        tracker_factory=lambda: ScriptedTracker(SwipeScript()),
        services=services,
    )
    qtbot.addWidget(window)
    window.show()
    return window, services


def start(qtbot, window: MainWindow) -> None:
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.video.frame is not None, timeout=5000)


def test_starts_in_tracking_only_without_recognition(qtbot, tmp_path) -> None:
    window, services = make_window(qtbot, tmp_path)
    assert services.dispatcher.mode is ControlMode.TRACKING_ONLY
    assert window.control_bar.buttons[ControlMode.TRACKING_ONLY].isChecked()
    assert not window.control_bar.disable_button.isEnabled()
    start(qtbot, window)
    qtbot.wait(2500)
    assert window.video.frame.gestures is None
    assert window.history.rowCount() == 0


def test_gesture_test_mode_shows_and_logs_gestures_without_executing(qtbot, tmp_path) -> None:
    controller = FakeController()
    window, services = make_window(qtbot, tmp_path, controller)
    start(qtbot, window)
    qtbot.mouseClick(
        window.control_bar.buttons[ControlMode.GESTURE_TEST], Qt.MouseButton.LeftButton
    )
    assert services.dispatcher.mode is ControlMode.GESTURE_TEST
    qtbot.waitUntil(lambda: window.history.rowCount() >= 1, timeout=8000)
    assert window.history.item(0, 1).text() == "SWIPE UP"
    assert window.history.item(0, 2).text() == "Next Short"
    assert window.history.item(0, 3).text().startswith("not executed")
    assert window.gesture_panel.last.text() == "SWIPE UP"
    assert controller.executed == []
    assert window.video._banner is not None or window.history.rowCount() >= 1


def test_live_control_executes_and_reports_confirmed_outcome(qtbot, tmp_path) -> None:
    controller = FakeController()
    window, _services = make_window(qtbot, tmp_path, controller)
    start(qtbot, window)
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    qtbot.waitUntil(lambda: bool(controller.executed), timeout=8000)
    qtbot.waitUntil(
        lambda: (
            "succeeded" in (window.history.item(0, 3).text() if window.history.rowCount() else "")
        ),
        timeout=3000,
    )
    assert controller.executed[0] is ActionType.NEXT_SHORT
    assert "succeeded" in window.control_bar.last_chip.text()
    # Brief 010 feedback block: recognized gesture, requested action, verified outcome.
    assert window.control_bar.feedback_labels["outcome"].text() == "Successful"
    assert window.control_bar.feedback_labels["action"].text() != "—"
    assert window.control_bar.property("live") is True


def test_emergency_disable_stops_control_immediately(qtbot, tmp_path) -> None:
    controller = FakeController()
    window, services = make_window(qtbot, tmp_path, controller)
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    qtbot.mouseClick(window.control_bar.disable_button, Qt.MouseButton.LeftButton)
    assert services.dispatcher.mode is ControlMode.TRACKING_ONLY
    qtbot.waitUntil(lambda: window.control_bar.buttons[ControlMode.TRACKING_ONLY].isChecked())
    window.set_control_mode(ControlMode.GESTURE_TEST)
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=2000)
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert services.dispatcher.mode is ControlMode.TRACKING_ONLY


def test_settings_dialog_changes_recognition_and_persists(qtbot, tmp_path) -> None:
    window, services = make_window(qtbot, tmp_path)
    dialog = GestureSettingsDialog(services.engine.settings, services.dispatcher.mapping, window)
    qtbot.addWidget(dialog)
    dialog.preset.setCurrentIndex(dialog.preset.findData(SensitivityPreset.LOW))
    dialog.enables["enable_stop"].setChecked(False)
    dialog.mapping_boxes[next(iter(dialog.mapping_boxes))].setCurrentIndex(0)  # first row -> none
    assert dialog.result_settings().preset is SensitivityPreset.LOW
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    services.apply_gesture_settings(dialog.result_settings())
    services.apply_mapping(dialog.result_mapping())
    reloaded = SettingsStore(tmp_path / "settings.json").load()
    assert reloaded.gestures.preset is SensitivityPreset.LOW
    assert reloaded.gestures.enable_stop is False
    assert reloaded.mapping[next(iter(dialog.mapping_boxes))] is ActionType.NONE
    assert services.dispatcher.mapping[next(iter(dialog.mapping_boxes))] is ActionType.NONE


def test_restore_defaults_in_dialog(qtbot, tmp_path) -> None:
    window, services = make_window(qtbot, tmp_path)
    dialog = GestureSettingsDialog(services.engine.settings, services.dispatcher.mapping, window)
    qtbot.addWidget(dialog)
    dialog.spins["stop_hold_s"].setValue(2.5)
    assert dialog.result_settings().preset is SensitivityPreset.CUSTOM
    dialog.restore_defaults()
    assert dialog.result_settings().stop_hold_s == pytest.approx(0.8)
    assert dialog.result_settings().preset is SensitivityPreset.BALANCED


def test_daily_statistics_reflect_real_events(qtbot, tmp_path) -> None:
    controller = FakeController()
    window, services = make_window(qtbot, tmp_path, controller)
    start(qtbot, window)
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    qtbot.waitUntil(lambda: bool(controller.executed), timeout=8000)
    window.set_control_mode(ControlMode.TRACKING_ONLY)
    services.analytics.flush()
    window._stats_tick = 0
    window._update_control_status()
    window.services.refresh_reports()
    window._update_control_status()
    assert int(window.today_panel.gestures.text()) >= 1
    assert window.today_panel.navigation.text().startswith("1")


def test_youtube_panel_without_controller(qtbot, tmp_path) -> None:
    window, _ = make_window(qtbot, tmp_path)
    window._update_control_status()
    # Brief 008: the browser state moved from the control bar to the session panel.
    assert "not available" in window.session_panel.browser.headline.text()
