"""Measure which camera modes the webcam really delivers (development tool, Brief 009).

For each backend (Media Foundation, DirectShow), pixel format (driver default, MJPG, YUY2) and
resolution / frame-rate request, the camera is opened, the request applied, and frames read
for ``--seconds``. Reported per mode: what the driver claims (width, height, fps, fourcc),
the delivered frame rate measured with perf_counter, the rate of *unique* frames (a frame
identical to the previous one is a duplicate), the read-interval jitter and, for Media
Foundation, the interval of the driver's own sample timestamps (CAP_PROP_POS_MSEC).

The API's return values are never taken as proof: only measured unique frames count.

Usage:
    python scripts/probe_camera_modes.py --index 0 --seconds 4 --json reports/b9_cameras.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

MODES = [
    (1920, 1080, 30),
    (1280, 720, 30),
    (1280, 720, 60),
    (640, 480, 30),
    (640, 480, 60),
    (640, 480, 120),
]
BACKENDS = {"msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW}
FORMATS = [None, "MJPG", "YUY2"]


def fourcc_text(value: float) -> str:
    code = int(value)
    text = "".join(chr((code >> 8 * i) & 0xFF) for i in range(4))
    return text if text.isprintable() and text.strip() else str(code)


def probe(
    index: int, api: int, fmt: str | None, mode: tuple[int, int, int], seconds: float
) -> dict:
    width, height, fps = mode
    cap = cv2.VideoCapture(index, api)
    result: dict = {"requested": f"{width}x{height}@{fps}", "format": fmt or "default"}
    if not cap.isOpened():
        result["error"] = "could not open"
        return result
    try:
        if fmt:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fmt))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        for _ in range(10):  # warm up (exposure, first buffers)
            cap.read()
        result["claimed"] = {
            "size": f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
            "fps": round(cap.get(cv2.CAP_PROP_FPS), 2),
            "fourcc": fourcc_text(cap.get(cv2.CAP_PROP_FOURCC)),
        }
        times, positions, unique = [], [], 0
        last = None
        shape = None
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            ok, image = cap.read()
            now = time.perf_counter()
            if not ok or image is None:
                continue
            shape = image.shape
            times.append(now)
            positions.append(cap.get(cv2.CAP_PROP_POS_MSEC))
            sample = image[::8, ::8].astype(np.int16)
            if last is None or np.abs(sample - last).mean() > 0.05:
                unique += 1
            last = sample
        span = times[-1] - times[0] if len(times) > 1 else 0.0
        intervals = np.diff(times) * 1000 if len(times) > 1 else np.zeros(0)
        pos = np.diff([p for p in positions if p > 0]) if positions else np.zeros(0)
        result.update(
            {
                "delivered_size": f"{shape[1]}x{shape[0]}" if shape else None,
                "delivered_fps": round((len(times) - 1) / span, 2) if span else 0.0,
                "unique_fps": round(unique / span, 2) if span else 0.0,
                "read_interval_ms_sd": round(float(intervals.std()), 2) if intervals.size else None,
                "driver_interval_ms_median": round(float(np.median(pos)), 2) if pos.size else None,
            }
        )
    finally:
        cap.release()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--backends", default="msmf,dshow")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    results = []
    for backend in args.backends.split(","):
        for fmt in FORMATS:
            for mode in MODES:
                r = probe(args.index, BACKENDS[backend], fmt, mode, args.seconds)
                r["backend"] = backend
                results.append(r)
                print(
                    f"{backend:5s} {r['format']:7s} {r['requested']:15s} -> "
                    f"claimed {r.get('claimed')} delivered {r.get('delivered_size')} "
                    f"{r.get('delivered_fps')} fps, unique {r.get('unique_fps')} fps, "
                    f"jitter sd {r.get('read_interval_ms_sd')} ms, driver interval "
                    f"{r.get('driver_interval_ms_median')} ms {r.get('error', '')}",
                    flush=True,
                )
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
