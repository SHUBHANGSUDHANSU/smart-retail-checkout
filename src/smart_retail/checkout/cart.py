"""Framework-independent shopping-cart service."""

from __future__ import annotations

import threading

from smart_retail.domain.models import CartItem, CartSnapshot, Product


class CartService:
    """Maintain exact track membership and expose aggregated product rows."""

    def __init__(self, products: dict[str, Product]) -> None:
        self._products = dict(products)
        self._cart_tracks: dict[int, str] = {}
        self._lock = threading.Lock()

    def add_item(self, track_id: int, product_class: str) -> bool:
        """Add one supported track and report whether state changed."""
        with self._lock:
            if track_id in self._cart_tracks or product_class not in self._products:
                return False
            self._cart_tracks[track_id] = product_class
            return True

    def remove_item(self, track_id: int) -> bool:
        """Remove an exact track and report whether state changed."""
        with self._lock:
            return self._cart_tracks.pop(track_id, None) is not None

    def contains_track(self, track_id: int) -> bool:
        with self._lock:
            return track_id in self._cart_tracks

    def product_for_class(self, product_class: str) -> Product | None:
        return self._products.get(product_class)

    def product_for_track(self, track_id: int) -> Product | None:
        with self._lock:
            product_class = self._cart_tracks.get(track_id)
        return self.product_for_class(product_class) if product_class else None

    def clear(self) -> int:
        """Clear the cart and return the number of removed physical tracks."""
        with self._lock:
            item_count = len(self._cart_tracks)
            self._cart_tracks.clear()
            return item_count

    def get_items(self) -> list[CartItem]:
        """Aggregate physical tracks by product in catalog order."""
        with self._lock:
            return list(self._get_items_unlocked())

    def get_total(self) -> int:
        with self._lock:
            return sum(item.subtotal for item in self._get_items_unlocked())

    def get_snapshot(self) -> CartSnapshot:
        """Return items and total calculated under one cart lock acquisition."""
        with self._lock:
            items = self._get_items_unlocked()
            return CartSnapshot(
                items=items,
                total=sum(item.subtotal for item in items),
            )

    def _get_items_unlocked(self) -> tuple[CartItem, ...]:
        quantities: dict[str, int] = {}
        for product_class in self._cart_tracks.values():
            quantities[product_class] = quantities.get(product_class, 0) + 1

        items: list[CartItem] = []
        for product_class, product in self._products.items():
            quantity = quantities.get(product_class, 0)
            if quantity:
                items.append(
                    CartItem(
                        product_id=product.product_id,
                        product_name=product.name,
                        unit_price=product.unit_price,
                        quantity=quantity,
                    )
                )
        return tuple(items)
