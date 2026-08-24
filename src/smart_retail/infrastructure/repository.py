"""Local product-catalog loading at the infrastructure boundary."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from smart_retail.domain.models import Product
from smart_retail.infrastructure.logging_config import log_event

LOGGER = logging.getLogger(__name__)


class ProductCatalogError(ValueError):
    """Raised when the configured product catalog is unavailable or invalid."""


def load_product_catalog(config_path: str | Path) -> dict[str, Product]:
    """Load and validate detector-class to product mappings from JSON."""
    path = Path(config_path)
    try:
        raw_products = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProductCatalogError(
            f"Could not read product config '{path}': {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise ProductCatalogError(
            f"Product config '{path}' is not valid JSON: {error}"
        ) from error

    if not isinstance(raw_products, dict) or not raw_products:
        raise ProductCatalogError(
            "Product config must contain at least one product object."
        )

    products: dict[str, Product] = {}
    for product_class, details in raw_products.items():
        if not isinstance(product_class, str) or not isinstance(details, dict):
            raise ProductCatalogError(
                "Each product must map a class name to an object."
            )
        name = details.get("name")
        price = details.get("price")
        if not isinstance(name, str) or not name.strip():
            raise ProductCatalogError(
                f"Product '{product_class}' must have a nonempty name."
            )
        if not isinstance(price, int) or isinstance(price, bool) or price < 0:
            raise ProductCatalogError(
                f"Product '{product_class}' price must be a nonnegative integer."
            )
        products[product_class] = Product(
            product_id=product_class,
            name=name,
            unit_price=price,
        )
    log_event(
        LOGGER,
        logging.INFO,
        "product_catalog_loaded",
        "Product catalog loaded",
        catalog=path.name,
        product_count=len(products),
    )
    return products
