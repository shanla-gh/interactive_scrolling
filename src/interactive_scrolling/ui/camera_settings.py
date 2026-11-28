"""Camera settings: device, resolution, frame rate, mirroring and what the camera view shows.

Opened from the top bar instead of keeping every camera control permanently on screen. The
dialog only edits the request; the camera itself is still started and stopped by the one
pipeline that owns it. Device, resolution and frame rate apply the next time the camera starts
(they are locked while it runs, as before).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.config.settings import SUPPORTED_RESOLUTIONS, CameraSettings
from interactive_scrolling.ui.panels import OverlayPanel

FRAME_RATES = (15, 30, 60)


class CameraSettingsDialog(QDialog):
    def __init__(
        self,
        camera: CameraSettings,
        overlay_panel: OverlayPanel,
        can_scan: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Camera settings")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        device = QWidget()
        row = QHBoxLayout(device)
        row.setContentsMargins(0, 0, 0, 0)
        self.camera_combo = QComboBox()
        self.camera_combo.setToolTip("Camera device")
        for index in range(4):
            self.camera_combo.addItem(f"Camera {index}", index)
        self.camera_combo.setCurrentIndex(max(0, self.camera_combo.findData(camera.index)))
        row.addWidget(self.camera_combo, 1)
        self.scan_button = QPushButton("Scan")
        self.scan_button.setToolTip("Detect available cameras (briefly opens each device)")
        self.scan_button.setEnabled(can_scan)
        row.addWidget(self.scan_button)
        form.addRow("Camera", device)

        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip("Requested capture resolution")
        for width, height in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{width}x{height}", (width, height))
        # QComboBox.findData() cannot match Python tuples, so select by list position.
        current = (camera.width, camera.height)
        if current not in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{current[0]}x{current[1]}", current)
            self.resolution_combo.setCurrentIndex(self.resolution_combo.count() - 1)
        else:
            self.resolution_combo.setCurrentIndex(SUPPORTED_RESOLUTIONS.index(current))
        form.addRow("Resolution", self.resolution_combo)

        self.fps_combo = QComboBox()
        self.fps_combo.setToolTip(
            "Requested frame rate. Many webcams deliver 30 frames per second whatever is "
            "requested; the delivered rate is shown below while the camera runs."
        )
        rates = sorted(set(FRAME_RATES) | {camera.fps})
        for fps in rates:
            self.fps_combo.addItem(f"{fps} fps", fps)
        self.fps_combo.setCurrentIndex(rates.index(camera.fps))
        form.addRow("Frame rate", self.fps_combo)
        layout.addLayout(form)

        self.locked_note = QLabel("Stop the camera to change these.")
        self.locked_note.setObjectName("dimHint")
        layout.addWidget(self.locked_note)

        self.overlay_panel = overlay_panel
        layout.addWidget(overlay_panel)
        self.appearance_button = QPushButton("Colours and sizes...")
        self.appearance_button.setObjectName("flatButton")
        self.appearance_button.setToolTip("Skeleton colour, sizes, trails, Broadcast overlay")
        layout.addWidget(self.appearance_button)

        self.diagnostics = QLabel("Camera off")
        self.diagnostics.setObjectName("dimHint")
        self.diagnostics.setWordWrap(True)
        layout.addWidget(self.diagnostics)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def set_idle(self, idle: bool, can_scan: bool) -> None:
        for widget in (self.camera_combo, self.resolution_combo, self.fps_combo):
            widget.setEnabled(idle)
        self.scan_button.setEnabled(idle and can_scan)
        self.locked_note.setVisible(not idle)

    def show_diagnostics(self, text: str) -> None:
        self.diagnostics.setText(text)
