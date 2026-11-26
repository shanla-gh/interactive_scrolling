"""Co-op through the services and the panel (loopback)."""

from __future__ import annotations

import time

from interactive_scrolling.actions.types import ActionStatus, ControlMode
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.integrations.coop.session import CoopGuestController
from interactive_scrolling.services import offline_services
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import camera_factory, wait_until
from tests.integration.test_coop import Browser


def test_host_and_guest_services_with_panel(qtbot) -> None:
    host_services = offline_services()
    browser = Browser()
    host_services.dispatcher.set_controller(browser)
    window = MainWindow(
        AppSettings(),
        camera_factory=camera_factory(),
        tracker_factory=None,
        services=host_services,
    )
    qtbot.addWidget(window)
    window.host_coop("Alex", 0)
    host = host_services._coop_host
    port = host.port
    window._update_control_status()
    assert "Code:" in window.coop_panel.code.text() and host.code in window.coop_panel.code.text()

    guest_services = offline_services()
    original = guest_services.dispatcher._controller
    guest_services.join_coop("Sam", "127.0.0.1", port, host.code)
    assert isinstance(guest_services.dispatcher._controller, CoopGuestController)
    assert wait_until(lambda: host.status().pending_approval)
    window._update_control_status()
    assert window.coop_panel.approve.isEnabled()
    window.coop_panel.approve.click()
    assert wait_until(lambda: guest_services._coop_guest.approved)

    host_services.dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    guest_services.dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    records = []
    guest_services.dispatcher.add_record_listener(records.append)
    event = GestureEvent(GestureType.INDEX_SWIPE_DOWN, time.perf_counter_ns(), 1, Handedness.LEFT)
    guest_services.dispatcher.submit(event)
    assert wait_until(lambda: any(r.status is ActionStatus.SUCCEEDED for r in records))
    window._update_control_status()
    assert window.coop_panel.last.text() == "Sam → Next Short → Success"
    assert "Sam: 1" in window.coop_panel.counts.text()

    guest_services.leave_coop()
    assert guest_services.dispatcher._controller is original
    assert wait_until(lambda: host.status().peer is None)
    window.close()
    guest_services.shutdown()
