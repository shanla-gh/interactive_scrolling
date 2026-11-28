"""Information and settings panels shown beside the video view."""

from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from interactive_scrolling.config.settings import OverlaySettings
from interactive_scrolling.core.pipeline import ProcessedFrame, TrackerState
from interactive_scrolling.motion.analyzer import HandMotion, PointMotion
from interactive_scrolling.vision.landmarks import TrackingResult

NO_DATA = "—"


class Card(QFrame):
    """A titled surface holding key/value rows and widgets."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 14)
        self._layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        self._layout.addWidget(heading)
        self._grid: QGridLayout | None = None

    def add_widget(self, widget: QWidget) -> None:
        self._grid = None
        self._layout.addWidget(widget)

    def add_heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("subHeading")
        self.add_widget(label)
        return label

    def add_row(self, key: str, tooltip: str = "", accent: bool = False) -> QLabel:
        if self._grid is None:
            container = QWidget()
            self._grid = QGridLayout(container)
            self._grid.setContentsMargins(0, 0, 0, 0)
            self._grid.setHorizontalSpacing(12)
            self._grid.setVerticalSpacing(5)
            self._grid.setColumnStretch(1, 1)
            self._layout.addWidget(container)
        row = self._grid.rowCount()
        key_label = QLabel(key)
        key_label.setObjectName("rowKey")
        value = QLabel(NO_DATA)
        value.setObjectName("rowValueAccent" if accent else "rowValue")
        # Long values wrap instead of widening the side panel beyond its tab.
        value.setWordWrap(True)
        value.setMinimumWidth(0)
        if tooltip:
            key_label.setToolTip(tooltip)
            value.setToolTip(tooltip)
        self._grid.addWidget(key_label, row, 0)
        self._grid.addWidget(value, row, 1)
        return value


class TrackingPanel(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Tracking status", parent)
        self.state = self.add_row("Tracking", accent=True)
        self.model = self.add_row("Model")
        self.hands = self.add_row("Hands detected")
        self.handedness = self.add_row(
            "Handedness",
            "Model's handedness classification and its score, for the user's real hands.",
        )
        self.landmarks = self.add_row("Landmarks")
        self.inference = self.add_row("Inference", "Measured time of the last model call.")
        self.model.setWordWrap(True)
        self.set_tracker_state(TrackerState.NOT_LOADED, "")
        self.update_tracking(None)

    def set_tracker_state(self, state: TrackerState, message: str) -> None:
        self.model.setText(state.value.capitalize())
        self.model.setToolTip(message)

    def update_tracking(self, tracking: TrackingResult | None) -> None:
        if tracking is None:
            self.state.setText("Inactive")
            for label in (self.hands, self.handedness, self.landmarks, self.inference):
                label.setText(NO_DATA)
            return
        count = tracking.hand_count
        self.state.setText("Tracking" if count else "Searching")
        self.hands.setText(str(count))
        self.handedness.setText(
            "  ".join(
                f"{h.handedness.value}"
                + (f" {h.handedness_score:.2f}" if h.handedness_score is not None else "")
                for h in tracking.hands
            )
            or NO_DATA
        )
        self.landmarks.setText(
            f"{tracking.landmark_count}" + (f"  (21 x {count})" if count else "")
        )
        self.inference.setText(
            f"{tracking.inference_ms:.1f} ms" if tracking.inference_ms is not None else NO_DATA
        )


def _format_point(point: PointMotion, mirrored: bool) -> tuple[str, str]:
    direction = point.display_direction(mirrored)
    direction_text = f"{direction.arrow}  {direction.label}"
    speed_text = f"{point.speed_palms_s:4.1f} palms/s  {point.speed_px_s:5.0f} px/s"
    return direction_text, speed_text


class _HandMotionBlock:
    def __init__(self, card: Card) -> None:
        self.heading = card.add_heading("")
        self.tip_direction = card.add_row("Fingertip", accent=True)
        self.tip_speed = card.add_row(
            "  speed",
            "Index fingertip speed. palms/s is relative to the measured palm length "
            "(wrist to middle-finger knuckle); px/s is in source image pixels.",
        )
        self.palm_direction = card.add_row("Palm", accent=True)
        self.palm_speed = card.add_row("  speed")
        self.displacement = card.add_row(
            "Displacement",
            "Net fingertip displacement over the last 200 ms, in source pixels "
            "(x to the right of the displayed image, y down).",
        )
        self._widgets = [
            self.heading,
            self.tip_direction,
            self.tip_speed,
            self.palm_direction,
            self.palm_speed,
            self.displacement,
        ]

    def show(self, motion: HandMotion | None, mirrored: bool, title: str) -> None:
        self.heading.setText(title)
        if motion is None:
            for label in self._widgets[1:]:
                label.setText(NO_DATA)
            return
        self.tip_direction.setText(_format_point(motion.fingertip, mirrored)[0])
        self.tip_speed.setText(_format_point(motion.fingertip, mirrored)[1])
        self.palm_direction.setText(_format_point(motion.palm, mirrored)[0])
        self.palm_speed.setText(_format_point(motion.palm, mirrored)[1])
        dx, dy = motion.fingertip.window_displacement_px
        if mirrored:
            dx = -dx
        self.displacement.setText(f"dx {dx:+5.0f}  dy {dy:+5.0f} px")


class MotionPanel(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Motion analysis", parent)
        self.blocks = [_HandMotionBlock(self), _HandMotionBlock(self)]
        self.update_motion(None, True)

    def update_motion(self, frame: ProcessedFrame | None, mirrored: bool) -> None:
        hands = frame.motion.hands if frame is not None else ()
        for i, block in enumerate(self.blocks):
            motion = hands[i] if i < len(hands) else None
            if motion is None:
                block.show(None, mirrored, f"HAND {i + 1}  ·  not detected")
            else:
                title = f"{motion.handedness.value.upper()} HAND  ·  TRACK {motion.track_id}"
                block.show(motion, mirrored, title)


OVERLAY_LABELS: dict[str, str] = {
    "show_landmarks": "Landmark points",
    "show_skeleton": "Skeleton connections",
    "show_bounding_box": "Bounding boxes",
    "show_labels": "Handedness labels",
    "show_fingertip_trail": "Fingertip motion trail",
    "show_palm_trail": "Palm motion trail",
    "show_vectors": "Motion vectors",
}


class OverlayPanel(Card):
    """Checkboxes bound directly to an :class:`OverlaySettings` instance."""

    changed = Signal()
    mirror_changed = Signal(bool)

    def __init__(
        self, overlay: OverlaySettings, mirrored: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__("View & overlay", parent)
        self.overlay = overlay
        self.mirror = QCheckBox("Mirror preview")
        self.mirror.setChecked(mirrored)
        self.mirror.setToolTip(
            "Flip the preview horizontally like a mirror. Tracking always runs on the "
            "unmirrored image, so handedness stays correct."
        )
        self.mirror.toggled.connect(self.mirror_changed)
        self.add_widget(self.mirror)
        self.checkboxes: dict[str, QCheckBox] = {}
        for f in fields(OverlaySettings):
            box = QCheckBox(OVERLAY_LABELS[f.name])
            box.setChecked(bool(getattr(overlay, f.name)))
            box.toggled.connect(lambda checked, name=f.name: self._set(name, checked))
            self.add_widget(box)
            self.checkboxes[f.name] = box

    def _set(self, name: str, checked: bool) -> None:
        setattr(self.overlay, name, checked)
        self.changed.emit()
