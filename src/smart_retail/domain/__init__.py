"""Framework-independent business concepts."""

from smart_retail.domain.events import CheckoutEvent, CheckoutEventType, ZoneState
from smart_retail.domain.models import CartItem, Product, TrackedObject

__all__ = [
    "CartItem",
    "CheckoutEvent",
    "CheckoutEventType",
    "Product",
    "TrackedObject",
    "ZoneState",
]
