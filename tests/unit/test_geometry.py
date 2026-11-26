"""Source-to-view coordinate mapping used by both the video image and the overlay."""

from __future__ import annotations

import pytest

from interactive_scrolling.visualization.geometry import ViewTransform


def test_fit_letterboxes_wide_view() -> None:
    t = ViewTransform.fit(640, 480, 1000, 480)
    assert (t.x, t.y, t.width, t.height) == pytest.approx((180, 0, 640, 480))
    assert t.scale == pytest.approx(1.0)


def test_fit_letterboxes_tall_view() -> None:
    t = ViewTransform.fit(1280, 720, 640, 1000)
    assert t.width == pytest.approx(640)
    assert t.height == pytest.approx(360)
    assert t.y == pytest.approx((1000 - 360) / 2)
    assert t.scale == pytest.approx(0.5)


@pytest.mark.parametrize(("vw", "vh"), [(800, 600), (1920, 1080), (333, 977), (1, 1)])
def test_fit_preserves_aspect_ratio(vw: int, vh: int) -> None:
    t = ViewTransform.fit(1280, 720, vw, vh)
    assert t.width / t.height == pytest.approx(1280 / 720)
    assert t.width <= vw + 1e-9 and t.height <= vh + 1e-9
    assert t.x >= -1e-9 and t.y >= -1e-9


def test_corners_map_to_image_rectangle() -> None:
    t = ViewTransform.fit(640, 480, 1000, 600)
    assert t.map_normalized(0, 0) == pytest.approx((t.x, t.y))
    assert t.map_normalized(1, 1) == pytest.approx((t.x + t.width, t.y + t.height))
    assert t.map_normalized(0.5, 0.5) == pytest.approx((500, 300))


def test_mirrored_mapping_flips_horizontally_only() -> None:
    plain = ViewTransform.fit(640, 480, 1000, 600)
    mirrored = ViewTransform.fit(640, 480, 1000, 600, mirrored=True)
    for nx, ny in [(0.1, 0.2), (0.9, 0.7), (0.5, 0.5)]:
        _, py = plain.map_normalized(nx, ny)
        mx, my = mirrored.map_normalized(nx, ny)
        assert my == pytest.approx(py)
        assert mx == pytest.approx(plain.map_normalized(1 - nx, ny)[0])


def test_source_pixels_and_normalized_agree() -> None:
    t = ViewTransform.fit(1280, 720, 900, 700, mirrored=True)
    assert t.map_source_px(320, 180) == pytest.approx(t.map_normalized(0.25, 0.25))


def test_vector_mapping_scales_and_mirrors() -> None:
    t = ViewTransform.fit(640, 480, 1280, 960)
    assert t.map_vector_px(10, -4) == pytest.approx((20, -8))
    tm = ViewTransform.fit(640, 480, 1280, 960, mirrored=True)
    assert tm.map_vector_px(10, -4) == pytest.approx((-20, -8))


def test_vector_mapping_is_consistent_with_point_mapping() -> None:
    t = ViewTransform.fit(640, 480, 777, 555, mirrored=True)
    a = t.map_source_px(100, 100)
    b = t.map_source_px(130, 80)
    assert t.map_vector_px(30, -20) == pytest.approx((b[0] - a[0], b[1] - a[1]))


def test_zero_view_size_is_safe() -> None:
    t = ViewTransform.fit(640, 480, 0, 0)
    assert t.width == 0 and t.height == 0


def test_invalid_source_rejected() -> None:
    with pytest.raises(ValueError):
        ViewTransform.fit(0, 480, 100, 100)
