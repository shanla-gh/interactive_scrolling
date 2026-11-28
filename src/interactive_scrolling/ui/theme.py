"""Application themes: Black, White and Gray, built from one set of semantic tokens (Brief 010).

Every colour the application chrome uses comes from :data:`THEMES`; the Qt stylesheet is
generated from the active token set and widgets that paint themselves (camera view, Now playing,
logs) read :func:`tokens` at paint time, so switching theme is immediate and touches nothing
else (camera, models, gesture control, browser capture and Co-op keep running).

Media pixels are never themed: the camera image, the YouTube Short and the Broadcast overlay's
transparent background are drawn as they are. Overlay graphics drawn *on* media (skeleton,
banners) keep their own fixed palette (``visualization/palette.py``) so they read on any video.

Design rules: restrained neutral surfaces separated by thin lines; one semantic green for
"on / success", amber for warnings, red for stop / error / destructive actions; the system UI
font everywhere except technical diagnostics (monospace); sentence-case labels.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

UI_FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"]
MONO_FONT_FAMILIES = ["Cascadia Mono", "Consolas", "Courier New"]
THEME_NAMES = ("black", "white", "gray")
DEFAULT_THEME = "black"


@dataclass(frozen=True, slots=True)
class Tokens:
    name: str
    bg: str
    """Application background."""
    surface: str
    """Primary surfaces (panels, inputs on light themes)."""
    surface_alt: str
    """Secondary surface (console, side panels)."""
    raised: str
    """Elevated surface (buttons, menus, inputs)."""
    text: str
    text_muted: str
    text_disabled: str
    border: str
    divider: str
    accent: str
    """Primary action and selection (the product green)."""
    on_accent: str
    """Text on the accent colour."""
    success: str
    warning: str
    danger: str
    danger_bg: str
    danger_border: str
    hover: str
    selected: str
    focus: str
    tooltip_bg: str
    tooltip_text: str
    selection: str
    media_bg: str
    """Behind letterboxed media (camera, Short): always dark, so video edges read the same."""


THEMES: dict[str, Tokens] = {
    "black": Tokens(
        name="black",
        bg="#101113",
        surface="#16181b",
        surface_alt="#191b1e",
        raised="#222529",
        text="#f1f2f4",
        text_muted="#a0a4aa",
        text_disabled="#62676e",
        border="#303338",
        divider="#26292d",
        accent="#4cc38a",
        on_accent="#0c1a12",
        success="#4cc38a",
        warning="#d9a43b",
        danger="#e5534b",
        danger_bg="#3a1c1c",
        danger_border="#7a2e2b",
        hover="#2a2d32",
        selected="#2c3036",
        focus="#6aa8ff",
        tooltip_bg="#222529",
        tooltip_text="#f1f2f4",
        selection="#1f4a35",
        media_bg="#0b0c0d",
    ),
    "white": Tokens(
        name="white",
        bg="#f6f7f8",
        surface="#ffffff",
        surface_alt="#eceef0",
        raised="#ffffff",
        text="#202124",
        text_muted="#62666d",
        text_disabled="#a3a7ad",
        border="#d8dce0",
        divider="#e3e6e9",
        accent="#1e8a55",
        on_accent="#ffffff",
        success="#1e8a55",
        warning="#9a6200",
        danger="#c62828",
        danger_bg="#fdecec",
        danger_border="#e8b4b4",
        hover="#eef0f2",
        selected="#e3e7ea",
        focus="#1a73e8",
        tooltip_bg="#202124",
        tooltip_text="#f6f7f8",
        selection="#cfe9dc",
        media_bg="#1b1c1e",
    ),
    "gray": Tokens(
        name="gray",
        bg="#41454a",
        surface="#50545a",
        surface_alt="#4a4e54",
        raised="#5c6167",
        text="#f1f2f4",
        text_muted="#d0d3d7",
        text_disabled="#959aa1",
        border="#656a70",
        divider="#5a5f65",
        accent="#7fd8a6",
        on_accent="#12261b",
        success="#7fd8a6",
        warning="#f2c46a",
        danger="#ff8f86",
        danger_bg="#5a3d3d",
        danger_border="#9a5b57",
        hover="#62676d",
        selected="#6a7076",
        focus="#9cc7ff",
        tooltip_bg="#2c2f33",
        tooltip_text="#f1f2f4",
        selection="#3f6a55",
        media_bg="#2b2e32",
    ),
}

_current: Tokens = THEMES[DEFAULT_THEME]


def tokens() -> Tokens:
    """The active theme's tokens (read at paint time by self-painting widgets)."""
    return _current


