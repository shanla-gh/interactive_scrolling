"""Daily Activity Report, Gesture Performance Report and Anti-Doomscroll settings."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.config.settings import WellbeingSettings
from interactive_scrolling.core.pipeline import PipelineMetrics
from interactive_scrolling.gestures.types import stored_gesture_label
from interactive_scrolling.ui.panels import NO_DATA, Card
from interactive_scrolling.wellbeing.report import DailyReport, PerformanceReport

UNAVAILABLE = "unavailable"


def duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min {secs:02d} s"


class DailyReportPanel(Card):
    """Today's activity. Gesture counts and executed actions are shown separately."""

    pause_toggled = Signal(bool)
    settings_requested = Signal()
    wrapped_requested = Signal(str)
    """"today" or "session"."""
    clear_requested = Signal()
    enabled_changed = Signal(bool)

    def __init__(self, analytics_enabled: bool, parent: QWidget | None = None) -> None:
        super().__init__("Today", parent)
        self.index = self.add_row(
            "Doomscroll Index",
            "0-100 from today's scrolling time and longest session against your own goals "
            "(lower is better). Entertainment only, not a medical assessment.",
            accent=True,
        )
        self.scrolling = self.add_row(
            "Scrolling time",
            "A loaded Short playing in the focused browser window. Not a measure of attention.",
            accent=True,
        )
        self.sessions = self.add_row(
            "Sessions", "Scrolling separated by more than 2 minutes counts as a new session."
        )
        self.longest = self.add_row("Longest session")
        self.current = self.add_row("Current session")
        self.add_heading("ACTIONS DONE (CONFIRMED)")
        self.navigation = self.add_row("Next / previous Short")
        self.tabs = self.add_row("Tab right / left")
        self.likes = self.add_row("Likes (half-heart)")
        self.playback = self.add_row("Pause / resume")
        self.add_heading("GESTURES RECOGNIZED")
        self.gestures = self.add_row(
            "Confirmed gestures",
            "Every recognized gesture, executed or not (test mode, rejected, failed).",
        )
        self.problems = self.add_row("Rejected / failed / unknown")
        self.pause = QPushButton("Pause gesture scrolling")
        self.pause.setCheckable(True)
        self.pause.setToolTip("Stops next/previous Short gestures until you resume.")
        self.pause.toggled.connect(self.pause_toggled)
        self.add_widget(self.pause)
        self.pause_reason = QLabel("")
        self.pause_reason.setObjectName("rowKey")
        self.pause_reason.setWordWrap(True)
        self.add_widget(self.pause_reason)
        for text, scope in (("Wrapped: today...", "today"), ("Wrapped: session...", "session")):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=scope: self.wrapped_requested.emit(s))
            self.add_widget(button)
        limits = QPushButton("Limits and reminders...")
        limits.clicked.connect(self.settings_requested)
        self.add_widget(limits)
        self.enabled = QCheckBox("Keep local statistics")
        self.enabled.setChecked(analytics_enabled)
        self.enabled.setToolTip("Stored only on this computer. No URLs, titles or video data.")
        self.enabled.toggled.connect(self.enabled_changed)
        self.add_widget(self.enabled)
        clear = QPushButton("Delete all statistics")
        clear.clicked.connect(self.clear_requested)
        self.add_widget(clear)
        self.error = QLabel("")
        self.error.setObjectName("rowKey")
        self.error.setWordWrap(True)
        self.add_widget(self.error)

    def show_report(
        self,
        report: DailyReport | None,
        current_session_s: float,
        humorous: bool,
        error: str | None = None,
    ) -> None:
        self.error.setText(error or "")
        self.current.setText(duration(current_session_s) if current_session_s else NO_DATA)
        if report is None:
            for label in (
                self.index,
                self.scrolling,
                self.sessions,
                self.longest,
                self.navigation,
                self.tabs,
                self.likes,
                self.playback,
                self.gestures,
                self.problems,
            ):
                label.setText(UNAVAILABLE)
            return
        if report.index is None:
            self.index.setText(UNAVAILABLE)
        else:
            self.index.setText(f"{report.index.value} - {report.index.label(humorous)}")
        self.scrolling.setText(duration(report.scrolling_s))
        self.sessions.setText(str(report.session_count))
        self.longest.setText(duration(report.longest_session_s) if report.sessions else NO_DATA)
        self.navigation.setText(f"{report.done('next_short')} / {report.done('previous_short')}")
        self.tabs.setText(
            f"{report.done('next_browser_tab')} / {report.done('previous_browser_tab')}"
        )
        self.likes.setText(f"{report.done('like_short')}  (already liked: {report.no_change})")
        self.playback.setText(str(report.done("toggle_playback")))
        self.gestures.setText(str(report.gestures_total))
        self.problems.setText(f"{report.rejected} / {report.failed} / {report.unknown}")

    def show_pause(self, paused: bool, reason: str) -> None:
        self.pause.blockSignals(True)
        self.pause.setChecked(paused)
        self.pause.setText("Resume gesture scrolling" if paused else "Pause gesture scrolling")
        self.pause.blockSignals(False)
        self.pause_reason.setText(reason)


