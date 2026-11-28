"""Full-application benchmark across presentation modes with identical input (Brief 009).

Deterministic replay through the real application: a recording's landmark frames are played
through the real ``MainWindow`` (real pipeline threads, real dispatcher, real Qt painting,
real optional models), so every scenario receives the same hand input at the recording's
own timing. The real MediaPipe hand model still runs on every frame (on the synthetic camera
image) so the inference cost is realistic; its output is replaced by the recorded landmarks.
The browser is scripted: every action is confirmed after ``--browser-ms``.

Measured per scenario (monotonic perf_counter timestamps):
  * per processed frame: capture -> recognition latency, processing interval (jitter),
    frames dropped (never processed);
  * per recognized gesture: decision delay after the stroke (engine), recognition -> dispatch
    (record created), dispatch -> verified result, result -> UI thread (feedback can paint);
  * UI thread lateness (10 ms timer), painted camera / overlay frames, optional worker rates,
    process CPU;
  * the recognized gesture sequence, to compare modes (recognition must not depend on mode).

This is replay of development recordings (one person), not a human interaction test.

Usage:
    python scripts/benchmark_modes.py --seconds 75 --json reports/b9_modes.json
    python scripts/benchmark_modes.py --only normal,broadcast_all
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import psutil  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from evaluate_gestures import load, tracking_of  # noqa: E402
from interactive_scrolling.actions.dispatcher import ActionDispatcher  # noqa: E402
from interactive_scrolling.actions.types import (  # noqa: E402
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
)
from interactive_scrolling.config.settings import AppSettings, CameraSettings  # noqa: E402
from interactive_scrolling.gestures.engine import GestureEngine  # noqa: E402
from interactive_scrolling.integrations.youtube.bridge import BridgeServer  # noqa: E402
from interactive_scrolling.integrations.youtube.controller import (  # noqa: E402
    YouTubeShortsController,
)
from interactive_scrolling.integrations.youtube.protocol import PreviewFrame  # noqa: E402
from interactive_scrolling.services import ControlServices  # noqa: E402
from interactive_scrolling.storage.settings_store import SettingsStore  # noqa: E402
from interactive_scrolling.ui.theme import apply_theme  # noqa: E402
from interactive_scrolling.vision.camera import Frame  # noqa: E402
from synthetic_scene import H, SceneCamera, W  # noqa: E402

SCENARIOS = {
    "normal": {"ui": "developer"},
    "normal_repeat": {"ui": "developer"},
    "normal_preview": {"ui": "developer", "preview": True},
    "broadcast_basic": {
        "ui": "creator",
        "creator": {"show_skeleton": False, "show_trails": False, "show_vectors": False},
    },
    "broadcast_skeleton_trails": {
        "ui": "creator",
        "creator": {"show_skeleton": True, "show_trails": True, "show_vectors": True},
    },
    "broadcast_transparent": {"ui": "creator", "creator": {"transparent_background": True}},
    "broadcast_clown": {"ui": "creator", "effects": {"clown_enabled": True}},
    "broadcast_eye": {"ui": "creator", "effects": {"eye_analytics_enabled": True}},
    "broadcast_all": {
        "ui": "creator",
        "creator": {
            "transparent_background": True,
            "show_vectors": True,
            "show_counters": True,
        },
        "effects": {"clown_enabled": True, "eye_analytics_enabled": True},
        "preview": True,
    },
    "background": {"ui": "background"},
}


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2)


def dist(values: list[float]) -> dict:
    return {
        "n": len(values),
        "median": pct(values, 0.5),
        "p95": pct(values, 0.95),
        "p99": pct(values, 0.99),
        "max": round(max(values), 2) if values else None,
    }


class ReplayCamera:
    """Delivers the synthetic image at the recording's own frame times."""

    frames: ClassVar[list[dict]] = []
    start_ns = 0

    def __init__(self, settings: CameraSettings) -> None:
        self.settings = settings
        self.actual_width, self.actual_height = W, H
        self._scene = SceneCamera(settings)
        self._i = 0

    def open(self) -> None:
        pass

    def read(self) -> Frame | None:
        frames = ReplayCamera.frames
        if self._i >= len(frames):
            time.sleep(0.05)
            return None
        t0 = frames[0]["t_ns"]
        due = ReplayCamera.start_ns + (frames[self._i]["t_ns"] - t0)
        delay = (due - time.perf_counter_ns()) / 1e9
        if delay > 0:
            time.sleep(delay)
        frame = Frame(image_bgr=self._scene._image, index=self._i, timestamp_ns=due)
        self._i += 1
        return frame

    def close(self) -> None:
        pass


