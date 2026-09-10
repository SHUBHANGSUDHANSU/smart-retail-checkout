"""Server-Sent Events transport for live application state."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from smart_retail.api.dependencies import APIRuntime, RuntimeDependency
from smart_retail.api.models import RealtimeEnvelopeResponse
from smart_retail.infrastructure.logging_config import log_event
from smart_retail.realtime.models import RealtimeMessage

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["realtime"])


def encode_sse_message(message: RealtimeMessage) -> str:
    """Encode one application message using standard SSE fields."""
    envelope = RealtimeEnvelopeResponse.from_message(message)
    return (
        f"id: {message.sequence}\n"
        f"event: {message.event_type.value}\n"
        f"data: {envelope.model_dump_json()}\n\n"
    )


async def stream_realtime_events(
    request: Request,
    runtime: APIRuntime,
) -> AsyncIterator[str]:
    """Yield messages and keepalives until disconnect or application shutdown."""
    subscription = runtime.subscribe_realtime()
    heartbeat_seconds = runtime.get_realtime_heartbeat_seconds()
    loop = asyncio.get_running_loop()
    last_output = loop.time()
    log_event(
        LOGGER,
        logging.INFO,
        "realtime.client_connected",
        "Realtime client connected",
        subscriber_id=subscription.subscriber_id,
    )
    try:
        while not subscription.closed:
            if await request.is_disconnected():
                break
            wait_seconds = min(heartbeat_seconds, 0.5)
            message = await asyncio.to_thread(subscription.get, wait_seconds)
            now = loop.time()
            if message is not None:
                last_output = now
                yield encode_sse_message(message)
            elif now - last_output >= heartbeat_seconds:
                last_output = now
                yield ": heartbeat\n\n"
    finally:
        runtime.unsubscribe_realtime(subscription)
        log_event(
            LOGGER,
            logging.INFO,
            "realtime.client_disconnected",
            "Realtime client disconnected",
            subscriber_id=subscription.subscriber_id,
        )


@router.get(
    "",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def get_realtime_stream(
    request: Request,
    runtime: RuntimeDependency,
) -> StreamingResponse:
    return StreamingResponse(
        stream_realtime_events(request, runtime),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
