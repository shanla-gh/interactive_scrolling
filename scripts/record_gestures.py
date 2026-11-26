"""Guided recording of labeled hand-landmark sequences for gesture calibration.

The window shows the live camera view with the hand skeleton and a sequence of prompts
(poses, swipes, natural movements). For every processed frame it stores the tracked hand
landmarks with the current prompt label. **No images are stored**, only landmark numbers.
Recordings are written to ``recordings/`` (ignored by Git) and are replayed by
``scripts/evaluate_gestures.py``.

Usage:
    python scripts/record_gestures.py
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from interactive_scrolling.config.settings import AppSettings, CameraSettings
from interactive_scrolling.core.pipeline import (
    CameraState,
    ProcessedFrame,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.core.platform import disable_power_throttling
from interactive_scrolling.ui.theme import apply_theme
from interactive_scrolling.ui.video_view import VideoView
from interactive_scrolling.vision.camera import OpenCVCamera
from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
from interactive_scrolling.vision.model_assets import default_model_path

# (label, seconds, instruction). Labels starting with "neg_" contain no intended gesture.
PROMPTS: list[tuple[str, float, str]] = [
    ("neg_rest", 8, "Sit normally. Hands relaxed, out of view or on the desk."),
    ("pose_open_palm", 5, "STOP pose: raise one hand, fingers up, palm to the camera. Hold still."),
    ("neg_rest", 3, "Relax."),
    ("pose_pointing", 5, "POINT with your index finger (other fingers folded). Hold still."),
    ("neg_rest", 3, "Relax."),
    ("pose_thumbs_up", 5, "THUMBS UP. Hold still."),
    ("neg_rest", 3, "Relax."),
    ("pose_fist", 4, "Make a FIST facing the camera. Hold still."),
    ("neg_rest", 3, "Relax."),
    ("pose_thumbs_up", 5, "THUMBS UP again (any hand). Hold still."),
    ("neg_rest", 3, "Relax."),
    ("swipe_down_x4", 12, "POINT and swipe your fingertip DOWN, exactly 4 times, natural pace."),
    ("neg_rest", 3, "Relax."),
    ("swipe_up_x4", 12, "POINT and swipe your fingertip UP, exactly 4 times, natural pace."),
    ("neg_rest", 3, "Relax."),
    ("sweep_right_x3", 12, "OPEN HAND sweep to YOUR RIGHT, exactly 3 times."),
    ("neg_rest", 3, "Relax."),
    ("sweep_left_x3", 12, "OPEN HAND sweep to YOUR LEFT, exactly 3 times."),
    ("neg_rest", 3, "Relax."),
    ("neg_natural", 15, "Move naturally: touch your face or hair, reach for the mouse, wave."),
    ("neg_two_hands", 8, "Show BOTH hands and move them naturally (no gestures)."),
    ("neg_open_hold", 6, "Hold an OPEN HAND still for a moment, then lower it slowly."),
]

# Second session: finger swipes performed with a moving pointing hand (finger stays extended),
# a stop pose held at a comfortable distance, repeated thumbs-up with release, and negatives.
PROMPTS_2: list[tuple[str, float, str]] = [
    ("neg_rest", 5, "Sit normally. Hands relaxed."),
    (
        "point_down_x4",
        14,
        "Keep your index finger POINTING and move the whole hand DOWN quickly, "
        "4 times. Return as you like.",
    ),
    ("neg_rest", 3, "Relax."),
    (
        "point_up_x4",
        14,
        "Keep your index finger POINTING and move the whole hand UP quickly, "
        "4 times. Return as you like.",
    ),
    ("neg_rest", 3, "Relax."),
    ("pose_stop", 5, "STOP: open hand, fingers up, palm to the camera, arm's length away. Hold."),
    ("neg_rest", 4, "Lower your hand."),
    ("pose_stop", 5, "STOP again. Hold still."),
    ("neg_rest", 4, "Lower your hand."),
    ("thumbs_up_x3", 12, "THUMBS UP for about one second, lower it, 3 times in total."),
    ("neg_rest", 3, "Relax."),
    ("sweep_right_x3", 12, "OPEN HAND sweep to YOUR RIGHT, exactly 3 times."),
    ("neg_rest", 3, "Relax."),
    ("sweep_left_x3", 12, "OPEN HAND sweep to YOUR LEFT, exactly 3 times."),
    ("neg_rest", 3, "Relax."),
    ("neg_typing", 10, "Pretend to type and use the mouse, glance at the screen."),
    ("neg_face", 10, "Touch your face, adjust your hair, scratch your head."),
]

# Third session (Brief 003): the four index-finger swipes, the half-heart, the stop pose and the
# negatives the new gestures must not be confused with. Record it once with each hand.
PROMPTS_3: list[tuple[str, float, str]] = [
    ("neg_rest", 5, "Sit normally. Hands relaxed."),
    (
        "index_down_x4",
        14,
        "POINT with your index finger and swipe DOWN, 4 times. Return as you like.",
    ),
    ("neg_rest", 3, "Relax."),
    ("index_up_x4", 14, "POINT and swipe UP, 4 times."),
    ("neg_rest", 3, "Relax."),
    ("index_right_x4", 14, "POINT and swipe to YOUR RIGHT, 4 times."),
    ("neg_rest", 3, "Relax."),
    ("index_left_x4", 14, "POINT and swipe to YOUR LEFT, 4 times."),
    ("neg_rest", 3, "Relax."),
    (
        "index_next_prev",
        12,
        "POINT: swipe DOWN, bring the hand back, pause, then swipe UP. Do this twice.",
    ),
    ("neg_rest", 3, "Relax."),
    ("half_heart_x3", 14, "HALF HEART (one hand) for about one second, lower it, 3 times."),
    ("neg_rest", 3, "Relax."),
    ("half_heart_hold", 6, "HALF HEART and keep holding it for the whole prompt."),
    ("neg_rest", 3, "Relax."),
    ("pose_stop", 5, "STOP: open hand, fingers up, palm to the camera. Hold."),
    ("neg_rest", 3, "Lower your hand."),
    ("neg_pinch", 8, "PINCH your thumb and index finger together a few times."),
    ("neg_c_shape", 8, "Make a C shape with your hand (as if holding a cup), move it a little."),
    ("pose_thumbs_up", 5, "THUMBS UP. Hold still. (This must NOT be a like any more.)"),
    ("pose_pointing", 5, "POINT with your index finger and hold still."),
    ("neg_diagonal", 10, "POINT and move diagonally (up-left, down-right...), a few times."),
    ("neg_natural", 12, "Move naturally: touch your face or hair, reach for the mouse, wave."),
    ("neg_typing", 10, "Pretend to type and use the mouse."),
    ("neg_two_hands", 8, "Show BOTH hands and move them naturally (no gestures)."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=Path("recordings"))
    parser.add_argument("--session", type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    prompts = {1: PROMPTS, 2: PROMPTS_2, 3: PROMPTS_3}[args.session]
    disable_power_throttling()

    frames: list[dict] = []
    lock = threading.Lock()
    state = {"label": "warmup", "index": -1, "segment_start": 0.0, "done": False}
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    settings = AppSettings()

    window = QWidget()
    window.setWindowTitle("Gesture calibration recording")
    layout = QVBoxLayout(window)
    prompt = QLabel("Starting camera...")
    prompt.setStyleSheet("font-size: 20pt; font-weight: 700; color: #3dff9a; padding: 10px;")
    prompt.setWordWrap(True)
    timer_label = QLabel("")
    timer_label.setStyleSheet("font-size: 12pt; color: #8b949e; padding: 0 10px;")
    view = VideoView(settings.overlay)
    layout.addWidget(prompt)
    layout.addWidget(timer_label)
    layout.addWidget(view, 1)
    window.resize(1100, 820)
    window.show()

    latest: dict[str, ProcessedFrame | None] = {"frame": None}

    class Listener:
        def on_frame(self, frame: ProcessedFrame) -> None:
            latest["frame"] = frame
            if frame.inference_ms is None or state["index"] < 0 or state["done"]:
                return
            t = frame.tracking
            record = {
                "t_ns": t.timestamp_ns,
                "label": state["label"],
                "segment": state["index"],
                "w": t.image_width,
                "h": t.image_height,
                "hands": [
                    {
                        "lm": [[round(float(v), 5) for v in row] for row in h.landmarks],
                        "world": None
                        if h.world_landmarks is None
                        else [[round(float(v), 5) for v in row] for row in h.world_landmarks],
                        "handedness": h.handedness.value,
                        "score": None
                        if h.handedness_score is None
                        else round(h.handedness_score, 3),
                    }
                    for h in t.hands
                ],
            }
            with lock:
                frames.append(record)

        def on_camera_state(self, state_, message, session) -> None:
            print(f"camera: {state_.value} {message}")

        def on_tracker_state(self, state_, message) -> None:
            print(f"tracker: {state_.value} {message}")

    model = default_model_path()
    pipeline = VisionPipeline(
        Listener(),
        camera_factory=OpenCVCamera,
        tracker_factory=lambda: MediaPipeHandTracker(settings.tracking, model),
    )
    pipeline.launch()
    pipeline.start_camera(CameraSettings(index=args.camera))

    def refresh() -> None:
        frame = latest["frame"]
        if frame is not None:
            view.set_frame(frame)
        ready = (
            pipeline.camera_state is CameraState.RUNNING
            and pipeline.tracker_state is TrackerState.READY
        )
        now = time.perf_counter()
        if state["index"] < 0:
            if ready:
                state["index"] = 0
                state["segment_start"] = now + 3.0
                prompt.setText("Get ready...  " + prompts[0][2])
            return
        if state["done"]:
            return
        label, seconds, text = prompts[state["index"]]
        if now < state["segment_start"]:
            timer_label.setText(f"Starting in {state['segment_start'] - now:.1f} s")
            state["label"] = "transition"
            return
        state["label"] = label
        remaining = state["segment_start"] + seconds - now
        prompt.setText(f"{state['index'] + 1}/{len(prompts)}   {text}")
        timer_label.setText(f"{remaining:.1f} s remaining")
        if remaining <= 0:
            state["index"] += 1
            if state["index"] >= len(prompts):
                state["done"] = True
                finish()
                return
            state["segment_start"] = now + 1.0
            prompt.setText(f"Next: {prompts[state['index']][2]}")

    def finish() -> None:
        pipeline.shutdown()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        path = args.output_dir / f"gestures_{datetime.now():%Y%m%d_%H%M%S}.json"
        with lock:
            payload = {"prompts": prompts, "frames": frames}
        path.write_text(json.dumps(payload), encoding="utf-8")
        prompt.setText(f"Done. Saved {len(frames)} frames (landmarks only) to {path}")
        print(f"saved {len(frames)} frames to {path}")
        QTimer.singleShot(2500, app.quit)

    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.timeout.connect(refresh)
    timer.start(33)
    app.exec()
    pipeline.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