class PerformancePanel(Card):
    """Gesture Performance Report: measured values only; missing data says so."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Gesture performance (today)", parent)
        self.gestures = self.add_row("Confirmed gestures", accent=True)
        self.dispatched = self.add_row(
            "Dispatched actions", "Actions that passed every check and were sent to the browser."
        )
        self.succeeded = self.add_row("Successful")
        self.failed = self.add_row("Failed")
        self.rejected = self.add_row("Rejected")
        self.unknown = self.add_row("Outcome unknown")
        self.not_executed = self.add_row("Not executed", "Gesture test mode or no action mapped.")
        self.rate = self.add_row(
            "Execution success",
            "Successful / dispatched actions. Action reliability, not recognition accuracy.",
            accent=True,
        )
        self.latency = self.add_row("Action latency", "Dispatch to confirmation (successful).")
        self.add_heading("LIVE")
        self.fps = self.add_row("Tracking FPS")
        self.processing = self.add_row("Capture-to-result latency")
        self.recognition = self.add_row("Gesture recognition time")
        self.add_heading("GESTURE DISTRIBUTION")
        self.distribution = QLabel(NO_DATA)
        self.distribution.setWordWrap(True)
        self.distribution.setObjectName("rowValue")
        self.add_widget(self.distribution)

    def show_report(self, report: PerformanceReport | None) -> None:
        if report is None:
            for label in (
                self.gestures,
                self.dispatched,
                self.succeeded,
                self.failed,
                self.rejected,
                self.unknown,
                self.not_executed,
                self.rate,
                self.latency,
            ):
                label.setText(UNAVAILABLE)
            self.distribution.setText(UNAVAILABLE)
            return
        self.gestures.setText(str(report.gestures_total))
        self.dispatched.setText(str(report.dispatched))
        self.succeeded.setText(str(report.succeeded))
        self.failed.setText(str(report.failed))
        self.rejected.setText(str(report.rejected))
        self.unknown.setText(str(report.unknown))
        self.not_executed.setText(str(report.not_executed))
        rate = report.success_rate
        self.rate.setText(
            f"{rate:.0%} of {report.dispatched} dispatched" if rate is not None else NO_DATA
        )
        if report.latency_ms_mean is None:
            self.latency.setText(NO_DATA)
        else:
            self.latency.setText(
                f"{report.latency_ms_mean:.0f} ms mean, {report.latency_ms_p95:.0f} ms p95 "
                f"(n={report.latency_samples})"
            )
        if report.gestures:
            self.distribution.setText(
                ", ".join(
                    f"{stored_gesture_label(name)} {count}"
                    for name, count in sorted(report.gestures.items(), key=lambda kv: -kv[1])
                )
            )
        else:
            self.distribution.setText(NO_DATA)

    def show_live(self, metrics: PipelineMetrics, gesture_ms: float | None) -> None:
        running = metrics.processing_fps > 0
        self.fps.setText(f"{metrics.processing_fps:.1f}" if running else NO_DATA)
        self.processing.setText(
            f"{metrics.latency_ms:.1f} ms" if running and metrics.latency_ms else NO_DATA
        )
        self.recognition.setText(f"{gesture_ms:.2f} ms" if gesture_ms is not None else NO_DATA)


class WellbeingDialog(QDialog):
    def __init__(self, settings: WellbeingSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Limits and reminders")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.enabled = QCheckBox("Show Reality Checks and limit reminders")
        self.enabled.setChecked(settings.enabled)
        form.addRow(self.enabled)

        def spin(value: float, low: float, high: float, suffix: str) -> QDoubleSpinBox:
            box = QDoubleSpinBox()
            box.setRange(low, high)
            box.setDecimals(0)
            box.setValue(value)
            box.setSuffix(suffix)
            return box

        self.session = spin(settings.session_limit_min, 1, 600, " min")
        self.budget = spin(settings.daily_budget_min, 1, 1440, " min")
        self.reality = spin(settings.reality_check_min, 0, 240, " min (0 = off)")
        form.addRow("Session limit", self.session)
        form.addRow("Daily scrolling budget", self.budget)
        form.addRow("Reality Check every", self.reality)
        self.breaks = QCheckBox("Suggest a break when a limit is reached")
        self.breaks.setChecked(settings.break_reminders)
        self.pause = QCheckBox("Pause gesture scrolling when a limit is reached (resume anytime)")
        self.pause.setChecked(settings.pause_at_limit)
        self.humor = QCheckBox("Playful wording (Doomscroll Index, Wrapped)")
        self.humor.setChecked(settings.humorous_labels)
        for box in (self.breaks, self.pause, self.humor):
            form.addRow(box)
        root.addLayout(form)
        note = QLabel(
            "Only gesture navigation between Shorts can be paused. Your mouse, keyboard, likes, "
            "playback and tab switching keep working, and nothing is opened or closed."
        )
        note.setWordWrap(True)
        note.setObjectName("rowKey")
        root.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def result_settings(self) -> WellbeingSettings:
        return WellbeingSettings(
            enabled=self.enabled.isChecked(),
            session_limit_min=self.session.value(),
            daily_budget_min=self.budget.value(),
            reality_check_min=self.reality.value(),
            break_reminders=self.breaks.isChecked(),
            pause_at_limit=self.pause.isChecked(),
            humorous_labels=self.humor.isChecked(),
        )
