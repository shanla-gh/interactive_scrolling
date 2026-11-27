"""Application-wide dark theme."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from interactive_scrolling.visualization import palette as p

UI_FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"]
MONO_FONT_FAMILIES = ["Cascadia Mono", "Consolas", "Courier New"]

STYLESHEET = f"""
QWidget {{
    background-color: {p.BACKGROUND};
    color: {p.TEXT};
    font-size: 10pt;
}}
QMainWindow::separator {{ background: {p.BORDER}; width: 1px; height: 1px; }}
QToolTip {{
    background-color: {p.SURFACE_RAISED}; color: {p.TEXT};
    border: 1px solid {p.BORDER}; padding: 4px 6px;
}}
#header {{ background-color: {p.SURFACE}; border-bottom: 1px solid {p.BORDER}; }}
#appTitle {{
    color: {p.TEXT}; font-size: 15pt; font-weight: 700; background: transparent;
}}
#appTitleAccent {{
    color: {p.ACCENT_GREEN}; font-size: 15pt; font-weight: 700; background: transparent;
}}
#appSubtitle {{ color: {p.TEXT_MUTED}; font-size: 9pt; background: transparent; }}
#card {{
    background-color: {p.SURFACE};
    border: 1px solid {p.BORDER};
    border-radius: 8px;
}}
#card QWidget {{ background-color: transparent; }}
#cardTitle {{
    color: {p.TEXT_MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px;
}}
#rowKey {{ color: {p.TEXT_MUTED}; }}
#rowValue {{ color: {p.TEXT}; font-family: "Cascadia Mono", "Consolas"; }}
#rowValueAccent {{
    color: {p.ACCENT_GREEN}; font-family: "Cascadia Mono", "Consolas"; font-weight: 600;
}}
#bigValue {{
    color: {p.ACCENT_GREEN}; font-family: "Cascadia Mono", "Consolas";
    font-size: 16pt; font-weight: 700;
}}
#subHeading {{ color: {p.TEXT_DIM}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
#statusPill {{
    border-radius: 10px; padding: 3px 10px; font-size: 8.5pt; font-weight: 700;
    background-color: {p.SURFACE_RAISED}; color: {p.TEXT_MUTED};
    border: 1px solid {p.BORDER};
}}
#statusPill[state="running"] {{ color: {p.ACCENT_GREEN}; border-color: #1f6b47; }}
#statusPill[state="starting"], #statusPill[state="stopping"] {{
    color: {p.ACCENT_AMBER}; border-color: #6b5220;
}}
#statusPill[state="error"] {{ color: {p.ACCENT_RED}; border-color: #6b2830; }}
QPushButton {{
    background-color: {p.SURFACE_RAISED}; color: {p.TEXT};
    border: 1px solid {p.BORDER}; border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {p.TEXT_DIM}; }}
QPushButton:disabled {{ color: {p.TEXT_DIM}; border-color: {p.SURFACE_RAISED}; }}
QPushButton#primaryButton {{
    background-color: #12352a; color: {p.ACCENT_GREEN}; border: 1px solid #1f6b47;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{ background-color: #174434; }}
