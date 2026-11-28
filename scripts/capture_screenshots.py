"""Render the real application windows to PNG files for visual review (Brief 007/008).

The application runs with a *synthetic* camera scene (a drawn room and figure, no person and
no webcam image) and a scripted pointing hand, so the screenshots are technical
demonstrations of the real widgets, never private footage. The transparent-background
screenshot uses the figure's known outline as the segmentation mask (the person-segmentation
model needs a real person); it shows the compositing and overlay, not the model's quality.

Output goes to ``screenshots/`` (ignored by git). Windows display scaling is emulated with
``QT_SCALE_FACTOR``; ``--size`` is the logical work area of the emulated screen, e.g.
1920x1080 at 150 % -> ``--scale 1.5 --size 1280x672`` (taskbar subtracted).

Usage:
    python scripts/capture_screenshots.py --out screenshots/brief007/x --scale 1.0 --size 1366x720
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--size", default="1366x720", help="logical work area WxH")
    parser.add_argument("--only", default="", help="comma-separated subset of shots")
    return parser.parse_args()


ARGS = parse()
os.environ["QT_SCALE_FACTOR"] = str(ARGS.scale)

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from interactive_scrolling.actions.dispatcher import ActionDispatcher  # noqa: E402
from interactive_scrolling.actions.types import ControlMode  # noqa: E402
from interactive_scrolling.config.settings import AppSettings, CameraSettings  # noqa: E402
from interactive_scrolling.gestures.engine import GestureEngine  # noqa: E402
from interactive_scrolling.services import ControlServices  # noqa: E402
from interactive_scrolling.storage.analytics import AnalyticsStore  # noqa: E402
from interactive_scrolling.storage.settings_store import SettingsStore  # noqa: E402
from interactive_scrolling.ui.theme import apply_theme  # noqa: E402
from synthetic_scene import (  # noqa: E402
    H,
    OutlineSegmenter,
    SceneCamera,
    ScriptedHand,
    W,
    failing_camera,
)


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget: QWidget, out: Path, name: str) -> None:
    pixmap = widget.grab()
    path = out / f"{name}.png"
    pixmap.save(str(path))
    print(f"{path}  ({pixmap.width()}x{pixmap.height()} device px)")


def main() -> int:
    from dataclasses import replace

    from interactive_scrolling.integrations.coop.session import CoopStatus, invitation_text
    from interactive_scrolling.ui.main_window import MainWindow
    from interactive_scrolling.ui.together import JoinDialog, TogetherPanel

    out = ARGS.out
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, ARGS.only.split(",")))

    def want(name: str) -> bool:
        return not only or name in only

    def shot(widget: QWidget, name: str) -> None:
        if want(name):
            save(widget, out, name)

    width, height = (int(v) for v in ARGS.size.split("x"))
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    data = Path(tempfile.mkdtemp(prefix="is-shots-"))
    store = SettingsStore(data / "settings.json")
    user = store.load()
    services = ControlServices(
        engine=GestureEngine(user.gestures),
        dispatcher=ActionDispatcher(None, user.mapping),
        user_settings=user,
        store=store,
        analytics=AnalyticsStore(data / "analytics.sqlite3"),
    )
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=W, height=H)),
        camera_factory=SceneCamera,
        tracker_factory=ScriptedHand,
        services=services,
        segmenter_factory=OutlineSegmenter,
    )
    window.resize(width, height)
    window.move(0, 0)
    window.show()
    pump(app, 0.6)
    shot(window, "00_normal_camera_off")
    if want("00b_getting_started"):
        window.open_getting_started()
        pump(app, 0.5)
        save(window.getting_started, out, "00b_getting_started")
        window.getting_started.reject()
        pump(app, 0.2)
    window.start_camera()
    pump(app, 4.5)
    shot(window, "01_normal")
    window.console.set_expanded(True)
    pump(app, 0.6)
    shot(window, "02_console_expanded")
    window.console.tabs.setCurrentIndex(2)
    pump(app, 0.4)
    shot(window, "02b_console_performance")
    window.console.tabs.setCurrentIndex(0)
    window.console.set_expanded(False)
    window.open_camera_settings()
    pump(app, 0.6)
    shot(window.camera_dialog, "03_camera_settings")
    window.camera_dialog.close()
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    pump(app, 3.5)  # a scripted swipe reaches the dispatcher (no browser: rejected)
    shot(window, "04_live_control_no_browser")
    window.set_control_mode(ControlMode.TRACKING_ONLY)

    from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog

    dialog = GestureSettingsDialog(services.engine.settings, services.dispatcher.mapping, window)
    dialog.show()
    pump(app, 0.5)
    shot(dialog, "05_gesture_settings")
    dialog.close()
    window.open_practice()
    practice = window.practice_dialog
    pump(app, 0.5)
    shot(practice, "06_practice")
    practice.close()

    # ---- Doomscroll Together on this computer (loopback): Host, request, connected, Guest.
    window.coop_panel.player_name = "Alex"
    window.host_coop("Alex", 0, "127.0.0.1")
    window._update_control_status()
    pump(app, 0.4)
    shot(window, "07_together_host_waiting")
    host = services._coop_host
    guest_data = Path(tempfile.mkdtemp(prefix="is-shots-guest-"))
    guest_store = SettingsStore(guest_data / "settings.json")
    guest_user = guest_store.load()
    guest_services = ControlServices(
        engine=GestureEngine(guest_user.gestures),
        dispatcher=ActionDispatcher(None, guest_user.mapping),
        user_settings=guest_user,
        store=guest_store,
    )
    guest_services.join_coop("Sam", "127.0.0.1", host.port, host.code)
    deadline = time.monotonic() + 5
    while not host.status().pending_approval and time.monotonic() < deadline:
        pump(app, 0.1)
    window._update_control_status()
    pump(app, 0.3)
    shot(window, "08_together_join_request")
    guest_panel = TogetherPanel()
    guest_panel.resize(300, 260)
    guest_panel.show_status(guest_services.coop_status())
    guest_panel.show()
    pump(app, 0.3)
    shot(guest_panel, "09_together_guest_waiting")
    window.coop_panel.approve.click()
    deadline = time.monotonic() + 5
    while not guest_services._coop_guest.approved and time.monotonic() < deadline:
        pump(app, 0.1)
    window._update_control_status()
    pump(app, 2.5)  # a ping measures the round trip
    shot(window, "10_together_connected")
    guest_panel.show_status(guest_services.coop_status())
    pump(app, 0.3)
    shot(guest_panel, "11_together_guest_connected")
    join = JoinDialog("Sam")
    join.invitation.setPlainText(invitation_text("Alex", "192.168.1.20", 47816, host.code))
    join.show()
    pump(app, 0.3)
    shot(join, "12_together_join_dialog")
    join.close()
    guest_panel.show_status(CoopStatus(role="off", state="no session"))
    guest_panel.show_error("The session code is not correct. Check the invitation.")
    pump(app, 0.2)
    shot(guest_panel, "13_together_error_wrong_code")
    guest_panel.close()
    guest_services.leave_coop()
    guest_services.shutdown()
    services.end_coop()
    window._update_control_status()

    # ---- Broadcast Mode
    window.set_ui_mode("creator")
    overlay = window.creator
    pump(app, 2.0)
    shot(overlay, "14_broadcast_standard")
    overlay._hover = True
    overlay.update()
    pump(app, 0.3)
    shot(overlay, "15_broadcast_hover_settings")
    overlay._hover = False
    window.open_broadcast_settings()
    pump(app, 0.6)
    shot(window._dialogs["broadcast"], "16_broadcast_settings")
    window._dialogs["broadcast"].transparent.setChecked(True)
    pump(app, 3.0)
    shot(overlay, "17_broadcast_transparent")
    window._dialogs["broadcast"].close()
    menu = overlay.build_menu()
    menu.popup(QPoint(40, 40))
    pump(app, 0.5)
    shot(menu, "18_broadcast_menu")
    menu.close()
    overlay.apply_settings(replace(overlay.settings, transparent_background=False))
    window.set_ui_mode("developer")
    pump(app, 0.5)
    tray_menu = window.tray.menu
    tray_menu.popup(QPoint(40, 40))
    pump(app, 0.5)
    shot(tray_menu, "19_tray_menu")
    tray_menu.close()
    window.more_menu.popup(QPoint(40, 40))
    pump(app, 0.5)
    shot(window.more_menu, "20_more_menu")
    window.more_menu.close()
    window.open_report()
    pump(app, 0.5)
    shot(window._dialogs["report"], "21_report")
    window._dialogs["report"].close()
    window.open_browser_setup()
    pump(app, 0.5)
    shot(window._dialogs["browser"], "22_browser_setup")
    window._dialogs["browser"].close()
    window.stop_camera()
    pump(app, 1.0)
    if want("23_camera_unavailable"):
        window.pipeline._camera_factory = failing_camera
        window.start_camera()
        pump(app, 1.5)
        save(window, out, "23_camera_unavailable")
    window.close()
    pump(app, 0.5)
    screen = QGuiApplication.primaryScreen()
    print(
        "screen",
        screen.geometry().width(),
        screen.geometry().height(),
        "dpr",
        screen.devicePixelRatio(),
    )
    QTimer.singleShot(0, app.quit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
