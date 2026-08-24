"""Pydantic schemas for versioned REST responses."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from smart_retail.domain.events import CartEvent, CartEventType
from smart_retail.domain.models import CartItem, CartSnapshot, CheckoutSession
from smart_retail.health import LivenessSnapshot, ReadinessSnapshot
from smart_retail.metrics import MetricsSnapshot


def _utc_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, timezone.utc)


class LivenessResponse(BaseModel):
    status: str
    uptime_seconds: float = Field(ge=0)

    @classmethod
    def from_snapshot(cls, snapshot: LivenessSnapshot) -> LivenessResponse:
        return cls(
            status=snapshot.status,
            uptime_seconds=round(snapshot.uptime_seconds, 3),
        )


class ReadinessResponse(BaseModel):
    status: str
    application_state: str
    components: dict[str, str]

    @classmethod
    def from_snapshot(cls, snapshot: ReadinessSnapshot) -> ReadinessResponse:
        return cls(
            status=snapshot.status,
            application_state=snapshot.application_state.value,
            components=dict(snapshot.components),
        )


class MetricsResponse(BaseModel):
    frames_processed_total: int = Field(ge=0)
    dropped_frames_total: int = Field(ge=0)
    detections_total: int = Field(ge=0)
    active_tracks: int = Field(ge=0)
    inference_latency_ms: float = Field(ge=0)
    frame_processing_latency_ms: float = Field(ge=0)
    current_fps: float = Field(ge=0)
    checkout_enter_events_total: int = Field(ge=0)
    checkout_exit_events_total: int = Field(ge=0)
    cart_additions_total: int = Field(ge=0)
    cart_removals_total: int = Field(ge=0)
    cart_resets_total: int = Field(ge=0)
    current_cart_items: int = Field(ge=0)
    current_cart_total: int = Field(ge=0)
    uptime_seconds: float = Field(ge=0)
    camera_errors_total: int = Field(ge=0)
    persistence_errors_total: int = Field(ge=0)

    @classmethod
    def from_snapshot(cls, snapshot: MetricsSnapshot) -> MetricsResponse:
        return cls(**asdict(snapshot))


class CartItemResponse(BaseModel):
    product_id: str
    product_name: str
    quantity: int = Field(ge=1)
    unit_price: int = Field(ge=0)
    subtotal: int = Field(ge=0)

    @classmethod
    def from_domain(cls, item: CartItem) -> CartItemResponse:
        return cls(
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_quantity: int = Field(ge=0)
    total: int = Field(ge=0)

    @classmethod
    def from_snapshot(cls, snapshot: CartSnapshot) -> CartResponse:
        return cls(
            items=[CartItemResponse.from_domain(item) for item in snapshot.items],
            total_quantity=snapshot.total_quantity,
            total=snapshot.total,
        )


class CartResetResponse(BaseModel):
    status: str
    removed_track_count: int = Field(ge=0)
    cart: CartResponse


class CartEventResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: int = Field(ge=1)
    session_id: int = Field(ge=1)
    timestamp: datetime
    track_id: int | None
    product_id: str | None
    event_type: CartEventType
    unit_price: int | None = Field(default=None, ge=0)

    @classmethod
    def from_domain(cls, event: CartEvent) -> CartEventResponse:
        return cls(
            id=event.event_id,
            session_id=event.session_id,
            timestamp=_utc_datetime(event.timestamp),
            track_id=event.track_id,
            product_id=event.product_id,
            event_type=event.event_type,
            unit_price=event.unit_price,
        )


class RecentEventsResponse(BaseModel):
    events: list[CartEventResponse]
    limit: int = Field(ge=1, le=200)


class CheckoutSessionResponse(BaseModel):
    id: int = Field(ge=1)
    started_at: datetime
    ended_at: datetime | None
    final_total: int | None = Field(default=None, ge=0)

    @classmethod
    def from_domain(cls, session: CheckoutSession) -> CheckoutSessionResponse:
        return cls(
            id=session.session_id,
            started_at=_utc_datetime(session.started_at),
            ended_at=(
                _utc_datetime(session.ended_at)
                if session.ended_at is not None
                else None
            ),
            final_total=session.final_total,
        )


class RecentSessionsResponse(BaseModel):
    sessions: list[CheckoutSessionResponse]
    limit: int = Field(ge=1, le=100)


class CheckoutSessionDetailResponse(CheckoutSessionResponse):
    events: list[CartEventResponse]


class ErrorResponse(BaseModel):
    code: str
    message: str
