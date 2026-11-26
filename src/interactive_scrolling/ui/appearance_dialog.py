"""Visual customization: skeleton colour, sizes, trails, feedback, telemetry, overlay placement."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.config.settings import (
    AppearanceSettings,
    CreatorSettings,
    OverlayCorner,
)

CORNERS = {
    OverlayCorner.TOP_LEFT: "Top left",
    OverlayCorner.TOP_RIGHT: "Top right",
    OverlayCorner.BOTTOM_LEFT: "Bottom left",
    OverlayCorner.BOTTOM_RIGHT: "Bottom right",
    OverlayCorner.CUSTOM: "Where I dragged it",
}


def _spin(low: float, high: float, step: float, value: float, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setValue(value)
    spin.setSuffix(suffix)
    return spin


class AppearanceDialog(QDialog):
    def __init__(
        self,
        appearance: AppearanceSettings,
        creator: CreatorSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Appearance")
        self.setMinimumWidth(420)
        self._color = appearance.skeleton_color
        root = QVBoxLayout(self)

        style_box = QGroupBox("Skeleton and motion")
        form = QFormLayout(style_box)
        color_row = QWidget()
        row = QHBoxLayout(color_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.auto_color = QCheckBox("Colour by hand")
        self.auto_color.setChecked(appearance.skeleton_color == "auto")
        self.pick = QPushButton("Choose colour...")
        self.pick.clicked.connect(self._choose_color)
        row.addWidget(self.auto_color)
        row.addWidget(self.pick)
        form.addRow("Skeleton colour", color_row)
        self.landmark = _spin(0.3, 3.0, 0.1, appearance.landmark_scale, " x")
        self.line = _spin(0.3, 3.0, 0.1, appearance.line_scale, " x")
        self.trail = _spin(0.1, 3.0, 0.1, appearance.trail_length_s, " s")
        form.addRow("Landmark size", self.landmark)
        form.addRow("Line thickness", self.line)
        form.addRow("Trail length", self.trail)
        self.feedback = QCheckBox("Show gesture feedback on the video")
        self.feedback.setChecked(appearance.show_gesture_feedback)
        self.telemetry = QCheckBox("Show tracking status chips on the video")
        self.telemetry.setChecked(appearance.show_telemetry)
        form.addRow(self.feedback)
        form.addRow(self.telemetry)
        root.addWidget(style_box)

        overlay_box = QGroupBox("Content Creator overlay")
        overlay = QFormLayout(overlay_box)
        self.corner = QComboBox()
        for corner, label in CORNERS.items():
            self.corner.addItem(label, corner)
        self.corner.setCurrentIndex(list(CORNERS).index(creator.corner))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(160, 3840)
        self.width_spin.setValue(creator.width)
        self.width_spin.setSuffix(" px wide (16:9)")
        self.opacity = _spin(0.3, 1.0, 0.05, creator.opacity, "")
        overlay.addRow("Position", self.corner)
        overlay.addRow("Size", self.width_spin)
        overlay.addRow("Opacity", self.opacity)
        root.addWidget(overlay_box)
        self._creator = creator

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _choose_color(self) -> None:
        start = QColor(self._color if self._color != "auto" else "#3dff9a")
        color = QColorDialog.getColor(start, self, "Skeleton colour")
        if color.isValid():
            self._color = color.name()
            self.auto_color.setChecked(False)

    def result_appearance(self) -> AppearanceSettings:
        color = "auto" if self.auto_color.isChecked() or self._color == "auto" else self._color
        return AppearanceSettings(
            skeleton_color=color,
            landmark_scale=round(self.landmark.value(), 2),
            line_scale=round(self.line.value(), 2),
            trail_length_s=round(self.trail.value(), 2),
            show_gesture_feedback=self.feedback.isChecked(),
            show_telemetry=self.telemetry.isChecked(),
        )

    def result_creator(self) -> CreatorSettings:
        width = self.width_spin.value()
        return replace(
            self._creator,
            corner=self.corner.currentData(),
            width=width,
            height=max(90, width * 9 // 16),
            opacity=round(self.opacity.value(), 2),
        )