QPushButton#primaryButton[running="true"] {{
    background-color: #3a1a20; color: {p.ACCENT_RED}; border-color: #6b2830;
}}
QComboBox {{
    background-color: {p.SURFACE_RAISED}; border: 1px solid {p.BORDER};
    border-radius: 6px; padding: 5px 10px; min-width: 70px;
}}
QComboBox:disabled {{ color: {p.TEXT_DIM}; }}
QComboBox QAbstractItemView {{
    background-color: {p.SURFACE_RAISED}; border: 1px solid {p.BORDER};
    selection-background-color: #12352a; selection-color: {p.ACCENT_GREEN};
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid {p.TEXT_DIM}; background: {p.SURFACE_RAISED};
}}
QCheckBox::indicator:checked {{ background: {p.ACCENT_GREEN}; border-color: {p.ACCENT_GREEN}; }}
QPlainTextEdit#activityLog {{
    background-color: {p.SURFACE}; border: 1px solid {p.BORDER}; border-radius: 8px;
    color: {p.TEXT_MUTED}; font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt;
    padding: 4px;
}}
#statusBar {{ background-color: {p.SURFACE}; border-top: 1px solid {p.BORDER}; }}
#statusBar QLabel {{
    background: transparent; color: {p.TEXT_MUTED};
    font-family: "Cascadia Mono", "Consolas"; font-size: 8.5pt;
}}
#statusBar QLabel#privacyBadge {{ color: {p.ACCENT_GREEN}; }}
QScrollArea {{ border: none; }}
#controlBar {{ background-color: {p.BACKGROUND}; border-bottom: 1px solid {p.BORDER}; }}
#controlBar[live="true"] {{ background-color: #1d1113; border-bottom: 1px solid #6b2830; }}
QPushButton#modeButton {{ padding: 5px 12px; color: {p.TEXT_MUTED}; }}
QPushButton#modeButton:checked {{
    background-color: #12352a; color: {p.ACCENT_GREEN}; border-color: #1f6b47; font-weight: 700;
}}
QPushButton#modeButton[mode="live_control"]:checked {{
    background-color: #3a1a20; color: {p.ACCENT_RED}; border-color: {p.ACCENT_RED};
}}
QPushButton#disableButton {{
    background-color: #3a1a20; color: {p.ACCENT_RED}; border: 1px solid #6b2830; font-weight: 700;
}}
QPushButton#disableButton:disabled {{
    background-color: {p.SURFACE_RAISED}; color: {p.TEXT_DIM}; border-color: {p.BORDER};
}}
QLabel#chip {{
    background-color: {p.SURFACE}; border: 1px solid {p.BORDER}; border-radius: 10px;
    padding: 3px 10px; color: {p.TEXT_MUTED}; font-size: 9pt;
}}
QLabel#chip[state="ok"] {{ color: {p.ACCENT_GREEN}; border-color: #1f6b47; }}
QLabel#chip[state="warn"] {{ color: {p.ACCENT_AMBER}; }}
QTabWidget#sideTabs::pane {{ border: none; }}
QTabBar::tab {{
    background: {p.SURFACE}; color: {p.TEXT_MUTED}; padding: 6px 9px; margin-right: 2px;
    border: 1px solid {p.BORDER}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {p.SURFACE_RAISED}; color: {p.ACCENT_GREEN}; }}
QTableWidget#gestureHistory {{
    background-color: {p.SURFACE}; border: 1px solid {p.BORDER}; border-radius: 8px;
    gridline-color: {p.SURFACE_RAISED}; font-family: "Cascadia Mono", "Consolas";
    font-size: 8.5pt;
}}
QHeaderView::section {{
    background-color: {p.SURFACE_RAISED}; color: {p.TEXT_MUTED}; border: none; padding: 4px;
    font-size: 8pt; font-weight: 700;
}}
QProgressBar {{ background: {p.SURFACE_RAISED}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {p.ACCENT_AMBER}; border-radius: 3px; }}
QGroupBox {{
    border: 1px solid {p.BORDER}; border-radius: 8px; margin-top: 12px; padding-top: 6px;
    color: {p.TEXT_MUTED}; font-weight: 700;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QDoubleSpinBox {{
    background-color: {p.SURFACE_RAISED}; border: 1px solid {p.BORDER}; border-radius: 6px;
    padding: 3px 6px;
}}
QScrollBar:vertical {{ background: {p.BACKGROUND}; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QSplitter::handle {{ background: {p.BACKGROUND}; }}
"""


def mono_font(point_size: float = 9.0, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FONT_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(point_size)
    font.setBold(bold)
    return font


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSizeF(10.0)
    app.setFont(font)
    pal = QPalette()
    for role, value in (
        (QPalette.ColorRole.Window, p.BACKGROUND),
        (QPalette.ColorRole.WindowText, p.TEXT),
        (QPalette.ColorRole.Base, p.SURFACE),
        (QPalette.ColorRole.AlternateBase, p.SURFACE_RAISED),
        (QPalette.ColorRole.Text, p.TEXT),
        (QPalette.ColorRole.Button, p.SURFACE_RAISED),
        (QPalette.ColorRole.ButtonText, p.TEXT),
        (QPalette.ColorRole.Highlight, "#12352a"),
        (QPalette.ColorRole.HighlightedText, p.ACCENT_GREEN),
    ):
        pal.setColor(role, QColor(value))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
