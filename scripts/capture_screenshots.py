"""Render the real application windows to PNG files for visual review (Brief 007).

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
import math
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

import numpy as np  # noqa: E402
from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.gesture_helpers import POINTING, make_observation  # noqa: E402

from interactive_scrolling.actions.dispatcher import ActionDispatcher  # noqa: E402
from interactive_scrolling.actions.types import ControlMode  # noqa: E402
from interactive_scrolling.config.settings import AppSettings, CameraSettings  # noqa: E402
from interactive_scrolling.gestures.engine import GestureEngine  # noqa: E402
from interactive_scrolling.services import ControlServices  # noqa: E402
from interactive_scrolling.storage.analytics import AnalyticsStore  # noqa: E402
from interactive_scrolling.storage.settings_store import SettingsStore  # noqa: E402
from interactive_scrolling.ui.theme import apply_theme  # noqa: E402
from interactive_scrolling.vision.camera import Frame  # noqa: E402

W, H = 1280, 720


def figure_mask(w: int, h: int) -> np.ndarray:
    """A head-and-shoulders outline (float 0..1), the synthetic 'person'."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    head = ((xx - w * 0.5) / (w * 0.085)) ** 2 + ((yy - h * 0.36) / (h * 0.17)) ** 2 <= 1.0
    torso = ((xx - w * 0.5) / (w * 0.26)) ** 2 + ((yy - h * 1.02) / (h * 0.5)) ** 2 <= 1.0
    return (head | torso).astype(np.float32)


class SceneCamera:
    """30 fps generated frames: a dim room with a lighter figure (no real image)."""

    def __init__(self, settings: CameraSettings) -> None:
        self.settings = settings
        self.actual_width, self.actual_height = W, H
        self.opened = False
        self._n = 0
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        room = np.stack([40 + 30 * yy / H, 46 + 26 * xx / W, 58 + 20 * yy / H], axis=-1)
        room[int(H * 0.15) : int(H * 0.55), int(W * 0.72) : int(W * 0.9)] = (70, 92, 120)  # window
        mask = figure_mask(W, H)[..., None]
        person = np.empty_like(room)
        person[...] = (196, 200, 206)  # light shirt
        skin = (((xx - W * 0.5) / (W * 0.085)) ** 2 + ((yy - H * 0.36) / (H * 0.17)) ** 2) <= 1
        person[skin] = (150, 170, 205)
        self._image = (room * (1 - mask) + person * mask).astype(np.uint8)

    def open(self) -> None:
        self.opened = True

    def read(self) -> Frame | None:
        time.sleep(1 / 30)
        self._n += 1
        return Frame(
            image_bgr=self._image.copy(), index=self._n - 1, timestamp_ns=time.perf_counter_ns()
        )

    def close(self) -> None:
        self.opened = False


class ScriptedHand:
    """A pointing hand at the right side that rests and swipes up every 3 s."""

    def __init__(self) -> None:
        self.t0: int | None = None

    def process(self, image_rgb: np.ndarray, timestamp_ms: int):  # type: ignore[no-untyped-def]
        if self.t0 is None:
            self.t0 = timestamp_ms
        t = ((timestamp_ms - self.t0) / 1000.0) % 3.0
        y = 470.0 if t < 1.6 else 470.0 - min(1.0, (t - 1.6) / 0.25) * 160.0
        x = 900.0 + 6 * math.sin(timestamp_ms / 300.0)
        return (make_observation(POINTING, (x, y), palm_px=95.0),)

    def close(self) -> None:
        pass


class OutlineSegmenter:
    """Technical demonstration: returns the synthetic figure's outline as the mask."""

    def __init__(self) -> None:
        self._mask: np.ndarray | None = None

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> np.ndarray:
        h, w = image_rgb.shape[:2]
        if self._mask is None or self._mask.shape != (h, w):
            self._mask = figure_mask(w, h)
        return self._mask

    def close(self) -> None:
        pass


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
    from interactive_scrolling.ui.main_window import MainWindow

    out = ARGS.out
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, ARGS.only.split(",")))

    def want(name: str) -> bool:
        return not only or name in only

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
    pump(app, 0.5)
    if want("00_main_camera_off"):
        save(window, out, "00_main_camera_off")
    window.start_camera()
    pump(app, 4.5)
    tabs = window.side_tabs
    for index in range(tabs.count()):
        name = f"01_main_tab_{index}_{tabs.tabText(index).lower().replace(' ', '_')}"
        tabs.setCurrentIndex(index)
        pump(app, 0.4)
        if want(name):
            save(window, out, name)
    tabs.setCurrentIndex(0)
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    pump(app, 3.5)  # a scripted swipe reaches the dispatcher (no browser: rejected)
    if want("02_live_control_no_browser"):
        save(window, out, "02_live_control_no_browser")
    window.set_control_mode(ControlMode.TRACKING_ONLY)

    from interactive_scrolling.ui.practice_dialog import PracticeDialog
    from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog

    dialog = GestureSettingsDialog(services.engine.settings, services.dispatcher.mapping, window)
    dialog.show()
    pump(app, 0.5)
    if want("03_gesture_settings"):
        save(dialog, out, "03_gesture_settings")
    dialog.close()
    practice = PracticeDialog(services, window)
    practice.show()
    pump(app, 0.5)
    if want("04_practice_start"):
        save(practice, out, "04_practice_start")
    practice.start("practice")
    pump(app, 1.5)
    if want("05_practice_running"):
        save(practice, out, "05_practice_running")
    practice.close()

    window.set_ui_mode("creator")
    overlay = window.creator
    pump(app, 2.0)
    if want("06_broadcast_standard"):
        save(overlay, out, "06_broadcast_standard")
    from dataclasses import replace

    overlay.apply_settings(replace(overlay.settings, transparent_background=True))
    pump(app, 3.0)
    if want("07_broadcast_transparent"):
        save(overlay, out, "07_broadcast_transparent")
    menu = overlay.build_menu()
    menu.popup(QPoint(40, 40))
    pump(app, 0.5)
    if want("08_broadcast_menu"):
        save(menu, out, "08_broadcast_menu")
    menu.close()
    overlay.apply_settings(replace(overlay.settings, transparent_background=False))
    window.set_ui_mode("developer")
    pump(app, 0.5)
    tray_menu = window.tray.menu
    tray_menu.popup(QPoint(40, 40))
    pump(app, 0.5)
    if want("09_tray_menu"):
        save(tray_menu, out, "09_tray_menu")
    tray_menu.close()
    window.stop_camera()
    pump(app, 1.0)
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
