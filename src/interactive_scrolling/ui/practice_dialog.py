"""Gesture Practice and Quick Calibration (Brief 004, CP E1-E3 and F1).

Practice
    The six gestures one after another, each until it was recognized three times (or
    skipped). The dialog shows what to do (a drawn guide and one sentence), the live hand
    skeleton, the recognizer's state and progress, and after every attempt either the
    recognized gesture or why it was not accepted, in plain language. No browser action is
    executed: the dispatcher is in Gesture test mode while the dialog is open and the previous
    mode is restored afterwards.

Quick Calibration
    The same six gestures, three demonstrations each, measured by
    ``gestures.calibration``. A demonstration that cannot be used is explained (hand too far
    away, wrong direction, too short, pose not held) and only that gesture is repeated. The
    summary lists what would change; nothing is applied until the user chooses "Use my
    profile". Single gestures can be recalibrated and the standard profile restored.

Optionally the session's landmark numbers (no images) are saved for analysis
(``scripts/evaluate_gestures.py``, ``scripts/simulate_calibration.py``).
"""

from __future__ import annotations

import logging
import math
import queue
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.actions.types import ActionRecord, ControlMode
from interactive_scrolling.core.pipeline import ProcessedFrame
from interactive_scrolling.gestures.calibration import DEMOS_PER_GESTURE, PromptResult, derive
from interactive_scrolling.gestures.explain import (
    event_label,
    explain_rejection,
    instruction,
    state_label,
)
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.visualization import palette

log = logging.getLogger(__name__)
G = GestureType
FINGER_SWIPES = (
    G.INDEX_SWIPE_UP,
    G.INDEX_SWIPE_DOWN,
    G.INDEX_SWIPE_RIGHT,
    G.INDEX_SWIPE_LEFT,
)
SEQUENCE = (
    G.INDEX_SWIPE_UP,
    G.INDEX_SWIPE_DOWN,
    G.INDEX_SWIPE_RIGHT,
    G.INDEX_SWIPE_LEFT,
    G.HALF_HEART,
    G.STOP_GESTURE,
)
METHODS = (("finger", "Pointing finger"), ("fist", "Whole hand, any shape"))
"""Swipe methods of Practice and Quick Calibration. ``fist`` is the whole-hand path (palm
centre, any hand shape that is not pointing; Brief 006); the key is kept from version 0.5."""


def steps_for(method: str) -> list[tuple[GestureType, str]]:
    """The practice/calibration steps: the four swipes with the chosen method, then the
    half-heart and the stop pose."""
    swipes = [(g, method) for g in FINGER_SWIPES]
    return [*swipes, (G.HALF_HEART, ""), (G.STOP_GESTURE, "")]


PRACTICE_SUCCESSES = 3
CALIBRATION_TIMEOUT_S = 12.0
LABELS = {
    G.INDEX_SWIPE_UP: "up",
    G.INDEX_SWIPE_DOWN: "down",
    G.INDEX_SWIPE_RIGHT: "right",
    G.INDEX_SWIPE_LEFT: "left",
    G.HALF_HEART: "half_heart",
    G.STOP_GESTURE: "stop",
}


