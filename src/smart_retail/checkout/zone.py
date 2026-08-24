"""Normalized checkout-zone geometry with no external framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass

from smart_retail.domain.events import ZoneState
from smart_retail.domain.models import Centroid


@dataclass(frozen=True, slots=True)
class CheckoutZone:
    """A resolution-independent rectangular checkout region."""

    left: float
    top: float
    right: float
    bottom: float
    hysteresis: float = 0.0

    def __post_init__(self) -> None:
        coordinates = (self.left, self.top, self.right, self.bottom)
        if not all(0.0 <= value <= 1.0 for value in coordinates):
            raise ValueError("Checkout-zone coordinates must be between 0.0 and 1.0.")
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Checkout zone must have positive width and height.")
        if self.hysteresis < 0.0:
            raise ValueError("Checkout-zone hysteresis cannot be negative.")
        if (
            self.hysteresis * 2 >= self.right - self.left
            or self.hysteresis * 2 >= self.bottom - self.top
        ):
            raise ValueError("Checkout-zone hysteresis is too large for the zone.")

    def pixel_bounds(
        self, frame_width: int, frame_height: int
    ) -> tuple[int, int, int, int]:
        """Convert normalized geometry into drawable pixel coordinates."""
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")

        x1 = round(self.left * frame_width)
        y1 = round(self.top * frame_height)
        x2 = min(frame_width - 1, round(self.right * frame_width))
        y2 = min(frame_height - 1, round(self.bottom * frame_height))
        return (x1, y1, x2, y2)

    def classify(
        self,
        centroid: Centroid,
        frame_width: int,
        frame_height: int,
    ) -> ZoneState:
        """Classify a centroid against the visible zone bounds."""
        return self.classify_for_previous_state(
            centroid,
            frame_width,
            frame_height,
            previous_state=None,
        )

    def classify_for_previous_state(
        self,
        centroid: Centroid,
        frame_width: int,
        frame_height: int,
        previous_state: ZoneState | None,
    ) -> ZoneState:
        """Apply separate entry and exit bounds when prior state is known."""
        x1, y1, x2, y2 = self.pixel_bounds(frame_width, frame_height)
        margin_x = round(self.hysteresis * frame_width)
        margin_y = round(self.hysteresis * frame_height)

        if previous_state is ZoneState.OUTSIDE:
            x1, y1, x2, y2 = (
                x1 + margin_x,
                y1 + margin_y,
                x2 - margin_x,
                y2 - margin_y,
            )
        elif previous_state is ZoneState.INSIDE:
            x1, y1, x2, y2 = (
                x1 - margin_x,
                y1 - margin_y,
                x2 + margin_x,
                y2 + margin_y,
            )

        center_x, center_y = centroid
        if x1 <= center_x <= x2 and y1 <= center_y <= y2:
            return ZoneState.INSIDE
        return ZoneState.OUTSIDE
