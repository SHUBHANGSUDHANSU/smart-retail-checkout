"""Application health and readiness routes."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from smart_retail.api.dependencies import RuntimeDependency
from smart_retail.api.models import LivenessResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=LivenessResponse)
def get_health(runtime: RuntimeDependency) -> LivenessResponse:
    return LivenessResponse.from_snapshot(runtime.get_liveness_snapshot())


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def get_readiness(runtime: RuntimeDependency) -> ReadinessResponse | JSONResponse:
    snapshot = runtime.get_readiness_snapshot()
    response = ReadinessResponse.from_snapshot(snapshot)
    if snapshot.ready:
        return response
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(mode="json"),
    )
