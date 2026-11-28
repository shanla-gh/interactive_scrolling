"""Approach C prototype: capture the browser *window* with Win32 PrintWindow (Brief 008).

For the live-preview architecture comparison only (never used by the application). Opens a
throw-away Edge window on YouTube Shorts and measures, with ctypes only:

* how fast ``PrintWindow(PW_RENDERFULLCONTENT)`` delivers the whole window (frames per second
  and milliseconds per grab, which runs on the calling thread);
* what it shows when another tab is in front (privacy: the whole window, any tab);
* whether it works while the window is minimized.

Window capture of this kind (like Windows Graphics Capture of a window) captures the window,
not the tab: these properties decide the comparison in docs/architecture/LIVE_PREVIEW.md.
Saved images show YouTube/other content: keep them local (screenshots/ is not committed).

Usage: python scripts/prototype_window_capture.py --out screenshots/brief008/window_capture
"""

from __future__ import annotations

import argparse
import ctypes
import json
import socket
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.browser_helpers import Browser, find_browser  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
PW_RENDERFULLCONTENT = 0x2
_H = wintypes.HANDLE
user32.GetWindowDC.argtypes = (wintypes.HWND,)
user32.GetWindowDC.restype = _H
user32.ReleaseDC.argtypes = (wintypes.HWND, _H)
user32.PrintWindow.argtypes = (wintypes.HWND, _H, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.SetWindowPos.argtypes = (
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
gdi32.CreateCompatibleDC.argtypes = (_H,)
gdi32.CreateCompatibleDC.restype = _H
gdi32.CreateCompatibleBitmap.argtypes = (_H, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = _H
gdi32.SelectObject.argtypes = (_H, _H)
gdi32.SelectObject.restype = _H
gdi32.GetDIBits.argtypes = (
    _H,
    _H,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
)
gdi32.DeleteObject.argtypes = (_H,)
gdi32.DeleteDC.argtypes = (_H,)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = (
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
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def edge_window(pid_root: int) -> int | None:
    """The visible top-level Chrome_WidgetWin_1 window of the launched browser."""
    import psutil

    pids = {pid_root} | {p.pid for p in psutil.Process(pid_root).children(recursive=True)}
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):  # type: ignore[no-untyped-def]
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if pid.value in pids and name.value == "Chrome_WidgetWin_1":
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if rect.right - rect.left > 400 and user32.IsWindowVisible(hwnd):
                found.append((area, hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return max(found)[1] if found else None


def grab(hwnd: int) -> np.ndarray | None:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = np.empty((h, w, 4), dtype=np.uint8)
    gdi32.GetDIBits(mem, bmp, 0, h, buffer.ctypes.data, ctypes.byref(header), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return buffer if ok else None


def measure(hwnd: int, seconds: float) -> dict:
    times = []
    distinct = 0
    last = None
    end = time.perf_counter() + seconds
    image = None
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        image = grab(hwnd)
        times.append((time.perf_counter() - t0) * 1000)
        if image is not None:
            sample = image[::16, ::16, :3].copy()
            if last is None or np.abs(sample.astype(int) - last).mean() > 0.5:
                distinct += 1
            last = sample.astype(int)
    return {
        "grabs_per_s": round(len(times) / seconds, 1),
        "ms_per_grab_median": round(sorted(times)[len(times) // 2], 1),
        "changing_frames_per_s": round(distinct / seconds, 1),
        "mean_brightness": round(float(image[..., :3].mean()), 1) if image is not None else None,
        "image": image,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    import cv2

    executable = find_browser(prefer_extension_support=True)
    browser = Browser(executable, free_port(), extension=False, headless=False)
    report: dict = {}
    try:
        page = browser.new_tab()
        page.call("Page.navigate", url="https://www.youtube.com/shorts")
        time.sleep(8)
        if "consent." in page.eval("location.host"):
            page.eval(
                "[...document.querySelectorAll('button')]"
                ".find(b => b.innerText.trim() === 'Reject all').click()"
            )
            time.sleep(5)
        browser.activate(page)
        hwnd = edge_window(browser.process.pid)
        if hwnd is None:
            print("browser window not found")
            return 1
        # The test browser starts off-screen; window capture needs it on a screen.
        user32.SetWindowPos(hwnd, 0, 40, 40, 1280, 900, 0x0004)
        time.sleep(2)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        report["window_px"] = [rect.right - rect.left, rect.bottom - rect.top]
        for name in ("shorts_in_front", "other_tab_in_front", "minimized"):
            if name == "other_tab_in_front":
                other = browser.new_tab()
                other.call("Page.navigate", url="https://example.com/")
                time.sleep(2)
            if name == "minimized":
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                time.sleep(1.5)
            result = measure(hwnd, args.seconds)
            image = result.pop("image")
            if image is not None:
                cv2.imwrite(str(args.out / f"window_capture_{name}.png"), image[..., :3])
            report[name] = result
            print(name, result)
    finally:
        browser.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
