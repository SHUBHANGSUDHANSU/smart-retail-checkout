"""Domain models shared across vision, checkout, and presentation layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

BoundingBox: TypeAlias = tuple[int, int, int, int]
Centroid: TypeAlias = tuple[float, float]


@dataclass(frozen=True, slots=True)
class TrackedObject:
    """One frame-level observation associated with an optional track ID."""

    track_id: int | None
    class_name: str
    confidence: float
    bbox: BoundingBox

    @property
    def centroid(self) -> Centroid:
        """Return the center of the bounding box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass(frozen=True, slots=True)
class Product:
    """A supported catalog product with a whole-currency-unit price."""

    product_id: str
    name: str
    unit_price: int

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ValueError("Product ID cannot be empty.")
        if not self.name.strip():
            raise ValueError("Product name cannot be empty.")
        if (
            not isinstance(self.unit_price, int)
            or isinstance(self.unit_price, bool)
            or self.unit_price < 0
        ):
            raise ValueError("Product unit price must be a nonnegative integer.")


@dataclass(frozen=True, slots=True)
class CartItem:
    """An aggregated, presentation-ready cart row."""

    product_id: str
    product_name: str
    unit_price: int
    quantity: int

    @property
    def subtotal(self) -> int:
        """Return the deterministic line total."""
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True)
class CartSnapshot:
    """One internally consistent view of the current in-memory cart."""

    items: tuple[CartItem, ...]
    total: int

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items)


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    """One persisted application run and its final checkout value."""

    session_id: int
    started_at: float
    ended_at: float | None
    final_total: int | None

    def __post_init__(self) -> None:
        if self.session_id < 1:
            raise ValueError("Checkout session ID must be positive.")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("Checkout session cannot end before it starts.")
        if self.final_total is not None and self.final_total < 0:
            raise ValueError("Checkout session total cannot be negative.")
        if (self.ended_at is None) != (self.final_total is None):
            raise ValueError(
                "Checkout session end time and final total must be set together."
            )
