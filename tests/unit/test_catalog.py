"""Tests for product-catalog file and input validation."""

import json

import pytest

from smart_retail.infrastructure.repository import (
    ProductCatalogError,
    load_product_catalog,
)


def test_missing_and_malformed_catalogs_are_rejected(tmp_path) -> None:
    with pytest.raises(ProductCatalogError, match="Could not read"):
        load_product_catalog(tmp_path / "missing.json")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ProductCatalogError, match="not valid JSON"):
        load_product_catalog(malformed)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "at least one product"),
        ([], "at least one product"),
        ({"bottle": []}, "map a class name to an object"),
        ({"bottle": {"name": "", "price": 40}}, "nonempty name"),
        ({"bottle": {"name": "Water", "price": True}}, "nonnegative integer"),
        ({"bottle": {"name": "Water", "price": -1}}, "nonnegative integer"),
        ({"bottle": {"name": "Water", "price": 4.5}}, "nonnegative integer"),
    ],
)
def test_invalid_catalog_shapes_are_rejected(tmp_path, payload, message) -> None:
    path = tmp_path / "products.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProductCatalogError, match=message):
        load_product_catalog(path)


def test_valid_catalog_preserves_literal_products_and_order(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps(
            {
                "water_bottle": {"name": "Spring Water", "price": 40},
                "granola_bar": {"name": "Oat Bar", "price": 65},
            }
        ),
        encoding="utf-8",
    )

    catalog = load_product_catalog(path)

    assert list(catalog) == ["water_bottle", "granola_bar"]
    assert catalog["water_bottle"].name == "Spring Water"
    assert catalog["water_bottle"].unit_price == 40
    assert isinstance(catalog["water_bottle"].unit_price, int)
    assert catalog["granola_bar"].name == "Oat Bar"
    assert catalog["granola_bar"].unit_price == 65
    assert isinstance(catalog["granola_bar"].unit_price, int)
