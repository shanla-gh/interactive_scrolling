"""The real Normal Mode window with a real live Shorts preview (development tool, Brief 008).

Starts the application window (synthetic camera scene, no person) with the real services and
browser bridge, a throw-away signed-out Edge profile with the real extension, opens YouTube
Shorts and starts the tab capture (the Chromium test switch replaces the click on the extension
icon). It then:

1. screenshots the window with the live preview (and after a Next Short while the app is the
   active window, through the preview-tab control path);
2. measures the preview frames actually painted by the app per second and the time the UI
   thread spends decoding them.

Output: ``--out`` (screenshots show YouTube content: keep them local, ``screenshots/`` is not
committed) and a JSON report with ``--json``.

Usage: python scripts/capture_live_preview.py --out screenshots/brief008/live --scale 1.0
"""

from __future__ import annotations

import argparse
import json
import os
import socket
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
    parser.add_argument("--size", default="1536x824")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--json", type=Path)
    return parser.parse_args()


ARGS = parse()
os.environ["QT_SCALE_FACTOR"] = str(ARGS.scale)

from PySide6.QtWidgets import QApplication  # noqa: E402
from tests.browser_helpers import TAB_CAPTURE_TEST_ARGS, Browser, find_browser  # noqa: E402

from interactive_scrolling.actions.types import ActionType, ControlMode  # noqa: E402
from interactive_scrolling.config.settings import AppSettings, CameraSettings  # noqa: E402
from interactive_scrolling.gestures.types import GestureEvent, GestureType  # noqa: E402
from interactive_scrolling.services import build_services  # noqa: E402
from interactive_scrolling.ui.theme import apply_theme  # noqa: E402
from interactive_scrolling.vision.landmarks import Handedness  # noqa: E402
from synthetic_scene import H, SceneCamera, ScriptedHand, W  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def main() -> int:
    from interactive_scrolling.ui.main_window import MainWindow

    executable = find_browser(prefer_extension_support=True)
    if executable is None:
        print("Microsoft Edge not installed")
        return 2
    ARGS.out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    services = build_services(Path(tempfile.mkdtemp(prefix="is-live-")), start_bridge=False)
    bridge = services.bridge
    bridge.port = free_port()
    assert bridge.start()
    token = services.user_settings.pairing_token
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=W, height=H)),
        camera_factory=SceneCamera,
        tracker_factory=ScriptedHand,
        services=services,
    )
    width, height = (int(v) for v in ARGS.size.split("x"))
    window.resize(width, height)
    window.move(0, 0)
    window.show()
    window.start_camera()
    report: dict = {}
    browser = Browser(
        executable, free_port(), extension=True, headless=False, extra_args=TAB_CAPTURE_TEST_ARGS
    )
    try:
        worker = browser.extension_worker()
        worker.eval(
            f"chrome.storage.local.set({{token: '{token}', port: {bridge.port}}})"
            ".then(() => connect())"
        )
        page = browser.new_tab()
        page.call("Page.navigate", url="https://www.youtube.com/shorts")
        pump(app, 5)
        if "consent." in page.eval("location.host"):
            page.eval(
                "[...document.querySelectorAll('button')]"
                ".find(b => b.innerText.trim() === 'Reject all').click()"
            )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            browser.activate(page)
            status = services.controller.status()
            if status.ready:
                break
            pump(app, 0.5)
        tab_id = bridge.clients()[0].context.shorts.tab_id
        browser.activate(page)
        pump(app, 0.5)
        report["start"] = worker.eval(f"startPreview({tab_id})")
        pump(app, 3.0)
        window.raise_()
        window.activateWindow()
        services.controller.app_in_front = True  # the harness window may not get OS focus
        pump(app, 2.0)
        path = ARGS.out / "live_preview_normal_mode.png"
        window.grab().save(str(path))
        print(path)

        # Painted preview frames and decode cost while the app is in front.
        decoded0 = window.preview.decoded
        from PySide6.QtGui import QImage

        costs = []
        end = time.monotonic() + ARGS.seconds
        while time.monotonic() < end:
            frame = bridge.preview.latest()
            if frame is not None:
                t0 = time.perf_counter()
                QImage.fromData(frame.jpeg, "JPG")
                costs.append((time.perf_counter() - t0) * 1000)
            pump(app, 0.1)
        report["painted_fps"] = round((window.preview.decoded - decoded0) / ARGS.seconds, 1)
        report["decode_ms_median"] = round(sorted(costs)[len(costs) // 2], 2) if costs else None
        status = bridge.preview.status()
        report["received_fps"] = round(status.fps, 1)
        report["transport_ms_median"] = status.transport_ms

        # A Next Short through the preview tab while the app is in front (Live control).
        window.set_control_mode(ControlMode.LIVE_CONTROL)
        before = page.eval("location.pathname")
        records = []
        services.dispatcher.add_record_listener(records.append)
        services.dispatcher.submit(
            GestureEvent(GestureType.INDEX_SWIPE_UP, time.perf_counter_ns(), 1, Handedness.RIGHT)
        )
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and not any(r.status.final for r in records):
            pump(app, 0.1)
        final = [r for r in records if r.status.final]
        report["next_from_app"] = (
            {
                "status": final[-1].status.value,
                "reason": final[-1].reason,
                "action": final[-1].action is ActionType.NEXT_SHORT,
                "url_changed": page.eval("location.pathname") != before,
            }
            if final
            else "no final record"
        )
        window.set_control_mode(ControlMode.TRACKING_ONLY)
        pump(app, 2.0)
        path = ARGS.out / "live_preview_after_next.png"
        window.grab().save(str(path))
        print(path)
        window.console.set_expanded(True)
        window.console.tabs.setCurrentIndex(3)
        window._update_control_status()
        pump(app, 1.0)
        path = ARGS.out / "live_preview_console_connections.png"
        window.grab().save(str(path))
        print(path)
        window.console.set_expanded(False)

        # Leaving Shorts hides the picture; stopping from the app ends the capture.
        page.call("Page.navigate", url="https://www.youtube.com/")
        pump(app, 3.0)
        path = ARGS.out / "live_preview_left_shorts.png"
        window.grab().save(str(path))
        print(path)
        report["left_shorts_picture"] = window.preview.image is not None
        page.call("Page.navigate", url="https://www.youtube.com/shorts")
        pump(app, 6.0)
        window.stop_preview()
        pump(app, 2.0)
        report["after_stop_connected"] = bridge.preview.status().connected
        path = ARGS.out / "live_preview_stopped.png"
        window.grab().save(str(path))
        print(path)
    finally:
        browser.close()
        window.close()
        pump(app, 0.5)
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if ARGS.json:
        ARGS.json.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
