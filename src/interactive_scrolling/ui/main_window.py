"""Main application window."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling import __version__
from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ControlMode
from interactive_scrolling.config.settings import AppSettings, CameraSettings
from interactive_scrolling.core.auxiliary import AuxiliaryWorker
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import (
    CameraFactory,
    CameraState,
    TrackerFactory,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.core.stall_monitor import Stall, StallMonitor
from interactive_scrolling.gestures.explain import event_label
from interactive_scrolling.gestures.types import GestureEvent
from interactive_scrolling.services import ControlServices, offline_services
from interactive_scrolling.storage.settings_store import (
    CALIBRATION_REPAIR_NOTICE,
    MOTION_STYLE_NOTICE,
    VERTICAL_DIRECTION_NOTICE,
)
from interactive_scrolling.ui.appearance_dialog import AppearanceDialog
from interactive_scrolling.ui.bridge import PipelineBridge, QtLogHandler
from interactive_scrolling.ui.camera_settings import CameraSettingsDialog
from interactive_scrolling.ui.console import DiagnosticsConsole
from interactive_scrolling.ui.control_bar import ControlBar
from interactive_scrolling.ui.creator_overlay import CreatorOverlay
from interactive_scrolling.ui.effects_panel import (
    CalibrationDialog,
    EffectsDialog,
    VisualBehaviorPanel,
)
from interactive_scrolling.ui.gesture_panels import GestureHistory, GesturePanel, outcome_banner
from interactive_scrolling.ui.hotkey import GlobalHotkey
from interactive_scrolling.ui.panels import MotionPanel, OverlayPanel, TrackingPanel
from interactive_scrolling.ui.preview_view import PreviewView
from interactive_scrolling.ui.report_panels import (
    DailyReportPanel,
    PerformancePanel,
    WellbeingDialog,
)
from interactive_scrolling.ui.session_panel import PanelDialog, SessionPanel
from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog
from interactive_scrolling.ui.theme import repolish
from interactive_scrolling.ui.together import TogetherPanel
from interactive_scrolling.ui.tray import TrayController
from interactive_scrolling.ui.video_view import VideoView
from interactive_scrolling.ui.wrapped import (
    WrappedData,
    WrappedDialog,
    render_wrapped,
    wrapped_from_report,
    wrapped_from_session,
)
from interactive_scrolling.ui.youtube_panel import YouTubePanel
from interactive_scrolling.vision.camera import CameraInfo
from interactive_scrolling.vision.compositing import MaskCompositor
from interactive_scrolling.visualization import palette
from interactive_scrolling.visualization.clown import ClownEffect, clown_stage
from interactive_scrolling.visualization.eye_overlay import EyeOverlay

log = logging.getLogger(__name__)

ProbeFunction = Callable[[], list[CameraInfo]]
SegmenterFactory = Callable[[], object]

UI_MODES = ("developer", "creator", "background")
"""Presentation modes. They are independent of the control (safety) modes and never touch the
camera, the models or the dispatcher: one runtime, several views."""

_LOG_COLORS = {
    logging.WARNING: palette.ACCENT_AMBER,
    logging.ERROR: palette.ACCENT_RED,
    logging.CRITICAL: palette.ACCENT_RED,
}


class _ProbeSignals(QObject):
    finished = Signal(list)


class _ControlSignals(QObject):
    """Dispatcher notifications (any thread) marshalled to the UI thread."""

    record = Signal(object)
    mode = Signal(object, object, str)
    notice = Signal(object)


def broadcast_counters(session_s: float, report) -> str:  # type: ignore[no-untyped-def]
    """Session timer and today's executed actions for the Broadcast overlay."""
    minutes, seconds = divmod(int(max(0.0, session_s)), 60)
    text = f"Session {minutes}:{seconds:02d}"
    if report is not None:
        text += f"  ·  {sum(report.succeeded.values())} actions today"
    return text


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        camera_factory: CameraFactory,
        tracker_factory: TrackerFactory | None,
        probe_cameras: ProbeFunction | None = None,
        resource_monitor: ResourceMonitor | None = None,
        services: ControlServices | None = None,
        register_hotkey: bool = False,
        segmenter_factory: SegmenterFactory | None = None,
        face_factory: SegmenterFactory | None = None,
        quit_on_close: bool = False,
    ) -> None:
        super().__init__()
        self._quit_on_close = quit_on_close
        self.ui_mode = "developer"
        self.settings = settings
        self.services = services or offline_services(settings.gestures)
        self._probe_cameras = probe_cameras
        self._resources = resource_monitor or ResourceMonitor()
        self._camera_state = CameraState.STOPPED
        self._session = 0
        self._last_resource_text = ""
        self._tick = 0

        self.setWindowTitle("Interactive Scrolling")
        self.resize(1360, 860)
        self.setMinimumSize(960, 560)

        # UI responsiveness instrumentation (Integration Audit 003): a watchdog thread
        # attributes every UI stall to the running handler, GC and worker progress.
        self.stall_monitor = StallMonitor(on_stall=self._report_stall)
        self.bridge = PipelineBridge(self)
        self.pipeline = VisionPipeline(
            listener=self.bridge,
            camera_factory=camera_factory,
            tracker_factory=tracker_factory,
            motion_settings=settings.motion,
            inference_max_width=settings.tracking.inference_max_width,
            gesture_engine=self.services.engine,
            on_gesture_event=self._on_gesture_event,
            progress=self.stall_monitor.worker_progress,
        )
        # Recognition diagnostics and the opt-in landmark recorder see every processed frame.
        self.pipeline.add_gesture_tap(self.services.gesture_tap)

        self.video = VideoView(settings.overlay)
        self.video.section = self.stall_monitor.section
        user_settings = self.services.user_settings
        self.video.set_appearance(user_settings.appearance)
        # Optional person segmentation for the creator overlay. It receives frames only after
        # hand tracking (read-only) and runs only while the transparent overlay is visible.
        self.segmenter: AuxiliaryWorker | None = None
        if segmenter_factory is not None:
            self.segmenter = AuxiliaryWorker("segmentation", segmenter_factory, max_fps=15.0)
            self.pipeline.add_frame_tap(self.segmenter.submit)
        # Optional face landmarks, shared by the clown effect and eye analytics. The worker
        # runs only while one of the two features is enabled.
        self.face_worker: AuxiliaryWorker | None = None
        if face_factory is not None:
            self.face_worker = AuxiliaryWorker(
                "face landmarks",
                face_factory,
                max_fps=15.0,
                on_result=lambda r: self.services.add_face(r.timestamp_ns / 1e9, r.value),
            )
            self.pipeline.add_frame_tap(self.face_worker.submit)
        self.clown = ClownEffect()
        self.eyes = EyeOverlay()
        self.creator = CreatorOverlay(
            user_settings.creator, user_settings.appearance, self.segmenter
        )
        self.creator.mirrored = settings.mirror_preview
        self.creator.developer_requested.connect(lambda: self.set_ui_mode("developer"))
        self.creator.background_requested.connect(lambda: self.set_ui_mode("background"))
        self.creator.quit_requested.connect(self.close)
        self.creator.settings_changed.connect(
            lambda value: self.services.update_settings(creator=value)
        )
        self.creator.settings_requested.connect(self.open_broadcast_settings)
        self.video.extra_painters.append(self._paint_clown)
        self.creator.extra_painters.append(self._paint_clown)
        self.video.extra_painters.append(self._paint_eyes)
        self.creator.extra_painters.append(self._paint_eyes)
        self._update_face_worker()
        self.video.set_mirrored(settings.mirror_preview)
        self.video.renderer.trail_duration_s = settings.motion.trail_duration_s
        self.tracking_panel = TrackingPanel()
        self.motion_panel = MotionPanel()
        self.overlay_panel = OverlayPanel(settings.overlay, settings.mirror_preview)
        self.control_bar = ControlBar()
        self.control_bar.settings_requested.connect(self.open_gesture_settings)
        self.control_bar.practice_requested.connect(self.open_practice)
        self.gesture_panel = GesturePanel()
        self.history = GestureHistory()
        user = self.services.user_settings
        self.youtube_panel = YouTubePanel(user.pairing_token, user.bridge_port)
        self.today_panel = DailyReportPanel(user.analytics_enabled)
        self.performance_panel = PerformancePanel()
        self.coop_panel = TogetherPanel()
        self.coop_panel.renew_requested.connect(self._renew_invitation)
        self.coop_panel.host_requested.connect(self.host_coop)
        self.coop_panel.end_requested.connect(self.services.end_coop)
        self.coop_panel.approve_requested.connect(self._approve_guest)
        self.coop_panel.shared_control_changed.connect(self._set_shared_control)
        self.coop_panel.join_requested.connect(self.join_coop)
        self.coop_panel.leave_requested.connect(self.services.leave_coop)
        self.coop_panel.wrapped_requested.connect(self.open_duo_wrapped)
        self.coop_panel.join_signals.finished.connect(self._join_finished)
        self.visual_panel = VisualBehaviorPanel()
        self.visual_panel.calibrate_requested.connect(self.calibrate_eyes)
        self.visual_panel.settings_requested.connect(self.open_effects)
        self.camera_dialog = CameraSettingsDialog(
            settings.camera, self.overlay_panel, self._probe_cameras is not None, self
        )
        # The camera request widgets keep their historical names on the window.
        self.camera_combo = self.camera_dialog.camera_combo
        self.resolution_combo = self.camera_dialog.resolution_combo
        self.scan_button = self.camera_dialog.scan_button
        self.scan_button.clicked.connect(self._scan_cameras)
        self.appearance_button = self.camera_dialog.appearance_button
        self.appearance_button.clicked.connect(self.open_appearance)
        feed = self._preview_feed()
        self.preview = PreviewView(feed)
        self.session_panel = SessionPanel(self.coop_panel)
        self.session_panel.browser.setup_requested.connect(self.open_browser_setup)
        self.session_panel.browser.stop_preview_requested.connect(self.stop_preview)
        self.session_panel.today.report_requested.connect(self.open_report)
        self._dialogs: dict[str, QDialog] = {}

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_console())
        self.setCentralWidget(central)
        self.video.set_minimal(True)
        self._set_now_playing(user.appearance.show_now_playing, save=False)
        # Shorts commands may go to the previewed tab only while this app is in front.
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(15)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.preview_timer.start()

        # Always queued: pipeline notifications may be emitted on the UI thread while the
        # pipeline holds its state lock; queuing keeps slots out of that critical section.
        queued = Qt.ConnectionType.QueuedConnection
        self.bridge.frame_ready.connect(self._on_frame_ready, queued)
        self.bridge.camera_state_changed.connect(self._on_camera_state, queued)
        self.bridge.tracker_state_changed.connect(self._on_tracker_state, queued)
        self.overlay_panel.changed.connect(self.video.update)
        self.overlay_panel.mirror_changed.connect(self._on_mirror_changed)

        self._control_signals = _ControlSignals()
        self._control_signals.record.connect(self._on_record, queued)
        self._control_signals.mode.connect(self._on_mode_changed, queued)
        self.services.dispatcher.add_record_listener(self._control_signals.record.emit)
        self.services.dispatcher.add_mode_listener(self._control_signals.mode.emit)
        self.creator.set_control_mode(self.services.dispatcher.mode)
        self.control_bar.mode_requested.connect(self.set_control_mode)
        self.control_bar.disable_requested.connect(self.emergency_disable)
        self.gesture_panel.settings_requested.connect(self.open_gesture_settings)
        self.gesture_panel.diagnostics_requested.connect(self.copy_diagnostics)
        self.gesture_panel.practice_requested.connect(self.open_practice)
        self.today_panel.enabled_changed.connect(self.services.set_analytics_enabled)
        self.today_panel.clear_requested.connect(self._clear_statistics)
        self.today_panel.pause_toggled.connect(self.services.pause_scrolling)
        self.today_panel.settings_requested.connect(self.open_wellbeing)
        self.today_panel.wrapped_requested.connect(self.open_wrapped)
        self.services.notice_listeners.append(self._control_signals.notice.emit)
        self._control_signals.notice.connect(self._on_notice, queued)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.emergency_disable)
        self.hotkey = GlobalHotkey(self.emergency_disable)
        if register_hotkey and self.hotkey.register():
            QCoreApplication.instance().installNativeEventFilter(self.hotkey)
        self.control_bar.set_hotkey_hint(self.hotkey.label)
        self.tray = TrayController(self.hotkey.label, self)
        self.tray.start_camera.connect(self.start_camera)
        self.tray.stop_camera.connect(self.stop_camera)
        self.tray.disable_control.connect(self.emergency_disable)
        self.tray.mode_requested.connect(self.set_ui_mode)
        self.tray.quit_requested.connect(self.close)
        self.tray.broadcast_settings_requested.connect(self.open_broadcast_settings)
        self.tray.show()

        self.log_handler = QtLogHandler()
        self.log_handler.emitter.record.connect(self._append_log)
        package_logger = logging.getLogger("interactive_scrolling")
        package_logger.addHandler(self.log_handler)
        # The activity log always shows INFO events, independent of console verbosity
        # (console handlers keep their own level, see app.configure_logging).
        if package_logger.getEffectiveLevel() > logging.INFO:
            package_logger.setLevel(logging.INFO)

        self._probe_signals = _ProbeSignals()
        self._probe_signals.finished.connect(self._on_probe_finished)

        self.diagnostics_timer = QTimer(self)
        self.diagnostics_timer.setInterval(250)
        self.diagnostics_timer.timeout.connect(self._update_diagnostics)
        self.diagnostics_timer.start()
        self._update_diagnostics()
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(500)
        self.status_timer.timeout.connect(self._update_control_status)
        self.status_timer.start()
        self._stats_tick = 0
        self._update_control_status()

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.heartbeat_timer.setInterval(50)
        self.heartbeat_timer.timeout.connect(self.stall_monitor.beat)
        self.heartbeat_timer.start()
        self.stall_monitor.start()

        self.services.start_activity()
        self._apply_camera_state(CameraState.STOPPED)
        log.info("interactive_scrolling %s started. All processing runs locally.", __version__)
        self.pipeline.launch()

    # ------------------------------------------------------------------ layout

    def _build_top_bar(self) -> QWidget:
        """Product name, camera state, Camera settings, Normal/Broadcast and Start/Stop
        camera. Everything else lives in the More menu, the session panel or the console."""
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(8)
        brand = QLabel("Interactive Scrolling")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        version = QLabel(f"beta {__version__}")
        version.setObjectName("version")
        version.setToolTip("Beta version. All processing runs on this computer.")
        layout.addWidget(version)
        layout.addSpacing(18)
        self.status_pill = QLabel()
        self.status_pill.setObjectName("cameraStatus")
        layout.addWidget(self.status_pill)
        layout.addStretch(1)

        self.camera_settings_button = QPushButton("Camera settings")
        self.camera_settings_button.setObjectName("flatButton")
        self.camera_settings_button.clicked.connect(self.open_camera_settings)
        layout.addWidget(self.camera_settings_button)
        layout.addSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[str, QPushButton] = {}
        for index, (mode, text, tip) in enumerate(
            (
                ("developer", "Normal", "The full application window"),
                (
                    "creator",
                    "Broadcast",
                    "A small always-on-top camera window over the browser, for recording and "
                    "streaming (OBS). Does not change gesture control.",
                ),
            )
        ):
            button = QPushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setProperty("first", index == 0)
            button.setProperty("last", index == 1)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, m=mode: self.set_ui_mode(m))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            layout.addWidget(button)
        self.mode_buttons["developer"].setChecked(True)
        self.creator_button = self.mode_buttons["creator"]

        self.more_button = QToolButton()
        self.more_button.setObjectName("flatButton")
        self.more_button.setText("More")
        self.more_button.setToolTip("Background mode, gesture practice, reports, help")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setMenu(self._build_more_menu())
        layout.addWidget(self.more_button)
        layout.addSpacing(6)

        self.start_button = QPushButton("Start camera")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(118)
        self.start_button.clicked.connect(self._toggle_camera)
        layout.addWidget(self.start_button)
        return bar

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)
        self.more_menu = menu
        entries: list[tuple[str, Callable[[], object]] | None] = [
            ("Run in the background (tray)", lambda: self.set_ui_mode("background")),
            ("Broadcast settings...", self.open_broadcast_settings),
            None,
            ("Practice gestures...", self.open_practice),
            ("Gesture settings...", self.open_gesture_settings),
            ("Face effects and eye analytics...", self.open_effects),
            None,
            ("Daily report...", self.open_report),
            ("Browser setup and pairing...", self.open_browser_setup),
            ("Copy diagnostics", self.copy_diagnostics),
            ("Getting started", self.open_getting_started),
        ]
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            text, slot = entry
            action = QAction(text, menu)
            action.triggered.connect(lambda _=False, s=slot: s())
            menu.addAction(action)
        menu.addSeparator()
        self.eye_overlay_action = QAction("Show eye and gaze overlay (estimate)", menu)
        self.eye_overlay_action.setCheckable(True)
        self.eye_overlay_action.setChecked(self.services.user_settings.effects.eye_overlay)
        self.eye_overlay_action.toggled.connect(self.set_eye_overlay)
        menu.addAction(self.eye_overlay_action)
        self.now_playing_action = QAction("Show Now playing", menu)
        self.now_playing_action.setCheckable(True)
        self.now_playing_action.toggled.connect(lambda on: self._set_now_playing(on))
        menu.addAction(self.now_playing_action)
        return menu

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        stage = QWidget()
        stage_layout = QHBoxLayout(stage)
        stage_layout.setContentsMargins(18, 12, 18, 12)
        stage_layout.setSpacing(18)

        camera = QWidget()
        camera_layout = QVBoxLayout(camera)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(6)
        camera_layout.addWidget(self._column_title("Your camera"))
        camera_layout.addWidget(self.video)
        camera_layout.addWidget(self.control_bar)
        camera_layout.addStretch(1)
        self._camera_column = camera
        stage_layout.addWidget(camera, 1)

        self.now_playing = QWidget()
        playing = QVBoxLayout(self.now_playing)
        playing.setContentsMargins(0, 0, 0, 0)
        playing.setSpacing(6)
        playing.addWidget(self._column_title("Now playing"))
        playing.addWidget(self.preview, 1)
        self.preview_info = QLabel("")
        self.preview_info.setObjectName("dimHint")
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        playing.addWidget(self.preview_info)
        self.now_playing.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        stage_layout.addWidget(self.now_playing)
        layout.addWidget(stage, 1)

        self.session_panel.setFixedWidth(292)
        layout.addWidget(self.session_panel)
        self._stage = stage
        stage.installEventFilter(self)
        return body

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        # The stage changes size with the window and when the console opens or closes.
        if watched is getattr(self, "_stage", None) and event.type() == QEvent.Type.Resize:
            self._fit_now_playing()
        return super().eventFilter(watched, event)

    @staticmethod
    def _column_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _build_console(self) -> QWidget:
        self.capture_fps_label = QLabel()
        self.processing_fps_label = QLabel()
        self.display_fps_label = QLabel()
        self.latency_label = QLabel()
        self.dropped_label = QLabel()
        self.resources_label = QLabel()
        self.stalls_label = QLabel()
        labels = [
            (self.capture_fps_label, "Frames per second delivered by the camera"),
            (self.processing_fps_label, "Frames per second through inference and motion analysis"),
            (self.latency_label, "Capture-to-result processing latency: mean / 95th percentile"),
            (self.resources_label, "Process CPU (share of all logical cores) and resident memory"),
            (self.display_fps_label, "Frames per second painted on screen"),
            (self.dropped_label, "Outdated frames skipped so latency cannot accumulate"),
            (
                self.stalls_label,
                f"Times the window did not respond for more than "
                f"{self.stall_monitor.threshold_ms:.0f} ms (measured by a watchdog thread)",
            ),
        ]
        for label, tip in labels:
            label.setToolTip(tip)
        self.connection_details = QLabel()
        self.connection_details.setObjectName("hint")
        self.connection_details.setWordWrap(True)
        self.connection_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.console = DiagnosticsConsole(
            [label for label, _ in labels],
            self.history,
            self.gesture_panel,
            [self.performance_panel, self.tracking_panel, self.motion_panel],
            [self.connection_details],
            expanded=self.services.user_settings.appearance.console_expanded,
        )
        self.activity_log = self.console.activity_log
        self.console.copy_requested.connect(self.copy_diagnostics)
        self.console.expanded_changed.connect(self._console_toggled)
        return self.console

    def _console_toggled(self, expanded: bool) -> None:
        appearance = self.services.user_settings.appearance
        if appearance.console_expanded != expanded:
            self.services.update_settings(appearance=replace(appearance, console_expanded=expanded))

    def _set_now_playing(self, shown: bool, save: bool = True) -> None:
        self.now_playing.setVisible(shown)
        if self.now_playing_action.isChecked() != shown:
            self.now_playing_action.setChecked(shown)
        self._fit_now_playing()
        appearance = self.services.user_settings.appearance
        if save and appearance.show_now_playing != shown:
            self.services.update_settings(appearance=replace(appearance, show_now_playing=shown))
            if not shown:
                # A hidden preview must not keep the browser capturing.
                self.stop_preview()

    def _fit_now_playing(self) -> None:
        """The Now playing column is as wide as a Short of the stage's height (9:16), within
        limits that keep the camera usable."""
        stage = getattr(self, "_stage", None)
        if stage is None:
            return
        chrome = 24 + 30  # stage margins and the column title
        height = max(200, stage.height() - chrome - 24)
        width = int(height * 9 / 16)
        width = max(170, min(width, int(stage.width() * 0.36)))
        self.now_playing.setFixedWidth(width)
        # The camera image keeps 16:9 at the top of its column with the gesture strip right
        # under it; on short windows it shrinks to leave room for the strip.
        camera_width = stage.width() - 36 - (width + 18 if self.now_playing.isVisible() else 0)
        strip = self.control_bar.sizeHint().height()
        video_height = min(int(camera_width * 9 / 16), stage.height() - chrome - strip - 12)
        self.video.setFixedHeight(max(160, video_height))

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_now_playing()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_now_playing)

    # ------------------------------------------------------------------ dialogs

    def _dialog(self, key: str, factory: Callable[[], QDialog]) -> QDialog:
        dialog = self._dialogs.get(key)
        if dialog is None:
            dialog = factory()
            self._dialogs[key] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def open_camera_settings(self) -> None:
        self.camera_dialog.show()
        self.camera_dialog.raise_()
        self.camera_dialog.activateWindow()

    def open_browser_setup(self) -> None:
        self._dialog(
            "browser", lambda: PanelDialog("Browser setup and pairing", [self.youtube_panel], self)
        )

    def open_report(self) -> None:
        self._dialog(
            "report",
            lambda: PanelDialog("Today", [self.today_panel, self.visual_panel], self),
        )

    def open_broadcast_settings(self) -> None:
        from interactive_scrolling.ui.broadcast_settings import BroadcastSettingsDialog

        existing = self._dialogs.pop("broadcast", None)
        if existing is not None:
            existing.close()
        dialog = BroadcastSettingsDialog(
            lambda: self.creator.settings,
            self.services.user_settings.effects,
            self.segmenter is not None,
        )
        dialog.creator_changed.connect(self._apply_creator)
        dialog.corner_requested.connect(self.creator.move_to_corner)
        dialog.effects_changed.connect(self._apply_effects)
        dialog.face_effects_requested.connect(self.open_effects)
        self._dialogs["broadcast"] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _apply_creator(self, settings) -> None:  # type: ignore[no-untyped-def]
        self.creator.apply_settings(settings)
        self.services.update_settings(creator=settings)

    def _apply_effects(self, effects) -> None:  # type: ignore[no-untyped-def]
        self.services.apply_effects(effects)
        self._update_face_worker()
        action = getattr(self, "eye_overlay_action", None)
        if action is not None and action.isChecked() != effects.eye_overlay:
            action.blockSignals(True)
            action.setChecked(effects.eye_overlay)
            action.blockSignals(False)
        if effects.clown_preview_stage is not None:
            self.clown.jump_to_stage(effects.clown_preview_stage)

    def stop_preview(self) -> None:
        controller = self.services.controller
        bridge = getattr(controller, "bridge", None)
        if bridge is not None and bridge.stop_preview():
            log.info("Live preview stopped from the app.")

    def _preview_feed(self):  # type: ignore[no-untyped-def]
        controller = self.services.controller
        bridge = getattr(controller, "bridge", None)
        return getattr(bridge, "preview", None)

    def _refresh_preview(self) -> None:
        if self.now_playing.isVisible() and self.isVisible():
            with self.stall_monitor.section("preview"):
                self.preview.refresh()

    def _on_application_state(self, state) -> None:  # type: ignore[no-untyped-def]
        controller = self.services.controller
        if controller is not None and hasattr(controller, "app_in_front"):
            controller.app_in_front = state == Qt.ApplicationState.ApplicationActive

    # ------------------------------------------------------------------ camera control

    def requested_camera_settings(self) -> CameraSettings:
        width, height = self.resolution_combo.currentData()
        base = self.settings.camera
        return CameraSettings(
            index=int(self.camera_combo.currentData()),
            width=width,
            height=height,
            fps=int(self.camera_dialog.fps_combo.currentData()),
            backend=base.backend,
        )

    def start_camera(self) -> bool:
        return self.pipeline.start_camera(self.requested_camera_settings())

    def stop_camera(self) -> None:
        self.pipeline.stop_camera()

    def _toggle_camera(self) -> None:
        if self._camera_state in (CameraState.RUNNING, CameraState.STARTING):
            self.stop_camera()
        elif not self.start_camera():
            log.warning("Camera is busy; try again in a moment.")

    def _on_camera_state(self, state: CameraState, message: str, session: int) -> None:
        self._session = session
        self._apply_camera_state(state)
        if state is CameraState.ERROR:
            log.error(message)
            self.video.clear(f"Camera error\n\n{message}")
            self.creator.clear()
        elif state is CameraState.STOPPED:
            log.info(message)
            self.video.clear("Camera is off.\n\nPress Start camera to begin.")
            self.creator.clear()
        elif state is CameraState.STARTING:
            log.info(message)
            self.video.clear(message)
        elif state is CameraState.RUNNING:
            log.info(message)

    def _apply_camera_state(self, state: CameraState) -> None:
        self._camera_state = state
        running = state in (CameraState.RUNNING, CameraState.STARTING)
        self.status_pill.setText(
            {
                CameraState.STOPPED: "●  Camera off",
                CameraState.STARTING: "●  Camera starting",
                CameraState.RUNNING: "●  Camera on",
                CameraState.STOPPING: "●  Camera stopping",
                CameraState.ERROR: "●  Camera error",
            }[state]
        )
        self.status_pill.setProperty("state", state.value)
        self.start_button.setText("Stop camera" if running else "Start camera")
        self.tray.update_state(
            state in (CameraState.RUNNING, CameraState.STARTING), self.services.dispatcher.mode
        )
        self.start_button.setProperty("running", running)
        self.start_button.setEnabled(state is not CameraState.STOPPING)
        idle = state in (CameraState.STOPPED, CameraState.ERROR)
        self.camera_dialog.set_idle(idle, self._probe_cameras is not None)
        for widget in (self.status_pill, self.start_button):
            repolish(widget)
        if not running:
            self.tracking_panel.update_tracking(None)
            self.motion_panel.update_motion(None, self.video.mirrored)

    def _on_tracker_state(self, state: TrackerState, message: str) -> None:
        self.tracking_panel.set_tracker_state(state, message)
        if state is TrackerState.UNAVAILABLE:
            log.error("Hand tracking unavailable: %s", message)
            self.video.set_status_text("TRACKING UNAVAILABLE")
        elif state is TrackerState.LOADING:
            self.video.set_status_text("LOADING MODEL")
        else:
            self.video.set_status_text("")
            if state is TrackerState.READY:
                log.info(message)

    def _on_frame_ready(self) -> None:
        with self.stall_monitor.section("frame update"):
            self._show_frame()

    def _show_frame(self) -> None:
        frame = self.bridge.take_latest()
        if frame is None:
            return
        # Discard frames from a stopped session so no stale image or landmarks remain.
        if frame.session != self._session or self._camera_state is not CameraState.RUNNING:
            return
        self._update_clown(frame)
        self.video.set_frame(frame)
        if self.creator.isVisible():
            self.creator.show_frame(frame)
        self.tracking_panel.update_tracking(frame.tracking)
        self.motion_panel.update_motion(frame, self.video.mirrored)
        enabled = self.services.dispatcher.mode is not ControlMode.TRACKING_ONLY
        self.gesture_panel.show_frame(frame.gestures, enabled)
        practice = getattr(self, "practice_dialog", None)
        if practice is not None and practice.isVisible():
            practice.show_frame(frame)

    def _on_mirror_changed(self, mirrored: bool) -> None:
        self.settings.mirror_preview = mirrored
        self.video.set_mirrored(mirrored)
        self.creator.mirrored = mirrored
        if self.video.frame is not None:
            self.motion_panel.update_motion(self.video.frame, mirrored)

    # ------------------------------------------------------------------ gesture control

    def set_control_mode(self, mode: ControlMode) -> None:
        """Switch Tracking only / Gesture test / Live control (deliberate user action)."""
        self.services.dispatcher.set_mode(mode)
        self.control_bar.set_mode(self.services.dispatcher.mode)

    def emergency_disable(self) -> None:
        if self.services.dispatcher.mode is not ControlMode.TRACKING_ONLY:
            self.services.dispatcher.emergency_disable()
        self.control_bar.set_mode(ControlMode.TRACKING_ONLY)

    def _on_mode_changed(self, old: ControlMode, new: ControlMode, reason: str) -> None:
        self.pipeline.set_gestures_enabled(new is not ControlMode.TRACKING_ONLY)
        self.control_bar.set_mode(new)
        self.creator.set_control_mode(new)
        self.tray.update_state(
            self._camera_state in (CameraState.RUNNING, CameraState.STARTING), new
        )
        if new is ControlMode.TRACKING_ONLY:
            self.gesture_panel.show_frame(None, enabled=False)
        if new is ControlMode.LIVE_CONTROL:
            log.warning(
                "LIVE CONTROL enabled: confirmed gestures will control YouTube Shorts "
                "and browser tabs."
            )

    def _on_gesture_event(self, event: GestureEvent) -> None:
        # Called on the processing thread; submitting never blocks.
        self.services.dispatcher.submit(event)

    def _on_record(self, record: ActionRecord) -> None:
        first = self.history.outcome_of(record.record_id) is None
        self.history.update_record(record)
        self.gesture_panel.show_record(record)
        self.creator.show_record(record)
        if first:
            self.video.show_gesture(event_label(record.event.gesture, record.event.detector))
        if record.status.final and record.status is not ActionStatus.NOT_EXECUTED:
            # The final outcome replaces the gesture banner: immediate feedback first, then
            # the verified result (YouTube can take a second to load the next Short).
            self.video.show_gesture(*outcome_banner(record))
        if record.status.final or record.status is ActionStatus.DISPATCHED:
            gesture = event_label(record.event.gesture, record.event.detector)
            self.control_bar.set_last(
                f"{gesture} \u2192 {record.action.label}: {record.status.value}"
            )
            if record.status.final and record.status is not ActionStatus.NOT_EXECUTED:
                log.info(
                    "%s -> %s: %s%s",
                    event_label(record.event.gesture, record.event.detector),
                    record.action.label,
                    record.status.value,
                    f" ({record.reason})" if record.reason else "",
                )

    # ------------------------------------------------------------------ presentation modes

    def set_ui_mode(self, mode: str) -> None:
        """Developer (dashboard), creator (floating overlay) or background (tray only).

        Only windows are shown or hidden: the camera, models, gesture engine, dispatcher, browser
        bridge and statistics keep running unchanged, and the emergency shortcut stays active.
        """
        if mode not in UI_MODES:
            raise ValueError(f"unknown UI mode {mode!r}")
        if mode == "background" and not self.tray.available:
            log.warning("No system tray available; staying in the current mode.")
            return
        self.ui_mode = mode
        if mode in self.mode_buttons:
            self.mode_buttons[mode].setChecked(True)
        if mode == "developer":
            self.creator.hide()
            self.showNormal()
            self.raise_()
            self.activateWindow()
        elif mode == "creator":
            self.creator.apply_settings(self.creator.settings, reposition=True)
            self.creator.show()
            self.hide()
        else:
            self.creator.hide()
            self.hide()
            self.tray.notify(
                "Interactive Scrolling is running in the background",
                "The tray icon shows the camera and control state. Right-click it for options.",
            )
        log.info("Presentation mode: %s", mode)

    # ------------------------------------------------------------------ face features

    def _update_face_worker(self) -> None:
        effects = self.services.user_settings.effects
        if self.face_worker is not None:
            self.face_worker.set_enabled(
                effects.clown_enabled or effects.eye_analytics_enabled or effects.eye_overlay
            )
        if not effects.eye_overlay:
            self.eyes.reset()
        self.clown.set_makeup_opacity(effects.clown_makeup_opacity)
        if not effects.clown_enabled:
            self.clown.reset()

    def clown_stage(self) -> int:
        effects = self.services.user_settings.effects
        if effects.clown_preview_stage is not None:
            return effects.clown_preview_stage
        return clown_stage(self.services.current_session_s(), effects.clown_thresholds)

    def _update_clown(self, frame) -> None:  # type: ignore[no-untyped-def]
        effects = self.services.user_settings.effects
        if self.face_worker is None or not (effects.clown_enabled or effects.eye_overlay):
            return
        result = self.face_worker.latest()
        face = None
        if result is not None and MaskCompositor.usable(
            result.timestamp_ns, result.session, frame.capture_ns, frame.session
        ):
            face = result.value
        if effects.eye_overlay:
            self.eyes.update(face, frame.capture_ns)
        if not effects.clown_enabled:
            return
        self.clown.update(
            face.landmarks if face is not None else None, frame.capture_ns, self.clown_stage()
        )

    def _paint_eyes(self, painter, transform, frame) -> None:  # type: ignore[no-untyped-def]
        if self.services.user_settings.effects.eye_overlay:
            self.eyes.paint(painter, transform)

    def set_eye_overlay(self, enabled: bool) -> None:
        effects = self.services.user_settings.effects
        if effects.eye_overlay != enabled:
            self._apply_effects(replace(effects, eye_overlay=enabled))
        if self.eye_overlay_action.isChecked() != enabled:
            self.eye_overlay_action.setChecked(enabled)

    def _paint_clown(self, painter, transform, frame) -> None:  # type: ignore[no-untyped-def]
        if self.services.user_settings.effects.clown_enabled:
            self.clown.paint(painter, transform)

    def open_effects(self) -> None:
        dialog = EffectsDialog(self.services.user_settings.effects, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.services.apply_effects(dialog.result_settings())
            self._update_face_worker()
            log.info("Face effect settings saved.")

    def calibrate_eyes(self) -> None:
        if self.face_worker is None:
            log.warning("Face landmarks are not available in this build.")
            return
        worker = self.face_worker
        was_enabled = worker.enabled
        worker.set_enabled(True)

        def latest():  # type: ignore[no-untyped-def]
            result = worker.latest()
            return result.value if result is not None else None

        dialog = CalibrationDialog(latest, self)
        dialog.exec()
        worker.set_enabled(was_enabled)
        self._update_face_worker()
        result = dialog.result
        if result is not None and result.reliable:
            effects = replace(
                self.services.user_settings.effects,
                eye_baseline_yaw=round(result.baseline.yaw, 2),
                eye_baseline_pitch=round(result.baseline.pitch, 2),
                eye_baseline_gaze=round(result.baseline.gaze, 4),
            )
            self.services.apply_effects(effects)
            log.info("Eye analytics calibrated (%d samples).", result.samples)

    def wrapped_data(self, scope: str):  # type: ignore[no-untyped-def]
        """Real statistics for Doomscroll Wrapped, or ``None`` if none are available."""
        services = self.services
        humorous = services.user_settings.wellbeing.humorous_labels
        w = services.user_settings.wellbeing
        services.refresh_reports()
        if scope == "today":
            report = services.report
            eyes = (
                services.eye_report
                if services.user_settings.effects.eye_analytics_enabled
                else None
            )
            return wrapped_from_report(report, humorous, eyes) if report is not None else None
        start, session_s = services.current_session()
        analytics = services.analytics
        if start is None or analytics is None or not analytics.enabled:
            return None
        analytics.flush()
        counts = analytics.counts_between(start, services.wall_clock())
        if counts is None:
            return None
        return wrapped_from_session(
            session_s, counts[0], counts[1], w.daily_budget_min, w.session_limit_min, humorous
        )

    def open_wrapped(self, scope: str = "today") -> None:
        data = self.wrapped_data(scope)
        if data is None:
            log.warning(
                "No %s statistics for Doomscroll Wrapped (statistics off or no scrolling "
                "session in progress).",
                "daily" if scope == "today" else "session",
            )
            return
        image, _ = render_wrapped(data, self.services.user_settings.wellbeing.humorous_labels)
        name = f"doomscroll-wrapped-{datetime.now():%Y-%m-%d-%H%M}.png"
        WrappedDialog(image, name, self).exec()

    # ------------------------------------------------------------------ co-op

    def host_coop(self, name: str, port: int, bind: str = "0.0.0.0") -> None:
        try:
            self.services.host_coop(name, port, bind)
        except ValueError as exc:
            self.coop_panel.show_error(f"Could not start the session: {exc}")
            return
        except OSError as exc:
            log.warning("Co-op session could not listen: %s", exc)
            self.coop_panel.show_error(
                f"Could not start the session: port {port} is in use or the network address "
                "is not available. Try another port or network."
            )
            return
        self.coop_panel.show_error("")
        # The code is a credential for the session: it is shown in the panel, not logged.
        log.info("Doomscroll Together session started (port %d).", port)
        self._update_control_status()

    def _renew_invitation(self) -> None:
        if self.services.renew_coop_invitation() is not None:
            log.info("Doomscroll Together: new invitation code created.")
        self._update_control_status()

    def _approve_guest(self, approved: bool) -> None:
        host = getattr(self.services, "_coop_host", None)
        if host is None:
            return
        if approved or host.status().pending_approval:
            host.approve(approved)
        else:
            host.remove_guest()  # "Remove" for a guest who was already let in

    def _set_shared_control(self, enabled: bool) -> None:
        host = getattr(self.services, "_coop_host", None)
        if host is not None:
            host.set_shared_control(enabled)

    def join_coop(self, name: str, address: str, port: int, code: str) -> None:
        signals = self.coop_panel.join_signals
        self.coop_panel.show_error("Connecting...")

        def run() -> None:
            from interactive_scrolling.integrations.coop.session import friendly_error

            try:
                self.services.join_coop(name, address, port, code)
            except Exception as exc:  # reported in the panel, never raised into Qt
                log.info("Doomscroll Together: joining failed: %s", exc)
                signals.finished.emit(friendly_error(exc))
                return
            signals.finished.emit("")

        threading.Thread(target=run, name="coop-join", daemon=True).start()

    def _join_finished(self, error: str) -> None:
        self.coop_panel.show_error(error)
        if not error:
            log.info("Joined the co-op session; waiting for the host to approve.")

    def open_duo_wrapped(self) -> None:
        status = self.services.coop_status()
        if status.role == "off" or not status.participants:
            log.warning("Duo Wrapped is available to the Host during or right after a session.")
            return
        host = getattr(self.services, "_coop_host", None)
        succeeded: dict[str, int] = {}
        for participant in host.participants.values() if host is not None else ():
            for action, count in participant.successes.items():
                succeeded[action] = succeeded.get(action, 0) + count
        data = WrappedData(
            scope="Co-op session",
            date_text=datetime.now().strftime("%a %d %b %Y"),
            scrolling_s=status.session_s,
            sessions=None,
            longest_s=None,
            next_previous=(succeeded.get("next_short", 0), succeeded.get("previous_short", 0)),
            tabs=(0, 0),
            likes=0,
            gestures=sum(c for _, _, c in status.participants),
            index=None,
            title="Scrolling, but make it social"
            if self.services.user_settings.wellbeing.humorous_labels
            else "",
            participants=tuple((n, c) for n, _, c in status.participants),
        )
        image, _ = render_wrapped(data, self.services.user_settings.wellbeing.humorous_labels)
        WrappedDialog(image, f"duo-wrapped-{datetime.now():%Y-%m-%d-%H%M}.png", self).exec()

    def open_wellbeing(self) -> None:
        dialog = WellbeingDialog(self.services.user_settings.wellbeing, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.services.apply_wellbeing(dialog.result_settings())
            log.info("Limits and reminders saved.")

    def _on_notice(self, notice) -> None:  # type: ignore[no-untyped-def]
        self.video.show_gesture(notice.title.upper(), palette.ACCENT_AMBER)
        self.tray.notify(notice.title, notice.text)

    def open_appearance(self) -> None:
        user = self.services.user_settings
        dialog = AppearanceDialog(user.appearance, self.creator.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            appearance = dialog.result_appearance()
            creator = dialog.result_creator()
            self.video.set_appearance(appearance)
            self.creator.set_appearance(appearance)
            self.creator.apply_settings(creator, reposition=True)
            self.services.update_settings(appearance=appearance, creator=creator)
            log.info("Appearance saved.")

    def _data_folder(self) -> Path:
        store = self.services.store
        if store is not None:
            return store.path.parent
        from interactive_scrolling.storage.paths import data_dir

        return data_dir()

    def _performance_summary(self) -> dict:
        summary: dict = {}
        mean = self.pipeline.gesture_ms_mean()
        if mean is not None:
            summary["gesture_recognition_ms_mean"] = round(mean, 3)
        metrics = self.pipeline.metrics()
        for name in (
            "capture_fps",
            "processing_fps",
            "inference_ms",
            "latency_ms",
            "frames_dropped",
        ):
            value = getattr(metrics, name, None)
            if isinstance(value, int | float):
                summary[name] = round(float(value), 2)
        summary["ui_stalls"] = getattr(self.stall_monitor, "stall_count", None)
        return summary

    def copy_diagnostics(self) -> None:
        """Copy the diagnostics report to the clipboard and save it next to the settings."""
        report = self.services.diagnostics_report(self._performance_summary())
        text = json.dumps(report, indent=2)
        QApplication.clipboard().setText(text)
        try:
            path = self.services.export_diagnostics(
                self._data_folder() / "diagnostics", self._performance_summary()
            )
            message = f"Diagnostics copied to the clipboard and saved as {path}"
        except OSError as exc:
            message = f"Diagnostics copied to the clipboard (saving failed: {exc})"
        log.info(message)
        self.control_bar.set_last(message)
        self.last_diagnostics_text = text

    def open_practice(self) -> None:
        from interactive_scrolling.ui.practice_dialog import PracticeDialog

        existing = getattr(self, "practice_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dialog = PracticeDialog(self.services, self._data_folder(), self)
        self.practice_dialog = dialog
        dialog.finished.connect(lambda _: setattr(self, "practice_dialog", None))
        dialog.show()

    def open_getting_started(self) -> None:
        from interactive_scrolling.ui.getting_started import GettingStartedDialog

        existing = getattr(self, "getting_started", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            return
        user = self.services.user_settings
        dialog = GettingStartedDialog(user.pairing_token, self.hotkey.label, self)
        dialog.start_camera_requested.connect(self.start_camera)
        dialog.practice_requested.connect(self.open_practice)
        dialog.finished.connect(lambda _: self._getting_started_closed(dialog))
        self.getting_started = dialog
        dialog.show()

    def _getting_started_closed(self, dialog) -> None:  # type: ignore[no-untyped-def]
        self.getting_started = None
        done = dialog.dont_show.isChecked()
        appearance = self.services.user_settings.appearance
        if appearance.getting_started_done != done:
            from dataclasses import replace

            self.services.update_settings(appearance=replace(appearance, getting_started_done=done))

    def show_getting_started_if_new(self) -> None:
        """First start: show the guide once (real application only)."""
        if not self.services.user_settings.appearance.getting_started_done:
            self.open_getting_started()

    def show_startup_notices(self) -> None:
        """One-time notices from settings migrations (e.g. the new scroll direction)."""
        store = self.services.store
        if store is None or not store.migrations:
            return
        titles = {
            VERTICAL_DIRECTION_NOTICE: "SCROLL DIRECTION UPDATED",
            CALIBRATION_REPAIR_NOTICE: "CALIBRATION RESET - PLEASE RECALIBRATE",
            MOTION_STYLE_NOTICE: "SWIPES NOW WORK WITH ANY HAND SHAPE",
        }
        notices = [m for m in store.migrations if m in titles]
        for notice in notices:
            self.video.show_gesture(titles[notice], palette.ACCENT_AMBER)
            self.control_bar.set_last(notice)
            self.tray.notify("Interactive Scrolling", notice)
        store.migrations = [m for m in store.migrations if m not in notices]

    def open_gesture_settings(self) -> None:
        dialog = GestureSettingsDialog(
            self.services.engine.settings, self.services.dispatcher.mapping, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.services.apply_gesture_settings(dialog.result_settings())
            self.services.apply_mapping(dialog.result_mapping())
            log.info("Gesture settings saved.")

    def _clear_statistics(self) -> None:
        analytics = self.services.analytics
        if analytics is not None and analytics.clear():
            log.info("Local statistics deleted.")
        self.services.refresh_reports()
        self._stats_tick = 0
        self._update_control_status()

    def _update_control_status(self) -> None:
        with self.stall_monitor.section("control status"):
            self._refresh_control_status()

    def _refresh_control_status(self) -> None:
        controller = self.services.controller
        status = controller.status() if controller is not None else None
        self.youtube_panel.show_status(status)
        feed = self.preview.feed
        preview = feed.status() if feed is not None else None
        self.session_panel.browser.show_status(status, preview)
        self.preview.set_status(preview, status is not None and status.connections > 0)
        if preview is not None and preview.connected:
            self.preview_info.setText(f"Live from your browser · {preview.fps:.0f} fps")
        else:
            self.preview_info.setText("")
        # Reports are computed on the services' activity thread; the UI only displays them.
        services = self.services
        analytics = services.analytics
        self.session_panel.today.show_values(
            services.current_session_s(),
            services.report,
            "" if analytics is not None and analytics.enabled else "Statistics are off.",
        )
        self.today_panel.show_report(
            services.report,
            services.current_session_s(),
            services.user_settings.wellbeing.humorous_labels,
            analytics.error if analytics is not None else "statistics are off in this session",
        )
        self.today_panel.show_pause(
            services.wellbeing.scrolling_paused, services.wellbeing.pause_reason
        )
        self.performance_panel.show_report(services.performance)
        coop = services.coop_status()
        self.coop_panel.show_status(coop)
        self.connection_details.setText(self._connection_text(status, preview, coop))
        if self.creator.isVisible():
            self.creator.counters_text = broadcast_counters(
                services.current_session_s(), services.report
            )
        effects = services.user_settings.effects
        self.visual_panel.show_report(
            effects.eye_analytics_enabled,
            effects.eye_baseline_yaw is not None,
            services.eye_report,
        )
        self._stats_tick += 1

    def _connection_text(self, status, preview, coop) -> str:  # type: ignore[no-untyped-def]
        """Technical connection details for the console (no codes, tokens or URLs)."""
        lines = []
        if status is not None:
            lines.append(
                f"Browser bridge: {'listening' if status.listening else 'stopped'}, "
                f"{status.connections} connection(s) {', '.join(status.browsers)}; "
                f"Shorts target: {'ready' if status.ready else status.reason}"
                f"{' (preview tab, app in front)' if status.via_preview else ''}"
            )
        if preview is not None and preview.connected:
            transport = f"{preview.transport_ms:.0f} ms" if preview.transport_ms else "—"
            lines.append(
                f"Live preview: {preview.state}, {preview.fps:.1f} fps received, browser-to-app "
                f"transport {transport} (median), {preview.frames} frames, "
                f"{preview.skipped} skipped by the browser, {self.preview.decoded} decoded"
            )
        elif preview is not None:
            lines.append(f"Live preview: off{f' ({preview.reason})' if preview.reason else ''}")
        if coop.role != "off":
            rtt = f"{coop.rtt_ms:.0f} ms" if coop.rtt_ms is not None else "—"
            confirm = f"{coop.confirm_ms:.0f} ms" if coop.confirm_ms is not None else "—"
            bind = f", listening on {coop.bind}:{coop.port}" if coop.bind else ""
            lines.append(
                f"Doomscroll Together: {coop.role}, {coop.state}{bind}; network round trip "
                f"{rtt}; last action confirmed after {confirm} (network and host execution, "
                "not screen sharing)"
            )
        else:
            lines.append("Doomscroll Together: no session")
        return "\n".join(lines)

    # ------------------------------------------------------------------ camera scan

    def _scan_cameras(self) -> None:
        if self._probe_cameras is None:
            return
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning...")
        log.info("Scanning for cameras...")
        probe = self._probe_cameras
        signals = self._probe_signals

        def run() -> None:
            try:
                found = probe()
            except Exception:
                log.exception("Camera scan failed")
                found = []
            signals.finished.emit(found)

        threading.Thread(target=run, name="camera-scan", daemon=True).start()

    def _on_probe_finished(self, cameras: list[CameraInfo]) -> None:
        self.scan_button.setText("Scan")
        self.scan_button.setEnabled(self._camera_state in (CameraState.STOPPED, CameraState.ERROR))
        if not cameras:
            log.warning("No cameras found.")
            return
        selected = self.camera_combo.currentData()
        self.camera_combo.clear()
        for camera in cameras:
            self.camera_combo.addItem(camera.label, camera.index)
        position = self.camera_combo.findData(selected)
        self.camera_combo.setCurrentIndex(max(0, position))
        log.info("Found %d camera(s): %s", len(cameras), ", ".join(c.label for c in cameras))

    # ------------------------------------------------------------------ diagnostics

    def _update_diagnostics(self) -> None:
        with self.stall_monitor.section("diagnostics"):
            self._refresh_diagnostics()

    def _refresh_diagnostics(self) -> None:
        m = self.pipeline.metrics()
        self._tick += 1

        def fmt(value: float | None, unit: str, digits: int = 1) -> str:
            return f"{value:.{digits}f} {unit}" if value is not None else "—"

        live = m.camera_state is CameraState.RUNNING
        self.capture_fps_label.setText(f"CAM {m.capture_fps:4.1f} FPS")
        self.processing_fps_label.setText(f"PROC {m.processing_fps:4.1f} FPS")
        display = self.video.display_rate.rate() if live else 0.0
        self.display_fps_label.setText(f"VIEW {display:4.1f} FPS")
        if live and m.latency_ms is not None:
            self.latency_label.setText(
                f"LATENCY {fmt(m.latency_ms, 'ms')} (p95 {fmt(m.latency_p95_ms, 'ms', 0)})"
            )
        else:
            self.latency_label.setText("LATENCY —")
        self.dropped_label.setText(f"DROPPED {m.frames_dropped}")
        stalls = self.stall_monitor
        self.stalls_label.setText(
            f"UI STALLS {stalls.stall_count}"
            + (f" (max {stalls.max_stall_ms:.0f} ms)" if stalls.stall_count else "")
        )
        if self._tick % 4 == 1:
            sample = self._resources.sample()
            self._last_resource_text = (
                f"CPU {sample.cpu_percent_of_machine:4.1f}%  RAM {sample.rss_mb:.0f} MB"
            )
        self.resources_label.setText(self._last_resource_text)
        self.performance_panel.show_live(m, self.pipeline.gesture_ms_mean if live else None)
        if self.camera_dialog.isVisible():
            if live:
                self.camera_dialog.show_diagnostics(
                    f"Running: {m.capture_fps:.1f} frames per second delivered, "
                    f"processing {m.processing_fps:.1f} per second, latency "
                    f"{fmt(m.latency_ms, 'ms')}."
                )
            else:
                self.camera_dialog.show_diagnostics("Camera off.")

    def _report_stall(self, stall: Stall) -> None:
        # Called on the watchdog thread; logging is thread safe and reaches the UI queued.
        level = logging.WARNING if stall.duration_ms >= 250 else logging.DEBUG
        log.log(level, "%s", stall.summary())

    def _append_log(self, text: str, level: int) -> None:
        color = QColor(_LOG_COLORS.get(level, palette.TEXT_MUTED)).name()
        self.activity_log.appendHtml(f'<span style="color:{color}">{_escape(text)}</span>')

    # ------------------------------------------------------------------ shutdown

    def closeEvent(self, event: QCloseEvent) -> None:
        self.services.dispatcher.emergency_disable()
        self.creator.close()
        self.preview_timer.stop()
        for dialog in self._dialogs.values():
            dialog.close()
        self.camera_dialog.close()
        self.tray.hide()
        if self.segmenter is not None:
            self.segmenter.shutdown()
        if self.face_worker is not None:
            self.face_worker.shutdown()
        self.hotkey.unregister()
        self.status_timer.stop()
        self.diagnostics_timer.stop()
        self.heartbeat_timer.stop()
        self.stall_monitor.stop()
        logging.getLogger("interactive_scrolling").removeHandler(self.log_handler)
        if not self.pipeline.shutdown(timeout_s=5.0):
            log.error("Pipeline did not shut down cleanly.")
        self.services.shutdown()
        event.accept()
        if self._quit_on_close:
            # The overlay and tray must not keep a process alive without its pipeline.
            QCoreApplication.quit()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
