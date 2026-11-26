"""Headless benchmark of the real pipeline: physical webcam + hand landmarker + motion.

Measures camera start time, capture/processing rates, inference time, capture-to-result
latency, dropped frames, process CPU and memory, and how many frames contained hands.
No images are stored; only numbers are written.

Example:
    python scripts/benchmark_pipeline.py --duration 30 --resolution 1280x720
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _measure import environment, summarize
from interactive_scrolling.config.settings import CameraSettings, TrackingSettings
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import (
    CameraState,
    ProcessedFrame,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.core.platform import disable_power_throttling
from interactive_scrolling.vision.camera import OpenCVCamera
from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
from interactive_scrolling.vision.model_assets import default_model_path


class Collector:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latencies: list[float] = []
        self.inference: list[float] = []
        self.hand_counts: list[int] = []
        self.states: list[str] = []

    def on_frame(self, frame: ProcessedFrame) -> None:
        with self.lock:
            self.latencies.append(frame.latency_ms)
            if frame.inference_ms is not None:
                self.inference.append(frame.inference_ms)
                self.hand_counts.append(frame.tracking.hand_count)

    def on_camera_state(self, state: CameraState, message: str, session: int) -> None:
        self.states.append(f"camera {state.value}: {message}")

    def on_tracker_state(self, state: TrackerState, message: str) -> None:
        self.states.append(f"tracker {state.value}: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--duration", type=float, default=30.0, help="seconds to measure")
    parser.add_argument("--warmup", type=float, default=3.0, help="seconds ignored at start")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--resolution", default="1280x720")
    parser.add_argument("--inference-width", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None, help="JSON report path")
    parser.add_argument(
        "--allow-power-throttling",
        action="store_true",
        help="keep Windows' default power throttling (the application disables it)",
    )
    args = parser.parse_args()
    throttling_disabled = False if args.allow_power_throttling else disable_power_throttling()
    width, height = (int(v) for v in args.resolution.lower().split("x"))

    collector = Collector()
    monitor = ResourceMonitor()
    tracking = TrackingSettings(inference_max_width=args.inference_width)
    model = default_model_path()
    load_started = time.perf_counter()
    pipeline = VisionPipeline(
        collector,
        camera_factory=OpenCVCamera,
        tracker_factory=lambda: MediaPipeHandTracker(tracking, model),
        inference_max_width=args.inference_width,
    )
    pipeline.launch()
    while pipeline.tracker_state in (TrackerState.NOT_LOADED, TrackerState.LOADING):
        time.sleep(0.01)
    model_load_s = time.perf_counter() - load_started
    if pipeline.tracker_state is not TrackerState.READY:
        print("Tracker unavailable:", collector.states, file=sys.stderr)
        return 1

    camera_started = time.perf_counter()
    pipeline.start_camera(CameraSettings(index=args.camera, width=width, height=height))
    while pipeline.camera_state is CameraState.STARTING:
        time.sleep(0.005)
    camera_start_s = time.perf_counter() - camera_started
    if pipeline.camera_state is not CameraState.RUNNING:
        print("Camera failed:", collector.states, file=sys.stderr)
        pipeline.shutdown()
        return 1

    time.sleep(args.warmup)
    with collector.lock:
        collector.latencies.clear()
        collector.inference.clear()
        collector.hand_counts.clear()
    start_metrics = pipeline.metrics()
    monitor.sample()
    samples = []
    started = time.perf_counter()
    while time.perf_counter() - started < args.duration:
        time.sleep(1.0)
        m = pipeline.metrics()
        r = monitor.sample()
        samples.append(
            {
                "t": round(time.perf_counter() - started, 1),
                "capture_fps": round(m.capture_fps, 1),
                "processing_fps": round(m.processing_fps, 1),
                "cpu_percent_machine": round(r.cpu_percent_of_machine, 1),
                "cpu_percent_core": round(r.cpu_percent_of_core, 1),
                "rss_mb": round(r.rss_mb, 1),
                "threads": r.thread_count,
            }
        )
    elapsed = time.perf_counter() - started
    end_metrics = pipeline.metrics()
    stop_started = time.perf_counter()
    pipeline.stop_camera()
    pipeline.wait_for_camera_stop(10)
    stop_s = time.perf_counter() - stop_started
    clean = pipeline.shutdown()

    with collector.lock:
        hand_counts = list(collector.hand_counts)
        report = {
            "kind": "pipeline-benchmark",
            "date_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "environment": environment(),
            "config": {
                "requested_resolution": f"{width}x{height}",
                "actual_resolution": f"{end_metrics.frame_width}x{end_metrics.frame_height}",
                "inference_max_width": args.inference_width,
                "power_throttling_disabled": throttling_disabled,
                "duration_s": round(elapsed, 1),
                "warmup_s": args.warmup,
            },
            "model_load_s": round(model_load_s, 2),
            "camera_start_s": round(camera_start_s, 2),
            "camera_stop_s": round(stop_s, 3),
            "clean_shutdown": clean,
            "frames": {
                "captured": end_metrics.frames_captured - start_metrics.frames_captured,
                "processed": end_metrics.frames_processed - start_metrics.frames_processed,
                "dropped": end_metrics.frames_dropped - start_metrics.frames_dropped,
                "with_hands": sum(1 for c in hand_counts if c > 0),
                "with_two_hands": sum(1 for c in hand_counts if c > 1),
            },
            "capture_fps": summarize([s["capture_fps"] for s in samples]),
            "processing_fps": summarize([s["processing_fps"] for s in samples]),
            "inference_ms": summarize(collector.inference),
            "latency_ms": summarize(collector.latencies),
            "cpu_percent_of_machine": summarize([s["cpu_percent_machine"] for s in samples]),
            "rss_mb": summarize([s["rss_mb"] for s in samples]),
            "rss_growth_mb": round(samples[-1]["rss_mb"] - samples[0]["rss_mb"], 1)
            if samples
            else None,
            "samples": samples,
        }
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("samples", "environment")}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
