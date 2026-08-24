"""Tests for pure normalized checkout-zone geometry."""

import pytest

from smart_retail.checkout.zone import CheckoutZone
from smart_retail.domain.events import ZoneState


def test_normalized_zone_converts_to_pixels(checkout_zone: CheckoutZone) -> None:
    assert checkout_zone.pixel_bounds(1000, 500) == (700, 25, 980, 475)


def test_zone_classifies_inside_outside_and_boundary_coordinates(
    checkout_zone: CheckoutZone,
) -> None:
    assert checkout_zone.classify((800.0, 250.0), 1000, 500) is ZoneState.INSIDE
    assert checkout_zone.classify((500.0, 250.0), 1000, 500) is ZoneState.OUTSIDE
    assert checkout_zone.classify((700.0, 25.0), 1000, 500) is ZoneState.INSIDE
    assert checkout_zone.classify((980.0, 475.0), 1000, 500) is ZoneState.INSIDE


@pytest.mark.parametrize("frame_width, frame_height", [(0, 500), (1000, 0)])
def test_pixel_bounds_rejects_nonpositive_frame_dimensions(
    checkout_zone: CheckoutZone,
    frame_width: int,
    frame_height: int,
) -> None:
    with pytest.raises(ValueError, match="Frame dimensions must be positive"):
        checkout_zone.pixel_bounds(frame_width, frame_height)


@pytest.mark.parametrize(
    "coordinates",
    [
        (-0.1, 0.05, 0.98, 0.95),
        (0.70, -0.1, 0.98, 0.95),
        (0.70, 0.05, 1.1, 0.95),
        (0.70, 0.05, 0.98, 1.1),
    ],
)
def test_zone_rejects_coordinates_outside_normalized_range(
    coordinates: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        CheckoutZone(*coordinates)


@pytest.mark.parametrize(
    "coordinates",
    [
        (0.70, 0.05, 0.70, 0.95),
        (0.70, 0.05, 0.98, 0.05),
    ],
)
def test_zone_rejects_zero_width_or_height(
    coordinates: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError, match="positive width and height"):
        CheckoutZone(*coordinates)


@pytest.mark.parametrize("hysteresis", [-0.01, 0.15])
def test_zone_rejects_invalid_hysteresis(hysteresis: float) -> None:
    with pytest.raises(ValueError, match="hysteresis"):
        CheckoutZone(0.70, 0.05, 0.98, 0.95, hysteresis=hysteresis)


def test_hysteresis_uses_different_entry_and_exit_bounds(
    checkout_zone: CheckoutZone,
) -> None:
    assert (
        checkout_zone.classify_for_previous_state(
            (705.0, 250.0), 1000, 500, ZoneState.OUTSIDE
        )
        is ZoneState.OUTSIDE
    )
    assert (
        checkout_zone.classify_for_previous_state(
            (695.0, 250.0), 1000, 500, ZoneState.INSIDE
        )
        is ZoneState.INSIDE
    )


def test_zone_geometry_scales_to_a_second_resolution(
    checkout_zone: CheckoutZone,
) -> None:
    assert checkout_zone.pixel_bounds(1920, 1080) == (1344, 54, 1882, 1026)
    assert checkout_zone.classify((1500.0, 540.0), 1920, 1080) is ZoneState.INSIDE
    assert checkout_zone.classify((1200.0, 540.0), 1920, 1080) is ZoneState.OUTSIDE
