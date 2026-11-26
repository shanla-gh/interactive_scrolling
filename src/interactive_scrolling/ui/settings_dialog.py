"""Gesture settings: sensitivity presets, key thresholds, enabled gestures, hand and mapping."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.actions.types import (
    CONFIGURABLE_GESTURES,
    DEFAULT_MAPPING,
    YOUTUBE_ACTIONS,
    ActionType,
    validate_mapping,
)
from interactive_scrolling.config.settings import (
    ConfigError,
    ControlHandPreference,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.types import GestureType

# (field, label, unit, minimum, maximum, step)
TUNABLES = (
    ("finger_swipe_min_distance_palms", "Swipe distance", "palm lengths", 0.3, 3.0, 0.05),
    ("finger_swipe_min_speed_palms_s", "Swipe speed", "palm lengths/s", 0.5, 10.0, 0.1),
    ("hand_sweep_min_distance_palms", "Sweep distance", "palm lengths", 0.5, 5.0, 0.05),
    ("hand_sweep_min_speed_palms_s", "Sweep speed", "palm lengths/s", 0.5, 12.0, 0.1),
    ("thumbs_up_hold_s", "Thumbs-up hold", "s", 0.1, 3.0, 0.05),
    ("stop_hold_s", "Stop-pose hold", "s", 0.1, 3.0, 0.05),
    ("cooldown_s", "Repeat cooldown", "s", 0.0, 5.0, 0.05),
    ("return_window_s", "Return-movement window", "s", 0.0, 3.0, 0.05),
)
ENABLES = (
    ("enable_finger_swipes", "Finger swipes (up / down)"),
    ("enable_hand_sweeps", "Hand sweeps (left / right)"),
    ("enable_thumbs_up", "Thumbs up"),
    ("enable_stop", "Stop gesture"),
)
PRESETS = (
    SensitivityPreset.LOW,
    SensitivityPreset.BALANCED,
    SensitivityPreset.HIGH,
    SensitivityPreset.CUSTOM,
)


class GestureSettingsDialog(QDialog):
    def __init__(
        self,
        settings: GestureSettings,
        mapping: dict[GestureType, ActionType],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gesture settings")
        self.setMinimumWidth(460)
        self._loading = False
        root = QVBoxLayout(self)

        top = QFormLayout()
        self.preset = QComboBox()
        for preset in PRESETS:
            self.preset.addItem(preset.value.capitalize(), preset)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        top.addRow("Sensitivity", self.preset)
        self.hand = QComboBox()
        for preference in ControlHandPreference:
            self.hand.addItem(
                {
                    "auto": "Automatic (first hand alone in view)",
                    "left": "Left hand",
                    "right": "Right hand",
                }[preference.value],
                preference,
            )
        top.addRow("Control hand", self.hand)
        root.addLayout(top)

        tune_box = QGroupBox("Thresholds")
        tune = QFormLayout(tune_box)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for name, label, unit, low, high, step in TUNABLES:
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(2)
            spin.setSuffix(f"  {unit}")
            spin.valueChanged.connect(self._custom_edit)
            self.spins[name] = spin
            tune.addRow(label, spin)
        root.addWidget(tune_box)

        enable_box = QGroupBox("Gestures")
        enable = QVBoxLayout(enable_box)
        self.enables: dict[str, QCheckBox] = {}
        for name, label in ENABLES:
            box = QCheckBox(label)
            self.enables[name] = box
            enable.addWidget(box)
        root.addWidget(enable_box)

        map_box = QGroupBox("Actions")
        form = QFormLayout(map_box)
        self.mapping_boxes: dict[GestureType, QComboBox] = {}
        for gesture in CONFIGURABLE_GESTURES:
            combo = QComboBox()
            combo.addItem(ActionType.NONE.label, ActionType.NONE)
            for action in sorted(YOUTUBE_ACTIONS, key=lambda a: a.value):
                combo.addItem(action.label, action)
            self.mapping_boxes[gesture] = combo
            form.addRow(gesture.label.title(), combo)
        reserved = QLabel("Hand sweeps are reserved for switching apps (planned for M4).")
        reserved.setObjectName("rowKey")
        form.addRow(reserved)
        root.addWidget(map_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self.restore_defaults
        )
        row = QHBoxLayout()
        self.error = QLabel("")
        self.error.setObjectName("rowKey")
        row.addWidget(self.error, 1)
        row.addWidget(buttons)
        root.addLayout(row)
        self.load(settings, mapping)

    # ------------------------------------------------------------------ state

    def load(self, settings: GestureSettings, mapping: dict[GestureType, ActionType]) -> None:
        self._loading = True
        self.preset.setCurrentIndex(PRESETS.index(settings.preset))
        self.hand.setCurrentIndex(list(ControlHandPreference).index(settings.control_hand))
        for name, spin in self.spins.items():
            spin.setValue(getattr(settings, name))
        for name, box in self.enables.items():
            box.setChecked(getattr(settings, name))
        for gesture, combo in self.mapping_boxes.items():
            combo.setCurrentIndex(combo.findData(mapping.get(gesture, ActionType.NONE)))
        self._loading = False

    def restore_defaults(self) -> None:
        self.load(GestureSettings(), DEFAULT_MAPPING)

    def _preset_changed(self) -> None:
        if self._loading:
            return
        preset = self.preset.currentData()
        if preset is SensitivityPreset.CUSTOM:
            return
        current = self.result_settings(validate=False)
        base = GestureSettings.from_preset(
            preset,
            control_hand=current.control_hand,
            **{name: getattr(current, name) for name, _ in ENABLES},
        )
        self.load(base, self.result_mapping())

    def _custom_edit(self) -> None:
        if not self._loading:
            self._loading = True
            self.preset.setCurrentIndex(PRESETS.index(SensitivityPreset.CUSTOM))
            self._loading = False

    def result_settings(self, validate: bool = True) -> GestureSettings:
        values: dict[str, object] = {name: spin.value() for name, spin in self.spins.items()}
        values.update({name: box.isChecked() for name, box in self.enables.items()})
        values["control_hand"] = self.hand.currentData()
        values["preset"] = self.preset.currentData()
        try:
            return replace(GestureSettings(), **values)  # type: ignore[arg-type]
        except ConfigError:
            if validate:
                raise
            return GestureSettings()

    def result_mapping(self) -> dict[GestureType, ActionType]:
        return validate_mapping({g: c.currentData() for g, c in self.mapping_boxes.items()})

    def accept(self) -> None:
        try:
            self.result_settings()
            self.result_mapping()
        except (ConfigError, ValueError) as exc:
            self.error.setText(str(exc))
            return
        super().accept()
