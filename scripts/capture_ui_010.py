"""Render the real Brief 010 application windows to PNG files for visual review.

The application runs with a *synthetic* camera scene (a drawn room and figure, no person and
no webcam image), a scripted pointing hand and a *synthetic* Short (a drawn 9:16 picture
labelled "Synthetic Short - demonstration") pushed through the real preview feed, so every
screenshot shows the real widgets with demonstration material only. The browser connection
is simulated by a stub controller (no browser is involved). Real-browser preview screenshots
come from ``scripts/capture_live_preview.py``.

Output goes to ``screenshots/`` (ignored by git). Windows display scaling is emulated with
``QT_SCALE_FACTOR`` (see ``capture_ui_010_sets.ps1``).

Usage:
    python scripts/capture_ui_010.py --out screenshots/brief010/main --set full
    python scripts/capture_ui_010.py --out screenshots/brief010/compat/x --set compat
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--size", default="1536x824", help="logical window size WxH")
    parser.add_argument("--set", choices=("full", "compat", "themes"), default="full")
    parser.add_argument("--only", default="", help="comma-separated subset of shots")
    return parser.parse_args()


ARGS = parse()
os.environ["QT_SCALE_FACTOR"] = str(ARGS.scale)

from PySide6.QtCore import QBuffer, QIODevice, QPoint, QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
)
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from interactive_scrolling.actions.dispatcher import ActionDispatcher  # noqa: E402
from interactive_scrolling.actions.types import ControlMode  # noqa: E402
from interactive_scrolling.config.settings import AppSettings, CameraSettings  # noqa: E402
from interactive_scrolling.gestures.engine import GestureEngine  # noqa: E402
from interactive_scrolling.integrations.youtube.controller import YouTubeStatus  # noqa: E402
from interactive_scrolling.integrations.youtube.preview import PreviewFeed  # noqa: E402
from interactive_scrolling.integrations.youtube.protocol import PreviewFrame  # noqa: E402
from interactive_scrolling.services import ControlServices  # noqa: E402
from interactive_scrolling.storage.analytics import AnalyticsStore  # noqa: E402
from interactive_scrolling.storage.settings_store import SettingsStore  # noqa: E402
from interactive_scrolling.ui.theme import apply_theme  # noqa: E402
from synthetic_scene import H, OutlineSegmenter, SceneCamera, ScriptedHand, W  # noqa: E402


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def synthetic_short(number: int) -> bytes:
    """A drawn 9:16 picture standing in for a YouTube Short (labelled as such)."""
    image = QImage(360, 640, QImage.Format.Format_RGB888)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 360, 640)
    gradient.setColorAt(0.0, QColor("#f2a65a"))
    gradient.setColorAt(0.55, QColor("#c8553d"))
    gradient.setColorAt(1.0, QColor("#2b2d42"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 236, 200, 230))
    phase = (number % 60) / 60.0
    painter.drawEllipse(QPointF(180 + 40 * (phase - 0.5), 230), 70, 70)
    painter.setBrush(QColor(43, 45, 66, 220))
    painter.drawRect(QRectF(0, 430, 360, 210))
    painter.setPen(QColor("#ffffff"))
    font = QFont()
    font.setPointSizeF(15)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(20, 470, 320, 40), Qt.AlignmentFlag.AlignLeft, "Synthetic Short")
    font.setPointSizeF(11)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(
        QRectF(20, 510, 320, 80),
        int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
        "Demonstration picture pushed through the real preview feed. Not YouTube content.",
    )
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", 80)
    return bytes(buffer.data())


class StubController:
    """Reports a connected Edge with a Shorts tab (no browser involved)."""

    def __init__(self) -> None:
        self.connected = True
        self.app_in_front = True

    def status(self) -> YouTubeStatus:
        if not self.connected:
            return YouTubeStatus(True, None, 0, (), False, "no browser connected")
        return YouTubeStatus(
            listening=True,
            bridge_error=None,
            connections=1,
            browsers=("edge",),
            ready=True,
            reason="",
            target_browser="edge",
            signed_in=True,
            paused=False,
            browser_focused=False,
            preview=True,
            via_preview=True,
        )


class ShortStream:
    """Pushes synthetic Short frames into a real PreviewFeed at 30 fps."""

    def __init__(self, feed: PreviewFeed) -> None:
        self.feed = feed
        self.running = False
        self._frames = [synthetic_short(i) for i in range(0, 60, 6)]

    def start(self) -> None:
        self.feed.attach(lambda: None)
        self.feed.set_state("streaming", "")
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self, reason: str = "stopped in the browser") -> None:
        self.running = False
        self.feed.detach(reason)

    def _run(self) -> None:
        number = 0
        while self.running:
            jpeg = self._frames[number % len(self._frames)]
            self.feed.push(PreviewFrame(time.time() * 1000.0, number, jpeg))
            number += 1
            time.sleep(1 / 30)


def main() -> int:
    from interactive_scrolling.ui.main_window import MainWindow

    out = ARGS.out
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, ARGS.only.split(",")))

    def want(name: str) -> bool:
        return not only or name in only

    def shot(widget: QWidget, name: str) -> None:
        if not want(name):
            return
        pixmap = widget.grab()
        path = out / f"{name}.png"
        pixmap.save(str(path))
        print(f"{path}  ({pixmap.width()}x{pixmap.height()} device px)")

    width, height = (int(v) for v in ARGS.size.split("x"))
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    data = Path(tempfile.mkdtemp(prefix="is-shots-"))
    store = SettingsStore(data / "settings.json")
    user = store.load()
    feed = PreviewFeed()
    controller = StubController()
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
    window.preview.feed = feed
    window.resize(width, height)
    window.move(0, 0)
    window.show()
    pump(app, 0.6)
    shot(window, "06_camera_off_browser_disconnected")
    services.controller = controller  # type: ignore[assignment]
    stream = ShortStream(feed)
    stream.start()
    window.start_camera()
    pump(app, 4.0)
    window._update_control_status()
    themes = ("black", "white", "gray")

    def theme_shots(prefix: str = "") -> None:
        for name in themes:
            window.set_theme(name)
            window.session_panel.set_expanded(True)
            pump(app, 0.8)
            shot(window, f"{prefix}{name}_expanded")
            window.session_panel.set_expanded(False)
            pump(app, 0.8)
            shot(window, f"{prefix}{name}_collapsed")
            window.session_panel.set_expanded(True)
            window.open_settings("appearance")
            pump(app, 0.5)
            shot(window.settings_window, f"{prefix}{name}_settings_appearance")
            window.settings_window.close()
        window.set_theme("black")
        pump(app, 0.3)

    if ARGS.set in ("themes", "compat"):
        theme_shots()
        if ARGS.set == "compat":
            window.set_focus_view(True)
            pump(app, 0.6)
            shot(window, "focus_view")
            window.set_focus_view(False)
            window.console.set_expanded(True)
            pump(app, 0.6)
            shot(window, "console_expanded")
            window.console.set_expanded(False)
            window.open_settings("gestures")
            pump(app, 0.5)
            shot(window.settings_window, "settings_gestures")
            window.settings_window.close()
            window.showMinimized()
            pump(app, 0.3)
            window.showNormal()
            window.resize(window.minimumSize())
            pump(app, 0.8)
            shot(window, "minimum_window")
        finish(app, window, stream)
        return 0

    # ---- full set (Black unless the shot is about themes)
    theme_shots("01_")
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    pump(app, 3.5)  # a scripted swipe reaches the dispatcher (no browser: rejected)
    shot(window, "02_live_control_feedback")
    window.set_control_mode(ControlMode.TRACKING_ONLY)
    window.workspace.setSizes([520, window.workspace.width() - 520 - 380, 380])
    pump(app, 0.8)
    shot(window, "03_resized_regions")
    window.reset_layout()
    window.set_focus_view(True)
    pump(app, 0.8)
    shot(window, "04_focus_view")
    window.set_focus_view(False)
    window.console.set_expanded(True)
    for index, tab in enumerate(
        ("activity", "recognition", "camera", "performance", "eyes", "browser")
    ):
        if index >= window.console.tabs.count():
            break
        window.console.tabs.setCurrentIndex(index)
        pump(app, 0.5)
        shot(window, f"05_diagnostics_{index}_{tab}")
    window.console.tabs.setCurrentIndex(0)
    window.console.set_expanded(False)
    pump(app, 0.3)
    shot(window, "05_diagnostics_collapsed")

    # ---- browser disconnected while the camera runs
    stream.stop("stopped in the browser")
    controller.connected = False
    window._update_control_status()
    pump(app, 0.8)
    shot(window, "07_browser_disconnected")
    controller.connected = True
    stream = ShortStream(feed)
    stream.start()
    window._update_control_status()
    pump(app, 0.8)

    # ---- Unified Settings, every page
    from interactive_scrolling.ui.settings_window import PAGES

    for index, (key, _title) in enumerate(PAGES):
        window.open_settings(key)
        pump(app, 0.5)
        shot(window.settings_window, f"08_settings_{index:02d}_{key}")
    window.settings_window.close()

    together_shots(app, window, services, shot)

    # ---- Broadcast Mode
    window.set_ui_mode("creator")
    overlay = window.creator
    pump(app, 2.0)
    shot(overlay, "10_broadcast")
    window.settings_window.transparent.setChecked(True)
    pump(app, 3.0)
    shot(overlay, "11_broadcast_transparent")
    window.settings_window.transparent.setChecked(False)
    window.set_ui_mode("developer")
    pump(app, 0.5)

    # ---- report and Wrapped
    window.open_report()
    pump(app, 0.5)
    shot(window._dialogs["report"], "12_daily_report")
    window._dialogs["report"].close()
    from interactive_scrolling.ui.wrapped import WrappedDialog, render_wrapped

    data = window.wrapped_data("today")
    if data is not None:
        image, _ = render_wrapped(data, True)
        dialog = WrappedDialog(image, "wrapped.png", window)
        dialog.show()
        pump(app, 0.5)
        shot(dialog, "13_wrapped_preview")
        dialog.close()
    tray_menu = window.tray.menu
    tray_menu.popup(QPoint(40, 40))
    pump(app, 0.4)
    shot(tray_menu, "14_tray_menu")
    tray_menu.close()
    finish(app, window, stream)
    return 0


def together_shots(app, window, services, shot) -> None:  # type: ignore[no-untyped-def]
    """Doomscroll Together on this computer (loopback): host waiting, request, connected."""
    from interactive_scrolling.ui.together import TogetherPanel

    window.coop_panel.player_name = "Alex"
    window.host_coop("Alex", 0, "127.0.0.1")
    window._update_control_status()
    pump(app, 0.5)
    shot(window, "09_together_1_host_waiting")
    host = services._coop_host
    guest_data = Path(tempfile.mkdtemp(prefix="is-shots-guest-"))
    guest_store = SettingsStore(guest_data / "settings.json")
    guest_user = guest_store.load()
    guest = ControlServices(
        engine=GestureEngine(guest_user.gestures),
        dispatcher=ActionDispatcher(None, guest_user.mapping),
        user_settings=guest_user,
        store=guest_store,
    )
    guest.join_coop("Sam", "127.0.0.1", host.port, host.code)
    deadline = time.monotonic() + 5
    while not host.status().pending_approval and time.monotonic() < deadline:
        pump(app, 0.1)
    window._update_control_status()
    pump(app, 0.4)
    shot(window, "09_together_2_join_request")
    panel = TogetherPanel()
    panel.resize(300, 240)
    panel.show_status(guest.coop_status())
    panel.show()
    pump(app, 0.3)
    shot(panel, "09_together_3_guest_waiting")
    window.coop_panel.approve.click()
    deadline = time.monotonic() + 5
    while not guest._coop_guest.approved and time.monotonic() < deadline:
        pump(app, 0.1)
    window._update_control_status()
    pump(app, 2.5)
    shot(window, "09_together_4_connected")
    window.session_panel.set_expanded(False)
    window._update_control_status()
    pump(app, 0.6)
    shot(window, "09_together_5_connected_collapsed")
    window.session_panel.set_expanded(True)
    panel.show_status(guest.coop_status())
    pump(app, 0.3)
    shot(panel, "09_together_6_guest_connected")
    panel.close()
    guest.leave_coop()
    guest.shutdown()
    services.end_coop()
    window._update_control_status()


def finish(app, window, stream) -> None:  # type: ignore[no-untyped-def]
    stream.stop()
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


if __name__ == "__main__":
    sys.exit(main())
