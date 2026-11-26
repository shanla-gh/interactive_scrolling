"""Main application window."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling import __version__
from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ControlMode
from interactive_scrolling.config.settings import SUPPORTED_RESOLUTIONS, AppSettings, CameraSettings
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
from interactive_scrolling.gestures.types import GestureEvent
from interactive_scrolling.services import ControlServices, offline_services
from interactive_scrolling.ui.appearance_dialog import AppearanceDialog
from interactive_scrolling.ui.bridge import PipelineBridge, QtLogHandler
from interactive_scrolling.ui.control_bar import ControlBar
from interactive_scrolling.ui.creator_overlay import CreatorOverlay
from interactive_scrolling.ui.effects_panel import (
    CalibrationDialog,
    EffectsDialog,
    VisualBehaviorPanel,
)
from interactive_scrolling.ui.gesture_panels import GestureHistory, GesturePanel
from interactive_scrolling.ui.hotkey import GlobalHotkey
from interactive_scrolling.ui.panels import MotionPanel, OverlayPanel, TrackingPanel
from interactive_scrolling.ui.report_panels import (
    DailyReportPanel,
    PerformancePanel,
    WellbeingDialog,
)
from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog
from interactive_scrolling.ui.tray import TrayController
from interactive_scrolling.ui.video_view import VideoView
from interactive_scrolling.ui.youtube_panel import YouTubePanel
from interactive_scrolling.vision.camera import CameraInfo
from interactive_scrolling.vision.compositing import MaskCompositor
from interactive_scrolling.visualization import palette
from interactive_scrolling.visualization.clown import ClownEffect, clown_stage

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

        self.setWindowTitle("interactive_scrolling")
        self.resize(1360, 860)
        self.setMinimumSize(980, 640)

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
        self.video.extra_painters.append(self._paint_clown)
        self.creator.extra_painters.append(self._paint_clown)
        self._update_face_worker()
        self.video.set_mirrored(settings.mirror_preview)
        self.video.renderer.trail_duration_s = settings.motion.trail_duration_s
        self.tracking_panel = TrackingPanel()
        self.motion_panel = MotionPanel()
        self.overlay_panel = OverlayPanel(settings.overlay, settings.mirror_preview)
        self.control_bar = ControlBar()
        self.gesture_panel = GesturePanel()
        self.history = GestureHistory()
        user = self.services.user_settings
        self.youtube_panel = YouTubePanel(user.pairing_token, user.bridge_port)
        self.today_panel = DailyReportPanel(user.analytics_enabled)
        self.performance_panel = PerformancePanel()
        self.visual_panel = VisualBehaviorPanel()
        self.visual_panel.calibrate_requested.connect(self.calibrate_eyes)
        self.visual_panel.settings_requested.connect(self.open_effects)
        self.appearance_button = QPushButton("Appearance...")
        self.appearance_button.setToolTip("Skeleton colour, sizes, trails, overlay position")
        self.appearance_button.clicked.connect(self.open_appearance)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self.control_bar)
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_status_bar())
        self.setCentralWidget(central)

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
        self.control_bar.mode_requested.connect(self.set_control_mode)
        self.control_bar.disable_requested.connect(self.emergency_disable)
        self.gesture_panel.settings_requested.connect(self.open_gesture_settings)
        self.today_panel.enabled_changed.connect(self.services.set_analytics_enabled)
        self.today_panel.clear_requested.connect(self._clear_statistics)
        self.today_panel.pause_toggled.connect(self.services.pause_scrolling)
        self.today_panel.settings_requested.connect(self.open_wellbeing)
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

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setSpacing(0)
        for text, name in (("interactive", "appTitle"), ("_scrolling", "appTitleAccent")):
            label = QLabel(text)
            label.setObjectName(name)
            title_row.addWidget(label)
        title_row.addStretch(1)
        titles.addLayout(title_row)
        subtitle = QLabel(f"Real-time gesture interaction  ·  v{__version__}")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)

        self.status_pill = QLabel("CAMERA OFF")
        self.status_pill.setObjectName("statusPill")
        layout.addWidget(self.status_pill)

        self.camera_combo = QComboBox()
        self.camera_combo.setToolTip("Camera device")
        for index in range(4):
            self.camera_combo.addItem(f"Camera {index}", index)
        self.camera_combo.setCurrentIndex(
            max(0, self.camera_combo.findData(self.settings.camera.index))
        )
        layout.addWidget(self.camera_combo)

        self.scan_button = QPushButton("Scan")
        self.scan_button.setToolTip("Detect available cameras (briefly opens each device)")
        self.scan_button.clicked.connect(self._scan_cameras)
        self.scan_button.setEnabled(self._probe_cameras is not None)
        layout.addWidget(self.scan_button)

        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip("Requested capture resolution")
        for width, height in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{width}x{height}", (width, height))
        # QComboBox.findData() cannot match Python tuples, so select by list position.
        current = (self.settings.camera.width, self.settings.camera.height)
        if current not in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{current[0]}x{current[1]}", current)
            self.resolution_combo.setCurrentIndex(self.resolution_combo.count() - 1)
        else:
            self.resolution_combo.setCurrentIndex(SUPPORTED_RESOLUTIONS.index(current))
        layout.addWidget(self.resolution_combo)

        self.creator_button = QPushButton("Creator overlay")
        self.creator_button.setToolTip(
            "Compact always-on-top camera overlay for streaming and recording (OBS)"
        )
        self.creator_button.clicked.connect(lambda: self.set_ui_mode("creator"))
        layout.addWidget(self.creator_button)
        self.tray_button = QPushButton("To tray")
        self.tray_button.setToolTip(
            "Hide the windows; the tray icon keeps showing camera and control status"
        )
        self.tray_button.clicked.connect(lambda: self.set_ui_mode("background"))
        layout.addWidget(self.tray_button)

        self.start_button = QPushButton("Start camera")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(130)
        self.start_button.clicked.connect(self._toggle_camera)
        layout.addWidget(self.start_button)
        return header

    def _build_body(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 16, 16, 8)
        top_layout.setSpacing(16)
        top_layout.addWidget(self.video, 1)

        self.side_tabs = QTabWidget()
        self.side_tabs.setObjectName("sideTabs")
        self.side_tabs.setFixedWidth(360)
        for title, panels in (
            ("Gestures", [self.gesture_panel]),
            ("Today", [self.today_panel, self.visual_panel]),
            ("Browser", [self.youtube_panel]),
            ("Performance", [self.performance_panel, self.tracking_panel, self.motion_panel]),
            ("View", [self.overlay_panel, self.appearance_button]),
        ):
            self.side_tabs.addTab(self._scroll_page(panels), title)
        top_layout.addWidget(self.side_tabs)
        splitter.addWidget(top)

        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.setChildrenCollapsible(False)
        history_container = QWidget()
        history_layout = QVBoxLayout(history_container)
        history_layout.setContentsMargins(16, 4, 8, 12)
        history_layout.setSpacing(6)
        history_heading = QLabel("GESTURE HISTORY")
        history_heading.setObjectName("cardTitle")
        history_layout.addWidget(history_heading)
        history_layout.addWidget(self.history)
        bottom.addWidget(history_container)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(8, 4, 16, 12)
        log_layout.setSpacing(6)
        heading = QLabel("LIVE ACTIVITY  /  DIAGNOSTICS")
        heading.setObjectName("cardTitle")
        log_layout.addWidget(heading)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setObjectName("activityLog")
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumBlockCount(500)
        self.activity_log.setMinimumHeight(60)
        log_layout.addWidget(self.activity_log)
        bottom.addWidget(log_container)
        bottom.setSizes([560, 560])
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([640, 170])
        return splitter

    @staticmethod
    def _scroll_page(panels: list[QWidget]) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 4, 0)
        layout.setSpacing(12)
        for panel in panels:
            layout.addWidget(panel)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("statusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(22)
        self.capture_fps_label = QLabel()
        self.processing_fps_label = QLabel()
        self.display_fps_label = QLabel()
        self.latency_label = QLabel()
        self.dropped_label = QLabel()
        self.resources_label = QLabel()
        self.stalls_label = QLabel()
        for label, tip in (
            (self.capture_fps_label, "Frames per second delivered by the camera"),
            (self.processing_fps_label, "Frames per second through inference and motion analysis"),
            (self.display_fps_label, "Frames per second painted on screen"),
            (self.latency_label, "Capture-to-result processing latency: mean / 95th percentile"),
            (self.dropped_label, "Outdated frames skipped so latency cannot accumulate"),
            (self.resources_label, "Process CPU (share of all logical cores) and resident memory"),
            (
                self.stalls_label,
                f"Times the window did not respond for more than "
                f"{self.stall_monitor.threshold_ms:.0f} ms (measured by a watchdog thread)",
            ),
        ):
            label.setToolTip(tip)
            layout.addWidget(label)
        layout.addStretch(1)
        privacy = QLabel("● LOCAL PROCESSING · NO FRAMES LEAVE THIS DEVICE")
        privacy.setObjectName("privacyBadge")
        layout.addWidget(privacy)
        return bar

    # ------------------------------------------------------------------ camera control

    def requested_camera_settings(self) -> CameraSettings:
        width, height = self.resolution_combo.currentData()
        base = self.settings.camera
        return CameraSettings(
            index=int(self.camera_combo.currentData()),
            width=width,
            height=height,
            fps=base.fps,
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
            self.video.clear("Camera is off. Press Start camera to begin.")
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
                CameraState.STOPPED: "CAMERA OFF",
                CameraState.STARTING: "STARTING",
                CameraState.RUNNING: "● LIVE",
                CameraState.STOPPING: "STOPPING",
                CameraState.ERROR: "CAMERA ERROR",
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
        self.camera_combo.setEnabled(idle)
        self.resolution_combo.setEnabled(idle)
        self.scan_button.setEnabled(idle and self._probe_cameras is not None)
        for widget in (self.status_pill, self.start_button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
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
            self.video.show_gesture(record.event.gesture.label)
        if record.status.final or record.status is ActionStatus.DISPATCHED:
            self.control_bar.set_last(
                f"{record.event.gesture.label} \u2192 {record.action.label}: {record.status.value}"
            )
            if record.status.final and record.status is not ActionStatus.NOT_EXECUTED:
                log.info(
                    "%s -> %s: %s%s",
                    record.event.gesture.label,
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
            self.face_worker.set_enabled(effects.clown_enabled or effects.eye_analytics_enabled)
        if not effects.clown_enabled:
            self.clown.reset()

    def clown_stage(self) -> int:
        effects = self.services.user_settings.effects
        if effects.clown_preview_stage is not None:
            return effects.clown_preview_stage
        return clown_stage(self.services.current_session_s(), effects.clown_thresholds)

    def _update_clown(self, frame) -> None:  # type: ignore[no-untyped-def]
        if not self.services.user_settings.effects.clown_enabled or self.face_worker is None:
            return
        result = self.face_worker.latest()
        face = None
        if result is not None and MaskCompositor.usable(
            result.timestamp_ns, result.session, frame.capture_ns, frame.session
        ):
            face = result.value
        self.clown.update(
            face.landmarks if face is not None else None, frame.capture_ns, self.clown_stage()
        )

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
        if status is None:
            self.control_bar.set_youtube("YouTube: not available", False)
        elif status.ready:
            self.control_bar.set_youtube(f"YouTube: ready ({status.target_browser})", True)
        else:
            self.control_bar.set_youtube(f"YouTube: {status.reason}", False)
        # Reports are computed on the services' activity thread; the UI only displays them.
        services = self.services
        analytics = services.analytics
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
        effects = services.user_settings.effects
        self.visual_panel.show_report(
            effects.eye_analytics_enabled,
            effects.eye_baseline_yaw is not None,
            services.eye_report,
        )
        self._stats_tick += 1

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
        self.capture_fps_label.setText(f"CAPTURE {m.capture_fps:4.1f} FPS")
        self.processing_fps_label.setText(f"PROCESSING {m.processing_fps:4.1f} FPS")
        display = self.video.display_rate.rate() if live else 0.0
        self.display_fps_label.setText(f"DISPLAY {display:4.1f} FPS")
        if live and m.latency_ms is not None:
            self.latency_label.setText(
                f"LATENCY {fmt(m.latency_ms, 'ms')} / p95 {fmt(m.latency_p95_ms, 'ms')}"
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
