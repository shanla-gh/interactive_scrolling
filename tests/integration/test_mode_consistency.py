"""Recognition must not depend on the presentation mode (Brief 009, CP 48.7).

The same scripted hand (a pointing hand that swipes up, then down, then left) is played into
the real window in Normal Mode, Broadcast Mode with every optional overlay layer and the
transparent background, Background Mode, and Normal Mode with the console expanded and Now
playing hidden. The recognized gesture sequence must be identical, the control mode must stay
as set, and no extra worker threads may appear.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import replace

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.services import offline_services
from interactive_scrolling.ui.main_window import MainWindow
from tests.gesture_helpers import POINTING, make_observation
from tests.helpers import ScriptedTracker, camera_factory
from tests.integration.test_ui_modes import FakeSegmenter

SWIPES = ((1.0, (0, -160)), (2.6, (0, 160)), (4.2, (-200, 0)))
DURATION_S = 5.6


def scripted_hand():  # type: ignore[no-untyped-def]
    start: list[int] = []

    def script(timestamp_ms: int):  # type: ignore[no-untyped-def]
        if not start:
            start.append(timestamp_ms)
        t = (timestamp_ms - start[0]) / 1000.0
        x, y = 640.0, 420.0
        for t0, (dx, dy) in SWIPES:
            if t >= t0:
                u = min(1.0, (t - t0) / 0.25)
                s = (1 - math.cos(math.pi * u)) / 2
                if t - t0 > 0.25 + 0.6:  # return to the start after a pause
                    back = min(1.0, (t - t0 - 0.85) / 0.4)
                    s *= 1 - back
                x += dx * s
                y += dy * s
        return (make_observation(POINTING, (x, y), palm_px=95.0),)

    return ScriptedTracker(script)


def run_mode(qtbot, configure) -> list[str]:  # type: ignore[no-untyped-def]
    services = offline_services()
    window = MainWindow(
        AppSettings(),
        camera_factory=camera_factory(),
        tracker_factory=scripted_hand,
        services=services,
        segmenter_factory=FakeSegmenter,
    )
    qtbot.addWidget(window)
    window.show()
    events: list[str] = []
    lock = threading.Lock()

    def tap(tracking, gestures) -> None:  # type: ignore[no-untyped-def]
        if gestures is not None:
            with lock:
                events.extend(e.gesture.name for e in gestures.events)

    window.pipeline.add_gesture_tap(tap)
    window.set_control_mode(ControlMode.GESTURE_TEST)
    configure(window, services)
    threads_before = threading.active_count()
    assert window.start_camera()
    qtbot.wait(int(DURATION_S * 1000))
    assert services.dispatcher.mode is ControlMode.GESTURE_TEST
    assert threading.active_count() <= threads_before + 3  # camera, processing, segmentation
    window.close()
    time.sleep(0.2)
    return events


def normal(window, services) -> None:  # type: ignore[no-untyped-def]
    window.set_ui_mode("developer")


def broadcast_everything(window, services) -> None:  # type: ignore[no-untyped-def]
    creator = replace(
        services.user_settings.creator,
        show_vectors=True,
        show_counters=True,
        transparent_background=True,
        smooth_skeleton=True,
    )
    services.update_settings(creator=creator)
    window.creator.apply_settings(creator)
    window.set_ui_mode("creator")


def background(window, services) -> None:  # type: ignore[no-untyped-def]
    if window.tray.available:
        window.set_ui_mode("background")
    else:  # offscreen test platform: Background Mode hides every window, as here
        window.creator.hide()
        window.hide()


def normal_console_no_preview(window, services) -> None:  # type: ignore[no-untyped-def]
    window.set_ui_mode("developer")
    window.console.set_expanded(True)
    # Brief 010: the Short is no longer hidden from a menu; collapse Your session instead.
    window.session_panel.set_expanded(False)


def test_recognition_is_the_same_in_every_presentation_mode(qtbot) -> None:
    reference = run_mode(qtbot, normal)
    # The sideways stroke moves to the image's left: the user's right in the mirrored view.
    assert reference == ["INDEX_SWIPE_UP", "INDEX_SWIPE_DOWN", "INDEX_SWIPE_RIGHT"], reference
    for configure in (broadcast_everything, background, normal_console_no_preview):
        assert run_mode(qtbot, configure) == reference, configure.__name__
