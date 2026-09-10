# Realtime updates

The operator dashboard uses Server-Sent Events (SSE) for state that flows from
the checkout application to the browser. Commands and durable history remain
REST operations. SSE fits this system better than WebSockets because the live
traffic is one-way: cart snapshots, checkout activity, and metrics travel from
server to browser, while reset remains `POST /api/v1/cart/reset`.

## Transport contract

`GET /api/v1/stream` responds with `text/event-stream`. Each application event
has an SSE `id`, a named `event`, and a one-line JSON `data` envelope:

```text
id: 42
event: cart.updated
data: {"sequence":42,"type":"cart.updated","timestamp":"...","payload":{...}}
```

Supported event types are:

- `cart.updated`: a complete, idempotent `CartResponse` snapshot after ADD,
  REMOVE, or RESET.
- `checkout.event`: the meaningful ADD, REMOVE, or RESET activity. Persisted
  IDs are nullable so a temporary SQLite failure does not hide a successful
  in-memory checkout mutation.
- `metrics.updated`: a complete `MetricsResponse`, coalesced to at most once
  per configured interval (one second by default).

Comment frames (`: heartbeat`) keep idle connections alive without pretending
that application state changed.

## Browser synchronization

The React app opens one `EventSource` in `RealtimeProvider`. Cart, events, and
metrics first fetch normal REST snapshots, then consume that shared stream.
Full snapshots make duplicate or reordered cart/metrics delivery harmless.
Persisted event IDs deduplicate checkout activity; the stream sequence handles
activity that could not be persisted.

Native EventSource reconnection is used. Reconnection triggers one REST
reconciliation. While the stream is unavailable, cart, events, and metrics use
non-overlapping five-second REST fallback reads. Normal high-frequency polling
stops while the stream is live. Health and readiness intentionally remain
five-second REST probes because they are low-frequency operational checks.

## Thread safety and backpressure

The in-process broadcaster gives every browser a private bounded queue. A
publisher never waits for browser network I/O. If a client falls behind, its
oldest queued message is discarded and a structured warning is logged; other
clients and the vision loop continue. Disconnect and shutdown remove and close
subscriptions idempotently.

Business services mutate state and create immutable snapshots while holding
their existing narrow locks. Those locks are released before publication.
Network streaming therefore cannot participate in the cart/checkout lock
order or stall inference.

## Deployment boundary

This broadcaster is deliberately single-process. Multiple application
instances would not share their subscriber registries or messages. A
distributed deployment should replace it with an external pub/sub transport
such as Redis while preserving the public SSE envelope. Public deployment
would also require authentication and authorization review; the local demo's
stream follows its explicit CORS allowlist but is unauthenticated.
