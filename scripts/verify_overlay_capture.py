"""Check how Windows capture paths see the transparent Content Creator overlay.

Shows the real :class:`CreatorOverlay` (transparent background, synthetic camera frame, a person
mask covering the left half) on the desktop and captures it twice:

1. **Desktop composition** (screen BitBlt with CAPTUREBLT, what screen/display capture and
   OBS "Display Capture" see): the right half must show whatever is behind the overlay, the left
   half the camera image - i.e. per-pixel transparency is composited by Windows.
2. **PrintWindow(PW_RENDERFULLCONTENT)** of the overlay window alone (similar to OBS "Window
   Capture" with the BitBlt method): reports what the transparent pixels look like there.

OBS's "Windows 10 (1903 and up)" window-capture method (Windows Graphics Capture) cannot be
exercised without driving OBS itself; it stays in the Director checklist. Nothing is stored
except the numeric report printed at the end.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

import numpy as np
from PIL import ImageGrab
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from interactive_scrolling.config.settings import AppearanceSettings, CreatorSettings, OverlayCorner
from interactive_scrolling.core.auxiliary import AuxResult
from interactive_scrolling.core.pipeline import ProcessedFrame
from interactive_scrolling.motion.analyzer import MotionFrame
from interactive_scrolling.ui.creator_overlay import CreatorOverlay
from interactive_scrolling.vision.landmarks import TrackingResult

X, Y, W, H = 200, 200, 480, 270


class FixedMask:
    def __init__(self) -> None:
        mask = np.zeros((90, 160), dtype=np.float32)
        mask[:, :80] = 1.0
        self.result: AuxResult | None = None
        self.mask = mask

    def latest(self) -> AuxResult | None:
        return self.result

    def set_enabled(self, enabled: bool) -> None:
        pass


def print_window(hwnd: int) -> np.ndarray:
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(hdc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, bitmap)
    ok = user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    buffer = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8)), (H, W, 4))
    out = buffer.copy()
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not ok:
        raise RuntimeError("PrintWindow failed")
    return out  # BGRA


def main() -> int:
    app = QApplication(sys.argv[:1])
    backdrop = QWidget()
    backdrop.setStyleSheet("background: #ff00ff;")  # magenta behind the overlay
    backdrop.setGeometry(X - 40, Y - 40, W + 80, H + 80)
    backdrop.show()
    worker = FixedMask()
    overlay = CreatorOverlay(
        CreatorSettings(
            width=W,
            height=H,
            x=X,
            y=Y,
            corner=OverlayCorner.CUSTOM,
            transparent_background=True,
            show_skeleton=False,
        ),
        AppearanceSettings(),
        worker,  # type: ignore[arg-type]
    )
    overlay.mirrored = False
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    image[..., 1] = 200  # green camera image
    now = time.perf_counter_ns()
    frame = ProcessedFrame(
        1,
        image,
        TrackingResult(0, now, 640, 360, ()),
        MotionFrame(now, ()),
        now,
        now,
        None,
        0.0,
    )
    worker.result = AuxResult(worker.mask, now, 1, now)
    overlay.show()
    overlay.move(X, Y)
    overlay.show_frame(frame)
    report: dict[str, object] = {}

    def capture() -> None:
        grab = np.asarray(ImageGrab.grab(bbox=(X, Y, X + W, Y + H), all_screens=True))
        left, right = grab[H // 2, W // 4], grab[H // 2, 3 * W // 4]
        report["desktop_left_rgb"] = left.tolist()
        report["desktop_right_rgb"] = right.tolist()
        report["desktop_person_opaque"] = bool(left[1] > 150 and left[0] < 80)
        report["desktop_background_shows_window_behind"] = bool(right[0] > 200 and right[2] > 200)
        pw = print_window(int(overlay.winId()))
        b, g, r, a = (int(v) for v in pw[H // 2, 3 * W // 4])
        report["printwindow_transparent_pixel_bgra"] = [b, g, r, a]
        report["printwindow_person_pixel_bgra"] = [int(v) for v in pw[H // 2, W // 4]]
        overlay.close()
        backdrop.close()
        app.quit()

    QTimer.singleShot(1500, capture)
    app.exec()
    print(report)
    return 0 if report.get("desktop_person_opaque") else 1


if __name__ == "__main__":
    raise SystemExit(main())
