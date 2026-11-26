"""Doomscroll Wrapped: a 9:16 summary card (1080 x 1920 PNG) from real statistics.

The card is rendered with QPainter from a :class:`WrappedData` built from the local reports
(today) or the current scrolling session, so every number on it comes from recorded events.
There is no photo, no name, no account information and no upload: the user previews the card
and chooses where to save the PNG. Text that would not fit is drawn smaller rather than
clipped, and every drawn text box is recorded in ``CardLayout`` for the automated layout tests.

Visual identity: dark background with a deep violet-to-black gradient, one hot accent
(red/coral, matching the clown nose) and one cool accent (cyan), bold condensed numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from interactive_scrolling.ui.report_panels import duration
from interactive_scrolling.wellbeing.index import DoomscrollIndex, doomscroll_index
from interactive_scrolling.wellbeing.report import DailyReport

WIDTH, HEIGHT = 1080, 1920
MARGIN = 84
HOT = "#ff3b5c"
COOL = "#3de0ff"
INK = "#f4f1ff"
MUTED = "#a69fc4"


@dataclass(frozen=True, slots=True)
class WrappedData:
    scope: str
    """"Today" or "This session" (or a co-op title)."""
    date_text: str
    scrolling_s: float
    sessions: int | None
    longest_s: float | None
    next_previous: tuple[int, int]
    tabs: tuple[int, int]
    likes: int
    gestures: int
    index: DoomscrollIndex | None
    title: str
    """Optional humorous or plain headline."""
    participants: tuple[tuple[str, int], ...] = ()
    """Co-op only: (participant name, successful shared actions)."""


@dataclass
class CardLayout:
    texts: list[tuple[str, QRectF]] = field(default_factory=list)


def _font(size: float, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont("Segoe UI")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPixelSize(max(8, int(size)))
    font.setWeight(weight)
    return font


def _fit(font: QFont, text: str, width: float) -> QFont:
    size = font.pixelSize()
    while size > 10 and QFontMetricsF(font).horizontalAdvance(text) > width:
        size -= 2
        font.setPixelSize(size)
    return font


def _text(
    painter: QPainter,
    layout: CardLayout,
    text: str,
    rect: QRectF,
    size: float,
    color: str,
    weight: QFont.Weight = QFont.Weight.Bold,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
) -> QRectF:
    font = _fit(_font(size, weight), text, rect.width())
    painter.setFont(font)
    painter.setPen(QColor(color))
    metrics = QFontMetricsF(font)
    box = QRectF(rect.left(), rect.top(), rect.width(), metrics.height())
    painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)
    advance = metrics.horizontalAdvance(text)
    if align & Qt.AlignmentFlag.AlignHCenter:
        used = QRectF(box.center().x() - advance / 2, box.top(), advance, box.height())
    elif align & Qt.AlignmentFlag.AlignRight:
        used = QRectF(box.right() - advance, box.top(), advance, box.height())
    else:
        used = QRectF(box.left(), box.top(), advance, box.height())
    layout.texts.append((text, used))
    return box


def render_wrapped(data: WrappedData, humorous: bool = True) -> tuple[QImage, CardLayout]:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
    layout = CardLayout()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    background = QLinearGradient(0, 0, WIDTH * 0.4, HEIGHT)
    background.setColorAt(0.0, QColor("#2a1250"))
    background.setColorAt(0.55, QColor("#120a24"))
    background.setColorAt(1.0, QColor("#06040c"))
    painter.fillRect(image.rect(), QBrush(background))
    for center, radius, color, alpha in (
        (QPointF(WIDTH * 0.95, 260), 520, HOT, 0.35),
        (QPointF(-60, HEIGHT * 0.62), 620, COOL, 0.18),
    ):
        glow = QRadialGradient(center, radius)
        c = QColor(color)
        c.setAlphaF(alpha)
        glow.setColorAt(0.0, c)
        c.setAlphaF(0.0)
        glow.setColorAt(1.0, c)
        painter.fillRect(image.rect(), QBrush(glow))

    inner = WIDTH - 2 * MARGIN
    y = 120.0
    _text(painter, layout, "DOOMSCROLL WRAPPED", QRectF(MARGIN, y, inner, 0), 40, HOT)
    y += 62
    _text(
        painter,
        layout,
        f"{data.scope}  ·  {data.date_text}",
        QRectF(MARGIN, y, inner, 0),
        34,
        MUTED,
        QFont.Weight.Medium,
    )
    y += 110
    _text(painter, layout, duration(data.scrolling_s), QRectF(MARGIN, y, inner, 0), 150, INK)
    y += 190
    _text(
        painter,
        layout,
        "of Shorts playing in front of you",
        QRectF(MARGIN, y, inner, 0),
        40,
        MUTED,
        QFont.Weight.Medium,
    )
    y += 110

    # Doomscroll Index gauge
    gauge = QRectF(MARGIN, y, 330, 330)
    painter.setPen(
        QPen(QColor(255, 255, 255, 40), 26, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
    )
    painter.drawArc(gauge.adjusted(13, 13, -13, -13), 225 * 16, -270 * 16)
    if data.index is not None:
        ring = QLinearGradient(gauge.topLeft(), gauge.bottomRight())
        ring.setColorAt(0.0, QColor(COOL))
        ring.setColorAt(1.0, QColor(HOT))
        painter.setPen(QPen(QBrush(ring), 26, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(
            gauge.adjusted(13, 13, -13, -13), 225 * 16, int(-270 * 16 * data.index.value / 100)
        )
    value = str(data.index.value) if data.index is not None else "-"
    _text(
        painter,
        layout,
        value,
        QRectF(gauge.left(), gauge.center().y() - 80, gauge.width(), 0),
        120,
        INK,
        align=Qt.AlignmentFlag.AlignHCenter,
    )
    _text(
        painter,
        layout,
        "DOOMSCROLL INDEX",
        QRectF(gauge.left(), gauge.bottom() + 4, gauge.width(), 0),
        26,
        MUTED,
        align=Qt.AlignmentFlag.AlignHCenter,
    )
    label_x = gauge.right() + 50
    label_w = WIDTH - MARGIN - label_x
    label = data.index.label(humorous) if data.index is not None else "No data"
    _text(painter, layout, label, QRectF(label_x, y + 90, label_w, 0), 58, HOT)
    _text(
        painter,
        layout,
        "0-100, lower is better",
        QRectF(label_x, y + 170, label_w, 0),
        30,
        MUTED,
        QFont.Weight.Medium,
    )
    y = gauge.bottom() + 100

    stats: list[tuple[str, str]] = [
        ("SESSIONS", "-" if data.sessions is None else str(data.sessions)),
        ("LONGEST", "-" if data.longest_s is None else duration(data.longest_s)),
        ("NEXT / PREV", f"{data.next_previous[0]} / {data.next_previous[1]}"),
        ("TABS  → / ←", f"{data.tabs[0]} / {data.tabs[1]}"),
        ("LIKES", str(data.likes)),
        ("SHARED ACTIONS" if data.participants else "GESTURES", str(data.gestures)),
    ]
    col_w = (inner - 40) / 2
    for i, (name, number) in enumerate(stats):
        col, row = i % 2, i // 2
        x = MARGIN + col * (col_w + 40)
        top = y + row * 200
        card = QRectF(x, top, col_w, 170)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(card, 28, 28)
        _text(painter, layout, name, QRectF(x + 36, top + 26, col_w - 72, 0), 28, MUTED)
        _text(painter, layout, number, QRectF(x + 36, top + 70, col_w - 72, 0), 66, INK)
    y += 3 * 200 + 20

    if data.participants:
        line = "   ".join(f"{name}: {count}" for name, count in data.participants)
        _text(painter, layout, line, QRectF(MARGIN, y, inner, 0), 40, COOL)
        y += 70
    if data.title:
        _text(painter, layout, f"“{data.title}”", QRectF(MARGIN, y, inner, 0), 52, INK)
    _text(
        painter,
        layout,
        "interactive scrolling · counted on-device, nothing uploaded",
        QRectF(MARGIN, HEIGHT - 120, inner, 0),
        28,
        MUTED,
        QFont.Weight.Medium,
        Qt.AlignmentFlag.AlignHCenter,
    )
    painter.end()
    return image, layout


TITLES = (
    (20, "Touched grass today"),
    (40, "Scrolled with restraint"),
    (60, "The algorithm knows my name"),
    (80, "One more Short, they said"),
    (101, "Professional clown, unpaid"),
)


def headline(index: DoomscrollIndex | None, humorous: bool) -> str:
    if index is None:
        return ""
    if not humorous:
        return f"Doomscroll Index {index.value}"
    return next(text for limit, text in TITLES if index.value < limit)


def date_text(when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{when:%a} {when.day} {when:%b %Y}"


def wrapped_from_report(report: DailyReport, humorous: bool) -> WrappedData:
    return WrappedData(
        scope="Today",
        date_text=date_text(datetime.combine(report.day, datetime.min.time())),
        scrolling_s=report.scrolling_s,
        sessions=report.session_count,
        longest_s=report.longest_session_s,
        next_previous=(report.done("next_short"), report.done("previous_short")),
        tabs=(report.done("next_browser_tab"), report.done("previous_browser_tab")),
        likes=report.done("like_short"),
        gestures=report.gestures_total,
        index=report.index,
        title=headline(report.index, humorous),
    )


def wrapped_from_session(
    session_s: float,
    gestures: int,
    succeeded: dict[str, int],
    daily_budget_min: float,
    session_limit_min: float,
    humorous: bool,
) -> WrappedData:
    """The current scrolling session. Its index treats the session as the whole day."""
    index = doomscroll_index(session_s, session_s, daily_budget_min, session_limit_min)
    return WrappedData(
        scope="This session",
        date_text=date_text(),
        scrolling_s=session_s,
        sessions=None,
        longest_s=None,
        next_previous=(succeeded.get("next_short", 0), succeeded.get("previous_short", 0)),
        tabs=(succeeded.get("next_browser_tab", 0), succeeded.get("previous_browser_tab", 0)),
        likes=succeeded.get("like_short", 0),
        gestures=gestures,
        index=index,
        title=headline(index, humorous),
    )


class WrappedDialog(QDialog):
    """Preview and deliberate export (the user chooses the file; nothing is uploaded)."""

    def __init__(self, image: QImage, default_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Doomscroll Wrapped")
        self.image = image
        self.default_name = default_name
        self.saved_path: str | None = None
        layout = QVBoxLayout(self)
        preview = QLabel()
        from PySide6.QtGui import QPixmap

        preview.setPixmap(
            QPixmap.fromImage(image).scaledToHeight(640, Qt.TransformationMode.SmoothTransformation)
        )
        layout.addWidget(preview)
        row = QHBoxLayout()
        save = QPushButton("Save PNG (1080 x 1920)...")
        save.clicked.connect(self.save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(close)
        layout.addLayout(row)
        self.status = QLabel("Nothing is shared or uploaded. You choose where the file goes.")
        self.status.setObjectName("rowKey")
        layout.addWidget(self.status)

    def save(self, path: str | None = None) -> bool:
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Doomscroll Wrapped", self.default_name, "PNG image (*.png)"
            )
        if not path:
            return False
        if not path.lower().endswith(".png"):
            path += ".png"
        ok = self.image.save(path, "PNG")
        self.saved_path = path if ok else None
        self.status.setText(f"Saved to {path}" if ok else f"Could not save to {path}")
        return ok