class GestureGuide(QWidget):
    """A simple drawing of the gesture to perform (no images or assets)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.gesture: GestureType = G.INDEX_SWIPE_UP
        self.setMinimumSize(180, 180)

    def set_gesture(self, gesture: GestureType) -> None:
        self.gesture = gesture
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        side = min(rect.width(), rect.height())
        box = QRectF(0, 0, side, side)
        box.moveCenter(rect.center())
        painter.setPen(QPen(QColor(palette.TEXT_MUTED), 1))
        painter.drawRoundedRect(box, 14, 14)
        pen = QPen(QColor(palette.ACCENT_CYAN), max(4.0, side / 28))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        c = box.center()
        r = side * 0.32
        if self.gesture.is_dynamic:
            angle = {
                G.INDEX_SWIPE_UP: -90,
                G.INDEX_SWIPE_DOWN: 90,
                G.INDEX_SWIPE_RIGHT: 0,
                G.INDEX_SWIPE_LEFT: 180,
            }[self.gesture]
            a = math.radians(angle)
            tail = QPointF(c.x() - r * math.cos(a), c.y() - r * math.sin(a))
            head = QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
            painter.drawLine(tail, head)
            for turn in (150, -150):
                b = math.radians(angle + turn)
                painter.drawLine(
                    head,
                    QPointF(head.x() + 0.4 * r * math.cos(b), head.y() + 0.4 * r * math.sin(b)),
                )
            # A pointing finger at the start of the arrow.
            painter.setPen(QPen(QColor(palette.ACCENT_AMBER), max(3.0, side / 40)))
            painter.drawEllipse(tail, side * 0.05, side * 0.05)
        elif self.gesture is G.HALF_HEART:
            path = QPainterPath()
            top = QPointF(c.x(), c.y() - r * 0.45)
            path.moveTo(QPointF(c.x(), c.y() + r))
            path.cubicTo(
                QPointF(c.x() - r * 1.3, c.y() + r * 0.1),
                QPointF(c.x() - r * 0.9, c.y() - r * 1.1),
                top,
            )
            painter.drawPath(path)
            painter.setPen(QPen(QColor(palette.TEXT_MUTED), 2, Qt.PenStyle.DashLine))
            mirror = QPainterPath()
            mirror.moveTo(QPointF(c.x(), c.y() + r))
            mirror.cubicTo(
                QPointF(c.x() + r * 1.3, c.y() + r * 0.1),
                QPointF(c.x() + r * 0.9, c.y() - r * 1.1),
                top,
            )
            painter.drawPath(mirror)
        else:
            palm = QRectF(c.x() - r * 0.5, c.y() - r * 0.05, r, r * 0.9)
            painter.drawRoundedRect(palm, 10, 10)
            for k in range(4):
                x = palm.left() + palm.width() * (0.12 + 0.25 * k)
                painter.drawLine(QPointF(x, palm.top()), QPointF(x, palm.top() - r * 0.75))
            painter.drawLine(
                QPointF(palm.left(), palm.center().y()),
                QPointF(palm.left() - r * 0.35, palm.top() - r * 0.1),
            )
        painter.end()


class PracticeDialog(QDialog):
    def __init__(self, services, data_folder: Path, parent: QWidget | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Practice and calibrate gestures")
        self.setMinimumSize(900, 560)
        self.services = services
        self.data_folder = data_folder
        self._previous_mode = services.dispatcher.mode
        services.dispatcher.set_mode(ControlMode.GESTURE_TEST, "practice")
        self.mode = "practice"
        self.index = 0
        self.successes = 0
        self.results: dict[GestureType, PromptResult] = {}
        self._prompt_started = 0.0
        self._seen_entries = 0
        self.derived = None
        self.saved_recording: Path | None = None
        self.method = "finger"
        self.steps = steps_for("finger")
        self.fist_results: dict[GestureType, PromptResult] = {}
        self._restore_settings = None

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        from interactive_scrolling.config.settings import OverlaySettings
        from interactive_scrolling.ui.video_view import VideoView

        self.video = VideoView(OverlaySettings())
        self.video.setMinimumSize(420, 300)
        self.video.clear("Start the camera in the main window to see your hand here.")
        left.addWidget(self.video, 1)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        root.addLayout(right, 2)

        # page 0: start
        start = QWidget()
        s = QVBoxLayout(start)
        intro = QLabel(
            "<b>Practice</b> shows each gesture and tells you after every try whether it "
            "was recognized - and if not, why. <b>Quick Calibration</b> measures three "
            "demonstrations of each gesture and adapts the recognition to your movements. "
            "Nothing is sent to the browser while this window is open."
        )
        intro.setWordWrap(True)
        s.addWidget(intro)
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Swipe method:"))
        self.method_box = QComboBox()
        for key, text in METHODS:
            self.method_box.addItem(text, key)
        method_row.addWidget(self.method_box, 1)
        s.addLayout(method_row)
        self.record_box = QCheckBox(
            "Save the hand-landmark numbers of this session for analysis (no video, no images)"
        )
        s.addWidget(self.record_box)
        practice = QPushButton("Start practice")
        practice.clicked.connect(lambda: self.start("practice"))
        calibrate = QPushButton("Start Quick Calibration (about 2 minutes)")
        calibrate.clicked.connect(lambda: self.start("calibration"))
        s.addWidget(practice)
        s.addWidget(calibrate)
        s.addStretch(1)
        self.stack.addWidget(start)

        # page 1: a prompt
        prompt = QWidget()
        p = QVBoxLayout(prompt)
        self.step = QLabel("")
        self.step.setObjectName("rowKey")
        p.addWidget(self.step)
        self.guide = GestureGuide()
        p.addWidget(self.guide, 1)
        self.title = QLabel("")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        p.addWidget(self.title)
        self.explanation = QLabel("")
        self.explanation.setWordWrap(True)
        p.addWidget(self.explanation)
        self.state = QLabel("")
        self.state.setStyleSheet(f"color: {palette.ACCENT_CYAN};")
        p.addWidget(self.state)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        p.addWidget(self.progress)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        p.addWidget(self.result)
        self.counter = QLabel("")
        p.addWidget(self.counter)
        buttons = QHBoxLayout()
        self.repeat_button = QPushButton("Repeat")
        self.repeat_button.clicked.connect(self.repeat)
        self.skip_button = QPushButton("Skip")
        self.skip_button.clicked.connect(self.advance)
        buttons.addWidget(self.repeat_button)
        buttons.addWidget(self.skip_button)
        p.addLayout(buttons)
        self.stack.addWidget(prompt)

        # page 2: summary
        summary = QWidget()
        m = QVBoxLayout(summary)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        m.addWidget(self.summary, 1)
        self.redo_row = QHBoxLayout()
        m.addLayout(self.redo_row)
        self.apply_button = QPushButton("Use my profile")
        self.apply_button.clicked.connect(self.apply_profile)
        self.defaults_button = QPushButton("Restore standard recognition")
        self.defaults_button.clicked.connect(self.restore_defaults)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(self.apply_button)
        row.addWidget(self.defaults_button)
        row.addWidget(close)
        m.addLayout(row)
        self.stack.addWidget(summary)

        self._pending_records: queue.SimpleQueue[ActionRecord] = queue.SimpleQueue()
        services.dispatcher.add_record_listener(self._record_from_any_thread)
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # ------------------------------------------------------------------ flow

    def start(self, mode: str) -> None:
        self.mode = mode
        self.method = self.method_box.currentData() if hasattr(self, "method_box") else "finger"
        self.steps = steps_for(self.method)
        self.index = 0
        self.results = {}
        self.fist_results = {}
        if self.method == "fist" and self.services.engine.settings.control_style == "finger":
            # "Pointing finger only" is set: whole-hand swipes are switched on for this window.
            from dataclasses import replace

            self._restore_settings = self.services.engine.settings
            self.services.engine.request_settings(
                replace(self._restore_settings, control_style="motion")
            )
        if self.record_box.isChecked():
            self.services.recorder.start()
        self.stack.setCurrentIndex(1)
        self._show_prompt()

    @property
    def current(self) -> tuple[GestureType, str]:
        return self.steps[self.index]

    def _show_prompt(self) -> None:
        gesture, detector = self.current
        title, text = instruction(gesture, detector)
        self.successes = 0
        self.guide.set_gesture(gesture)
        what = "Practice" if self.mode == "practice" else "Quick Calibration"
        self.step.setText(f"{what} - gesture {self.index + 1} of {len(self.steps)}")
        count = PRACTICE_SUCCESSES if self.mode == "practice" else DEMOS_PER_GESTURE
        self.title.setText(f"{title}  ({count} times)" if gesture.is_dynamic else title)
        self.explanation.setText(text)
        self.result.setText("")
        self.result.setStyleSheet("")
        self._update_counter()
        self._prompt_started = time.monotonic()
        self._seen_entries = len(self.services.diagnostics.recent(1000))
        prefix = "practice" if self.mode == "practice" else "calib"
        middle = "fist_" if detector == "fist" else ""
        self.services.recorder.label(
            f"{prefix}_{middle}{LABELS[gesture]}", CALIBRATION_TIMEOUT_S, title
        )
        if self.mode == "calibration":
            self.services.calibration.begin(gesture, detector or "finger")

    def _update_counter(self) -> None:
        if self.mode == "practice":
            self.counter.setText(f"Recognized {self.successes} of {PRACTICE_SUCCESSES}")

    def repeat(self) -> None:
        self._show_prompt()

    def _store(self, result: PromptResult) -> None:
        gesture, detector = self.current
        (self.fist_results if detector == "fist" else self.results)[gesture] = result

    def advance(self) -> None:
        if self.mode == "calibration" and self.services.calibration.active:
            result = self.services.calibration.end()
            if result is not None:
                self._store(result)
        self.index += 1
        if self.index >= len(self.steps):
            self._finish()
        else:
            self._show_prompt()

    def _finish(self) -> None:
        if self.services.recorder.recording:
            try:
                self.saved_recording = self.services.save_recording(self.data_folder / "recordings")
            except OSError as exc:
                log.warning("Recording could not be saved: %s", exc)
        lines = []
        if self.mode == "calibration":
            self.derived = derive(
                self.results,
                self.services.user_settings.gestures,
                "",
                fist_results=self.fist_results,
            )
            lines.append("<b>Quick Calibration results</b>")
            for gesture, detector in self.steps:
                store = self.fist_results if detector == "fist" else self.results
                result = store.get(gesture)
                n = result.valid_demos if result else 0
                status = "&#10003;" if n >= 2 or (n >= 1 and not gesture.is_dynamic) else "&#10007;"
                lines.append(f"{status} {instruction(gesture, detector)[0]}: {n} usable")
            lines.append("<br><b>What would change</b>")
            lines += [f"- {note}" for note in self.derived.notes]
            self.apply_button.setEnabled(True)
            self._redo_buttons()
        else:
            lines.append("<b>Practice finished.</b> You can now use the gestures in Live control.")
            self.apply_button.setEnabled(False)
        if self.saved_recording is not None:
            lines.append(f"<br>Landmark recording saved: {self.saved_recording}")
        self.summary.setText("<br>".join(lines))
        self.stack.setCurrentIndex(2)

    def _redo_buttons(self) -> None:
        while self.redo_row.count():
            item = self.redo_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, (gesture, detector) in enumerate(self.steps):
            name = LABELS[gesture].replace("_", "-")
            button = QPushButton(f"Redo {'hand ' if detector == 'fist' else ''}{name}")
            button.clicked.connect(lambda _=False, i=index: self.recalibrate(i))
            self.redo_row.addWidget(button)

    def recalibrate(self, step: int | GestureType) -> None:
        """Repeat one gesture's demonstrations only, then return to the summary."""
        self.mode = "calibration"
        if isinstance(step, GestureType):
            step = next(i for i, (g, _) in enumerate(self.steps) if g is step)
        self.index = step
        self._single = True
        self.stack.setCurrentIndex(1)
        self._show_prompt()

    def apply_profile(self) -> None:
        if self.derived is None:
            return
        self.services.apply_calibration(self.derived.settings, self.derived.profile)
        self._restore_settings = None  # the applied profile is now the user's setting
        self.summary.setText(self.summary.text() + "<br><br><b>Your profile is in use.</b>")
        self.apply_button.setEnabled(False)

    def restore_defaults(self) -> None:
        self.services.reset_calibration()
        self._restore_settings = None
        self.summary.setText(self.summary.text() + "<br><br><b>Standard recognition restored.</b>")

    # ------------------------------------------------------------------ live input

    def _record_from_any_thread(self, record: ActionRecord) -> None:
        self._pending_records.put(record)

    def show_frame(self, frame: ProcessedFrame) -> None:
        self.video.set_frame(frame)
        gestures = frame.gestures
        if gestures is None or self.stack.currentIndex() != 1:
            return
        self.state.setText(state_label(gestures) + (f"   {gestures.hint}" if gestures.hint else ""))
        target = self.current[0]
        progress = [c.progress for c in gestures.candidates if c.gesture is target]
        self.progress.setValue(int(100 * (progress[0] if progress else 0)))

    def _matches(self, record: ActionRecord) -> bool:
        gesture, detector = self.current
        if record.event.gesture is not gesture:
            return False
        if not gesture.is_dynamic:
            return True
        made = record.event.detector or "finger"
        if detector == "fist":
            return made in ("fist", "hand")
        return made == detector

    def _tick(self) -> None:
        records = []
        while True:
            try:
                records.append(self._pending_records.get_nowait())
            except queue.Empty:
                break
        if self.stack.currentIndex() != 1:
            return
        target, detector = self.current
        if self.mode == "practice":
            for record in records:
                label = event_label(record.event.gesture, record.event.detector)
                if record.status.final and self._matches(record):
                    self.successes += 1
                    self.result.setText(f"\u2713 Recognized: {label}")
                    self.result.setStyleSheet(f"color: {palette.ACCENT_GREEN};")
                elif record.status.final:
                    self.result.setText(f"That was {label}. {instruction(target, detector)[0]}.")
                    self.result.setStyleSheet(f"color: {palette.ACCENT_AMBER};")
            self._show_latest_rejection(target)
            self._update_counter()
            if self.successes >= PRACTICE_SUCCESSES:
                QTimer.singleShot(700, self.advance)
                self.successes = -100  # advance once
            return
        # calibration
        progress = self.services.calibration.progress()
        if progress is None:
            return
        n = progress.valid_demos
        self.counter.setText(f"Captured {n} of {DEMOS_PER_GESTURE}")
        feedback = progress.feedback()
        elapsed = time.monotonic() - self._prompt_started
        if n >= DEMOS_PER_GESTURE or (not target.is_dynamic and n >= 1 and elapsed > 2.0):
            self.result.setText("\u2713 Captured.")
            self.result.setStyleSheet(f"color: {palette.ACCENT_GREEN};")
            self.advance_after_capture()
        elif feedback and elapsed > 3.0:
            self.result.setText(feedback[0])
            self.result.setStyleSheet(f"color: {palette.ACCENT_AMBER};")
        if elapsed > CALIBRATION_TIMEOUT_S and self.services.calibration.active:
            self.result.setText(
                ((feedback[0] + " ") if feedback else "") + "Press Repeat to try again or Skip."
            )
            self.result.setStyleSheet(f"color: {palette.ACCENT_AMBER};")
            result = self.services.calibration.end()
            if result is not None:
                self._store(result)

    def advance_after_capture(self) -> None:
        if getattr(self, "_single", False):
            result = self.services.calibration.end()
            if result is not None:
                self._store(result)
            self._single = False
            self.index = len(self.steps) - 1
            self._finish()
            return
        self.advance()

    def _show_latest_rejection(self, target: GestureType) -> None:
        entries = self.services.diagnostics.recent(1000)
        fresh = entries[self._seen_entries :] if len(entries) >= self._seen_entries else entries
        self._seen_entries = len(entries)
        for entry in reversed(fresh):
            if entry["kind"] == "rejected" and entry["gesture"] == target.value:
                from interactive_scrolling.gestures.types import GestureRejection

                rejection = GestureRejection(
                    target,
                    entry["reason"],
                    0,
                    entry["code"],
                    entry["measured"],
                    entry["required"],
                    entry["unit"],
                    tuple(entry["details"]),
                )
                if entry["code"] in ("tracking_lost", "hand_changed"):
                    continue
                self.result.setText(explain_rejection(rejection))
                self.result.setStyleSheet(f"color: {palette.ACCENT_AMBER};")
                return

    # ------------------------------------------------------------------ close

    def done(self, code: int) -> None:
        self.timer.stop()
        if self.services.calibration.active:
            self.services.calibration.end()
        if self.services.recorder.recording:
            self.services.save_recording(self.data_folder / "recordings")
        if self._restore_settings is not None:
            # Fist swipes were only switched on for this window.
            self.services.engine.request_settings(self._restore_settings)
            self._restore_settings = None
        self.services.dispatcher.remove_record_listener(self._record_from_any_thread)
        # Live control is never switched back on silently after practice: the user does
        # that deliberately (an emergency disable meanwhile is kept as well).
        if self.services.dispatcher.mode is ControlMode.GESTURE_TEST:
            restore = self._previous_mode
            if restore is ControlMode.LIVE_CONTROL:
                restore = ControlMode.GESTURE_TEST
                log.info("Practice finished; switch Live control on again to control the browser.")
            self.services.dispatcher.set_mode(restore, "practice finished")
        super().done(code)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.done(0)
        super().closeEvent(event)
