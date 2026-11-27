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
    AVAILABLE_ACTIONS,
    CONFIGURABLE_GESTURES,
    DEFAULT_MAPPING,
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

# (field, label, unit, minimum, maximum, step, tooltip)
TUNABLES = (
    (
        "swipe_min_distance_palms",
        "Swipe distance (up/down)",
        "palm lengths",
        0.3,
        3.0,
        0.05,
        "How far the index fingertip must travel. One palm length is your wrist-to-knuckle "
        "distance, so the value does not depend on how far you sit from the camera.",
    ),
    (
        "swipe_min_speed_palms_s",
        "Swipe speed",
        "palm lengths/s",
        0.5,
        10.0,
        0.1,
        "Minimum peak speed of the fingertip during a swipe.",
    ),
    (
        "swipe_horizontal_distance_palms",
        "Swipe distance (left/right)",
        "palm lengths",
        0.0,
        3.0,
        0.05,
        "Distance for left/right swipes; 0 means the same as up/down.",
    ),
    (
        "fist_swipe_distance_palms",
        "Whole-hand swipe distance",
        "palm lengths",
        0.15,
        3.0,
        0.05,
        "How far the centre of the hand must move when the hand is not pointing (any shape).",
    ),
    (
        "swipe_up_distance_palms",
        "Distance finger up",
        "palm lengths",
        0.0,
        3.0,
        0.05,
        "Set by Quick Calibration; 0 means the shared distance.",
    ),
    (
        "swipe_down_distance_palms",
        "Distance finger down",
        "palm lengths",
        0.0,
        3.0,
        0.05,
        "Set by Quick Calibration; 0 means the shared distance.",
    ),
    (
        "half_heart_hold_s",
        "Half-heart hold",
        "s",
        0.1,
        3.0,
        0.05,
        "How long the half-heart must be held still before it counts.",
    ),
    (
        "stop_hold_s",
        "Stop-pose hold",
        "s",
        0.1,
        3.0,
        0.05,
        "How long the open palm must be held still before it counts.",
    ),
    (
        "cooldown_s",
        "Swipe cooldown",
        "s",
        0.0,
        5.0,
        0.05,
        "Minimum time between two swipes.",
    ),
    (
        "return_window_s",
        "Return-movement window",
        "s",
        0.0,
        3.0,
        0.05,
        "After a swipe, moving the hand back within this time is ignored (it is not read as "
        "the opposite swipe).",
    ),
)
# Physical movement first, content second ("Move finger up -> Next Short"), so a finger
# movement and the direction the feed moves can never be confused.
CONTROL_STYLE_LABELS = (
    ("motion", "Any hand shape (recommended)"),
    ("finger", "Pointing finger only (fewer accidental triggers)"),
)
ENABLES = (
    ("enable_swipe_up", "Move finger up"),
    ("enable_swipe_down", "Move finger down"),
    ("enable_swipe_right", "Move finger to your right"),
    ("enable_swipe_left", "Move finger to your left"),
    ("enable_half_heart", "Half-heart"),
    ("enable_stop", "Open palm (stop)"),
)
CONFIGURABLE_GESTURES_ORDER = (
    GestureType.INDEX_SWIPE_UP,
    GestureType.INDEX_SWIPE_DOWN,
    GestureType.INDEX_SWIPE_RIGHT,
    GestureType.INDEX_SWIPE_LEFT,
    GestureType.HALF_HEART,
    GestureType.STOP_GESTURE,
)
assert set(CONFIGURABLE_GESTURES_ORDER) == set(CONFIGURABLE_GESTURES)
ACTION_ORDER = (
    ActionType.NEXT_SHORT,
    ActionType.PREVIOUS_SHORT,
    ActionType.LIKE_SHORT,
    ActionType.TOGGLE_PLAYBACK,
    ActionType.NEXT_BROWSER_TAB,
    ActionType.PREVIOUS_BROWSER_TAB,
)
assert set(ACTION_ORDER) == set(AVAILABLE_ACTIONS)
PRESETS = (
    SensitivityPreset.HIGH,
    SensitivityPreset.BALANCED,
    SensitivityPreset.LOW,
    SensitivityPreset.PERSONAL,
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
            self.preset.addItem(preset.display, preset)
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
        self.style = QComboBox()
        for key, text in CONTROL_STYLE_LABELS:
            self.style.addItem(text, key)
        self.style.setToolTip(
            "Any hand shape: a pointing finger, a fist, an open or relaxed hand - hold the hand "
            "still for a moment, then move it. Pointing finger only: fewer accidental swipes "
            "while you move your hands for other reasons."
        )
        top.addRow("Swipe with", self.style)
        root.addLayout(top)

        tune_box = QGroupBox("Thresholds")
        tune = QFormLayout(tune_box)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for name, label, unit, low, high, step, tip in TUNABLES:
            spin = QDoubleSpinBox()
            spin.setToolTip(tip)
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(2)
            spin.setSuffix(f"  {unit}")
            spin.valueChanged.connect(self._custom_edit)
            self.spins[name] = spin
            tune.addRow(label, spin)
        root.addWidget(tune_box)

        map_box = QGroupBox("Gestures and actions")
        form = QFormLayout(map_box)
        self.enables: dict[str, QCheckBox] = {}
        self.mapping_boxes: dict[GestureType, QComboBox] = {}
        enable_names = dict(zip(CONFIGURABLE_GESTURES_ORDER, (n for n, _ in ENABLES), strict=True))
        for gesture in CONFIGURABLE_GESTURES_ORDER:
            name = enable_names[gesture]
            box = QCheckBox(dict(ENABLES)[name])
            box.setToolTip("Untick to switch this gesture off.")
            self.enables[name] = box
            combo = QComboBox()
            combo.addItem(ActionType.NONE.label, ActionType.NONE)
            for action in ACTION_ORDER:
                combo.addItem(action.label, action)
            self.mapping_boxes[gesture] = combo
            form.addRow(box, combo)
        note = QLabel(
            "Shorts actions work only on a YouTube Shorts tab; tab actions only while the "
            "browser is the active window. Either hand can be used."
        )
        note.setWordWrap(True)
        note.setObjectName("rowKey")
        form.addRow(note)
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
        index = self.style.findData(settings.control_style)
        self.style.setCurrentIndex(index if index >= 0 else 0)
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
        if preset.keeps_values:
            return
        current = self.result_settings(validate=False)
        base = GestureSettings.from_preset(
            preset,
            control_hand=current.control_hand,
            control_style=current.control_style,
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
        values["control_style"] = self.style.currentData()
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
