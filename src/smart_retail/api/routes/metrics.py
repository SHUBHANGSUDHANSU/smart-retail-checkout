"""Read-only application metrics route."""

from fastapi import APIRouter

from smart_retail.api.dependencies import RuntimeDependency
from smart_retail.api.models import MetricsResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
def get_metrics(runtime: RuntimeDependency) -> MetricsResponse:
    return MetricsResponse.from_snapshot(runtime.get_metrics_snapshot())
