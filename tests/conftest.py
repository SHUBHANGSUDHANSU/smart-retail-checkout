from collections.abc import Callable

import pytest

from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.domain.models import Product, TrackedObject


@pytest.fixture
def product_catalog() -> dict[str, Product]:
    return {
        "bottle": Product("bottle", "Water Bottle", 40),
        "apple": Product("apple", "Apple", 45),
    }


@pytest.fixture
def cart_service(product_catalog: dict[str, Product]) -> CartService:
    return CartService(product_catalog)


@pytest.fixture
def checkout_zone() -> CheckoutZone:
    return CheckoutZone(0.70, 0.05, 0.98, 0.95, hysteresis=0.01)


@pytest.fixture
def event_engine(checkout_zone: CheckoutZone) -> CheckoutEventEngine:
    return CheckoutEventEngine(
        checkout_zone,
        confirmation_frames=2,
        expiry_grace_frames=3,
        clock=lambda: 123.5,
    )


@pytest.fixture
def make_tracked_object() -> Callable[..., TrackedObject]:
    def make(
        track_id: int | None,
        center_x: float,
        center_y: float = 250.0,
        class_name: str = "bottle",
    ) -> TrackedObject:
        return TrackedObject(
            track_id=track_id,
            class_name=class_name,
            confidence=0.90,
            bbox=(
                round(center_x - 10),
                round(center_y - 10),
                round(center_x + 10),
                round(center_y + 10),
            ),
        )

    return make