def stylesheet(t: Tokens) -> str:
    return f"""
QWidget {{ background-color: {t.bg}; color: {t.text}; font-size: 10pt; }}
QLabel {{ background: transparent; }}
QWidget:disabled {{ color: {t.text_disabled}; }}

/* top bar and workspace panels */
#topBar {{ background-color: {t.bg}; border-bottom: 1px solid {t.divider}; }}
#brand {{ font-size: 11.5pt; font-weight: 600; color: {t.text}; }}
#version {{ color: {t.text_disabled}; font-size: 8.5pt; }}
#cameraStatus {{ color: {t.text_muted}; }}
#cameraStatus[state="running"] {{ color: {t.success}; }}
#cameraStatus[state="starting"], #cameraStatus[state="stopping"] {{ color: {t.warning}; }}
#cameraStatus[state="error"] {{ color: {t.danger}; }}
#leftPanel {{ background-color: {t.bg}; }}
#cinema {{ background-color: {t.bg}; }}
#sessionPanel, #sessionStrip {{
    background-color: {t.surface_alt}; border-left: 1px solid {t.divider};
}}
#sessionPanel QWidget, #sessionStrip QWidget {{ background-color: transparent; }}
QSplitter::handle {{ background: {t.divider}; }}
QSplitter::handle:hover {{ background: {t.border}; }}

/* buttons */
QPushButton, QToolButton {{
    background-color: {t.raised}; color: {t.text}; border: 1px solid {t.border};
    border-radius: 5px; padding: 5px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background-color: {t.hover}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {t.focus}; }}
QPushButton:disabled, QToolButton:disabled {{
    color: {t.text_disabled}; border-color: {t.divider}; background-color: {t.surface_alt};
}}
QPushButton#flatButton, QToolButton#flatButton {{
    background: transparent; border: 1px solid transparent; color: {t.text_muted}; padding: 5px 8px;
}}
QPushButton#flatButton:hover, QToolButton#flatButton:hover {{
    color: {t.text}; background-color: {t.hover};
}}
QPushButton#flatButton:focus, QToolButton#flatButton:focus {{ border-color: {t.focus}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#layerButton {{
    background: transparent; border: 1px solid {t.divider}; color: {t.text_muted};
    border-radius: 5px; padding: 3px 9px;
}}
QPushButton#layerButton:hover {{ color: {t.text}; background-color: {t.hover}; }}
QPushButton#layerButton:checked {{
    color: {t.text}; background-color: {t.selected}; border-color: {t.border};
}}
QPushButton#layerButton:focus {{ border-color: {t.focus}; }}
QPushButton#linkButton {{
    background: transparent; border: none; color: {t.text_muted}; padding: 2px 0;
    text-align: left;
}}
QPushButton#linkButton:hover {{ color: {t.text}; text-decoration: underline; }}
QPushButton#linkButton:focus {{ color: {t.text}; text-decoration: underline; }}
QPushButton#primaryButton {{
    background-color: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background-color: {t.accent}; border-color: {t.text}; }}
QPushButton#primaryButton[running="true"] {{
    background-color: transparent; color: {t.danger}; border-color: {t.danger_border};
}}
QPushButton#primaryButton[running="true"]:hover {{ background-color: {t.danger_bg}; }}
QPushButton#dangerButton {{
    background-color: {t.danger_bg}; color: {t.danger}; border: 1px solid {t.danger_border};
    font-weight: 600;
}}
QPushButton#dangerButton:hover {{ border-color: {t.danger}; }}
QPushButton#dangerButton:disabled {{
    background: transparent; color: {t.text_disabled}; border-color: {t.divider};
}}

/* segmented controls: one rounded rectangle, segments separated by thin lines */
#segmented {{
    background-color: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 6px;
}}
#segmented QPushButton {{
    background: transparent; border: none; border-radius: 4px; color: {t.text_muted};
    padding: 3px 11px; margin: 2px;
}}
#segmented QPushButton:hover {{ color: {t.text}; background-color: {t.hover}; }}
#segmented QPushButton:checked {{
    background-color: {t.raised}; color: {t.text}; font-weight: 600; border: 1px solid {t.border};
}}
#segmented QPushButton:focus {{ border: 1px solid {t.focus}; }}
#segmented QPushButton[mode="live_control"]:checked {{
    background-color: {t.danger_bg}; color: {t.danger}; border: 1px solid {t.danger_border};
}}

/* gesture control */
#gestureState {{ color: {t.text_muted}; }}
#gestureStrip[live="true"] #gestureState {{ color: {t.danger}; font-weight: 600; }}
QPushButton#disableButton {{
    background-color: {t.danger_bg}; color: {t.danger}; border: 1px solid {t.danger_border};
    font-weight: 600; padding: 6px 10px;
}}
QPushButton#disableButton:disabled {{
    background: transparent; color: {t.text_disabled}; border-color: {t.divider};
}}

/* text roles */
#sectionTitle {{ color: {t.text_muted}; font-weight: 600; }}
#sectionValue {{ color: {t.text}; }}
#hint {{ color: {t.text_muted}; }}
#hint[error="true"] {{ color: {t.danger}; }}
#panelTitle {{ font-size: 11pt; font-weight: 600; color: {t.text}; }}
#dimHint {{ color: {t.text_disabled}; font-size: 9pt; }}
#bigNumber {{ font-size: 15pt; font-weight: 600; color: {t.text}; }}
#sessionClock {{ font-size: 17pt; font-weight: 600; color: {t.text}; }}
#numberCaption {{ color: {t.text_muted}; font-size: 8.5pt; }}
#statusDot {{ color: {t.text_disabled}; }}
#statusDot[state="ok"] {{ color: {t.success}; }}
#statusDot[state="warn"] {{ color: {t.warning}; }}
#statusDot[state="error"] {{ color: {t.danger}; }}
#feedbackGesture {{ color: {t.text}; font-weight: 600; }}
#feedbackOutcome {{ color: {t.text_muted}; }}
#feedbackOutcome[state="ok"] {{ color: {t.success}; }}
#feedbackOutcome[state="warn"] {{ color: {t.warning}; }}
#feedbackOutcome[state="error"] {{ color: {t.danger}; }}
#separator {{ background-color: {t.divider}; max-height: 1px; min-height: 1px; border: none; }}
#inviteCode {{
    font-family: "Cascadia Mono", "Consolas"; font-size: 12pt; font-weight: 600; color: {t.text};
}}

/* legacy card styles used inside settings pages */
#card {{ background-color: transparent; border: none; }}
#card QWidget {{ background-color: transparent; }}
#cardTitle {{ color: {t.text_muted}; font-weight: 600; }}
#rowKey {{ color: {t.text_muted}; }}
#rowValue {{ color: {t.text}; }}
#rowValueAccent {{ color: {t.success}; font-weight: 600; }}
#bigValue {{ color: {t.text}; font-size: 15pt; font-weight: 600; }}
#subHeading {{ color: {t.text_disabled}; font-weight: 600; }}

/* inputs */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {t.surface}; color: {t.text}; border: 1px solid {t.border};
    border-radius: 5px; padding: 4px 8px; selection-background-color: {t.selection};
    selection-color: {t.text};
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t.focus};
}}
QComboBox {{ min-width: 70px; }}
QComboBox QAbstractItemView {{
    background-color: {t.raised}; color: {t.text}; border: 1px solid {t.border};
    selection-background-color: {t.selected}; selection-color: {t.text};
}}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 3px; border: 1px solid {t.text_disabled};
    background: {t.surface};
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QCheckBox:focus {{ color: {t.text}; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.text}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QMenu {{
    background-color: {t.raised}; color: {t.text}; border: 1px solid {t.border}; padding: 4px;
}}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {t.selected}; }}
QMenu::separator {{ height: 1px; background: {t.divider}; margin: 4px 6px; }}

/* settings window */
QListWidget#settingsNav {{
    background-color: {t.surface_alt}; border: none; border-right: 1px solid {t.divider};
    padding: 8px 6px; outline: none;
}}
QListWidget#settingsNav::item {{ padding: 7px 12px; border-radius: 5px; color: {t.text_muted}; }}
QListWidget#settingsNav::item:hover {{ background-color: {t.hover}; color: {t.text}; }}
QListWidget#settingsNav::item:selected {{
    background-color: {t.selected}; color: {t.text}; font-weight: 600;
}}
#settingsPageTitle {{ font-size: 13pt; font-weight: 600; color: {t.text}; }}

/* console */
#console {{ background-color: {t.surface_alt}; border-top: 1px solid {t.divider}; }}
#console QWidget {{ background-color: {t.surface_alt}; }}
#consoleSummary, #consoleStats QLabel {{
    color: {t.text_muted}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt;
}}
QPlainTextEdit#activityLog {{
    background-color: {t.surface}; border: 1px solid {t.divider}; border-radius: 4px;
    color: {t.text_muted}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt; padding: 4px;
}}
QTableWidget, QTableWidget#gestureHistory {{
    background-color: {t.surface}; color: {t.text}; border: 1px solid {t.divider};
    border-radius: 4px; gridline-color: {t.divider}; font-family: "Cascadia Mono", "Consolas";
    font-size: 8.5pt; selection-background-color: {t.selected}; selection-color: {t.text};
}}
QHeaderView::section {{
    background-color: {t.surface_alt}; color: {t.text_muted}; border: none; padding: 3px 4px;
    font-size: 8.5pt;
}}
QTableCornerButton::section {{ background-color: {t.surface_alt}; border: none; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {t.text_muted}; padding: 4px 10px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
QTabBar::tab:hover {{ color: {t.text}; }}

/* misc */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; color: {t.text}; }}
QProgressBar::chunk {{ background: {t.warning}; border-radius: 3px; }}
QGroupBox {{
    border: none; border-top: 1px solid {t.divider}; margin-top: 14px; padding-top: 8px;
    color: {t.text_muted}; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 0; padding: 0 6px 0 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QDialog {{ background-color: {t.bg}; }}
"""


