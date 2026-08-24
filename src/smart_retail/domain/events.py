"""Domain events emitted by the checkout state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ZoneState(str, Enum):
    """Stable location of a tracked centroid relative to checkout."""

    OUTSIDE = "outside"
    INSIDE = "inside"


class CheckoutEventType(str, Enum):
    """Supported checkout-zone transitions."""

    ENTER = "ENTER"
    EXIT = "EXIT"


class CartEventType(str, Enum):
    """Meaningful persisted changes to checkout history."""

    ADD = "ADD"
    REMOVE = "REMOVE"
    RESET = "RESET"


@dataclass(frozen=True, slots=True)
class CheckoutEvent:
    """A confirmed transition for one tracked product."""

    event_type: CheckoutEventType
    track_id: int
    product_class: str
    timestamp: float

    def __str__(self) -> str:
        return (
            f"{self.event_type.value}: track_id={self.track_id} "
            f"class={self.product_class}"
        )


@dataclass(frozen=True, slots=True)
class CartEvent:
    """One persisted cart mutation with a historical unit-price snapshot."""

    event_id: int
    session_id: int
    timestamp: float
    track_id: int | None
    product_id: str | None
    event_type: CartEventType
    unit_price: int | None

    def __post_init__(self) -> None:
        if self.event_id < 1 or self.session_id < 1:
            raise ValueError("Cart event and session IDs must be positive.")
        if self.event_type is CartEventType.RESET:
            if any(
                value is not None
                for value in (self.track_id, self.product_id, self.unit_price)
            ):
                raise ValueError("RESET events cannot reference a product or track.")
            return
        if self.track_id is None or self.product_id is None or self.unit_price is None:
            raise ValueError("ADD and REMOVE events require product and track data.")
        if self.unit_price < 0:
            raise ValueError("Cart-event unit price cannot be negative.")
