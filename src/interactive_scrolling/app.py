"""Application entry point: ``interactive-scrolling`` or ``python -m interactive_scrolling``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from interactive_scrolling import __version__
from interactive_scrolling.config.settings import (
    AppSettings,
    CameraBackend,
    CameraSettings,
    ConfigError,
    TrackingSettings,
)

log = logging.getLogger("interactive_scrolling")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="interactive-scrolling",
        description="Real-time, local hand tracking with live skeleton and motion visualization.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default: 0)")
    parser.add_argument(
        "--resolution",
        default="1280x720",
        help="requested capture resolution WIDTHxHEIGHT (default: 1280x720)",
    )
    parser.add_argument(
        "--backend",
        choices=[b.value for b in CameraBackend],
        default=CameraBackend.MSMF.value,
        help="OpenCV capture backend (default: msmf)",
    )
    parser.add_argument("--model", type=Path, default=None, help="path to hand_landmarker.task")
    parser.add_argument("--max-hands", type=int, default=2, help="maximum hands to track (1-4)")
    parser.add_argument("--no-mirror", action="store_true", help="start with mirroring disabled")
    parser.add_argument(
        "--auto-start", action="store_true", help="start the camera immediately after launch"
    )
    parser.add_argument(
        "--allow-power-throttling",
        action="store_true",
        help="keep Windows' default power throttling (lower power use, slower tracking)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="console log level (default: INFO)",
    )
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> AppSettings:
    try:
        width_text, height_text = args.resolution.lower().split("x")
        width, height = int(width_text), int(height_text)
    except ValueError as exc:
        raise ConfigError(
            f"Invalid resolution '{args.resolution}', expected WIDTHxHEIGHT."
        ) from exc
    return AppSettings(
        camera=CameraSettings(
            index=args.camera, width=width, height=height, backend=CameraBackend(args.backend)
        ),
        tracking=TrackingSettings(model_path=args.model, num_hands=args.max_hands),
        mirror_preview=not args.no_mirror,
    )


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Filter on the console handlers, so that loggers set to a lower level for the UI
    # activity log do not make the console more verbose than requested.
    for handler in logging.getLogger().handlers:
        handler.setLevel(numeric)
    # MediaPipe and OpenCV write verbose native logs to stderr; keep only errors.
    os.environ.setdefault("GLOG_minloglevel", "2")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        settings = build_settings(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.allow_power_throttling:
        from interactive_scrolling.core.platform import disable_power_throttling

        disable_power_throttling()

    # Heavy imports happen after argument parsing so --help and --version stay fast.
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from interactive_scrolling.ui.main_window import MainWindow
    from interactive_scrolling.ui.theme import apply_theme
    from interactive_scrolling.vision.camera import OpenCVCamera, probe_cameras
    from interactive_scrolling.vision.face_tracker import MediaPipeFaceTracker
    from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
    from interactive_scrolling.vision.model_assets import (
        FACE_MODEL,
        SEGMENTER_MODEL,
        default_model_path,
    )
    from interactive_scrolling.vision.segmenter import MediaPipePersonSegmenter

    model_path = settings.tracking.model_path or default_model_path()
    tracking_settings = settings.tracking

    def tracker_factory() -> MediaPipeHandTracker:
        return MediaPipeHandTracker(tracking_settings, model_path)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("interactive_scrolling")
    app.setApplicationVersion(__version__)
    # The creator overlay and the tray icon are extra top-level objects; the application ends
    # when the main window closes (which also stops the camera), never "when the last window
    # closes" while the dashboard is merely hidden.
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)

    from interactive_scrolling.services import build_services

    services = build_services()
    window = MainWindow(
        settings,
        camera_factory=OpenCVCamera,
        tracker_factory=tracker_factory,
        probe_cameras=partial(probe_cameras, 4, settings.camera.backend),
        services=services,
        register_hotkey=True,
        segmenter_factory=lambda: MediaPipePersonSegmenter(SEGMENTER_MODEL.path()),
        face_factory=lambda: MediaPipeFaceTracker(FACE_MODEL.path()),
        quit_on_close=True,
    )
    window.show()
    if args.auto_start:
        QTimer.singleShot(0, window.start_camera)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
