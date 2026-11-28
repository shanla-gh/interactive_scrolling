"""Normal Mode redesign (Brief 008): top bar, gesture strip, session panel, console, Broadcast
settings and the Now playing column."""

from __future__ import annotations

from dataclasses import replace

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.services import offline_services
from interactive_scrolling.ui.main_window import MainWindow
from tests.helpers import camera_factory
from tests.integration.test_ui_modes import FakeSegmenter


def make_window(qtbot, services=None, segmenter=True) -> MainWindow:  # type: ignore[no-untyped-def]
    window = MainWindow(
        AppSettings(),
        camera_factory=camera_factory(),
        tracker_factory=None,
        services=services or offline_services(),
        segmenter_factory=FakeSegmenter if segmenter else None,
    )
    qtbot.addWidget(window)
    window.resize(1366, 728)
    window.show()
    return window


def test_top_bar_holds_only_the_essentials(qtbot) -> None:
    window = make_window(qtbot)
    bar = window.start_button.parentWidget()
    buttons = sorted(b.text() for b in bar.findChildren(type(window.start_button)))
    assert buttons == ["Broadcast", "Camera settings", "Normal", "Start camera"]
    assert window.more_button.text() == "More"
    # Camera device, resolution and scan live in Camera settings, not permanently on screen.
    assert window.camera_combo.window() is window.camera_dialog
    assert not window.camera_dialog.isVisible()


def test_gesture_control_stays_visible_and_safe(qtbot) -> None:
    window = make_window(qtbot)
    strip = window.control_bar
    assert strip.isVisible() and strip.buttons[ControlMode.TRACKING_ONLY].isChecked()
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    qtbot.waitUntil(lambda: strip.property("live") is True)
    assert strip.state.text() == "Gestures control YouTube"
    assert strip.disable_button.isEnabled()
    # Changing the presentation mode never changes the control mode.
    window.set_ui_mode("creator")
    window.set_ui_mode("developer")
    assert window.services.dispatcher.mode is ControlMode.LIVE_CONTROL
    window.emergency_disable()
    qtbot.waitUntil(lambda: strip.buttons[ControlMode.TRACKING_ONLY].isChecked())
    assert window.services.dispatcher.mode is ControlMode.TRACKING_ONLY


def test_camera_settings_frame_rate_is_requested(qtbot) -> None:
    window = make_window(qtbot)
    dialog = window.camera_dialog
    dialog.fps_combo.setCurrentIndex(dialog.fps_combo.findData(15))
    assert window.requested_camera_settings().fps == 15


def test_console_collapse_state_is_remembered(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    assert not window.console.expanded
    window.console.toggle.click()
    assert window.console.expanded and window.console.tabs.isVisible()
    assert services.user_settings.appearance.console_expanded is True
    window.console.toggle.click()
    assert services.user_settings.appearance.console_expanded is False


def test_hiding_now_playing_is_remembered_and_stops_the_capture(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    stops: list[bool] = []
    window.stop_preview = lambda: stops.append(True)  # type: ignore[method-assign]
    window.now_playing_action.setChecked(False)
    assert not window.now_playing.isVisible()
    assert services.user_settings.appearance.show_now_playing is False
    assert stops == [True]
    window.now_playing_action.setChecked(True)
    assert window.now_playing.isVisible()


def test_transparent_background_is_one_click_away_in_broadcast_settings(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.set_ui_mode("creator")
    window.creator.settings_requested.emit()  # the overlay's Settings button / menu entry
    dialog = window._dialogs["broadcast"]
    assert dialog.isVisible() and dialog.transparent.isEnabled()
    dialog.transparent.setChecked(True)
    assert window.creator.settings.transparent_background is True
    assert services.user_settings.creator.transparent_background is True
    dialog.layers["show_vectors"].setChecked(True)
    assert window.creator.settings.show_vectors is True
    assert window.creator.settings.transparent_background is True  # independent options


def test_broadcast_settings_reachable_from_more_menu_and_tray(qtbot) -> None:
    window = make_window(qtbot)
    texts = [a.text() for a in window.more_menu.actions()]
    assert "Broadcast settings..." in texts
    tray = [a.text() for a in window.tray.menu.actions()]
    assert "Broadcast settings..." in tray and "Normal Mode" in tray


def test_broadcast_settings_without_segmentation_explains_why(qtbot) -> None:
    window = make_window(qtbot, segmenter=False)
    window.open_broadcast_settings()
    dialog = window._dialogs["broadcast"]
    assert not dialog.transparent.isEnabled()


def test_clown_controls_apply_to_the_effect(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.open_broadcast_settings()
    dialog = window._dialogs["broadcast"]
    dialog.clown.setChecked(True)
    dialog.makeup.setValue(55)
    assert services.user_settings.effects.clown_enabled is True
    assert services.user_settings.effects.clown_makeup_opacity == 0.55
    assert window.clown.makeup_opacity == 0.55
    dialog.stage.setCurrentIndex(dialog.stage.findData(2))
    assert services.user_settings.effects.clown_preview_stage == 2
    services.apply_effects(replace(services.user_settings.effects, clown_enabled=False))


def test_session_panel_states_without_a_browser(qtbot) -> None:
    window = make_window(qtbot)
    window._update_control_status()
    browser = window.session_panel.browser
    assert browser.headline.text() == "Browser connection not available"
    assert window.preview.message().startswith("Connect your browser first")
    assert window.session_panel.today.values["shorts"].text() in ("—", "0")
