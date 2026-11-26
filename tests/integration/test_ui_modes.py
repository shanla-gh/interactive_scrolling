"""Three presentation modes on one shared runtime, the creator overlay and its transparency."""

from __future__ import annotations

import threading

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import (
    AppearanceSettings,
    AppSettings,
    CameraSettings,
    CreatorSettings,
)
from interactive_scrolling.core.pipeline import CameraState, TrackerState
from interactive_scrolling.ui.creator_overlay import CreatorOverlay
from interactive_scrolling.ui.main_window import MainWindow
from tests.helpers import ScriptedTracker, SyntheticCamera, camera_factory, make_hand


class FakeSegmenter:
    """Person mask: the left half of the image is the person."""

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False
        self.writeable: list[bool] = []
        self.thread = None

    def process(self, image_rgb: np.ndarray, timestamp_ms: int) -> np.ndarray:
        self.calls += 1
        self.writeable.append(bool(image_rgb.flags.writeable))
        self.thread = threading.get_ident()
        h, w = image_rgb.shape[:2]
        mask = np.zeros((h // 4, w // 4), dtype=np.float32)
        mask[:, : (w // 8)] = 1.0
        return mask

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset() -> None:
    SyntheticCamera.instances.clear()


def make_window(qtbot, segmenter: FakeSegmenter | None = None) -> MainWindow:
    tracker = ScriptedTracker(lambda ms: (make_hand((320, 300), palm_px=80),))
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=640, height=480)),
        camera_factory=camera_factory(fps=60),
        tracker_factory=lambda: tracker,
        segmenter_factory=(lambda: segmenter) if segmenter is not None else None,
    )
    window.tracker = tracker  # type: ignore[attr-defined]
    qtbot.addWidget(window)
    qtbot.addWidget(window.creator)
    window.show()
    qtbot.waitUntil(lambda: window.pipeline.tracker_state is TrackerState.READY, timeout=5000)
    return window


def start(qtbot, window: MainWindow) -> None:
    assert window.start_camera()
    qtbot.waitUntil(lambda: window.video.frame is not None, timeout=5000)


def render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    widget.render(image)
    return image


def test_overlay_window_is_frameless_on_top_and_never_takes_focus(qtbot) -> None:
    overlay = CreatorOverlay(CreatorSettings(), AppearanceSettings())
    qtbot.addWidget(overlay)
    flags = overlay.windowFlags()
    for flag in (
        Qt.WindowType.FramelessWindowHint,
        Qt.WindowType.WindowStaysOnTopHint,
        Qt.WindowType.WindowDoesNotAcceptFocus,
        Qt.WindowType.Tool,
    ):
        assert flags & flag
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert overlay.focusPolicy() is Qt.FocusPolicy.NoFocus


def test_mode_switches_share_one_runtime(qtbot) -> None:
    window = make_window(qtbot)
    start(qtbot, window)
    pipeline, dispatcher, engine = (
        window.pipeline,
        window.services.dispatcher,
        window.services.engine,
    )
    session = window.pipeline.session
    window.set_control_mode(ControlMode.GESTURE_TEST)
    threads_before = {t.name for t in threading.enumerate()}
    for mode in ("creator", "developer", "creator", "developer"):
        window.set_ui_mode(mode)
        qtbot.wait(150)
        assert window.pipeline is pipeline and window.services.dispatcher is dispatcher
        assert window.services.engine is engine
        assert window.pipeline.camera_state is CameraState.RUNNING
        assert window.pipeline.session == session  # the camera was never restarted
        assert window.services.dispatcher.mode is ControlMode.GESTURE_TEST
    assert len(SyntheticCamera.instances) == 1  # one camera for all modes
    captures = [t for t in threading.enumerate() if t.name.startswith("camera-capture")]
    assert len(captures) == 1
    assert {t.name for t in threading.enumerate()} <= threads_before | {"stall-monitor"}
    window.set_ui_mode("creator")
    qtbot.waitUntil(lambda: window.creator._frame is not None, timeout=3000)
    assert window.creator.isVisible() and not window.isVisible()
    window.set_ui_mode("developer")
    assert window.isVisible() and not window.creator.isVisible()


def test_emergency_disable_works_while_in_creator_mode(qtbot) -> None:
    window = make_window(qtbot)
    start(qtbot, window)
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    window.set_ui_mode("creator")
    window.emergency_disable()
    qtbot.waitUntil(lambda: window.services.dispatcher.mode is ControlMode.TRACKING_ONLY)


def test_background_mode_needs_a_tray(qtbot) -> None:
    window = make_window(qtbot)
    if window.tray.available:
        window.set_ui_mode("background")
        assert not window.isVisible() and not window.creator.isVisible()
    else:  # offscreen test platform: no tray, so the window must stay visible
        window.set_ui_mode("background")
        assert window.isVisible()
    with pytest.raises(ValueError):
        window.set_ui_mode("skeleton-only")


def test_segmentation_runs_only_while_the_transparent_overlay_is_shown(qtbot) -> None:
    segmenter = FakeSegmenter()
    window = make_window(qtbot, segmenter)
    start(qtbot, window)
    qtbot.wait(300)
    assert segmenter.calls == 0  # not loaded or run while disabled
    window.creator.apply_settings(CreatorSettings(transparent_background=True))
    window.set_ui_mode("creator")
    qtbot.waitUntil(lambda: segmenter.calls >= 3, timeout=5000)
    # The worker only ever sees read-only frames and runs off the UI and processing threads.
    assert not any(segmenter.writeable)
    assert segmenter.thread not in (threading.main_thread().ident,)
    window.set_ui_mode("developer")
    qtbot.waitUntil(lambda: segmenter.closed, timeout=3000)
    calls = segmenter.calls
    qtbot.wait(300)
    assert segmenter.calls == calls


def test_hand_tracker_receives_unmodified_frames_with_transparency_on(qtbot) -> None:
    segmenter = FakeSegmenter()
    window = make_window(qtbot, segmenter)
    window.creator.apply_settings(CreatorSettings(transparent_background=True))
    window.set_ui_mode("creator")
    start(qtbot, window)
    qtbot.waitUntil(lambda: segmenter.calls >= 3, timeout=5000)
    frame = window.video.frame
    assert frame is not None
    # Synthetic camera frames are pure blue (BGR 255,0,0 -> RGB 0,0,255) except pixel (0, 0).
    assert (frame.image_rgb[1:, :, 2] == 255).all() and (frame.image_rgb[1:, :, :2] == 0).all()
    assert all(shape == (480, 640, 3) for shape in window.tracker.shapes)  # type: ignore[attr-defined]


def test_transparent_overlay_removes_background_and_hides_camera_without_mask(qtbot) -> None:
    segmenter = FakeSegmenter()
    window = make_window(qtbot, segmenter)
    overlay = window.creator
    overlay.apply_settings(
        CreatorSettings(width=320, height=240, transparent_background=True, show_skeleton=False)
    )
    overlay.mirrored = False
    window.set_ui_mode("creator")
    start(qtbot, window)
    qtbot.waitUntil(lambda: segmenter.calls >= 3, timeout=5000)
    qtbot.waitUntil(lambda: overlay._frame is not None, timeout=3000)
    image = render(overlay)
    assert overlay.transparent_state == "active"
    person = image.pixelColor(40, 120)
    background = image.pixelColor(280, 120)
    assert person.alpha() > 200 and person.blue() > 150
    assert background.alpha() < 40

    # Segmentation stops delivering (e.g. model failure): the camera image must disappear.
    window.segmenter.set_enabled(False)  # type: ignore[union-attr]
    qtbot.wait(200)
    image = render(overlay)
    assert overlay.transparent_state == "unavailable"
    assert image.pixelColor(280, 200).blue() < 150 or image.pixelColor(280, 200).alpha() < 40
    assert image.pixelColor(40, 200).alpha() < 40


def test_opaque_overlay_shows_the_camera(qtbot) -> None:
    window = make_window(qtbot)
    overlay = window.creator
    overlay.apply_settings(CreatorSettings(width=320, height=240, show_skeleton=False))
    window.set_ui_mode("creator")
    start(qtbot, window)
    qtbot.waitUntil(lambda: overlay._frame is not None, timeout=3000)
    color = render(overlay).pixelColor(160, 120)
    assert color.alpha() == 255 and color.blue() > 200
    assert overlay.transparent_state == "off"


def test_overlay_settings_are_persisted_through_services(qtbot, tmp_path) -> None:
    from interactive_scrolling.services import build_services
    from interactive_scrolling.storage.settings_store import SettingsStore

    services = build_services(tmp_path, start_bridge=False)
    try:
        window = MainWindow(
            AppSettings(), camera_factory=camera_factory(), tracker_factory=None, services=services
        )
        qtbot.addWidget(window)
        window.creator._toggle("show_counters", True)
        stored = SettingsStore(tmp_path / "settings.json").load()
        assert stored.creator.show_counters is True
        window.close()
    finally:
        services.shutdown()
