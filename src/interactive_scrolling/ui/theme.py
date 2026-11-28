"""Application-wide dark theme (Brief 008 redesign).

Design rules: neutral dark surfaces separated by thin lines rather than boxes; one restrained
green for "on" and the primary action; red only for stopping, live control and errors; the
system UI font everywhere except the diagnostics console (monospace where columns of numbers
must line up); sentence-case labels instead of letter-spaced capitals.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from interactive_scrolling.visualization import palette as p

UI_FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"]
MONO_FONT_FAMILIES = ["Cascadia Mono", "Consolas", "Courier New"]

# Product UI colours (the camera overlay keeps its own brighter palette).
BG = p.BACKGROUND
SURFACE = p.SURFACE
RAISED = p.SURFACE_RAISED
LINE = p.BORDER
TEXT = p.TEXT
MUTED = p.TEXT_MUTED
DIM = p.TEXT_DIM
GREEN = "#4cc38a"
GREEN_BG = "#163a2a"
GREEN_LINE = "#25603f"
RED = "#e5534b"
RED_BG = "#3a1c1c"
RED_LINE = "#7a2e2b"
AMBER = "#d9a43b"

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 10pt;
}}
QToolTip {{
    background-color: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px;
}}
QLabel {{ background: transparent; }}

/* ---------------------------------------------------------------- top bar */
#topBar {{ background-color: {BG}; border-bottom: 1px solid {LINE}; }}
#brand {{ font-size: 11.5pt; font-weight: 600; color: {TEXT}; }}
#version {{ color: {DIM}; font-size: 8.5pt; }}
#cameraStatus {{ color: {MUTED}; }}
#cameraStatus[state="running"] {{ color: {GREEN}; }}
#cameraStatus[state="starting"], #cameraStatus[state="stopping"] {{ color: {AMBER}; }}
#cameraStatus[state="error"] {{ color: {RED}; }}

/* ---------------------------------------------------------------- buttons */
QPushButton, QToolButton {{
    background-color: {RAISED}; color: {TEXT};
    border: 1px solid {LINE}; border-radius: 5px; padding: 5px 12px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {DIM}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {DIM}; border-color: {RAISED}; }}
QPushButton#flatButton, QToolButton#flatButton {{
    background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 5px 8px;
}}
QPushButton#flatButton:hover, QToolButton#flatButton:hover {{
    color: {TEXT}; border-color: {LINE};
}}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#linkButton {{
    background: transparent; border: none; color: {MUTED}; padding: 2px 0; text-align: left;
}}
QPushButton#linkButton:hover {{ color: {TEXT}; text-decoration: underline; }}
QPushButton#primaryButton {{
    background-color: {GREEN}; color: #0c1a12; border: 1px solid {GREEN}; font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background-color: #5ad398; }}
QPushButton#primaryButton[running="true"] {{
    background-color: transparent; color: {RED}; border-color: {RED_LINE};
}}
QPushButton#primaryButton[running="true"]:hover {{ background-color: {RED_BG}; }}
QPushButton#segment {{
    background: transparent; color: {MUTED}; border: 1px solid {LINE}; border-radius: 0;
    padding: 5px 12px;
}}
QPushButton#segment[first="true"] {{
    border-top-left-radius: 5px; border-bottom-left-radius: 5px;
}}
QPushButton#segment[last="true"] {{
    border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}}
QPushButton#segment:checked {{ background-color: {RAISED}; color: {TEXT}; border-color: {DIM}; }}

/* ---------------------------------------------------------------- gesture control */
#gestureStrip {{ background: transparent; }}
#gestureStripLabel {{ color: {MUTED}; }}
#gestureState {{ color: {MUTED}; }}
#gestureStrip[live="true"] #gestureState {{ color: {RED}; font-weight: 600; }}
QPushButton#modeButton {{
    background: transparent; color: {MUTED}; border: 1px solid {LINE}; border-radius: 0;
    padding: 4px 12px;
}}
QPushButton#modeButton[first="true"] {{
    border-top-left-radius: 5px; border-bottom-left-radius: 5px;
}}
QPushButton#modeButton[last="true"] {{
    border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}}
QPushButton#modeButton:checked {{
    background-color: {RAISED}; color: {TEXT}; border-color: {DIM}; font-weight: 600;
}}
QPushButton#modeButton[mode="live_control"]:checked {{
    background-color: {RED_BG}; color: {RED}; border-color: {RED_LINE};
}}
QPushButton#disableButton {{
    background-color: {RED_BG}; color: {RED}; border: 1px solid {RED_LINE}; font-weight: 600;
    padding: 4px 10px;
}}
QPushButton#disableButton:disabled {{
    background: transparent; color: {DIM}; border-color: {LINE};
}}

/* ---------------------------------------------------------------- sections */
#sectionTitle {{ color: {MUTED}; font-weight: 600; }}
#sectionValue {{ color: {TEXT}; }}
#hint {{ color: {MUTED}; }}
#dimHint {{ color: {DIM}; font-size: 9pt; }}
#statusDot {{ color: {DIM}; }}
#statusDot[state="ok"] {{ color: {GREEN}; }}
#statusDot[state="warn"] {{ color: {AMBER}; }}
#statusDot[state="error"] {{ color: {RED}; }}
#bigNumber {{ font-size: 15pt; font-weight: 600; color: {TEXT}; }}
#numberCaption {{ color: {MUTED}; font-size: 8.5pt; }}
#sessionPanel {{ background-color: {BG}; border-left: 1px solid {LINE}; }}
#separator {{ background-color: {LINE}; max-height: 1px; min-height: 1px; border: none; }}
#inviteCode {{
    font-family: "Cascadia Mono", "Consolas"; font-size: 12pt; font-weight: 600; color: {TEXT};
}}

/* ---------------------------------------------------------------- legacy cards (dialogs) */
#card {{ background-color: transparent; border: none; }}
#card QWidget {{ background-color: transparent; }}
#cardTitle {{ color: {MUTED}; font-weight: 600; }}
#rowKey {{ color: {MUTED}; }}
#rowValue {{ color: {TEXT}; }}
#rowValueAccent {{ color: {GREEN}; font-weight: 600; }}
#bigValue {{ color: {TEXT}; font-size: 15pt; font-weight: 600; }}
#subHeading {{ color: {DIM}; font-weight: 600; }}

/* ---------------------------------------------------------------- inputs */
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {RAISED}; border: 1px solid {LINE}; border-radius: 5px; padding: 4px 8px;
    selection-background-color: {GREEN_BG};
}}
QComboBox {{ min-width: 70px; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled {{ color: {DIM}; }}
QComboBox QAbstractItemView {{
    background-color: {RAISED}; border: 1px solid {LINE};
    selection-background-color: {GREEN_BG}; selection-color: {TEXT};
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 3px; border: 1px solid {DIM}; background: {RAISED};
}}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {GREEN}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QMenu {{ background-color: {RAISED}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {LINE}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}

/* ---------------------------------------------------------------- console */
#console {{ background-color: {SURFACE}; border-top: 1px solid {LINE}; }}
#console QWidget {{ background-color: {SURFACE}; }}
#consoleTitle {{ color: {MUTED}; font-weight: 600; }}
#consoleSummary, #consoleStats QLabel {{
    color: {MUTED}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt;
}}
QPlainTextEdit#activityLog {{
    background-color: {BG}; border: 1px solid {LINE}; border-radius: 4px;
    color: {MUTED}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt; padding: 4px;
}}
QTableWidget#gestureHistory {{
    background-color: {BG}; border: 1px solid {LINE}; border-radius: 4px;
    gridline-color: {SURFACE}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt;
}}
QHeaderView::section {{
    background-color: {SURFACE}; color: {MUTED}; border: none; padding: 3px 4px;
    font-size: 8.5pt;
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 4px 10px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {GREEN}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* ---------------------------------------------------------------- misc */
QScrollArea {{ border: none; }}
QProgressBar {{ background: {RAISED}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {AMBER}; border-radius: 3px; }}
QGroupBox {{
    border: none; border-top: 1px solid {LINE}; margin-top: 14px; padding-top: 8px;
    color: {MUTED}; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 0; padding: 0 6px 0 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: {LINE}; }}
QDialog {{ background-color: {BG}; }}
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


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSizeF(10.0)
    app.setFont(font)
    pal = QPalette()
    for role, value in (
        (QPalette.ColorRole.Window, BG),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, SURFACE),
        (QPalette.ColorRole.AlternateBase, RAISED),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.Button, RAISED),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.Highlight, GREEN_BG),
        (QPalette.ColorRole.HighlightedText, TEXT),
    ):
        pal.setColor(role, QColor(value))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
