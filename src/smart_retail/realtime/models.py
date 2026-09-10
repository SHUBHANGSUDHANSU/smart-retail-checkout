"""Immutable application messages carried by the realtime transport."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from smart_retail.domain.events import CartEvent, CartEventType
from smart_retail.domain.models import CartSnapshot
from smart_retail.metrics import MetricsSnapshot


class RealtimeEventType(str, Enum):
    CART_UPDATED = "cart.updated"
    CHECKOUT_EVENT = "checkout.event"
    METRICS_UPDATED = "metrics.updated"


@dataclass(frozen=True, slots=True)
class RealtimeCheckoutActivity:
    """One live cart mutation, whether or not SQLite remained available."""

    event_id: int | None
    session_id: int | None
    timestamp: float
    track_id: int | None
    product_id: str | None
    event_type: CartEventType
    unit_price: int | None

    @classmethod
    def from_mutation(
        cls,
        *,
        event_type: CartEventType,
        timestamp: float,
        track_id: int | None = None,
        product_id: str | None = None,
        unit_price: int | None = None,
        persisted_event: CartEvent | None = None,
    ) -> RealtimeCheckoutActivity:
        return cls(
            event_id=(
                persisted_event.event_id if persisted_event is not None else None
            ),
            session_id=(
                persisted_event.session_id if persisted_event is not None else None
            ),
            timestamp=timestamp,
            track_id=track_id,
            product_id=product_id,
            event_type=event_type,
            unit_price=unit_price,
        )

    def __post_init__(self) -> None:
        if self.event_id is not None and self.event_id < 1:
            raise ValueError("Realtime event ID must be positive when present.")
        if self.session_id is not None and self.session_id < 1:
            raise ValueError("Realtime session ID must be positive when present.")
        if not math.isfinite(self.timestamp):
            raise ValueError("Realtime checkout timestamp must be finite.")
        if self.event_type is CartEventType.RESET:
            if any(
                value is not None
                for value in (self.track_id, self.product_id, self.unit_price)
            ):
                raise ValueError("Realtime RESET events cannot reference a product.")
            return
        if self.track_id is None or self.product_id is None or self.unit_price is None:
            raise ValueError("Realtime ADD and REMOVE events require product data.")
        if self.unit_price < 0:
            raise ValueError("Realtime unit price cannot be negative.")


RealtimePayload: TypeAlias = CartSnapshot | RealtimeCheckoutActivity | MetricsSnapshot


@dataclass(frozen=True, slots=True)
class RealtimeMessage:
    """One ordered, immutable message shared by all current subscribers."""

    sequence: int
    event_type: RealtimeEventType
    timestamp: float
    payload: RealtimePayload

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Realtime message sequence must be positive.")
        if not math.isfinite(self.timestamp):
            raise ValueError("Realtime message timestamp must be finite.")
