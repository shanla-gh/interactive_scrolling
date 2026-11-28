"""Doomscroll Wrapped: real statistics, 1080 x 1920 layout without clipping, PNG export."""

from __future__ import annotations

import itertools
from datetime import date

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage

from interactive_scrolling.ui.wrapped import (
    HEIGHT,
    WIDTH,
    WrappedData,
    WrappedDialog,
    render_wrapped,
    wrapped_from_report,
    wrapped_from_session,
)
from interactive_scrolling.wellbeing.index import doomscroll_index
from interactive_scrolling.wellbeing.report import DailyReport
from interactive_scrolling.wellbeing.sessions import Session


def report(scroll_s: float = 4320, sessions: int = 3) -> DailyReport:
    items = tuple(Session(i * 1000.0, i * 1000.0 + 600, 600.0) for i in range(sessions))
    return DailyReport(
        day=date(2026, 11, 26),
        scrolling_s=scroll_s,
        sessions=items,
        shorts_open_s=scroll_s + 100,
        gestures={"index_swipe_down": 40},
        gestures_total=57,
        succeeded={
            "next_short": 38,
            "previous_short": 4,
            "next_browser_tab": 5,
            "previous_browser_tab": 2,
            "like_short": 3,
        },
        no_change=1,
        rejected=2,
        failed=0,
        unknown=0,
        not_executed=0,
        index=doomscroll_index(scroll_s, 600, 60, 20),
    )


class _Eyes:
    screen_s, away_s, unknown_s = 1800.0, 300.0, 420.0


EYES = _Eyes()


def test_eye_analytics_line_shows_unknown_time_too(qtbot) -> None:
    shown = [t for t, _ in texts(wrapped_from_report(report(), humorous=True, eye_report=EYES))]
    line = next(t for t in shown if t.startswith("Eyes (estimated)"))
    assert "30 min 00 s facing the screen" in line and "7 min 00 s unknown" in line
    plain = [t for t, _ in texts(wrapped_from_report(report(), humorous=True))]
    assert not any(t.startswith("Eyes") for t in plain)


def texts(data: WrappedData) -> list[tuple[str, QRectF]]:
    image, layout = render_wrapped(data)
    assert (image.width(), image.height()) == (WIDTH, HEIGHT)
    return layout.texts


@pytest.mark.parametrize(
    "data",
    [
        wrapped_from_report(report(), humorous=True),
        wrapped_from_report(report(scroll_s=0, sessions=0), humorous=False),
        wrapped_from_report(report(scroll_s=99 * 3600 + 59 * 60, sessions=12), humorous=True),
        wrapped_from_session(1500, 12, {"next_short": 9}, 60, 20, humorous=True),
        wrapped_from_report(report(), humorous=True, eye_report=EYES),
    ],
    ids=["typical", "empty", "huge", "session", "with_eyes"],
)
def test_layout_fits_the_card_without_overlaps(qtbot, data: WrappedData) -> None:
    boxes = texts(data)
    canvas = QRectF(0, 0, WIDTH, HEIGHT)
    for text, box in boxes:
        assert canvas.contains(box), f"{text!r} is clipped: {box}"
    for (a, ra), (b, rb) in itertools.combinations(boxes, 2):
        assert not ra.intersects(rb), f"{a!r} overlaps {b!r}"


def test_card_shows_the_real_numbers(qtbot) -> None:
    data = wrapped_from_report(report(), humorous=True)
    shown = [t for t, _ in texts(data)]
    assert "1 h 12 min" in shown  # 4320 s
    assert "38 / 4" in shown and "5 / 2" in shown and "3" in shown and "57" in shown
    assert str(data.index.value) in shown
    assert not any("thumbs" in t.lower() or "academic" in t.lower() for t in shown)


def test_session_card_uses_session_counts(qtbot) -> None:
    data = wrapped_from_session(
        25 * 60, 14, {"next_short": 11, "like_short": 2}, 60, 20, humorous=False
    )
    shown = [t for t, _ in texts(data)]
    assert data.scope == "This session" and "25 min 00 s" in shown
    assert "11 / 0" in shown and "14" in shown


def test_export_writes_a_1080_by_1920_png(qtbot, tmp_path) -> None:
    image, _ = render_wrapped(wrapped_from_report(report(), humorous=True))
    dialog = WrappedDialog(image, "card.png")
    qtbot.addWidget(dialog)
    target = tmp_path / "my card"
    assert dialog.save(str(target))
    saved = QImage(str(target) + ".png")
    assert (saved.width(), saved.height()) == (1080, 1920)
