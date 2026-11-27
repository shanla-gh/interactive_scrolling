"""Brief 007 first-use guide."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel

from interactive_scrolling.ui.getting_started import GettingStartedDialog
from interactive_scrolling.ui.youtube_panel import EXTENSION_DIR
from tests.integration.test_control_ui import make_window


def test_guide_shows_once_and_remembers_dont_show(qtbot, tmp_path: Path) -> None:
    window, services = make_window(qtbot, tmp_path)
    assert services.user_settings.appearance.getting_started_done is False
    window.show_getting_started_if_new()
    dialog = window.getting_started
    assert isinstance(dialog, GettingStartedDialog) and dialog.isVisible()
    dialog.accept()
    qtbot.waitUntil(lambda: services.user_settings.appearance.getting_started_done)
    window.show_getting_started_if_new()
    assert window.getting_started is None  # not shown again


def test_guide_explains_stopping_and_the_extension_folder(qtbot) -> None:
    dialog = GettingStartedDialog("pairing-code-123", "Ctrl+Alt+Space")
    qtbot.addWidget(dialog)
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Ctrl+Alt+Space" in texts and "Stop control" in texts
    assert str(EXTENSION_DIR) in texts
    assert "next Short" in texts and "previous Short" in texts