def mono_font(point_size: float = 9.0, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FONT_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(point_size)
    font.setBold(bold)
    return font


def repolish(widget) -> None:  # type: ignore[no-untyped-def]
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


APP_STYLESHEET = "QToolTip { border: 1px solid palette(mid); padding: 4px 6px; }"
"""The only application-wide rule; it never changes (tooltip colours come from the palette).
Changing an application stylesheet re-polishes every widget of the process (measured: about
380 ms for the 850 widgets of the main window, Settings, overlay and tray), so themes are
applied per window instead."""

_windows: weakref.WeakSet[QWidget] = weakref.WeakSet()
_active = False
"""True once a theme was applied (the real application and screenshot tools); plain widget
tests keep Qt's default look and skip the styling cost."""


class _ShowFilter(QObject):
    """Restyles a hidden window the moment it is shown again, if the theme changed meanwhile."""

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            _style(watched)
        return False


_show_filter: _ShowFilter | None = None


def _palette(t: Tokens) -> QPalette:
    pal = QPalette()
    for role, value in (
        (QPalette.ColorRole.Window, t.bg),
        (QPalette.ColorRole.WindowText, t.text),
        (QPalette.ColorRole.Base, t.surface),
        (QPalette.ColorRole.AlternateBase, t.surface_alt),
        (QPalette.ColorRole.Text, t.text),
        (QPalette.ColorRole.Button, t.raised),
        (QPalette.ColorRole.ButtonText, t.text),
        (QPalette.ColorRole.Highlight, t.selection),
        (QPalette.ColorRole.HighlightedText, t.text),
        (QPalette.ColorRole.ToolTipBase, t.tooltip_bg),
        (QPalette.ColorRole.ToolTipText, t.tooltip_text),
        (QPalette.ColorRole.PlaceholderText, t.text_disabled),
        (QPalette.ColorRole.Mid, t.border),
    ):
        pal.setColor(role, QColor(value))
    return pal


def _live_windows() -> list[QWidget]:
    """Registered windows whose Qt object still exists (deleted ones are dropped)."""
    alive = []
    for widget in list(_windows):
        if isValid(widget):
            alive.append(widget)
        else:
            _windows.discard(widget)
    return alive


def _style(widget: QWidget) -> None:
    if not isValid(widget):
        return
    if not _active or widget.property("themeName") == _current.name:
        return
    widget.setStyleSheet(stylesheet(_current))
    widget.setProperty("themeName", _current.name)
    widget.update()


def register(widget: QWidget) -> None:
    """Style a top-level window (and, through Qt's cascade, its child widgets and child
    dialogs) with the current theme, now and after every theme change."""
    global _show_filter
    if _show_filter is None:
        _show_filter = _ShowFilter()
    if widget not in _windows:
        _windows.add(widget)
        widget.installEventFilter(_show_filter)
    _style(widget)


def set_theme(app: QApplication, name: str, first: QWidget | None = None) -> Tokens:
    """Switch the theme at runtime (no restart; nothing but styles is touched).

    ``first`` (the main window) is restyled at once; other visible windows each in a later
    event-loop turn, so no single step blocks the interface for long; hidden windows when they
    are next shown.
    """
    global _current, _active
    _current = THEMES.get(name, THEMES[DEFAULT_THEME])
    _active = True
    app.setPalette(_palette(_current))
    if first is not None:
        register(first)
    for widget in _live_windows():
        if widget is first or not widget.isVisible():
            continue
        QTimer.singleShot(0, lambda w=widget: _style(w))
    return _current


def deactivate(app: QApplication) -> None:
    """Back to Qt's default look (tests)."""
    global _current, _active
    _active = False
    _current = THEMES[DEFAULT_THEME]
    for widget in _live_windows():
        widget.setStyleSheet("")
        widget.setProperty("themeName", None)
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())


def is_active() -> bool:
    return _active


def apply_theme(app: QApplication, name: str = DEFAULT_THEME) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSizeF(10.0)
    app.setFont(font)
    app.setStyleSheet(APP_STYLESHEET)
    set_theme(app, name)


# Backwards-compatible names (Black theme values) for code that predates the token system.
BG = THEMES["black"].bg
SURFACE = THEMES["black"].surface
RAISED = THEMES["black"].raised
LINE = THEMES["black"].border
TEXT = THEMES["black"].text
MUTED = THEMES["black"].text_muted
DIM = THEMES["black"].text_disabled
GREEN = THEMES["black"].accent
RED = THEMES["black"].danger
AMBER = THEMES["black"].warning
