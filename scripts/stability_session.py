"""Sustained stability session with the real application window, webcam and model.

The script opens the normal main window and drives it like a user would: it starts the
camera, periodically stops and restarts it, resizes the window, toggles mirroring and
overlay layers, and finally closes the window. Once per second it records the measured
pipeline metrics, process CPU/memory and the UI event-loop responsiveness (how late a
50 ms heartbeat timer fires). Camera restart timings are observed by the 1 s sampler, so
they have one-second resolution. No images are stored.

The window runs with the production services (gesture engine, dispatcher, browser bridge on a
free port, local analytics in a temporary directory), so periodic UI work such as the daily
statistics query is part of the measurement. The window's stall monitor attributes every UI
stall to the running handler, garbage collection and worker-thread progress; the report lists
these stalls and the measured duration of each UI handler.

Example:
    python scripts/stability_session.py --minutes 10 --output reports/stability.json
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from _measure import environment, summarize
from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.app import configure_logging
from interactive_scrolling.config.settings import AppSettings
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import CameraState
from interactive_scrolling.core.platform import disable_power_throttling
from interactive_scrolling.services import build_services
from interactive_scrolling.storage.settings_store import SettingsStore, UserSettings
from interactive_scrolling.ui.main_window import MainWindow
from interactive_scrolling.ui.stall_probe import EventProbe
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
    parser.add_argument(
        "--mode",
        choices=[m.value for m in ControlMode if m is not ControlMode.LIVE_CONTROL],
        default=ControlMode.GESTURE_TEST.value,
        help="control mode during the session (live control is never enabled by this script)",
    )
    parser.add_argument(
        "--ui-mode",
        choices=["developer", "creator", "background"],
        default="developer",
        help="presentation mode for the session (Brief 007)",
    )
    parser.add_argument(
        "--cycle-modes",
        type=float,
        default=0.0,
        help="seconds between presentation-mode changes (developer -> creator -> background); "
        "invariants are checked every second",
    )
    parser.add_argument(
        "--optional-models",
        action="store_true",
        help="load the person-segmentation and face-landmark models and enable eye analytics",
    )
    parser.add_argument("--transparent", action="store_true", help="transparent Broadcast overlay")
    args = parser.parse_args()
    mode = ControlMode(args.mode)

    configure_logging("WARNING")
    warnings = WarningCollector()
    logging.getLogger().addHandler(warnings)
    throttling_disabled = disable_power_throttling()

    settings = AppSettings()
    model = default_model_path()
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    data_dir = Path(tempfile.mkdtemp(prefix="is-stability-"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    SettingsStore(data_dir / "settings.json").save(UserSettings(bridge_port=port))
    services = build_services(data_dir)
    extra: dict = {}
    if args.optional_models:
        from interactive_scrolling.vision.face_tracker import MediaPipeFaceTracker
        from interactive_scrolling.vision.model_assets import FACE_MODEL, SEGMENTER_MODEL
        from interactive_scrolling.vision.segmenter import MediaPipePersonSegmenter

        extra = {
            "segmenter_factory": lambda: MediaPipePersonSegmenter(SEGMENTER_MODEL.path()),
            "face_factory": lambda: MediaPipeFaceTracker(FACE_MODEL.path()),
        }
        from dataclasses import replace as _replace

        effects = _replace(services.user_settings.effects, eye_analytics_enabled=True)
        services.update_settings(effects=effects)
    if args.transparent:
        from dataclasses import replace as _replace

        services.update_settings(
            creator=_replace(services.user_settings.creator, transparent_background=True)
        )
    window = MainWindow(
        settings,
        camera_factory=OpenCVCamera,
        tracker_factory=lambda: MediaPipeHandTracker(settings.tracking, model),
        services=services,
        **extra,
    )
    probe = EventProbe()
    probe.attach(app)
    window.stall_monitor.context_provider = probe.describe
    window.show()
    monitor = ResourceMonitor()

    duration_s = args.minutes * 60
    start_ns = time.perf_counter_ns()
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
        "last_cycle": time.perf_counter(),
        "cycle_index": 0,
    }
    transitions: list[dict] = []
    violations: list[str] = []
    cycle = ("developer", "creator", "background")

    def check_invariants(elapsed: float) -> None:
        if window.services.dispatcher.mode is not mode:
            violations.append(
                f"{elapsed:.0f}s control mode changed to {window.services.dispatcher.mode}"
            )
        workers = [t.name for t in threading.enumerate() if t.is_alive()]
        for name in ("camera-capture", "vision-processing"):
            n = sum(1 for w in workers if w.startswith(name))
            if n > 1:
                violations.append(f"{elapsed:.0f}s {n} {name} threads")
        seg = window.segmenter
        if seg is not None:
            should = window.creator.isVisible() and window.creator.settings.transparent_background
            if seg.enabled != should:
                violations.append(
                    f"{elapsed:.0f}s segmentation enabled={seg.enabled}, expected {should}"
                )

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
        # Counting threads enumerates the whole system on Windows (~13 ms on the UI thread),
        # so it is sampled every 10 s only.
        r = monitor.sample(include_threads=state["tick"] % 10 == 0)
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
                "gesture_ms": round(window.pipeline.gesture_ms_mean, 3)
                if window.pipeline.gesture_ms_mean is not None
                else None,
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

        if args.cycle_modes and time.perf_counter() - state["last_cycle"] >= args.cycle_modes:
            state["last_cycle"] = time.perf_counter()
            state["cycle_index"] += 1
            target = cycle[state["cycle_index"] % len(cycle)]
            t_switch = time.perf_counter()
            window.set_ui_mode(target)
            transitions.append(
                {
                    "at_s": round(elapsed, 1),
                    "to": target,
                    "ms": round((time.perf_counter() - t_switch) * 1000, 1),
                }
            )
        if state["tick"] > 3:
            check_invariants(elapsed)
        if state["tick"] % 30 == 0 and window.isVisible():
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
    QTimer.singleShot(600, lambda: window.set_control_mode(mode))
    if args.ui_mode != "developer":
        QTimer.singleShot(1500, lambda: window.set_ui_mode(args.ui_mode))
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
            "control_mode": mode.value,
            "ui_mode": args.ui_mode,
            "optional_models": args.optional_models,
            "transparent": args.transparent,
            "mode_transitions": len(transitions),
            "mode_transition_ms": summarize([t["ms"] for t in transitions]),
            "invariant_violations": violations[:50],
            "gesture_ms": summarize([s["gesture_ms"] for s in running if s["gesture_ms"]]),
            "gestures_recognized": window.history.rowCount(),
            "cpu_percent_of_machine": summarize([s["cpu_percent_machine"] for s in samples]),
            "rss_mb": summarize([s["rss_mb"] for s in samples]),
            "rss_first_minute_mean": round(sum(first_minute) / len(first_minute), 1)
            if first_minute
            else None,
            "rss_last_minute_mean": round(sum(last_minute) / len(last_minute), 1)
            if last_minute
            else None,
            "threads": summarize(
                [float(s["threads"]) for s in samples if s["threads"] is not None]
            ),
            "ui_heartbeat_lateness_ms": summarize(heartbeat_lateness),
            "samples_with_hands": sum(1 for s in samples if s["hands"]),
            "frames_dropped_total": samples[-1]["dropped_total"] if samples else None,
            "camera_restarts": restarts,
            "ui_stalls": [
                {
                    "duration_ms": round(st.duration_ms, 1),
                    "section": st.section,
                    "gc_ms": round(st.gc_ms, 1),
                    "worker_gaps_ms": {k: round(v, 1) for k, v in st.worker_gaps_ms.items()},
                    "ui_stack_top": [line.strip() for line in st.ui_stack[-3:]],
                    "qt": st.context,
                    "at_s": round((st.started_ns - start_ns) / 1e9, 1),
                }
                for st in window.stall_monitor.stalls
            ],
            "ui_sections_ms": {
                name: {
                    "calls": v.calls,
                    "mean": round(v.mean_ms, 3),
                    "max": round(v.max_ms, 1),
                }
                for name, v in window.stall_monitor.section_stats().items()
            },
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
