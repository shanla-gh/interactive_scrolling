"""The once-per-second resource sample blocked the UI thread for ~13 ms.

Found by the UI stall monitor in Integration Audit 003 (Brief 003): ``ResourceMonitor.sample``
called ``psutil.Process.num_threads()``, which on Windows enumerates every process and thread
of the system (13 ms per call on the development machine, more under load). The window called
it on the UI thread every second although it never displays the thread count. Counting threads
is now opt-in and the window does not request it.
"""

from __future__ import annotations

from unittest import mock

import psutil

from interactive_scrolling.core.diagnostics import ResourceMonitor


def test_default_sample_does_not_enumerate_threads() -> None:
    monitor = ResourceMonitor()
    with mock.patch.object(psutil.Process, "num_threads", side_effect=AssertionError("slow")):
        sample = monitor.sample()
    assert sample.thread_count is None
    assert sample.rss_mb > 0


def test_thread_count_is_available_on_request() -> None:
    sample = ResourceMonitor().sample(include_threads=True)
    assert sample.thread_count is not None and sample.thread_count >= 1


def test_main_window_resource_sampling_does_not_request_threads(qtbot) -> None:
    from interactive_scrolling.config.settings import AppSettings
    from interactive_scrolling.ui.main_window import MainWindow
    from tests.helpers import camera_factory

    calls: list[bool] = []

    class Recording(ResourceMonitor):
        def sample(self, include_threads: bool = False):  # type: ignore[override]
            calls.append(include_threads)
            return super().sample(include_threads)

    window = MainWindow(
        AppSettings(),
        camera_factory=camera_factory(),
        tracker_factory=None,
        resource_monitor=Recording(),
    )
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: len(calls) >= 1, timeout=3000)
    assert calls and not any(calls)
    window.close()
