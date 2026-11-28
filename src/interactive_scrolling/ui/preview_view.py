"""Now playing: the live picture of the YouTube Short the user chose to show in the app.

The picture comes from the browser extension's tab capture (see
``integrations/youtube/preview.py``). It keeps the Short's own shape (no stretching), is
decoded only when a new frame arrived, and is never shown while the browser reports that the
tab left Shorts. Without a preview the widget explains in one sentence how to start one.
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from interactive_scrolling.integrations.youtube.preview import PreviewFeed, PreviewStatus
from interactive_scrolling.ui import theme

SHORTS_ASPECT = 9 / 16

HOW_TO = (
    "Watch here while you scroll.\n\nIn your browser, open a YouTube Short, click the "
    "Interactive Scrolling extension icon and choose “Show this Short in the app”."
)
NOT_CONNECTED = (
    "Your browser is not connected.\n\nSet up the Interactive Scrolling extension once "
    "(Settings, Browser), then open YouTube Shorts."
)


class PreviewView(QWidget):
    def __init__(self, feed: PreviewFeed | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.feed = feed
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(90, 160)
        self.image: QImage | None = None
        self._number: int | None = None
        self.status: PreviewStatus | None = None
        self.browser_connected = False
        self.decoded = 0
        """Frames decoded (each new frame once; repeated paints reuse it)."""

    # ------------------------------------------------------------------ state

    def refresh(self) -> bool:
        """Take the newest frame from the feed; returns True when the picture changed."""
        if self.feed is None:
            return False
        frame = self.feed.latest()
        if frame is None:
            if self.image is not None:
                self.image = None
                self._number = None
                self.update()
                return True
            return False
        if frame.number == self._number:
            return False
        image = QImage.fromData(frame.jpeg, "JPG")
        if image.isNull():
            return False
        self.image = image
        self._number = frame.number
        self.decoded += 1
        self.update()
        return True

    def set_status(self, status: PreviewStatus | None, browser_connected: bool) -> None:
        changed = (status is None) != (self.status is None) or (
            status is not None
            and self.status is not None
            and (status.state, status.reason) != (self.status.state, self.status.reason)
        )
        self.status = status
        if browser_connected != self.browser_connected:
            changed = True
        self.browser_connected = browser_connected
        if changed:
            self.update()

    def message(self) -> str:
        """The sentence shown instead of a picture."""
        status = self.status
        if status is not None and status.connected and status.state == "hidden":
            if "not on screen" in status.reason:
                return "The Short is not on screen in your browser tab."
            return (
                "Your browser tab left YouTube Shorts.\n\nThe picture returns when the tab "
                "shows a Short again."
            )
        if status is not None and status.connected:
            return "Waiting for the first picture..."
        if not self.browser_connected:
            return NOT_CONNECTED
        if status is not None and status.reason and status.reason != "waiting for the first frame":
            return f"Preview stopped: {status.reason}.\n\n{HOW_TO}"
        return HOW_TO

    # ------------------------------------------------------------------ painting

    def frame_rect(self) -> QRectF:
        """Where the 9:16 picture goes: as large as fits, centred (cinema area, Brief 010)."""
        w, h = self.width(), self.height()
        if w / max(1, h) > SHORTS_ASPECT:
            pw, ph = h * SHORTS_ASPECT, float(h)
        else:
            pw, ph = float(w), w / SHORTS_ASPECT
        return QRectF((w - pw) / 2, (h - ph) / 2, pw, ph)

    section = staticmethod(lambda name: contextlib.nullcontext())
    """Timing hook (the window sets it to ``StallMonitor.section``)."""

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        with self.section("preview paint"):
            self._paint()

    def _paint(self) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.frame_rect()
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        t = theme.tokens()
        painter.fillPath(path, QColor(t.media_bg if self.image is not None else t.surface_alt))
        if self.image is not None:
            painter.save()
            painter.setClipPath(path)
            img = self.image
            scale = min(rect.width() / img.width(), rect.height() / img.height())
            dw, dh = img.width() * scale, img.height() * scale
            target = QRectF(
                rect.x() + (rect.width() - dw) / 2, rect.y() + (rect.height() - dh) / 2, dw, dh
            )
            painter.drawImage(target, img)
            painter.restore()
        else:
            painter.setPen(QPen(QColor(t.border), 1))
            painter.drawPath(path)
            painter.setPen(QColor(t.text_muted))
            margin = 22
            text_rect = rect.adjusted(margin, margin, -margin, -margin)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self.message(),
            )
        painter.end()
