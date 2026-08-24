"""Focused tests for framework-independent cart behavior."""

from collections.abc import Callable

import pytest

from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.config import load_config
from smart_retail.domain.models import TrackedObject
from smart_retail.infrastructure.repository import load_product_catalog


def test_same_track_is_charged_once(cart_service: CartService) -> None:
    assert cart_service.add_item(7, "bottle") is True
    assert cart_service.add_item(7, "bottle") is False
    assert cart_service.get_snapshot().total_quantity == 1
    assert cart_service.get_snapshot().total == 40


def test_two_tracks_of_same_class_aggregate_quantity(
    cart_service: CartService,
) -> None:
    cart_service.add_item(7, "bottle")
    cart_service.add_item(19, "bottle")

    snapshot = cart_service.get_snapshot()

    assert snapshot.items[0].quantity == 2
    assert snapshot.total == 80


def test_remove_and_reset_are_safe(cart_service: CartService) -> None:
    cart_service.add_item(7, "bottle")
    cart_service.add_item(19, "bottle")

    assert cart_service.remove_item(999) is False
    assert cart_service.remove_item(7) is True
    assert cart_service.contains_track(7) is False
    assert cart_service.contains_track(19) is True
    assert cart_service.get_total() == 40

    cart_service.add_item(12, "apple")

    assert cart_service.clear() == 2
    assert cart_service.contains_track(12) is False
    assert cart_service.contains_track(19) is False
    assert cart_service.get_snapshot().items == ()
    assert cart_service.get_snapshot().total == 0


def test_visible_items_aggregate_tracks_by_product(cart_service: CartService) -> None:
    cart_service.add_item(7, "bottle")
    cart_service.add_item(12, "apple")
    cart_service.add_item(19, "bottle")

    items = {item.product_id: item for item in cart_service.get_items()}

    assert items["bottle"].product_name == "Water Bottle"
    assert items["bottle"].quantity == 2
    assert items["bottle"].subtotal == 80
    assert items["apple"].quantity == 1
    assert items["apple"].subtotal == 45
    assert cart_service.get_total() == 125
    assert isinstance(cart_service.get_total(), int)


def test_unsupported_class_is_not_added(cart_service: CartService) -> None:
    assert cart_service.add_item(4, "person") is False
    assert cart_service.contains_track(4) is False
    assert cart_service.get_items() == []
    assert cart_service.get_total() == 0


def test_products_are_available_for_notifications(cart_service: CartService) -> None:
    cart_service.add_item(7, "bottle")

    assert cart_service.product_for_class("bottle").name == "Water Bottle"
    assert cart_service.product_for_track(7).name == "Water Bottle"
    assert cart_service.product_for_class("person") is None
    assert cart_service.product_for_track(999) is None


def test_cart_operations_are_silent(
    cart_service: CartService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cart_service.add_item(7, "bottle")
    cart_service.remove_item(7)
    cart_service.clear()

    assert capsys.readouterr().out == ""


def test_reset_with_active_inside_track_does_not_immediately_readd(
    cart_service: CartService,
    event_engine: CheckoutEventEngine,
    make_tracked_object: Callable[..., TrackedObject],
) -> None:
    event_engine.process_frame([make_tracked_object(7, 500)], 1000, 500, frame_number=0)
    event_engine.process_frame([make_tracked_object(7, 800)], 1000, 500, frame_number=1)
    enter = event_engine.process_frame(
        [make_tracked_object(7, 800)], 1000, 500, frame_number=2
    ).events[0]
    cart_service.add_item(enter.track_id, enter.product_class)

    cart_service.clear()
    event_engine.reset()
    update = event_engine.process_frame(
        [make_tracked_object(7, 800)], 1000, 500, frame_number=3
    )

    assert update.events == ()
    assert cart_service.get_items() == []


def test_product_catalog_prices_match_demo() -> None:
    expected_prices = {
        "bottle": 40,
        "cup": 199,
        "banana": 30,
        "apple": 45,
        "orange": 35,
    }
    config = load_config({})
    cart_service = CartService(load_product_catalog(config.products_config_path))

    for track_id, product_class in enumerate(expected_prices, start=1):
        cart_service.add_item(track_id, product_class)

    items = {item.product_id: item for item in cart_service.get_items()}

    assert {
        product_id: item.unit_price for product_id, item in items.items()
    } == expected_prices
