"""Main application window."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling import __version__
from interactive_scrolling.config.settings import SUPPORTED_RESOLUTIONS, AppSettings, CameraSettings
from interactive_scrolling.core.diagnostics import ResourceMonitor
from interactive_scrolling.core.pipeline import (
    CameraFactory,
    CameraState,
    TrackerFactory,
    TrackerState,
    VisionPipeline,
)
from interactive_scrolling.ui.bridge import PipelineBridge, QtLogHandler
from interactive_scrolling.ui.panels import MotionPanel, OverlayPanel, TrackingPanel
from interactive_scrolling.ui.video_view import VideoView
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


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        camera_factory: CameraFactory,
        tracker_factory: TrackerFactory | None,
        probe_cameras: ProbeFunction | None = None,
        resource_monitor: ResourceMonitor | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
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
        )

        self.video = VideoView(settings.overlay)
        self.video.set_mirrored(settings.mirror_preview)
        self.video.renderer.trail_duration_s = settings.motion.trail_duration_s
        self.tracking_panel = TrackingPanel()
        self.motion_panel = MotionPanel()
        self.overlay_panel = OverlayPanel(settings.overlay, settings.mirror_preview)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
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

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 4, 0)
        side_layout.setSpacing(12)
        side_layout.addWidget(self.tracking_panel)
        side_layout.addWidget(self.motion_panel)
        side_layout.addWidget(self.overlay_panel)
        side_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(340)
        top_layout.addWidget(scroll)
        splitter.addWidget(top)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(16, 4, 16, 12)
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
        splitter.addWidget(log_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([700, 130])
        return splitter

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

    def _on_mirror_changed(self, mirrored: bool) -> None:
        self.settings.mirror_preview = mirrored
        self.video.set_mirrored(mirrored)
        if self.video.frame is not None:
            self.motion_panel.update_motion(self.video.frame, mirrored)

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
        self.diagnostics_timer.stop()
        logging.getLogger("interactive_scrolling").removeHandler(self.log_handler)
        if not self.pipeline.shutdown(timeout_s=5.0):
            log.error("Pipeline did not shut down cleanly.")
        event.accept()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
