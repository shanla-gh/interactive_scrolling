"""Broadcast settings: every option of the Broadcast overlay in one plain dialog.

Brief 008: the Director could not find the transparent background (it was only in the
overlay's right-click menu). It is now the first option here, and this dialog opens from the
top bar's More menu, from a Settings button that appears on the overlay under the mouse, from
the overlay's right-click menu and from the tray. Changes apply immediately.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.config.settings import CreatorSettings, EffectsSettings, OverlayCorner
from interactive_scrolling.visualization.clown import MAX_MAKEUP_OPACITY, MIN_MAKEUP_OPACITY

LAYERS = (
    ("show_skeleton", "Hand skeleton"),
    ("smooth_skeleton", "Smooth skeleton (display only)"),
    ("show_trails", "Motion trails"),
    ("show_vectors", "Motion vectors"),
    ("show_last_gesture", "Last gesture"),
    ("show_outcome", "Action result (and who did it in Doomscroll Together)"),
    ("show_control_state", "Gesture control status"),
    ("show_counters", "Session timer and counters"),
)
SIZES = (320, 480, 640, 960)
CORNERS = (
    (OverlayCorner.BOTTOM_RIGHT, "Bottom right"),
    (OverlayCorner.BOTTOM_LEFT, "Bottom left"),
    (OverlayCorner.TOP_RIGHT, "Top right"),
    (OverlayCorner.TOP_LEFT, "Top left"),
)


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("dimHint")
    label.setWordWrap(True)
    return label


class BroadcastSettingsDialog(QDialog):
    creator_changed = Signal(object)
    """A new :class:`CreatorSettings` (applied immediately by the window)."""
    effects_changed = Signal(object)
    """A new :class:`EffectsSettings` (clown on/off, makeup strength)."""
    corner_requested = Signal(object)
    face_effects_requested = Signal()

    def __init__(
        self,
        current_creator: Callable[[], CreatorSettings],
        effects: EffectsSettings,
        segmentation_available: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Broadcast settings")
        self._current = current_creator
        creator = current_creator()
        self.effects = effects
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        columns = QHBoxLayout()
        columns.setSpacing(28)
        outer.addLayout(columns)
        layout = QVBoxLayout()
        layout.setSpacing(8)
        columns.addLayout(layout, 1)

        layout.addWidget(_heading("Background"))
        self.transparent = QCheckBox("Transparent background")
        self.transparent.setChecked(creator.transparent_background)
        self.transparent.setEnabled(segmentation_available)
        self.transparent.toggled.connect(lambda on: self._set(transparent_background=on))
        layout.addWidget(self.transparent)
        layout.addWidget(
            _hint(
                "Removes the room around you, on this computer. If removal is not possible "
                "for a moment, the camera image is hidden instead of showing the room."
                if segmentation_available
                else "Not available: the person-segmentation model is missing in this installation."
            )
        )

        layout.addSpacing(6)
        layout.addWidget(_heading("Show on the overlay"))
        self.layers: dict[str, QCheckBox] = {}
        for name, label in LAYERS:
            box = QCheckBox(label)
            box.setChecked(bool(getattr(creator, name)))
            box.toggled.connect(lambda on, n=name: self._set(**{n: on}))
            layout.addWidget(box)
            self.layers[name] = box

        layout.addStretch(1)
        layout = QVBoxLayout()
        layout.setSpacing(8)
        columns.addLayout(layout, 1)
        layout.addWidget(_heading("Clown effect"))
        self.clown = QCheckBox("Progressive clown makeup (nose, lips, light white makeup)")
        self.clown.setChecked(effects.clown_enabled)
        self.clown.toggled.connect(lambda on: self._effects(clown_enabled=on))
        layout.addWidget(self.clown)
        makeup = QHBoxLayout()
        makeup.addWidget(QLabel("White makeup"))
        self.makeup = QSlider(Qt.Orientation.Horizontal)
        self.makeup.setRange(int(MIN_MAKEUP_OPACITY * 100), int(MAX_MAKEUP_OPACITY * 100))
        self.makeup.setValue(round(effects.clown_makeup_opacity * 100))
        self.makeup.setToolTip("Strength of the white makeup in the last stage")
        self.makeup.valueChanged.connect(
            lambda v: self._effects(clown_makeup_opacity=round(v / 100, 2))
        )
        makeup.addWidget(self.makeup, 1)
        self.makeup_value = QLabel(f"{self.makeup.value()} %")
        self.makeup.valueChanged.connect(lambda v: self.makeup_value.setText(f"{v} %"))
        makeup.addWidget(self.makeup_value)
        layout.addLayout(makeup)
        preview = QHBoxLayout()
        preview.addWidget(QLabel("Preview stage"))
        self.stage = QComboBox()
        self.stage.addItem("Off (follow the session)", None)
        for stage, text in ((1, "1 - nose"), (2, "2 - nose and lips"), (3, "3 - full makeup")):
            self.stage.addItem(text, stage)
        index = self.stage.findData(effects.clown_preview_stage)
        self.stage.setCurrentIndex(max(0, index))
        self.stage.currentIndexChanged.connect(
            lambda _: self._effects(clown_preview_stage=self.stage.currentData())
        )
        preview.addWidget(self.stage, 1)
        layout.addLayout(preview)
        more = QPushButton("Stage timing and eye analytics...")
        more.setObjectName("flatButton")
        more.clicked.connect(self.face_effects_requested)
        layout.addWidget(more)

        layout.addSpacing(6)
        layout.addWidget(_heading("Window"))
        form = QFormLayout()
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(round(creator.opacity * 100))
        self.opacity.valueChanged.connect(lambda v: self._set(opacity=round(v / 100, 2)))
        form.addRow("Opacity", self.opacity)
        self.size = QComboBox()
        for width in SIZES:
            self.size.addItem(f"{width} x {width * 9 // 16}", width)
        if creator.width not in SIZES:
            self.size.addItem(f"{creator.width} x {creator.height} (custom)", creator.width)
        self.size.setCurrentIndex(self.size.findData(creator.width))
        self.size.activated.connect(self._size)
        form.addRow("Size", self.size)
        self.corner = QComboBox()
        self.corner.addItem("Where I placed it", OverlayCorner.CUSTOM.value)
        for corner, text in CORNERS:
            self.corner.addItem(text, corner.value)
        self.corner.setCurrentIndex(max(0, self.corner.findData(creator.corner.value)))
        self.corner.activated.connect(self._corner)
        form.addRow("Position", self.corner)
        layout.addLayout(form)
        layout.addWidget(
            _hint("Drag the overlay to move it; drag its lower-right corner to resize it.")
        )
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addStretch(1)
        outer.addLayout(row)

    def _set(self, **changes: object) -> None:
        # Always from the overlay's current settings: it may have been moved or resized.
        self.creator_changed.emit(replace(self._current(), **changes))

    def _size(self, _index: int) -> None:
        width = int(self.size.currentData())
        self._set(width=width, height=width * 9 // 16)

    def _effects(self, **changes: object) -> None:
        self.effects = replace(self.effects, **changes)
        self.effects_changed.emit(self.effects)

    def _corner(self, _index: int) -> None:
        corner = OverlayCorner(self.corner.currentData())
        if corner is not OverlayCorner.CUSTOM:
            self.corner_requested.emit(corner)
