"""Studio Mode workspace (Brief 008, rebuilt as the cinema workspace in Brief 010): top bar,
gesture panel, Your session panel, console, Unified Settings and the live Short.

Brief 010 changed these expectations on purpose (documented in UI_VALIDATION_010.md): the
top bar holds Black | White | Gray, Studio | Broadcast, Settings and Start camera (no More
menu, no Camera settings button); camera, Broadcast and clown options are pages of Unified
Settings instead of separate dialogs; the Short is the centre of the window and is no longer
hidden from a menu (the Now playing toggle is gone).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import QApplication

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.integrations.coop.session import CoopStatus
from interactive_scrolling.services import offline_services
from interactive_scrolling.ui import theme
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.ui.session_panel import STRIP_WIDTH
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


def reset_theme() -> None:
    theme.deactivate(QApplication.instance())


def test_top_bar_holds_only_the_essentials(qtbot) -> None:
    window = make_window(qtbot)
    bar = window.start_button.parentWidget()
    buttons = sorted(b.text() for b in bar.findChildren(type(window.start_button)))
    assert buttons == [
        "Black",
        "Broadcast",
        "Gray",
        "Settings",
        "Start camera",
        "Studio",
        "White",
    ]
    # Camera device, resolution and scan live in Settings, not permanently on screen.
    assert window.camera_combo.window() is window.settings_window
    assert not window.settings_window.isVisible()


def test_theme_selector_sits_left_of_the_mode_selector(qtbot) -> None:
    window = make_window(qtbot)
    layout = window._top_bar.layout()
    index = [layout.indexOf(w) for w in (window.theme_control, window.mode_control)]
    assert index[0] < index[1]
    assert window.theme_control.objectName() == "segmented"
    assert len(window.theme_control.buttons) == 3
    assert window.mode_control.objectName() == "segmented"


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
    window.control_bar.camera_button.click()  # the quick control opens Settings, Camera
    assert window.settings_window.isVisible()
    assert window.settings_window.current_key == "camera"
    form = window.camera_form
    form.fps_combo.setCurrentIndex(form.fps_combo.findData(15))
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


def test_session_panel_collapses_without_ending_the_session(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    ended: list[bool] = []
    services.end_coop = lambda: ended.append(True)  # type: ignore[method-assign]
    stops: list[bool] = []
    window.stop_preview = lambda: stops.append(True)  # type: ignore[method-assign]
    cinema_before = window.cinema.width()
    window.session_panel.collapse_button.click()
    qtbot.waitUntil(lambda: window.workspace.sizes()[2] == STRIP_WIDTH)
    assert window.session_panel.strip.isVisible() and not window.session_panel.panel.isVisible()
    assert services.user_settings.appearance.session_panel_expanded is False
    qtbot.waitUntil(lambda: window.cinema.width() > cinema_before)
    assert ended == [] and stops == []  # nothing stops when the panel is hidden
    window.session_panel.strip.expand_button.click()
    assert window.session_panel.panel.isVisible()
    assert services.user_settings.appearance.session_panel_expanded is True


def test_collapsed_strip_shows_an_active_session(qtbot) -> None:
    window = make_window(qtbot)
    window.session_panel.set_expanded(False)
    status = CoopStatus(role="host", state="connected", peer="Sam", approved=True)
    window.session_panel.show_coop(status)
    strip = window.session_panel.strip
    assert strip.together.isVisible() and strip.together_count.text() == "2"
    assert "Playing with Sam" in strip.together.toolTip()
    names = [row[1].text() for row in window.session_panel.people.rows]
    assert names == ["You", "Sam"]


def test_panel_state_and_widths_survive_a_restart(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.session_panel.set_expanded(False)
    window.workspace.setSizes([420, 900, STRIP_WIDTH])
    window._save_layout()
    saved = services.user_settings.appearance
    assert saved.session_panel_expanded is False and saved.left_panel_width == 420
    window.close()
    again = make_window(qtbot, services)
    assert not again.session_panel.expanded
    qtbot.waitUntil(lambda: abs(again.workspace.sizes()[0] - 420) <= 2)


def test_focus_view_keeps_safety_controls_and_is_remembered(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.focus_button.click()
    assert not window.session_panel.isVisible() and not window.console.isVisible()
    assert window.control_bar.disable_button.isVisible()
    assert window.control_bar.segments.isVisible()
    assert window.preview.isVisible() and window.video.isVisible()
    assert services.user_settings.appearance.focus_view is True
    assert window.focus_button.text() == "Exit focus view"
    window.focus_button.click()
    assert window.session_panel.isVisible() and window.console.isVisible()
    assert services.user_settings.appearance.focus_view is False


def test_reset_layout_restores_the_defaults(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.session_panel.set_expanded(False)
    window.console.set_expanded(True)
    window.reset_layout()
    a = services.user_settings.appearance
    assert a.session_panel_expanded and not a.console_expanded and a.left_panel_width == 0
    assert window.session_panel.expanded and not window.console.expanded


def test_runtime_theme_switch_touches_nothing_else(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    try:
        window.set_control_mode(ControlMode.GESTURE_TEST)
        window.console.set_expanded(True)
        window.session_panel.set_expanded(False)
        before = (
            window.pipeline.camera_state,
            services.dispatcher.mode,
            services.engine.settings,
            window.console.expanded,
            window.session_panel.expanded,
        )
        for name in ("white", "gray", "black", "white"):
            window.theme_control.buttons[name].click()
            assert theme.tokens().name == name
            assert services.user_settings.appearance.theme == name
        after = (
            window.pipeline.camera_state,
            services.dispatcher.mode,
            services.engine.settings,
            window.console.expanded,
            window.session_panel.expanded,
        )
        assert before == after
        assert "#f6f7f8" in window.styleSheet()  # the White background
        window.open_settings("appearance")
        assert window.settings_window.theme.buttons["white"].isChecked()
        window.settings_window.theme.buttons["gray"].click()
        assert window.theme_control.buttons["gray"].isChecked()
    finally:
        reset_theme()


def test_saved_theme_is_applied_at_start(qtbot) -> None:
    services = offline_services()
    services.update_settings(appearance=replace(services.user_settings.appearance, theme="gray"))
    try:
        window = make_window(qtbot, services)
        assert theme.tokens().name == "gray"
        assert window.theme_control.buttons["gray"].isChecked()
    finally:
        reset_theme()


def test_transparent_background_is_one_click_away_in_broadcast_settings(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.set_ui_mode("creator")
    window.creator.settings_requested.emit()  # the overlay's Settings button / menu entry
    settings = window.settings_window
    assert settings.isVisible() and settings.current_key == "broadcast"
    assert settings.transparent.isEnabled()
    settings.transparent.setChecked(True)
    assert window.creator.settings.transparent_background is True
    assert services.user_settings.creator.transparent_background is True
    settings.layers["show_vectors"].setChecked(True)
    assert window.creator.settings.show_vectors is True
    assert window.creator.settings.transparent_background is True  # independent options


def test_broadcast_settings_reachable_from_the_tray(qtbot) -> None:
    window = make_window(qtbot)
    tray = [a.text() for a in window.tray.menu.actions()]
    assert "Broadcast settings..." in tray and "Studio Mode" in tray
    window.tray.broadcast_settings_requested.emit()
    assert window.settings_window.current_key == "broadcast"


def test_broadcast_settings_without_segmentation_explains_why(qtbot) -> None:
    window = make_window(qtbot, segmenter=False)
    window.open_broadcast_settings()
    settings = window.settings_window
    assert not settings.transparent.isEnabled()
    assert "not available" in settings.transparent_hint.text().lower()


def test_clown_controls_apply_to_the_effect(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.open_settings("effects")
    settings = window.settings_window
    settings.clown.setChecked(True)
    settings.makeup.setValue(55)
    assert services.user_settings.effects.clown_enabled is True
    assert services.user_settings.effects.clown_makeup_opacity == 0.55
    assert window.clown.makeup_opacity == 0.55
    settings.stage_preview.setCurrentIndex(settings.stage_preview.findData(2))
    settings.stage_preview.activated.emit(settings.stage_preview.currentIndex())
    assert services.user_settings.effects.clown_preview_stage == 2
    # The Broadcast page shows the same option (one setting, two places).
    window.open_settings("broadcast")
    assert settings.broadcast_clown.isChecked()
    services.apply_effects(replace(services.user_settings.effects, clown_enabled=False))


def test_decreasing_clown_stages_are_refused(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.open_settings("effects")
    settings = window.settings_window
    settings.stages[0].setValue(40)  # nose after 40 min, lips after 20: invalid
    assert services.user_settings.effects.clown_stage1_min == 10.0
    assert "must not decrease" in settings.clown_error.text()


def test_eye_layer_shortcut_and_settings_agree(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.control_bar.layer_buttons["eyes"].click()
    assert services.user_settings.effects.eye_overlay is True
    window.open_settings("eyes")
    assert window.settings_window.eye_overlay.isChecked()
    window.settings_window.eye_overlay.setChecked(False)
    assert services.user_settings.effects.eye_overlay is False
    assert not window.control_bar.layer_buttons["eyes"].isChecked()


def test_every_settings_page_opens(qtbot) -> None:
    from interactive_scrolling.ui.settings_window import PAGES

    window = make_window(qtbot)
    for key, title in PAGES:
        window.open_settings(key)
        assert window.settings_window.current_key == key
        assert window.settings_window.nav.currentItem().text() == title


def test_gesture_page_applies_validated_settings(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.open_gesture_settings()
    form = window.settings_window.gesture_form
    form.style.setCurrentIndex(form.style.findData("finger"))
    assert form.apply()
    # The engine takes requested settings on its own thread with the next frame.
    assert services.user_settings.gestures.control_style == "finger"


def test_together_preferences_prefill_the_host_dialog(qtbot) -> None:
    services = offline_services()
    window = make_window(qtbot, services)
    window.open_settings("together")
    settings = window.settings_window
    settings.player_name.setText("Robin")
    settings.player_name.editingFinished.emit()
    settings.host_port.setValue(48000)
    assert services.user_settings.together.player_name == "Robin"
    assert services.user_settings.together.host_port == 48000
    assert window.coop_panel.player_name == "Robin" and window.coop_panel.host_port == 48000
    settings.player_name.setText("<bad>")
    settings.player_name.editingFinished.emit()
    assert services.user_settings.together.player_name == "Robin"
    assert settings.together_error.text()


def test_session_panel_states_without_a_browser(qtbot) -> None:
    window = make_window(qtbot)
    window._update_control_status()
    browser = window.session_panel.browser
    assert browser.headline.text() == "Browser connection not available"
    assert window.preview.message().startswith("Your browser is not connected")
    assert window.preview_info.text() == "Browser not connected"
    assert window.session_panel.today.values["shorts"].text() in ("—", "0")


def test_feedback_waits_for_the_browser_before_success(qtbot) -> None:
    from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ActionType
    from interactive_scrolling.gestures.types import GestureEvent, GestureType, Handedness

    window = make_window(qtbot)
    event = GestureEvent(GestureType.INDEX_SWIPE_UP, 0, 1, Handedness.RIGHT, detector="finger")
    pending = ActionRecord(
        "r1", event, ActionType.NEXT_SHORT, ControlMode.LIVE_CONTROL, ActionStatus.DISPATCHED
    )
    window.control_bar.show_record(pending)
    outcome = window.control_bar.feedback_labels["outcome"]
    assert outcome.text() == "Waiting for the browser..."
    done = ActionRecord(
        "r1", event, ActionType.NEXT_SHORT, ControlMode.LIVE_CONTROL, ActionStatus.SUCCEEDED
    )
    window.control_bar.show_record(done)
    assert outcome.text() == "Successful" and outcome.property("state") == "ok"


def test_collapsed_console_skips_detail_panel_updates(qtbot) -> None:
    window = make_window(qtbot)
    calls: list[object] = []
    window.tracking_panel.update_tracking = lambda t: calls.append(t)  # type: ignore[method-assign]
    window.console.set_expanded(False)
    window.start_camera()
    qtbot.waitUntil(lambda: window.video.frame is not None, timeout=5000)
    qtbot.wait(200)
    assert calls == []
    window.console.set_expanded(True)
    qtbot.waitUntil(lambda: len(calls) > 0, timeout=3000)
    window.stop_camera()
