from collections.abc import Iterator

import pytest

from smart_retail.domain.models import Product
from smart_retail.infrastructure.sqlite_repository import SQLiteCheckoutRepository


@pytest.fixture
def sqlite_repository(
    tmp_path,
    product_catalog: dict[str, Product],
) -> Iterator[SQLiteCheckoutRepository]:
    repository = SQLiteCheckoutRepository(tmp_path / "checkout.db")
    repository.initialize(product_catalog)
    yield repository
    repository.close()
