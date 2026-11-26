"""Optional inference workers, appearance settings and their persistence."""

from __future__ import annotations

import json
import time
from typing import ClassVar

import numpy as np
import pytest

from interactive_scrolling.config.settings import (
    AppearanceSettings,
    ConfigError,
    CreatorSettings,
    OverlayCorner,
)
from interactive_scrolling.core.auxiliary import AuxiliaryWorker
from interactive_scrolling.storage.settings_store import SettingsStore, UserSettings
from interactive_scrolling.vision.compositing import MaskCompositor
from tests.helpers import wait_until


class Counting:
    instances: ClassVar[list[Counting]] = []

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.closed = False
        self.fail = fail
        Counting.instances.append(self)

    def process(self, image: np.ndarray, timestamp_ms: int) -> int:
        self.calls += 1
        if self.fail:
            raise RuntimeError("broken model")
        return int(image[0, 0, 0])

    def close(self) -> None:
        self.closed = True


def frame(value: int = 7) -> np.ndarray:
    return np.full((8, 8, 3), value, dtype=np.uint8)


def test_disabled_worker_never_loads_its_model() -> None:
    Counting.instances.clear()
    worker = AuxiliaryWorker("test", Counting, max_fps=100)
    for _ in range(5):
        worker.submit(frame(), time.perf_counter_ns(), 1)
    time.sleep(0.2)
    assert Counting.instances == [] and worker.latest() is None
    worker.shutdown()


def test_enabled_worker_processes_latest_frame_and_closes_when_disabled() -> None:
    Counting.instances.clear()
    worker = AuxiliaryWorker("test", Counting, max_fps=100)
    worker.set_enabled(True)
    ts = time.perf_counter_ns()
    worker.submit(frame(42), ts, 3)
    assert wait_until(lambda: worker.latest() is not None)
    result = worker.latest()
    assert result.value == 42 and result.timestamp_ns == ts and result.session == 3
    assert worker.state == "running"
    worker.set_enabled(False)
    assert wait_until(lambda: Counting.instances[0].closed)
    assert worker.latest() is None
    worker.shutdown()


def test_worker_gets_a_read_only_view() -> None:
    seen: list[bool] = []

    class Probe(Counting):
        def process(self, image: np.ndarray, timestamp_ms: int) -> int:
            seen.append(image.flags.writeable)
            with pytest.raises(ValueError):
                image[0, 0, 0] = 1
            return 0

    worker = AuxiliaryWorker("test", Probe, max_fps=100)
    worker.set_enabled(True)
    original = frame(9)
    worker.submit(original, time.perf_counter_ns(), 1)
    assert wait_until(lambda: seen)
    assert seen == [False] and original.flags.writeable and original[0, 0, 0] == 9
    worker.shutdown()


def test_repeated_failures_make_the_worker_unavailable() -> None:
    worker = AuxiliaryWorker("test", lambda: Counting(fail=True), max_fps=1000)
    worker.set_enabled(True)
    for _ in range(40):
        worker.submit(frame(), time.perf_counter_ns(), 1)
        time.sleep(0.005)
    assert wait_until(lambda: worker.state == "unavailable", timeout_s=5)
    assert "repeated failures" in worker.message
    worker.shutdown()


def test_missing_model_is_reported_not_raised() -> None:
    def factory():
        raise FileNotFoundError("model not found")

    worker = AuxiliaryWorker("test", factory)
    worker.set_enabled(True)
    assert wait_until(lambda: worker.state == "unavailable")
    assert "model not found" in worker.message
    worker.shutdown()


def test_rate_limit() -> None:
    Counting.instances.clear()
    worker = AuxiliaryWorker("test", Counting, max_fps=10)
    worker.set_enabled(True)
    end = time.perf_counter() + 1.0
    while time.perf_counter() < end:
        worker.submit(frame(), time.perf_counter_ns(), 1)
        time.sleep(0.005)
    assert Counting.instances[0].calls <= 13
    worker.shutdown()


def test_mask_compositor_rejects_stale_or_foreign_masks() -> None:
    assert MaskCompositor.usable(1_000_000_000, 1, 1_200_000_000, 1)
    assert not MaskCompositor.usable(1_000_000_000, 1, 1_700_000_000, 1)
    assert not MaskCompositor.usable(1_000_000_000, 1, 1_000_000_000, 2)


def test_mask_compositor_soft_edges_and_smoothing() -> None:
    compositor = MaskCompositor()
    image = np.full((40, 40, 3), 200, dtype=np.uint8)
    mask = np.zeros((10, 10), dtype=np.float32)
    mask[:, :5] = 1.0
    rgba = compositor.compose(image, mask, 1, (40, 40))
    assert rgba.shape == (40, 40, 4)
    assert rgba[20, 2, 3] == 255 and rgba[20, 37, 3] == 0
    # A new, empty mask is blended with the previous one instead of switching off at once.
    rgba = compositor.compose(image, np.zeros((10, 10), np.float32), 2, (40, 40))
    assert 100 <= rgba[20, 2, 3] <= 160


@pytest.mark.parametrize(
    "overrides",
    [
        {"skeleton_color": "red"},
        {"skeleton_color": "#12345"},
        {"landmark_scale": 0.0},
        {"line_scale": 9.0},
        {"trail_length_s": True},
    ],
)
def test_invalid_appearance_is_rejected(overrides: dict) -> None:
    with pytest.raises(ConfigError):
        AppearanceSettings(**overrides)


def test_invalid_creator_settings_are_rejected() -> None:
    with pytest.raises(ConfigError):
        CreatorSettings(opacity=0.1)
    with pytest.raises(ConfigError):
        CreatorSettings(width=50)


def test_appearance_and_creator_settings_survive_restart(tmp_path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = UserSettings(
        appearance=AppearanceSettings(skeleton_color="#ff8800", landmark_scale=1.5),
        creator=CreatorSettings(x=10, y=20, corner=OverlayCorner.CUSTOM, show_counters=True),
    )
    assert store.save(settings)
    assert SettingsStore(tmp_path / "settings.json").load() == settings
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    raw["creator"]["opacity"] = 5
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    loaded_store = SettingsStore(tmp_path / "settings.json")
    loaded = loaded_store.load()
    assert loaded.creator.opacity == 1.0 and loaded.creator.x == 10
    assert any("creator.opacity" in w for w in loaded_store.warnings)
