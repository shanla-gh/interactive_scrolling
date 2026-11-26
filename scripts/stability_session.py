"""Sustained stability session with the real application window, webcam and model.

The script opens the normal main window and drives it like a user would: it starts the
camera, periodically stops and restarts it, resizes the window, toggles mirroring and
overlay layers, and finally closes the window. Once per second it records the measured
pipeline metrics, process CPU/memory and the UI event-loop responsiveness (how late a
50 ms heartbeat timer fires). Camera restart timings are observed by the 1 s sampler, so
they have one-second resolution. No images are stored.

Example:
    python scripts/stability_session.py --minutes 10 --output reports/stability.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from _measure import environment, summarize
from interactive_scrolling.app import configure_logging
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import CameraState
from interactive_scrolling.core.platform import disable_power_throttling
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.ui.theme import apply_theme
from interactive_scrolling.vision.camera import OpenCVCamera
from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
from interactive_scrolling.vision.model_assets import default_model_path

HEARTBEAT_MS = 50
SIZES = [(1360, 860), (1000, 660), (1700, 1000), (1180, 720)]


class WarningCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(f"{record.levelname}: {record.getMessage()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--restart-every", type=float, default=120.0, help="seconds")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    configure_logging("WARNING")
    warnings = WarningCollector()
    logging.getLogger().addHandler(warnings)
    throttling_disabled = disable_power_throttling()

    settings = AppSettings()
    model = default_model_path()
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    window = MainWindow(
        settings,
        camera_factory=OpenCVCamera,
        tracker_factory=lambda: MediaPipeHandTracker(settings.tracking, model),
    )
    window.show()
    monitor = ResourceMonitor()

    duration_s = args.minutes * 60
    samples: list[dict] = []
    heartbeat_lateness: list[float] = []
    restarts: list[dict] = []
    state = {
        "start": time.perf_counter(),
        "last_beat": time.perf_counter(),
        "beat_max": 0.0,
        "last_restart": time.perf_counter(),
        "tick": 0,
        "restart_pending": None,
    }

    def heartbeat() -> None:
        now = time.perf_counter()
        late = (now - state["last_beat"]) * 1000 - HEARTBEAT_MS
        state["last_beat"] = now
        heartbeat_lateness.append(max(0.0, late))
        state["beat_max"] = max(state["beat_max"], late)

    def sample() -> None:
        state["tick"] += 1
        elapsed = time.perf_counter() - state["start"]
        m = window.pipeline.metrics()
        r = monitor.sample()
        frame = window.video.frame
        samples.append(
            {
                "t": round(elapsed, 1),
                "camera": m.camera_state.value,
                "capture_fps": round(m.capture_fps, 1),
                "processing_fps": round(m.processing_fps, 1),
                "display_fps": round(window.video.display_rate.rate(), 1),
                "latency_ms": round(m.latency_ms, 1) if m.latency_ms else None,
                "inference_ms": round(m.inference_ms, 1) if m.inference_ms else None,
                "dropped_total": m.frames_dropped,
                "hands": frame.tracking.hand_count if frame else None,
                "cpu_percent_machine": round(r.cpu_percent_of_machine, 1),
                "rss_mb": round(r.rss_mb, 1),
                "threads": r.thread_count,
                "ui_heartbeat_max_late_ms": round(state["beat_max"], 1),
            }
        )
        state["beat_max"] = 0.0

        pending = state["restart_pending"]
        if pending is not None:
            if pending["phase"] == "stopping" and m.camera_state is CameraState.STOPPED:
                pending["stopped_after_s"] = round(time.perf_counter() - pending["t0"], 2)
                pending["phase"] = "starting"
                pending["t1"] = time.perf_counter()
                window.start_camera()
            elif pending["phase"] == "starting" and m.camera_state is CameraState.RUNNING:
                pending["running_after_s"] = round(time.perf_counter() - pending["t1"], 2)
                pending["ok"] = True
                del pending["t0"], pending["t1"], pending["phase"]
                restarts.append(pending)
                state["restart_pending"] = None
            elif time.perf_counter() - pending["t0"] > 20:
                pending["ok"] = False
                pending["camera_state"] = m.camera_state.value
                restarts.append({k: v for k, v in pending.items() if k not in ("t0", "t1")})
                state["restart_pending"] = None
                window.start_camera()
        elif time.perf_counter() - state["last_restart"] >= args.restart_every:
            state["last_restart"] = time.perf_counter()
            state["restart_pending"] = {
                "at_s": round(elapsed, 1),
                "phase": "stopping",
                "t0": time.perf_counter(),
            }
            window.stop_camera()

        if state["tick"] % 30 == 0:
            window.resize(*SIZES[(state["tick"] // 30) % len(SIZES)])
        if state["tick"] % 45 == 0:
            window.overlay_panel.mirror.toggle()
        if state["tick"] % 20 == 0:
            box = window.overlay_panel.checkboxes["show_palm_trail"]
            box.toggle()

        if elapsed >= duration_s:
            finish()

    def finish() -> None:
        sampler.stop()
        beat.stop()
        t0 = time.perf_counter()
        window.close()
        report["shutdown_s"] = round(time.perf_counter() - t0, 3)
        report["camera_state_after_close"] = window.pipeline.camera_state.value
        report["worker_threads_alive_after_close"] = [
            t.name
            for t in threading.enumerate()
            if t.name.startswith(("camera-capture", "vision-processing", "tracker-loader"))
            and t.is_alive()
        ]
        app.quit()

    report: dict = {}
    beat = QTimer()
    # A precise timer, so lateness reflects event-loop blocking rather than the coarse
    # default timer slack (Windows' 15.6 ms scheduler tick).
    beat.setTimerType(Qt.TimerType.PreciseTimer)
    beat.setInterval(HEARTBEAT_MS)
    beat.timeout.connect(heartbeat)
    beat.start()
    sampler = QTimer()
    sampler.setInterval(1000)
    sampler.timeout.connect(sample)
    sampler.start()
    QTimer.singleShot(500, window.start_camera)
    app.exec()

    running = [s for s in samples if s["camera"] == "running" and s["processing_fps"] > 0]
    first_minute = [s["rss_mb"] for s in samples if 30 <= s["t"] < 90]
    last_minute = [s["rss_mb"] for s in samples if s["t"] >= samples[-1]["t"] - 60]
    report.update(
        {
            "kind": "gui-stability-session",
            "date_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "environment": environment(),
            "power_throttling_disabled": throttling_disabled,
            "requested_minutes": args.minutes,
            "measured_seconds": samples[-1]["t"] if samples else 0,
            "capture_fps": summarize([s["capture_fps"] for s in running]),
            "processing_fps": summarize([s["processing_fps"] for s in running]),
            "display_fps": summarize([s["display_fps"] for s in running]),
            "latency_ms": summarize([s["latency_ms"] for s in running if s["latency_ms"]]),
            "inference_ms": summarize([s["inference_ms"] for s in running if s["inference_ms"]]),
            "cpu_percent_of_machine": summarize([s["cpu_percent_machine"] for s in samples]),
            "rss_mb": summarize([s["rss_mb"] for s in samples]),
            "rss_first_minute_mean": round(sum(first_minute) / len(first_minute), 1)
            if first_minute
            else None,
            "rss_last_minute_mean": round(sum(last_minute) / len(last_minute), 1)
            if last_minute
            else None,
            "threads": summarize([float(s["threads"]) for s in samples]),
            "ui_heartbeat_lateness_ms": summarize(heartbeat_lateness),
            "samples_with_hands": sum(1 for s in samples if s["hands"]),
            "frames_dropped_total": samples[-1]["dropped_total"] if samples else None,
            "camera_restarts": restarts,
            "warnings_and_errors": warnings.records[-50:],
            "samples": samples,
        }
    )
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("samples", "environment")}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
