"""Explicitly synthetic commands registered only in demo mode."""

from typing import Annotated

from fastapi import APIRouter, Path, status

from smart_retail.api.dependencies import DemoRuntimeDependency
from smart_retail.api.models import (
    CartResponse,
    DemoManifestResponse,
    DemoMutationResponse,
    DemoProductResponse,
    ErrorResponse,
)

router = APIRouter(prefix="/demo", tags=["demo"])
DemoProductId = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
]


@router.get("", response_model=DemoManifestResponse)
def get_demo_manifest(runtime: DemoRuntimeDependency) -> DemoManifestResponse:
    return DemoManifestResponse(
        mode="demo",
        vision_active=False,
        message="Using simulated checkout events. Computer vision is not active.",
        products=[
            DemoProductResponse.from_domain(product)
            for product in runtime.get_demo_products()
        ],
    )


@router.post(
    "/items/{product_id}",
    response_model=DemoMutationResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def add_demo_item(
    product_id: DemoProductId,
    runtime: DemoRuntimeDependency,
) -> DemoMutationResponse:
    result = runtime.add_demo_item(product_id)
    return DemoMutationResponse(
        status="added",
        track_id=result.track_id,
        product=DemoProductResponse.from_domain(result.product),
        cart=CartResponse.from_snapshot(result.cart),
    )


@router.post(
    "/items/{product_id}/remove",
    response_model=DemoMutationResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def remove_demo_item(
    product_id: DemoProductId,
    runtime: DemoRuntimeDependency,
) -> DemoMutationResponse:
    result = runtime.remove_demo_item(product_id)
    return DemoMutationResponse(
        status="removed",
        track_id=result.track_id,
        product=DemoProductResponse.from_domain(result.product),
        cart=CartResponse.from_snapshot(result.cart),
    )