class ReplayTracker:
    """Runs the real hand model for its cost, returns the recorded hands of the frame."""

    def __init__(self) -> None:
        from interactive_scrolling.config.settings import TrackingSettings
        from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
        from interactive_scrolling.vision.model_assets import default_model_path

        self._real = MediaPipeHandTracker(TrackingSettings(), default_model_path())

    def process(self, image_rgb: np.ndarray, timestamp_ms: int):  # type: ignore[no-untyped-def]
        self._real.process(image_rgb, timestamp_ms)
        frames = ReplayCamera.frames
        offset = timestamp_ms * 1_000_000 - ReplayCamera.start_ns
        index = int(np.searchsorted(ReplayFrameTimes.times, offset, side="left"))
        index = min(max(index, 0), len(frames) - 1)
        return tracking_of(frames[index], False).hands

    def close(self) -> None:
        self._real.close()


class ReplayFrameTimes:
    times: np.ndarray = np.zeros(0)


class ScriptedBrowser:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(True)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        time.sleep(self.delay_s)
        return ActionResult(ActionStatus.SUCCEEDED, "", "scripted")

    def cancel_all(self) -> None:
        pass


def run(name: str, spec: dict, frames: list[dict], args: argparse.Namespace) -> dict:
    from interactive_scrolling.ui.main_window import MainWindow
    from interactive_scrolling.vision.face_tracker import MediaPipeFaceTracker
    from interactive_scrolling.vision.model_assets import FACE_MODEL, SEGMENTER_MODEL
    from interactive_scrolling.vision.segmenter import MediaPipePersonSegmenter

    app = QApplication.instance() or QApplication(sys.argv[:1])
    data = Path(tempfile.mkdtemp(prefix="is-modes-"))
    store = SettingsStore(data / "settings.json")
    user = store.load()
    bridge = BridgeServer(0, user.pairing_token)
    services = ControlServices(
        engine=GestureEngine(user.gestures, profile=user.calibration),
        dispatcher=ActionDispatcher(ScriptedBrowser(args.browser_ms / 1000), user.mapping),
        user_settings=user,
        store=store,
        bridge=bridge,
        controller=YouTubeShortsController(bridge),
    )
    if spec.get("creator"):
        services.update_settings(creator=replace(user.creator, **spec["creator"]))
    if spec.get("effects"):
        services.apply_effects(replace(user.effects, **spec["effects"]))
    ReplayCamera.frames = frames
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=W, height=H)),
        camera_factory=ReplayCamera,
        tracker_factory=ReplayTracker,
        services=services,
        segmenter_factory=lambda: MediaPipePersonSegmenter(SEGMENTER_MODEL.path()),
        face_factory=lambda: MediaPipeFaceTracker(FACE_MODEL.path()),
    )
    window.resize(1536, 824)
    window.show()
    pump(app, 4.0)  # models load

    per_frame: list[float] = []
    intervals: list[float] = []
    last_done = [0]
    events: list[dict] = []
    records: dict[str, dict] = {}
    ui_arrivals: dict[str, int] = {}
    lateness: list[float] = []
    painted = {"overlay": 0}
    lock = threading.Lock()

    def gesture_tap(tracking, gestures) -> None:  # type: ignore[no-untyped-def]
        now = time.perf_counter_ns()
        with lock:
            per_frame.append((now - tracking.timestamp_ns) / 1e6)
            if last_done[0]:
                intervals.append((now - last_done[0]) / 1e6)
            last_done[0] = now
            if gestures is not None:
                for ev in gestures.events:
                    events.append(
                        {
                            "gesture": ev.gesture.value,
                            "t_s": round((ev.timestamp_ns - ReplayCamera.start_ns) / 1e9, 3),
                            "decision_ms": round(ev.decision_delay_s * 1000, 1),
                            "recognized_ns": now,
                        }
                    )

    def record_listener(record) -> None:  # type: ignore[no-untyped-def]
        now = time.perf_counter_ns()
        with lock:
            entry = records.setdefault(
                record.record_id, {"event_ns": record.event.timestamp_ns, "created_ns": now}
            )
            if record.status.final and "final_ns" not in entry:
                entry["final_ns"] = now
                entry["status"] = record.status.value

    def ui_slot(record) -> None:  # type: ignore[no-untyped-def]
        if record.status.final:
            ui_arrivals.setdefault(record.record_id, time.perf_counter_ns())

    window.pipeline.add_gesture_tap(gesture_tap)
    split: dict[str, list[float]] = {"inference": [], "processing": [], "wait": []}
    bridge_listener = window.bridge
    original_on_frame = bridge_listener.on_frame

    def on_frame(processed) -> None:  # type: ignore[no-untyped-def]
        with lock:
            if processed.inference_ms is not None:
                split["inference"].append(processed.inference_ms)
            split["processing"].append(processed.processing_ms)
            split["wait"].append(processed.latency_ms - processed.processing_ms)
        original_on_frame(processed)

    bridge_listener.on_frame = on_frame  # type: ignore[method-assign]
    services.dispatcher.add_record_listener(record_listener)
    window._control_signals.record.connect(ui_slot)
    overlay = window.creator
    original_paint = type(overlay).paintEvent

    def counting_paint(event):  # type: ignore[no-untyped-def]
        painted["overlay"] += 1
        return original_paint(overlay, event)

    overlay.paintEvent = counting_paint  # type: ignore[method-assign]
    beat = QTimer()
    beat.setInterval(10)
    last_beat = [time.perf_counter_ns()]

    def on_beat() -> None:
        now = time.perf_counter_ns()
        lateness.append(max(0.0, (now - last_beat[0]) / 1e6 - 10.0))
        last_beat[0] = now

    beat.timeout.connect(on_beat)
    beat.start()

    window.set_control_mode(ControlMode.LIVE_CONTROL)
    window.set_ui_mode(spec["ui"])
    stop_preview = threading.Event()
    if spec.get("preview"):
        jpeg = args.preview_jpeg.read_bytes()
        feed = bridge.preview
        feed.attach(lambda: None)

        def feeder() -> None:
            n = 0
            while not stop_preview.is_set():
                n += 1
                feed.push(PreviewFrame(time.time() * 1000, n, jpeg))
                time.sleep(1 / 30)

        threading.Thread(target=feeder, daemon=True).start()
    process = psutil.Process()
    process.cpu_percent(None)
    video_paints0 = (
        window.video.display_rate.count if hasattr(window.video.display_rate, "count") else None
    )
    decoded0 = window.preview.decoded
    seg0 = window.segmenter.processed if window.segmenter else 0
    face0 = window.face_worker.processed if window.face_worker else 0
    ReplayCamera.start_ns = time.perf_counter_ns() + int(0.5e9)
    ReplayFrameTimes.times = np.array([f["t_ns"] - frames[0]["t_ns"] for f in frames])
    duration = (frames[-1]["t_ns"] - frames[0]["t_ns"]) / 1e9
    window.start_camera()
    pump(app, duration + 1.5)
    cpu = process.cpu_percent(None) / psutil.cpu_count()
    beat.stop()
    stop_preview.set()
    seg = (window.segmenter.processed - seg0) if window.segmenter else 0
    face = (window.face_worker.processed - face0) if window.face_worker else 0
    metrics = window.pipeline.metrics()
    window.close()
    pump(app, 0.5)
    services.dispatcher.shutdown()

    dispatch, verify, to_ui, decision = [], [], [], []
    for ev in events:
        decision.append(ev["decision_ms"])
    for rid, r in records.items():
        dispatch.append((r["created_ns"] - r["event_ns"]) / 1e6)
        if "final_ns" in r:
            verify.append((r["final_ns"] - r["created_ns"]) / 1e6)
            if rid in ui_arrivals:
                to_ui.append((ui_arrivals[rid] - r["final_ns"]) / 1e6)
    statuses: dict[str, int] = {}
    for r in records.values():
        statuses[r.get("status", "pending")] = statuses.get(r.get("status", "pending"), 0) + 1
    _ = video_paints0
    return {
        "scenario": name,
        "seconds": round(duration, 1),
        "recording_frames": len(frames),
        "processed_frames": len(per_frame),
        "frames_dropped": metrics.frames_dropped,
        "capture_to_recognition_ms": dist(per_frame),
        "processing_interval_ms": dist(intervals),
        "ui_lateness_ms": dist(lateness),
        "inference_ms": dist(split["inference"]),
        "processing_ms": dist(split["processing"]),
        "wait_before_processing_ms": dist(split["wait"]),
        "decision_delay_ms": dist(decision),
        "event_capture_to_dispatch_ms": dist(dispatch),
        "dispatch_to_verified_ms": dist(verify),
        "verified_to_ui_thread_ms": dist(to_ui),
        "gestures": [(e["gesture"], e["t_s"]) for e in events],
        "action_statuses": statuses,
        "overlay_paints": painted["overlay"],
        "preview_decoded": window.preview.decoded - decoded0,
        "segmentation_runs": seg,
        "face_runs": face,
        "cpu_percent_of_machine": round(cpu, 2),
        "rss_mb": round(process.memory_info().rss / 2**20),
    }


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.002)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--recording", type=Path, default=ROOT / "recordings/gestures_s5_right_20261127_135040.json"
    )
    parser.add_argument("--start-s", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=75.0)
    parser.add_argument("--browser-ms", type=float, default=150.0)
    parser.add_argument("--only", default="")
    parser.add_argument(
        "--preview-jpeg",
        type=Path,
        default=ROOT / "screenshots/brief008/preview_proto/preview_front.jpg",
        help="a JPEG used as the live preview picture (local file)",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    from interactive_scrolling.core.platform import disable_power_throttling

    disable_power_throttling()  # as the application does at start
    frames = load(args.recording)
    t0 = frames[0]["t_ns"] + int(args.start_s * 1e9)
    frames = [f for f in frames if t0 <= f["t_ns"] <= t0 + int(args.seconds * 1e9)]
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    only = [s for s in args.only.split(",") if s] or list(SCENARIOS)
    results = []
    for name in only:
        result = run(name, SCENARIOS[name], frames, args)
        results.append(result)
        c = result["capture_to_recognition_ms"]
        print(
            f"{name:26s} frames {result['processed_frames']}/{result['recording_frames']} "
            f"latency med {c['median']} p95 {c['p95']} p99 {c['p99']} max {c['max']} | "
            f"gestures {len(result['gestures'])} | ui late p99 {result['ui_lateness_ms']['p99']} "
            f"| cpu {result['cpu_percent_of_machine']} | inf med "
            f"{result['inference_ms']['median']} proc med {result['processing_ms']['median']} "
            f"wait med {result['wait_before_processing_ms']['median']}",
            flush=True,
        )
    reference = results[0]["gestures"]
    for result in results:
        same = [g for g, _ in result["gestures"]] == [g for g, _ in reference]
        result["same_gestures_as_first_scenario"] = same
    text = json.dumps(results, indent=2)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    print(
        "same gesture sequence in all scenarios:",
        all(r["same_gestures_as_first_scenario"] for r in results),
    )
    _ = statistics
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
