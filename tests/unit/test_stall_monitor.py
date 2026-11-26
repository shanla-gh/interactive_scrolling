"""UI stall detection and attribution (the test thread plays the UI thread)."""

from __future__ import annotations

import gc
import threading
import time

from interactive_scrolling.core.stall_monitor import StallMonitor
from tests.helpers import wait_until


def beat_for(monitor: StallMonitor, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        monitor.beat()
        time.sleep(0.01)


def test_stall_is_attributed_to_the_running_section() -> None:
    monitor = StallMonitor(threshold_ms=80)
    monitor.start()
    try:
        beat_for(monitor, 0.1)
        with monitor.section("slow handler"):
            time.sleep(0.25)
        beat_for(monitor, 0.1)
        assert wait_until(lambda: monitor.stall_count == 1, timeout_s=2)
        stall = monitor.stalls[0]
        assert stall.section == "slow handler"
        assert 200 <= stall.duration_ms < 1000
        assert any("sleep" in line for line in stall.ui_stack)
        stats = monitor.section_stats()["slow handler"]
        assert stats.calls == 1 and stats.max_ms >= 240
        assert "slow handler" in stall.summary()
    finally:
        monitor.stop()


def test_regular_heartbeats_are_not_stalls() -> None:
    monitor = StallMonitor(threshold_ms=80)
    monitor.start()
    try:
        beat_for(monitor, 0.4)
        assert monitor.stall_count == 0
    finally:
        monitor.stop()


def test_paused_worker_is_reported_with_the_stall() -> None:
    monitor = StallMonitor(threshold_ms=80)
    stop = threading.Event()
    pause = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            if pause.is_set():
                time.sleep(0.3)
                pause.clear()
            monitor.worker_progress("processing")
            time.sleep(0.01)

    thread = threading.Thread(target=worker, daemon=True)
    monitor.start()
    thread.start()
    try:
        beat_for(monitor, 0.1)
        pause.set()
        time.sleep(0.3)  # the UI and the worker pause together (process-wide)
        beat_for(monitor, 0.2)
        assert wait_until(lambda: monitor.stall_count >= 1, timeout_s=2)
        assert monitor.stalls[0].worker_gaps_ms["processing"] >= 150
    finally:
        stop.set()
        thread.join(1)
        monitor.stop()


def test_garbage_collection_during_a_stall_is_measured() -> None:
    monitor = StallMonitor(threshold_ms=50)
    monitor.start()
    try:
        beat_for(monitor, 0.05)
        junk = [[{"i": i}] for i in range(300_000)]
        start = time.perf_counter()
        while time.perf_counter() - start < 0.15:
            gc.collect()
        del junk
        beat_for(monitor, 0.1)
        assert wait_until(lambda: monitor.stall_count >= 1, timeout_s=2)
        assert monitor.stalls[0].gc_ms > 0
    finally:
        monitor.stop()


def test_stop_removes_the_gc_callback() -> None:
    monitor = StallMonitor()
    monitor.start()
    monitor.stop()
    assert monitor._gc_callback not in gc.callbacks
