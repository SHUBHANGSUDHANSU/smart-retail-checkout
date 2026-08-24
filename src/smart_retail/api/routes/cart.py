"""Current-cart read and reset routes."""

from fastapi import APIRouter, status

from smart_retail.api.dependencies import RuntimeDependency
from smart_retail.api.models import CartResetResponse, CartResponse, ErrorResponse

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartResponse)
def get_cart(runtime: RuntimeDependency) -> CartResponse:
    return CartResponse.from_snapshot(runtime.get_cart_snapshot())


@router.post(
    "/reset",
    response_model=CartResetResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Application or persistence is unavailable",
        }
    },
)
def reset_cart(runtime: RuntimeDependency) -> CartResetResponse:
    result = runtime.reset_checkout(source="api")
    return CartResetResponse(
        status="reset",
        removed_track_count=result.removed_track_count,
        cart=CartResponse.from_snapshot(result.cart),
    )
