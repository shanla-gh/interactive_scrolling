"""Face features UI: eye-analytics calibration and the Visual Behavior Report (the clown and eye
options are in Unified Settings since Brief 010)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.storage.analytics import EyeReport
from interactive_scrolling.ui.panels import NO_DATA, Card
from interactive_scrolling.ui.report_panels import UNAVAILABLE, duration
from interactive_scrolling.vision.face_tracker import FaceObservation
from interactive_scrolling.wellbeing.eyes import Calibration, calibrate

CALIBRATION_S = 3.0


class CalibrationDialog(QDialog):
    """Collects faces for a few seconds while the user looks at the middle of the screen."""

    def __init__(
        self, latest_face: Callable[[], FaceObservation | None], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Eye analytics calibration")
        self._latest = latest_face
        self._faces: list[FaceObservation] = []
        self._last: FaceObservation | None = None
        self.result: Calibration | None = None
        layout = QVBoxLayout(self)
        self.text = QLabel(
            "Sit as usual and look at the MIDDLE of your screen for 3 seconds, then wait."
        )
        self.text.setWordWrap(True)
        layout.addWidget(self.text)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._collect)
        self._elapsed = 0.0

    def start(self) -> None:
        self._faces.clear()
        self._elapsed = 0.0
        self.start_button.setEnabled(False)
        self.text.setText("Look at the middle of the screen...")
        self._timer.start()

    def _collect(self) -> None:
        self._elapsed += 0.05
        face = self._latest()
        if face is not None and face is not self._last:
            self._faces.append(face)
            self._last = face
        if self._elapsed >= CALIBRATION_S:
            self._timer.stop()
            self.finish()

    def finish(self) -> None:
        self.result = calibrate(self._faces)
        if self.result is None:
            self.text.setText("No face was tracked. Check the camera and try again.")
        elif not self.result.reliable:
            self.text.setText(
                f"The measurements varied too much (head {self.result.yaw_sd:.1f} deg, "
                f"{self.result.samples} samples). Keep still and try again."
            )
        else:
            self.text.setText(
                f"Calibrated from {self.result.samples} samples "
                f"(head variation {self.result.yaw_sd:.1f} deg)."
            )
        self.start_button.setEnabled(True)
        self.start_button.setText("Try again")


class VisualBehaviorPanel(Card):
    """Visual Behavior Report: estimated, coarse, mutually exclusive durations for today."""

    calibrate_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Visual behavior (estimated)", parent)
        self.state = self.add_row("Eye analytics", accent=True)
        self.screen = self.add_row(
            "Facing the screen", "Head and eyes towards the screen (coarse webcam estimate)."
        )
        self.away = self.add_row("Looking away")
        self.unknown = self.add_row(
            "Unknown", "No face, eyes closed longer than a blink, or ambiguous measurements."
        )
        self.longest = self.add_row("Longest facing the screen")
        self.blinks = self.add_row("Blinks")
        self.quality = self.add_row("Tracking quality", "Share of the time with a known state.")
        note = QLabel(
            "Estimates from a standard webcam. They do not measure attention and never control "
            "anything."
        )
        note.setWordWrap(True)
        note.setObjectName("rowKey")
        self.add_widget(note)
        for text, signal in (
            ("Calibrate...", self.calibrate_requested),
            ("Face effects and eye analytics...", self.settings_requested),
        ):
            button = QPushButton(text)
            button.clicked.connect(signal)
            self.add_widget(button)

    def show_report(self, enabled: bool, calibrated: bool, report: EyeReport | None) -> None:
        self.state.setText(
            ("on" + (" (calibrated)" if calibrated else " (not calibrated)")) if enabled else "off"
        )
        if report is None:
            for label in (self.screen, self.away, self.unknown, self.longest, self.blinks):
                label.setText(NO_DATA if enabled else UNAVAILABLE)
            self.quality.setText(NO_DATA if enabled else UNAVAILABLE)
            return
        total = report.screen_s + report.away_s + report.unknown_s
        self.screen.setText(duration(report.screen_s))
        self.away.setText(duration(report.away_s))
        self.unknown.setText(duration(report.unknown_s))
        self.longest.setText(duration(report.longest_screen_s))
        if report.blinks is None:
            self.blinks.setText("unavailable (frame rate too low to count)")
        else:
            minutes = report.screen_s / 60
            rate = f", {report.blinks / minutes:.0f}/min facing the screen" if minutes >= 1 else ""
            self.blinks.setText(f"{report.blinks}{rate}")
        known = report.screen_s + report.away_s
        self.quality.setText(f"{known / total:.0%} known" if total > 0 else NO_DATA)
