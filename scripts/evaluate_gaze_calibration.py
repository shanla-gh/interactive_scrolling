"""Gaze calibration accuracy with a real person (Director tool, Brief 009).

Shows a full-screen sequence of targets: 9 calibration points, then 8 *different* evaluation
points (separate samples, never used for fitting), each held for ``--hold-s`` while the face
landmarker samples the webcam (first 0.6 s per point skipped: the eyes are still moving).
Features per sample: iris offsets of both eyes (horizontal, vertical, in eye widths) and head
yaw / pitch / roll (``wellbeing/gaze.py``). Two models are fitted on the calibration samples
only and scored on the evaluation samples:

* ``affine``: screen x, y = linear function of the features (ridge regression);
* ``quadratic``: adds squared iris terms.

Reported: median / p90 pixel error, error as a share of the screen diagonal, 3x3 region
accuracy, tracking availability (share of samples with a usable estimate) and drift (error of
a repeated centre point at the end against the calibration). Only these numbers are saved
(``--json``); no images, landmarks or gaze coordinates.

Usage: python scripts/evaluate_gaze_calibration.py --json reports/b9_gaze_calibration.json
Press Esc to abort.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from interactive_scrolling.vision.face_tracker import MediaPipeFaceTracker
from interactive_scrolling.vision.model_assets import FACE_MODEL
from interactive_scrolling.wellbeing.gaze import estimate_gaze

CALIBRATION = [(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)]
EVALUATION = [
    (0.3, 0.3),
    (0.7, 0.3),
    (0.3, 0.7),
    (0.7, 0.7),
    (0.5, 0.2),
    (0.5, 0.8),
    (0.2, 0.5),
    (0.8, 0.5),
]
DRIFT = [(0.5, 0.5)]
SETTLE_S = 0.6


def features(estimate) -> list[float]:  # type: ignore[no-untyped-def]
    r, left = estimate.right, estimate.left
    return [
        (r.offset_h + left.offset_h) / 2,
        (r.offset_v + left.offset_v) / 2,
        estimate.head_yaw_deg / 30,
        estimate.head_pitch_deg / 30,
        estimate.head_roll_deg / 30,
    ]


def design(x: np.ndarray, quadratic: bool) -> np.ndarray:
    columns = [np.ones(len(x)), *x.T]
    if quadratic:
        columns += [x[:, 0] ** 2, x[:, 1] ** 2, x[:, 0] * x[:, 1]]
    return np.stack(columns, axis=1)


def fit(x: np.ndarray, y: np.ndarray, quadratic: bool, ridge: float = 1e-3) -> np.ndarray:
    a = design(x, quadratic)
    return np.linalg.solve(a.T @ a + ridge * np.eye(a.shape[1]), a.T @ y)


class Targets(QWidget):
    def __init__(self, points: list[tuple[float, float, str]], hold_s: float) -> None:
        super().__init__()
        self.points = points
        self.hold_s = hold_s
        self.index = -1
        self.started = 0.0
        self.samples: list[tuple[int, list[float] | None]] = []
        self.aborted = False
        self.camera = cv2.VideoCapture(0, cv2.CAP_MSMF)
        self.tracker = MediaPipeFaceTracker(FACE_MODEL.path())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setWindowState(Qt.WindowState.WindowFullScreen)

    def start(self) -> None:
        self.showFullScreen()
        self.next_point()
        self.timer.start(15)

    def next_point(self) -> None:
        self.index += 1
        self.started = time.monotonic()
        if self.index >= len(self.points):
            self.timer.stop()
            self.close()
        self.update()

    def tick(self) -> None:
        ok, frame = self.camera.read()
        elapsed = time.monotonic() - self.started
        if ok and elapsed >= SETTLE_S and self.index < len(self.points):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face = self.tracker.process(rgb, int(time.monotonic() * 1000))
            estimate = estimate_gaze(face)
            usable = estimate is not None and estimate.usable
            self.samples.append((self.index, features(estimate) if usable else None))
        if elapsed >= self.hold_s:
            self.next_point()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Escape:
            self.aborted = True
            self.timer.stop()
            self.close()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(17, 18, 20))
        if 0 <= self.index < len(self.points):
            x, y, phase = self.points[self.index]
            centre = QPointF(x * self.width(), y * self.height())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(76, 195, 138))
            painter.drawEllipse(centre, 14, 14)
            painter.setBrush(QColor(17, 18, 20))
            painter.drawEllipse(centre, 4, 4)
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                20, 30, f"{phase}: look at the dot ({self.index + 1}/{len(self.points)})"
            )
        painter.end()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hold-s", type=float, default=2.0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    points = (
        [(x, y, "calibration") for x, y in CALIBRATION]
        + [(x, y, "evaluation") for x, y in EVALUATION]
        + [(x, y, "drift check") for x, y in DRIFT]
    )
    widget = Targets(points, args.hold_s)
    began = time.monotonic()
    QTimer.singleShot(0, widget.start)
    app.exec()
    widget.camera.release()
    if widget.aborted:
        print("aborted")
        return 1
    screen = app.primaryScreen().geometry()
    width, height = screen.width(), screen.height()
    diagonal = float(np.hypot(width, height))
    usable = [(i, f) for i, f in widget.samples if f is not None]
    report: dict = {
        "screen_px": [width, height],
        "duration_s": round(time.monotonic() - began, 1),
        "samples": len(widget.samples),
        "tracking_availability": round(len(usable) / max(1, len(widget.samples)), 3),
    }
    n_cal = len(CALIBRATION)
    n_eval = len(EVALUATION)
    cal = [(f, points[i]) for i, f in usable if i < n_cal]
    ev = [(f, points[i]) for i, f in usable if n_cal <= i < n_cal + n_eval]
    drift = [(f, points[i]) for i, f in usable if i >= n_cal + n_eval]
    if len(cal) < 20 or len(ev) < 10:
        report["result"] = "not enough usable samples"
        print(json.dumps(report, indent=2))
        return 1
    xc = np.array([f for f, _ in cal])
    yc = np.array([[p[0] * width, p[1] * height] for _, p in cal])
    for name, quadratic in (("affine", False), ("quadratic", True)):
        coef = fit(xc, yc, quadratic)
        result = {}
        for label, data in (("evaluation", ev), ("drift_centre", drift)):
            if not data:
                continue
            x = np.array([f for f, _ in data])
            truth = np.array([[p[0] * width, p[1] * height] for _, p in data])
            predicted = design(x, quadratic) @ coef
            errors = np.linalg.norm(predicted - truth, axis=1)
            region_ok = np.mean(
                (np.clip(predicted[:, 0] // (width / 3), 0, 2) == truth[:, 0] // (width / 3))
                & (np.clip(predicted[:, 1] // (height / 3), 0, 2) == truth[:, 1] // (height / 3))
            )
            result[label] = {
                "median_px": round(float(np.median(errors))),
                "p90_px": round(float(np.percentile(errors, 90))),
                "median_share_of_diagonal": round(float(np.median(errors)) / diagonal, 3),
                "region_3x3_accuracy": round(float(region_ok), 3),
                "samples": len(data),
            }
        report[name] = result
    print(json.dumps(report, indent=2))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _ = statistics
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
