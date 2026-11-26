"""Main application window."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

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
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import (
    CameraFactory,
    CameraState,
    TrackerFactory,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.gestures.types import GestureEvent
from interactive_scrolling.services import ControlServices, offline_services
from interactive_scrolling.ui.bridge import PipelineBridge, QtLogHandler
from interactive_scrolling.ui.control_bar import ControlBar
from interactive_scrolling.ui.gesture_panels import GestureHistory, GesturePanel
from interactive_scrolling.ui.hotkey import GlobalHotkey
from interactive_scrolling.ui.panels import MotionPanel, OverlayPanel, TrackingPanel
from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog
from interactive_scrolling.ui.video_view import VideoView
from interactive_scrolling.ui.youtube_panel import StatsPanel, YouTubePanel
from interactive_scrolling.vision.camera import CameraInfo
from interactive_scrolling.visualization import palette

log = logging.getLogger(__name__)

ProbeFunction = Callable[[], list[CameraInfo]]

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
    ) -> None:
        super().__init__()
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

        self.bridge = PipelineBridge(self)
        self.pipeline = VisionPipeline(
            listener=self.bridge,
            camera_factory=camera_factory,
            tracker_factory=tracker_factory,
            motion_settings=settings.motion,
            inference_max_width=settings.tracking.inference_max_width,
            gesture_engine=self.services.engine,
            on_gesture_event=self._on_gesture_event,
        )

        self.video = VideoView(settings.overlay)
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
        self.stats_panel = StatsPanel(user.analytics_enabled)

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
        self.stats_panel.enabled_changed.connect(self.services.set_analytics_enabled)
        self.stats_panel.clear_requested.connect(self._clear_statistics)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.emergency_disable)
        self.hotkey = GlobalHotkey(self.emergency_disable)
        if register_hotkey and self.hotkey.register():
            QCoreApplication.instance().installNativeEventFilter(self.hotkey)
        self.control_bar.set_hotkey_hint(self.hotkey.label)

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
            ("YouTube", [self.youtube_panel, self.stats_panel]),
            ("Tracking", [self.tracking_panel, self.motion_panel]),
            ("View", [self.overlay_panel]),
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
        for label, tip in (
            (self.capture_fps_label, "Frames per second delivered by the camera"),
            (self.processing_fps_label, "Frames per second through inference and motion analysis"),
            (self.display_fps_label, "Frames per second painted on screen"),
            (self.latency_label, "Capture-to-result processing latency: mean / 95th percentile"),
            (self.dropped_label, "Outdated frames skipped so latency cannot accumulate"),
            (self.resources_label, "Process CPU (share of all logical cores) and resident memory"),
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
        elif state is CameraState.STOPPED:
            log.info(message)
            self.video.clear("Camera is off. Press Start camera to begin.")
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
        frame = self.bridge.take_latest()
        if frame is None:
            return
        # Discard frames from a stopped session so no stale image or landmarks remain.
        if frame.session != self._session or self._camera_state is not CameraState.RUNNING:
            return
        self.video.set_frame(frame)
        self.tracking_panel.update_tracking(frame.tracking)
        self.motion_panel.update_motion(frame, self.video.mirrored)
        enabled = self.services.dispatcher.mode is not ControlMode.TRACKING_ONLY
        self.gesture_panel.show_frame(frame.gestures, enabled)

    def _on_mirror_changed(self, mirrored: bool) -> None:
        self.settings.mirror_preview = mirrored
        self.video.set_mirrored(mirrored)
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
        if new is ControlMode.TRACKING_ONLY:
            self.gesture_panel.show_frame(None, enabled=False)
        if new is ControlMode.LIVE_CONTROL:
            log.warning("LIVE CONTROL enabled: confirmed gestures will control YouTube Shorts.")

    def _on_gesture_event(self, event: GestureEvent) -> None:
        # Called on the processing thread; submitting never blocks.
        self.services.dispatcher.submit(event)

    def _on_record(self, record: ActionRecord) -> None:
        first = self.history.outcome_of(record.record_id) is None
        self.history.update_record(record)
        self.gesture_panel.show_record(record)
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
            log.info("Local statistics cleared.")
        self._stats_tick = 0
        self._update_control_status()

    def _update_control_status(self) -> None:
        controller = self.services.controller
        status = controller.status() if controller is not None else None
        self.youtube_panel.show_status(status)
        if status is None:
            self.control_bar.set_youtube("YouTube: not available", False)
        elif status.ready:
            self.control_bar.set_youtube(f"YouTube: ready ({status.target_browser})", True)
        else:
            self.control_bar.set_youtube(f"YouTube: {status.reason}", False)
        analytics = self.services.analytics
        if analytics is not None and self._stats_tick % 4 == 0:
            self.stats_panel.show_stats(analytics.daily_stats(), analytics.error)
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
        if self._tick % 4 == 1:
            sample = self._resources.sample()
            self._last_resource_text = (
                f"CPU {sample.cpu_percent_of_machine:4.1f}%  RAM {sample.rss_mb:.0f} MB"
            )
        self.resources_label.setText(self._last_resource_text)

    def _append_log(self, text: str, level: int) -> None:
        color = QColor(_LOG_COLORS.get(level, palette.TEXT_MUTED)).name()
        self.activity_log.appendHtml(f'<span style="color:{color}">{_escape(text)}</span>')

    # ------------------------------------------------------------------ shutdown

    def closeEvent(self, event: QCloseEvent) -> None:
        self.services.dispatcher.emergency_disable()
        self.hotkey.unregister()
        self.status_timer.stop()
        self.diagnostics_timer.stop()
        logging.getLogger("interactive_scrolling").removeHandler(self.log_handler)
        if not self.pipeline.shutdown(timeout_s=5.0):
            log.error("Pipeline did not shut down cleanly.")
        self.services.shutdown()
        event.accept()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
