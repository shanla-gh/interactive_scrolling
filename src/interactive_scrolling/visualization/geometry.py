"""Mapping between source-image coordinates and on-screen view coordinates.

The frame is drawn aspect-correct ("letterboxed") and centred inside the view. The same
:class:`ViewTransform` is used to place the video image and every overlay element, which
is what keeps landmarks aligned with the user's hand at any window size and with or
without mirroring.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ViewTransform:
    source_width: int
    source_height: int
    x: float
    y: float
    width: float
    height: float
    mirrored: bool = False

    @classmethod
    def fit(
        cls,
        source_width: int,
        source_height: int,
        view_width: float,
        view_height: float,
        mirrored: bool = False,
    ) -> ViewTransform:
        """Largest aspect-preserving rectangle for the source, centred in the view."""
        if source_width <= 0 or source_height <= 0:
            raise ValueError("Source dimensions must be positive.")
        view_width = max(0.0, float(view_width))
        view_height = max(0.0, float(view_height))
        scale = min(view_width / source_width, view_height / source_height)
        width = source_width * scale
        height = source_height * scale
        return cls(
            source_width=source_width,
            source_height=source_height,
            x=(view_width - width) / 2.0,
            y=(view_height - height) / 2.0,
            width=width,
            height=height,
            mirrored=mirrored,
        )

    @property
    def scale(self) -> float:
        """View pixels per source pixel."""
        return self.width / self.source_width

    def map_normalized(self, nx: float, ny: float) -> tuple[float, float]:
        """Map normalized source coordinates to view coordinates."""
        sx = 1.0 - nx if self.mirrored else nx
        return self.x + sx * self.width, self.y + ny * self.height

    def map_source_px(self, px: float, py: float) -> tuple[float, float]:
        """Map source pixel coordinates to view coordinates."""
        return self.map_normalized(px / self.source_width, py / self.source_height)

    def map_vector_px(self, vx: float, vy: float) -> tuple[float, float]:
        """Map a source-pixel displacement/velocity vector to view space (no translation)."""
        s = self.scale
        return (-vx * s if self.mirrored else vx * s), vy * s
