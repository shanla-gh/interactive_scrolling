"""Unified Settings (Brief 010): every feature option in one window with a page list.

Pages: General, Appearance, Camera, Gestures, Eye tracking, Visual effects, Broadcast, Browser,
Doomscroll Together, Analytics & Wrapped, Privacy & system. The main window keeps only
time-critical controls (camera, gesture control, emergency stop, Host / Join); its quick
buttons open the matching page here.

Each option writes to the one authoritative store (``ControlServices.user_settings``) through
the window, immediately: theme and visual options apply at once without touching the camera,
models, gesture control, browser capture or a Doomscroll Together session. Only gesture
recognition settings use Apply (they are validated together). Camera device, resolution and
frame rate apply the next time the camera starts, which the page says.

A page re-reads the current settings whenever it is shown, so options that also exist as
shortcuts (theme in the top bar, layers in the camera panel, the overlay's own menu) always
show the current value.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling import __version__
from interactive_scrolling.config.settings import (
    SUPPORTED_RESOLUTIONS,
    AppearanceSettings,
    CameraSettings,
    ConfigError,
    CreatorSettings,
    EffectsSettings,
    OverlayCorner,
    TogetherSettings,
    WellbeingSettings,
)
from interactive_scrolling.ui.control_bar import SegmentedControl
from interactive_scrolling.ui.settings_dialog import GestureSettingsDialog
from interactive_scrolling.ui.youtube_panel import EXTENSION_DIR
from interactive_scrolling.visualization.clown import MAX_MAKEUP_OPACITY, MIN_MAKEUP_OPACITY

if TYPE_CHECKING:
    from interactive_scrolling.ui.main_window import MainWindow

PAGES: tuple[tuple[str, str], ...] = (
    ("general", "General"),
    ("appearance", "Appearance"),
    ("camera", "Camera"),
    ("gestures", "Gestures"),
    ("eyes", "Eye tracking"),
    ("effects", "Visual effects"),
    ("broadcast", "Broadcast"),
    ("browser", "Browser"),
    ("together", "Doomscroll Together"),
    ("analytics", "Analytics & Wrapped"),
    ("privacy", "Privacy & system"),
)
THEME_OPTIONS = (
    ("black", "Black", "Dark theme"),
    ("white", "White", "Light theme"),
    ("gray", "Gray", "Neutral gray theme"),
)
FRAME_RATES = (15, 30, 60)
BROADCAST_LAYERS = (
    ("show_skeleton", "Hand skeleton"),
    ("smooth_skeleton", "Smooth skeleton (display only)"),
    ("show_trails", "Motion trails"),
    ("show_vectors", "Motion vectors"),
    ("show_last_gesture", "Last gesture"),
    ("show_outcome", "Action result (and who did it in Doomscroll Together)"),
    ("show_control_state", "Gesture control status"),
    ("show_counters", "Session timer and counters"),
)
OVERLAY_SIZES = (320, 480, 640, 960)
OVERLAY_CORNERS = (
    (OverlayCorner.BOTTOM_RIGHT, "Bottom right"),
    (OverlayCorner.BOTTOM_LEFT, "Bottom left"),
    (OverlayCorner.TOP_RIGHT, "Top right"),
    (OverlayCorner.TOP_LEFT, "Top left"),
)


# ---------------------------------------------------------------------- building blocks


def hint(text: str, dim: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName("dimHint" if dim else "hint")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def link(text: str, slot: Callable[[], object], tip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("linkButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    button.clicked.connect(lambda _=False: slot())
    return button


def button(text: str, slot: Callable[[], object], tip: str = "") -> QPushButton:
    widget = QPushButton(text)
    if tip:
        widget.setToolTip(tip)
    widget.clicked.connect(lambda _=False: slot())
    return widget


def spin(low: float, high: float, step: float, decimals: int, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


class Page(QScrollArea):
    """One settings page: a title, an optional introduction and sections, scrollable."""

    def __init__(self, title: str, intro: str = "") -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(28, 22, 28, 22)
        self.body.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("settingsPageTitle")
        self.body.addWidget(label)
        if intro:
            self.body.addWidget(hint(intro))
        self.setWidget(content)
        self._end = False

    def section(self, title: str) -> QVBoxLayout:
        self.body.addSpacing(12)
        self.body.addWidget(heading(title))
        layout = QVBoxLayout()
        layout.setSpacing(7)
        self.body.addLayout(layout)
        return layout

    def finish(self) -> None:
        if not self._end:
            self.body.addStretch(1)
            self._end = True

    def load(self) -> None:
        """Re-read the current settings into the widgets (signals blocked)."""


def form() -> QFormLayout:
    layout = QFormLayout()
    layout.setHorizontalSpacing(16)
    layout.setVerticalSpacing(8)
    layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return layout


def set_checked(box: QCheckBox, value: bool) -> None:
    with QSignalBlocker(box):
        box.setChecked(value)


# ---------------------------------------------------------------------- camera form


class CameraSettingsForm(QWidget):
    """Device, resolution and frame-rate request; the window owns it from the start (the
    camera is started from the top bar with these values)."""

    def __init__(self, camera: CameraSettings, can_scan: bool, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        rows = form()
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
        rows.addRow("Camera", device)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip("Requested capture resolution")
        for width, height in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{width}x{height}", (width, height))
        current = (camera.width, camera.height)
        # QComboBox.findData() cannot match Python tuples, so select by list position.
        if current not in SUPPORTED_RESOLUTIONS:
            self.resolution_combo.addItem(f"{current[0]}x{current[1]}", current)
            self.resolution_combo.setCurrentIndex(self.resolution_combo.count() - 1)
        else:
            self.resolution_combo.setCurrentIndex(SUPPORTED_RESOLUTIONS.index(current))
        rows.addRow("Resolution", self.resolution_combo)
        self.fps_combo = QComboBox()
        self.fps_combo.setToolTip(
            "Requested frame rate. Many webcams deliver 30 frames per second whatever is "
            "requested; the delivered rate is measured while the camera runs."
        )
        rates = sorted(set(FRAME_RATES) | {camera.fps})
        for fps in rates:
            self.fps_combo.addItem(f"{fps} fps", fps)
        self.fps_combo.setCurrentIndex(rates.index(camera.fps))
        rows.addRow("Requested frame rate", self.fps_combo)
        self.measured = QLabel("Camera off")
        self.measured.setObjectName("sectionValue")
        rows.addRow("Measured", self.measured)
        layout.addLayout(rows)
        self.locked_note = hint("Stop the camera to change the device, resolution or frame rate.")
        self.locked_note.setVisible(False)
        layout.addWidget(self.locked_note)
        self.diagnostics = hint("", dim=True)
        layout.addWidget(self.diagnostics)

    def set_idle(self, idle: bool, can_scan: bool) -> None:
        for widget in (self.camera_combo, self.resolution_combo, self.fps_combo):
            widget.setEnabled(idle)
        self.scan_button.setEnabled(idle and can_scan)
        self.locked_note.setVisible(not idle)

    def show_measured(self, text: str, detail: str = "") -> None:
        self.measured.setText(text)
        self.diagnostics.setText(detail)
        self.diagnostics.setVisible(bool(detail))

    def show_diagnostics(self, text: str) -> None:  # compatibility with the old dialog
        self.diagnostics.setText(text)


# ---------------------------------------------------------------------- the window


class SettingsWindow(QDialog):
    def __init__(self, window: MainWindow) -> None:
        # A window of its own (no parent): restyling it is then separate from the main window
        # (see theme.set_theme), and it can sit next to the main window.
        super().__init__(None)
        self.window_ = window
        self.setWindowTitle("Settings - Interactive Scrolling")
        self.setObjectName("settingsWindow")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("settingsNav")
        self.nav.setFixedWidth(196)
        self.stack = QStackedWidget()
        self.pages: dict[str, Page] = {}
        builders = {
            "general": self._general,
            "appearance": self._appearance,
            "camera": self._camera,
            "gestures": self._gestures,
            "eyes": self._eyes,
            "effects": self._effects,
            "broadcast": self._broadcast,
            "browser": self._browser,
            "together": self._together,
            "analytics": self._analytics,
            "privacy": self._privacy,
        }
        for key, title in PAGES:
            self.nav.addItem(title)
            page = builders[key](title)
            page.finish()
            self.pages[key] = page
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._show_row)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.stack, 1)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(28, 8, 20, 14)
        saved = hint("Changes are saved immediately.", dim=True)
        saved.setWordWrap(False)
        bottom.addWidget(saved)
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        right.addLayout(bottom)
        root.addWidget(self.nav)
        root.addLayout(right, 1)
        self.nav.setCurrentRow(0)
        self.resize(900, 640)

    # ------------------------------------------------------------------ navigation

    @property
    def current_key(self) -> str:
        return PAGES[max(0, self.nav.currentRow())][0]

    def open_page(self, key: str) -> None:
        keys = [k for k, _ in PAGES]
        row = keys.index(key) if key in keys else 0
        if self.nav.currentRow() != row:
            self.nav.setCurrentRow(row)
        else:
            self.pages[key].load()
        self.fit_to_screen()
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_row(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        self.pages[PAGES[row][0]].load()

    def refresh(self) -> None:
        """Re-read the visible page (a shortcut elsewhere changed a setting)."""
        if self.isVisible():
            self.pages[self.current_key].load()

    def fit_to_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(900, area.width() - 40)
        height = min(640, area.height() - 40)
        self.resize(max(560, width), max(380, height))

    # ------------------------------------------------------------------ helpers

    @property
    def services(self):  # type: ignore[no-untyped-def]
        return self.window_.services

    @property
    def user(self):  # type: ignore[no-untyped-def]
        return self.window_.services.user_settings

    def _appearance_change(self, **changes: object) -> None:
        self.window_.apply_appearance(replace(self.user.appearance, **changes))

    def _effects_change(self, **changes: object) -> bool:
        try:
            effects = replace(self.user.effects, **changes)
        except ConfigError as exc:
            self.window_.show_notice(str(exc))
            return False
        self.window_.apply_effects(effects)
        return True

    def _creator_change(self, **changes: object) -> None:
        self.window_.apply_creator(replace(self.window_.creator.settings, **changes))

    # ------------------------------------------------------------------ pages

    def _general(self, title: str) -> Page:
        page = Page(title)
        w = self.window_
        layout = page.section("Start")
        self.show_guide = QCheckBox("Show the getting started guide when the app starts")
        self.show_guide.toggled.connect(
            lambda on: self._appearance_change(getting_started_done=not on)
        )
        layout.addWidget(self.show_guide)
        layout.addWidget(link("Open the getting started guide", w.open_getting_started))

        layout = page.section("Background mode")
        layout.addWidget(
            hint(
                "Hide every window and keep running from the system tray: the camera, gesture "
                "control and browser connection stay as they are. Open the app again from the "
                "tray icon."
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Run in the background now", lambda: w.set_ui_mode("background")))
        row.addStretch(1)
        layout.addLayout(row)

        layout = page.section("Emergency stop")
        self.hotkey_note = hint("")
        layout.addWidget(self.hotkey_note)

        layout = page.section("About")
        layout.addWidget(
            hint(
                f"Interactive Scrolling {__version__} (beta). Not a stable release. All camera "
                "processing runs on this computer."
            )
        )

        def load() -> None:
            set_checked(self.show_guide, not self.user.appearance.getting_started_done)
            label = w.hotkey.label
            self.hotkey_note.setText(
                "Stop gesture control at any time with the Stop button under the camera, "
                "Esc while this app is in front"
                + (f", or {label} from any window." if label else ".")
                + " It works whatever the eye or face features are doing."
            )

        page.load = load  # type: ignore[method-assign]
        return page

    def _appearance(self, title: str) -> Page:
        page = Page(
            title,
            "Themes change the application around your camera and the Short. The camera "
            "image, the Short and the transparent Broadcast background are never tinted.",
        )
        w = self.window_
        layout = page.section("Theme")
        self.theme = SegmentedControl(list(THEME_OPTIONS))
        self.theme.selected.connect(lambda name: w.set_theme(str(name)))
        row = QHBoxLayout()
        row.addWidget(self.theme)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(hint("The same choice as Black | White | Gray in the top bar.", True))

        layout = page.section("Workspace")
        self.session_expanded = QCheckBox("Show the Your session panel (otherwise a narrow strip)")
        self.session_expanded.toggled.connect(w.set_session_panel_expanded)
        self.console_expanded = QCheckBox("Show diagnostics expanded")
        self.console_expanded.toggled.connect(w.set_console_expanded)
        self.focus = QCheckBox("Focus view: only the camera, the Short and gesture control")
        self.focus.toggled.connect(w.set_focus_view)
        for box in (self.session_expanded, self.console_expanded, self.focus):
            layout.addWidget(box)
        row = QHBoxLayout()
        row.addWidget(
            button(
                "Restore the default layout",
                w.reset_layout,
                "Default panel widths, Your session expanded, diagnostics collapsed",
            )
        )
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(hint("Drag the lines between the panels to resize them.", True))

        layout = page.section("On the camera image")
        self.feedback = QCheckBox("Show the recognized gesture and its result on the camera image")
        self.feedback.toggled.connect(lambda on: self._appearance_change(show_gesture_feedback=on))
        layout.addWidget(self.feedback)

        def load() -> None:
            a = self.user.appearance
            with QSignalBlocker(self.theme):
                self.theme.set_value(a.theme)
            set_checked(self.session_expanded, a.session_panel_expanded)
            set_checked(self.console_expanded, a.console_expanded)
            set_checked(self.focus, a.focus_view)
            set_checked(self.feedback, a.show_gesture_feedback)

        page.load = load  # type: ignore[method-assign]
        return page

    def _camera(self, title: str) -> Page:
        page = Page(title)
        w = self.window_
        layout = page.section("Device")
        layout.addWidget(w.camera_form)
        layout = page.section("Image")
        layout.addWidget(w.overlay_panel.mirror)
        layout.addWidget(
            hint(
                "Mirroring flips only what you see. Recognition always uses the unmirrored "
                "image, so left and right stay correct.",
                True,
            )
        )
        layout = page.section("Frame rate")
        layout.addWidget(
            hint(
                "Requested is what the app asks the camera for; measured is what the camera "
                "actually delivers. Motion recognition uses the real time of every frame, so "
                "it works at any rate, but below about 22 frames per second downward swipes "
                "wait a little longer to avoid wrong directions. Many webcams deliver at most "
                "30 frames per second, even when a driver offers 60."
            )
        )
        return page

    def _gestures(self, title: str) -> Page:
        page = Page(
            title,
            "How gestures are recognized and what they do. Sensitivity presets cover ordinary "
            "use; advanced thresholds are for calibration checks.",
        )
        w = self.window_
        self.gesture_form = GestureSettingsDialog(
            self.services.engine.settings, self.services.dispatcher.mapping, embedded=True
        )
        self.gesture_form.applied.connect(w.apply_gesture_settings)
        self.gesture_form.revert_button.clicked.connect(lambda: page.load())
        page.body.addWidget(self.gesture_form)
        layout = page.section("Practice and calibration")
        layout.addWidget(
            hint(
                "Practice shows what the recognizer sees while you move; Quick Calibration "
                "measures your own swipes and can set the Personal sensitivity."
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Practice and calibrate...", w.open_practice))
        row.addStretch(1)
        layout.addLayout(row)

        def load() -> None:
            self.gesture_form.load(self.services.engine.settings, self.services.dispatcher.mapping)
            self.gesture_form.error.setText("")

        page.load = load  # type: ignore[method-assign]
        return page

    def _eyes(self, title: str) -> Page:
        page = Page(
            title,
            "Passive only: eye features show and count, they never control anything - no "
            "cursor, clicks, tabs, playback or gestures.",
        )
        w = self.window_
        layout = page.section("Eye and gaze overlay")
        self.eye_overlay = QCheckBox("Show eye outlines, irises and estimated gaze direction")
        self.eye_overlay.toggled.connect(w.set_eye_overlay)
        layout.addWidget(self.eye_overlay)
        layout.addWidget(
            hint(
                "On the camera image and the Broadcast overlay. The arrows are an estimate "
                "from head pose and iris position, not an exact line of sight; they are hidden "
                "while you blink or turn far away.",
                True,
            )
        )
        layout = page.section("Eye analytics")
        self.eye_analytics = QCheckBox(
            "Estimate screen-facing time, looking-away time and blinks (daily totals)"
        )
        self.eye_analytics.toggled.connect(
            lambda on: self._effects_change(eye_analytics_enabled=on)
        )
        layout.addWidget(self.eye_analytics)
        self.eye_calibration = hint("")
        layout.addWidget(self.eye_calibration)
        row = QHBoxLayout()
        row.addWidget(
            button(
                "Calibrate looking at the screen (3 s)...",
                w.calibrate_eyes,
                "Look at the middle of the screen for three seconds",
            )
        )
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(
            hint(
                "Screen-facing time is not attention, and nothing here measures engagement, "
                "mood or health.",
                True,
            )
        )
        layout = page.section("Gaze point on the screen")
        layout.addWidget(
            hint(
                "Not available. A passive gaze point and a gaze heatmap need a measured "
                "accuracy with a real person first; that measurement has not been made. "
                "scripts/evaluate_gaze_calibration.py measures it (9 calibration points, 8 "
                "separate evaluation points)."
            )
        )
        layout = page.section("Privacy")
        layout.addWidget(
            hint(
                "Face landmarks are computed on this computer and only while one of these "
                "features is on. No face images, landmarks or gaze coordinates are stored; "
                "eye analytics keep daily totals only."
            )
        )

        def load() -> None:
            e = self.user.effects
            set_checked(self.eye_overlay, e.eye_overlay)
            set_checked(self.eye_analytics, e.eye_analytics_enabled)
            self.eye_calibration.setText(
                "Calibrated for your usual position."
                if e.eye_baseline_yaw is not None
                else "Not calibrated: the estimate assumes the camera sits on top of the screen."
            )
            available = w.face_worker is not None
            for box in (self.eye_overlay, self.eye_analytics):
                box.setEnabled(available)
            if not available:
                self.eye_calibration.setText("Face landmarks are not available in this build.")

        page.load = load  # type: ignore[method-assign]
        return page

    def _effects(self, title: str) -> Page:
        page = Page(title)
        w = self.window_
        layout = page.section("Hand tracking layers (camera image)")
        for name, box in w.overlay_panel.checkboxes.items():
            del name
            layout.addWidget(box)

        layout = page.section("Skeleton style")
        rows = form()
        color = QWidget()
        color_row = QHBoxLayout(color)
        color_row.setContentsMargins(0, 0, 0, 0)
        self.auto_color = QCheckBox("Colour by hand")
        self.auto_color.toggled.connect(self._auto_color)
        self.pick_color = QPushButton("Choose colour...")
        self.pick_color.clicked.connect(self._choose_color)
        color_row.addWidget(self.auto_color)
        color_row.addWidget(self.pick_color)
        color_row.addStretch(1)
        rows.addRow("Colour", color)
        self.landmark = spin(0.3, 3.0, 0.1, 1, " x")
        self.landmark.valueChanged.connect(
            lambda v: self._appearance_change(landmark_scale=round(v, 2))
        )
        self.line = spin(0.3, 3.0, 0.1, 1, " x")
        self.line.valueChanged.connect(lambda v: self._appearance_change(line_scale=round(v, 2)))
        self.trail = spin(0.1, 3.0, 0.1, 1, " s")
        self.trail.valueChanged.connect(
            lambda v: self._appearance_change(trail_length_s=round(v, 2))
        )
        rows.addRow("Landmark size", self.landmark)
        rows.addRow("Line thickness", self.line)
        rows.addRow("Trail length", self.trail)
        layout.addLayout(rows)

        layout = page.section("Progressive clown transformation")
        self.clown = QCheckBox("Red nose, then lips, then light white makeup as you keep scrolling")
        self.clown.toggled.connect(lambda on: self._effects_change(clown_enabled=on))
        layout.addWidget(self.clown)
        rows = form()
        self.makeup = QSlider(Qt.Orientation.Horizontal)
        self.makeup.setRange(int(MIN_MAKEUP_OPACITY * 100), int(MAX_MAKEUP_OPACITY * 100))
        self.makeup_value = QLabel()
        self.makeup.valueChanged.connect(lambda v: self.makeup_value.setText(f"{v} %"))
        self.makeup.sliderReleased.connect(
            lambda: self._effects_change(clown_makeup_opacity=round(self.makeup.value() / 100, 2))
        )
        self.makeup.valueChanged.connect(self._makeup_keyboard)
        slider = QWidget()
        slider_row = QHBoxLayout(slider)
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.addWidget(self.makeup, 1)
        slider_row.addWidget(self.makeup_value)
        rows.addRow("White makeup strength", slider)
        self.stages: list[QDoubleSpinBox] = []
        for index, label in enumerate(("Red nose after", "Lips after", "White makeup after")):
            box = spin(0, 600, 1, 0, " min of scrolling")
            box.valueChanged.connect(lambda _v, i=index: self._stage_changed(i))
            self.stages.append(box)
            rows.addRow(label, box)
        self.stage_preview = QComboBox()
        self.stage_preview.addItem("Off (follow the scrolling session)", None)
        for stage, text in ((1, "1 - nose"), (2, "2 - nose and lips"), (3, "3 - full makeup")):
            self.stage_preview.addItem(text, stage)
        self.stage_preview.activated.connect(
            lambda _: self._effects_change(clown_preview_stage=self.stage_preview.currentData())
        )
        rows.addRow("Preview a stage", self.stage_preview)
        layout.addLayout(rows)
        self.clown_error = hint("", True)
        layout.addWidget(self.clown_error)
        layout.addWidget(
            hint("No artificial hair; your own face stays visible under the makeup.", True)
        )

        layout = page.section("Transparent background")
        layout.addWidget(
            hint("Removes the room around you on the Broadcast overlay (for OBS and streams).")
        )
        layout.addWidget(link("Broadcast settings", lambda: self.open_page("broadcast")))

        def load() -> None:
            a = self.user.appearance
            e = self.user.effects
            set_checked(self.auto_color, a.skeleton_color == "auto")
            self.pick_color.setEnabled(a.skeleton_color != "auto")
            for box, value in (
                (self.landmark, a.landmark_scale),
                (self.line, a.line_scale),
                (self.trail, a.trail_length_s),
            ):
                with QSignalBlocker(box):
                    box.setValue(value)
            set_checked(self.clown, e.clown_enabled)
            with QSignalBlocker(self.makeup):
                self.makeup.setValue(round(e.clown_makeup_opacity * 100))
            self.makeup_value.setText(f"{self.makeup.value()} %")
            for box, value in zip(self.stages, e.clown_thresholds, strict=True):
                with QSignalBlocker(box):
                    box.setValue(value)
            with QSignalBlocker(self.stage_preview):
                index = self.stage_preview.findData(e.clown_preview_stage)
                self.stage_preview.setCurrentIndex(max(0, index))
            self.clown_error.setText("")
            for box in w.overlay_panel.checkboxes.values():
                field = next(k for k, v in w.overlay_panel.checkboxes.items() if v is box)
                set_checked(box, bool(getattr(w.overlay_panel.overlay, field)))

        page.load = load  # type: ignore[method-assign]
        return page

    def _auto_color(self, on: bool) -> None:
        self.pick_color.setEnabled(not on)
        if on:
            self._appearance_change(skeleton_color="auto")
        elif self.user.appearance.skeleton_color == "auto":
            self._appearance_change(skeleton_color="#3dff9a")

    def _choose_color(self) -> None:
        current = self.user.appearance.skeleton_color
        start = QColor(current if current != "auto" else "#3dff9a")
        color = QColorDialog.getColor(start, self, "Skeleton colour")
        if color.isValid():
            self._appearance_change(skeleton_color=color.name())

    def _makeup_keyboard(self, value: int) -> None:
        if not self.makeup.isSliderDown():
            self._effects_change(clown_makeup_opacity=round(value / 100, 2))

    def _stage_changed(self, index: int) -> None:
        values = [box.value() for box in self.stages]
        if self._effects_change(
            clown_stage1_min=values[0], clown_stage2_min=values[1], clown_stage3_min=values[2]
        ):
            self.clown_error.setText("")
        else:
            self.clown_error.setText("The stages must not decrease (nose, then lips, then makeup).")

    def _broadcast(self, title: str) -> Page:
        page = Page(
            title,
            "Broadcast shows your camera in a small always-on-top window over the browser, for "
            "recording or streaming. Gesture control works exactly as in Studio.",
        )
        w = self.window_
        layout = page.section("Background")
        self.transparent = QCheckBox("Transparent background")
        self.transparent.toggled.connect(lambda on: self._creator_change(transparent_background=on))
        layout.addWidget(self.transparent)
        self.transparent_hint = hint("", True)
        layout.addWidget(self.transparent_hint)

        layout = page.section("Show on the overlay")
        self.layers: dict[str, QCheckBox] = {}
        for name, label in BROADCAST_LAYERS:
            box = QCheckBox(label)
            box.toggled.connect(lambda on, n=name: self._creator_change(**{n: on}))
            layout.addWidget(box)
            self.layers[name] = box
        self.broadcast_eyes = QCheckBox("Eye and gaze overlay (estimate)")
        self.broadcast_eyes.toggled.connect(w.set_eye_overlay)
        self.broadcast_clown = QCheckBox("Progressive clown makeup")
        self.broadcast_clown.toggled.connect(lambda on: self._effects_change(clown_enabled=on))
        layout.addWidget(self.broadcast_eyes)
        layout.addWidget(self.broadcast_clown)
        layout.addWidget(
            link("Clown timing and makeup strength", lambda: self.open_page("effects"))
        )

        layout = page.section("Window")
        rows = form()
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.valueChanged.connect(lambda v: self._creator_change(opacity=round(v / 100, 2)))
        rows.addRow("Opacity", self.opacity)
        self.size = QComboBox()
        self.size.activated.connect(self._size)
        rows.addRow("Size", self.size)
        self.corner = QComboBox()
        self.corner.addItem("Where I placed it", OverlayCorner.CUSTOM.value)
        for corner, text in OVERLAY_CORNERS:
            self.corner.addItem(text, corner.value)
        self.corner.activated.connect(self._corner)
        rows.addRow("Position", self.corner)
        layout.addLayout(rows)
        layout.addWidget(
            hint("Drag the overlay to move it; drag its lower-right corner to resize it.", True)
        )
        row = QHBoxLayout()
        row.addWidget(button("Open Broadcast now", lambda: w.set_ui_mode("creator")))
        row.addStretch(1)
        layout.addLayout(row)
        layout = page.section("Capturing the overlay in OBS")
        layout.addWidget(
            hint(
                "Use a Window Capture of 'Interactive Scrolling - Broadcast' (Windows 10 capture "
                "method) and allow transparency, or a Display Capture. See "
                "docs/BROADCAST_GUIDE.md."
            )
        )

        def load() -> None:
            c = w.creator.settings
            e = self.user.effects
            available = w.segmenter is not None
            self.transparent.setEnabled(available)
            set_checked(self.transparent, c.transparent_background)
            self.transparent_hint.setText(
                "Removes the room around you, on this computer. If removal is not possible for "
                "a moment, the camera image is hidden instead of showing the room."
                if available
                else "Not available: the person-segmentation model is missing in this installation."
            )
            for name, box in self.layers.items():
                set_checked(box, bool(getattr(c, name)))
            set_checked(self.broadcast_eyes, e.eye_overlay)
            set_checked(self.broadcast_clown, e.clown_enabled)
            self.broadcast_eyes.setEnabled(w.face_worker is not None)
            self.broadcast_clown.setEnabled(w.face_worker is not None)
            with QSignalBlocker(self.opacity):
                self.opacity.setValue(round(c.opacity * 100))
            with QSignalBlocker(self.size):
                self.size.clear()
                for width in OVERLAY_SIZES:
                    self.size.addItem(f"{width} x {width * 9 // 16}", width)
                if c.width not in OVERLAY_SIZES:
                    self.size.addItem(f"{c.width} x {c.height} (custom)", c.width)
                self.size.setCurrentIndex(self.size.findData(c.width))
            with QSignalBlocker(self.corner):
                self.corner.setCurrentIndex(max(0, self.corner.findData(c.corner.value)))

        page.load = load  # type: ignore[method-assign]
        return page

    def _size(self, _index: int) -> None:
        width = int(self.size.currentData())
        self._creator_change(width=width, height=width * 9 // 16)

    def _corner(self, _index: int) -> None:
        corner = OverlayCorner(self.corner.currentData())
        if corner is not OverlayCorner.CUSTOM:
            self.window_.creator.move_to_corner(corner)

    def _browser(self, title: str) -> Page:
        page = Page(
            title,
            "The Interactive Scrolling extension connects Microsoft Edge (tested) or Google "
            "Chrome to this app on this computer only. It lets gestures control YouTube Shorts "
            "and shows the Short you choose in the app.",
        )
        w = self.window_
        layout = page.section("Connection")
        layout.addWidget(w.youtube_panel)
        layout = page.section("One-time setup")
        steps = hint(
            "1. Open edge://extensions (or chrome://extensions) and turn on Developer mode.\n"
            "2. Choose Load unpacked and select the extension folder (copy its path below).\n"
            "3. Click the extension icon, paste the pairing code above and keep the port.\n"
            "After an app update, press Reload on the extension in the same page."
        )
        layout.addWidget(steps)
        row = QHBoxLayout()
        row.addWidget(
            button(
                "Copy extension folder path",
                lambda: QGuiApplication.clipboard().setText(str(EXTENSION_DIR)),
                str(EXTENSION_DIR),
            )
        )
        row.addStretch(1)
        layout.addLayout(row)
        layout = page.section("Live preview of the Short")
        layout.addWidget(
            hint(
                "Open a YouTube Short, click the extension icon and choose 'Show this Short in "
                "the app'. The browser asks once per tab; it captures only that tab, only while "
                "it shows Shorts, and the picture never leaves this computer. Stop it here or "
                "in the browser."
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Stop the live preview", w.stop_preview))
        row.addStretch(1)
        layout.addLayout(row)
        layout = page.section("Tabs")
        layout.addWidget(
            hint(
                "Left and right swipes switch browser tabs only while the browser is the active "
                "window; other tabs are never shown in the app."
            )
        )
        return page

    def _together(self, title: str) -> Page:
        page = Page(
            title,
            "Scroll one feed with a friend: the host's browser plays, you both swipe. Host, "
            "Join, Leave and End are in the Your session panel.",
        )
        w = self.window_
        layout = page.section("You")
        rows = form()
        self.player_name = QLineEdit()
        self.player_name.setMaxLength(24)
        self.player_name.setPlaceholderText("Player 1")
        self.player_name.editingFinished.connect(self._together_changed)
        rows.addRow("Your name", self.player_name)
        self.host_port = QSpinBox()
        self.host_port.setRange(1024, 65535)
        self.host_port.setKeyboardTracking(False)
        self.host_port.valueChanged.connect(lambda _v: self._together_changed())
        rows.addRow("Port when you host", self.host_port)
        layout.addLayout(rows)
        self.together_error = hint("", True)
        layout.addWidget(self.together_error)
        layout = page.section("Network and safety")
        layout.addWidget(
            hint(
                "Sessions work on a private network only: the same Wi-Fi, or a private VPN "
                "you both join (for example Tailscale). Nothing is opened to the internet and "
                "no firewall rule is changed by the app; Windows may ask once whether to allow "
                "the connection.\n\nThe host lets each guest in, can switch guest control off "
                "and can remove the guest. Guests can only go to the next or previous Short "
                "and pause; both share one cooldown. An invitation code expires after 15 "
                "minutes. The emergency stop on either computer stops that person's gestures."
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Show Your session", lambda: w.set_session_panel_expanded(True)))
        row.addStretch(1)
        layout.addLayout(row)

        def load() -> None:
            t = self.user.together
            with QSignalBlocker(self.player_name):
                self.player_name.setText(t.player_name)
            with QSignalBlocker(self.host_port):
                self.host_port.setValue(t.host_port)
            self.together_error.setText("")

        page.load = load  # type: ignore[method-assign]
        return page

    def _together_changed(self) -> None:
        from interactive_scrolling.integrations.coop.protocol import CoopProtocolError, valid_name

        name = self.player_name.text().strip()
        if name:
            try:
                valid_name(name)
            except CoopProtocolError as exc:
                self.together_error.setText(str(exc))
                return
        self.together_error.setText("")
        self.window_.apply_together(
            TogetherSettings(player_name=name, host_port=self.host_port.value())
        )

    def _analytics(self, title: str) -> Page:
        page = Page(
            title,
            "Statistics stay on this computer: counts and times only, no addresses, titles or "
            "videos.",
        )
        w = self.window_
        layout = page.section("Statistics")
        self.stats = QCheckBox("Keep local statistics (scrolling time, actions, sessions)")
        self.stats.toggled.connect(w.set_analytics_enabled)
        layout.addWidget(self.stats)
        row = QHBoxLayout()
        row.addWidget(button("Daily report...", w.open_report))
        row.addWidget(button("Wrapped: today...", lambda: w.open_wrapped("today")))
        row.addWidget(button("Wrapped: this session...", lambda: w.open_wrapped("session")))
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(
            hint(
                "Doomscroll Index: 0-100 from today's scrolling time and longest session against "
                "your own goals below (lower is better). Entertainment, not a medical or "
                "psychological assessment.",
                True,
            )
        )
        layout = page.section("Limits and reminders")
        self.wb_enabled = QCheckBox("Show Reality Checks and limit reminders")
        layout.addWidget(self.wb_enabled)
        rows = form()
        self.wb_session = spin(1, 600, 1, 0, " min")
        self.wb_budget = spin(1, 1440, 5, 0, " min")
        self.wb_reality = spin(0, 240, 1, 0, " min (0 = off)")
        rows.addRow("Session limit", self.wb_session)
        rows.addRow("Daily scrolling budget", self.wb_budget)
        rows.addRow("Reality Check every", self.wb_reality)
        layout.addLayout(rows)
        self.wb_breaks = QCheckBox("Suggest a break when a limit is reached")
        self.wb_pause = QCheckBox(
            "Pause gesture scrolling when a limit is reached (resume anytime)"
        )
        self.wb_humor = QCheckBox("Playful wording (Doomscroll Index, Wrapped)")
        for box in (self.wb_breaks, self.wb_pause, self.wb_humor):
            layout.addWidget(box)
        for box in (self.wb_enabled, self.wb_breaks, self.wb_pause, self.wb_humor):
            box.toggled.connect(lambda _on: self._wellbeing_changed())
        for box in (self.wb_session, self.wb_budget, self.wb_reality):
            box.valueChanged.connect(lambda _v: self._wellbeing_changed())
        layout.addWidget(
            hint(
                "Only gesture navigation between Shorts can be paused. Your mouse, keyboard, "
                "likes, playback and tab switching keep working.",
                True,
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Restore default limits", self._wellbeing_defaults))
        row.addStretch(1)
        layout.addLayout(row)

        def load() -> None:
            set_checked(self.stats, self.user.analytics_enabled)
            s = self.user.wellbeing
            set_checked(self.wb_enabled, s.enabled)
            set_checked(self.wb_breaks, s.break_reminders)
            set_checked(self.wb_pause, s.pause_at_limit)
            set_checked(self.wb_humor, s.humorous_labels)
            for box, value in (
                (self.wb_session, s.session_limit_min),
                (self.wb_budget, s.daily_budget_min),
                (self.wb_reality, s.reality_check_min),
            ):
                with QSignalBlocker(box):
                    box.setValue(value)

        page.load = load  # type: ignore[method-assign]
        return page

    def _wellbeing_changed(self) -> None:
        self.services.apply_wellbeing(
            WellbeingSettings(
                enabled=self.wb_enabled.isChecked(),
                session_limit_min=self.wb_session.value(),
                daily_budget_min=self.wb_budget.value(),
                reality_check_min=self.wb_reality.value(),
                break_reminders=self.wb_breaks.isChecked(),
                pause_at_limit=self.wb_pause.isChecked(),
                humorous_labels=self.wb_humor.isChecked(),
            )
        )

    def _wellbeing_defaults(self) -> None:
        self.services.apply_wellbeing(WellbeingSettings())
        self.pages["analytics"].load()

    def _privacy(self, title: str) -> Page:
        page = Page(title)
        w = self.window_
        layout = page.section("What stays on this computer")
        layout.addWidget(
            hint(
                "Camera images, hand and face landmarks are processed in memory on this "
                "computer and never saved or sent anywhere. The live preview travels from your "
                "browser to this app over this computer only. Doomscroll Together sends only "
                "gesture actions and names, over your private network."
            )
        )
        layout = page.section("Your data")
        self.data_folder = hint("", True)
        layout.addWidget(self.data_folder)
        row = QHBoxLayout()
        row.addWidget(button("Open the data folder", self._open_data_folder))
        row.addWidget(button("Delete all statistics...", self._delete_statistics))
        row.addStretch(1)
        layout.addLayout(row)
        layout = page.section("Diagnostics")
        layout.addWidget(
            hint(
                "Copy diagnostics creates a report for a problem description: settings, "
                "timings and recent outcomes, without images, page addresses, codes or tokens."
            )
        )
        row = QHBoxLayout()
        row.addWidget(button("Copy diagnostics", w.copy_diagnostics))
        row.addStretch(1)
        layout.addLayout(row)
        layout = page.section("System")
        self.system_note = hint("", True)
        layout.addWidget(self.system_note)

        def load() -> None:
            self.data_folder.setText(f"Settings and statistics: {w._data_folder()}")
            self.system_note.setText(
                f"Version {__version__} (beta). Windows power throttling is switched off for "
                "this app so the camera timing stays steady."
            )

        page.load = load  # type: ignore[method-assign]
        return page

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.window_._data_folder())))

    def _delete_statistics(self) -> None:
        answer = QMessageBox.question(
            self,
            "Delete all statistics",
            "Delete all local statistics (scrolling time, actions, eye totals)? This cannot be "
            "undone. Settings are kept.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.window_.clear_statistics()


__all__ = [
    "PAGES",
    "AppearanceSettings",
    "CameraSettingsForm",
    "CreatorSettings",
    "EffectsSettings",
    "SettingsWindow",
]
