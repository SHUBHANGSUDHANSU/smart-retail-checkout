# Frontend Phase 6 Realtime SSE Design

## Purpose

Replace the dashboard's high-frequency cart, checkout-event, and metrics polling with one production-style Server-Sent Events (SSE) connection while retaining REST for initial snapshots, commands, history, and low-frequency health checks. The computer-vision pipeline and checkout business rules remain unchanged.

## Current State

The vision loop sends tracked objects to `CheckoutEventEngine`, applies confirmed transitions to `CartService`, records meaningful cart events in SQLite, updates `MetricsService`, and renders the OpenCV UI. API resets enter the same serialized checkout command path. React currently starts independent non-overlapping polling loops for cart (1.5 seconds), recent events (2 seconds), metrics (2 seconds), and health/readiness (5 seconds).

## Chosen Architecture

Each application runtime owns one `RealtimePublisher`, which owns one thread-safe `RealtimeBroadcaster`. FastAPI exposes the broadcaster through `GET /api/v1/stream`. Each browser app owns one `EventSource` through `RealtimeProvider`; feature hooks subscribe to typed messages from that provider rather than creating their own connections.

REST remains authoritative for initial and recovery snapshots:

1. A feature hook requests its current REST snapshot.
2. The application-level SSE connection supplies subsequent live updates.
3. A successful SSE connection or reconnection triggers one REST reconciliation.
4. While SSE is unavailable, cart, recent events, and metrics use bounded five-second REST fallback polling.
5. Health and readiness continue using their existing five-second REST polling because these inexpensive operational probes benefit from remaining independent of the realtime transport.

## Realtime Contract

Every application message has:

- a process-local monotonically increasing `sequence` used as the SSE `id`;
- a stable event `type`;
- an ISO 8601 UTC `timestamp`;
- an explicitly serialized JSON `payload`.

Supported event types are:

- `cart.updated`: the complete existing `CartResponse` representation;
- `checkout.event`: one ADD, REMOVE, or RESET activity record, including persisted event/session identifiers when persistence succeeds and nullable identifiers when it is unavailable;
- `metrics.updated`: the complete existing `MetricsResponse` representation.

Cart and metric messages are full snapshots rather than incremental mutations, so applying the same message more than once is harmless. A checkout activity includes the envelope sequence for live deduplication and its persisted event ID when available. REST reconciliation replaces live history with persisted history and merges events by persisted ID, preventing duplicates across reconnect races.

The endpoint uses standard framing:

```text
id: 42
event: cart.updated
data: {"sequence":42,"type":"cart.updated","timestamp":"...","payload":{...}}

```

Heartbeat traffic is an SSE comment (`: heartbeat`) and is never exposed as an application event.

## Broadcaster and Backpressure

The in-process broadcaster maintains one bounded `queue.Queue` per subscriber. Its registry is protected by a short-lived `threading.Lock`. Publishing copies the current subscriber collection under the registry lock, releases that lock, and uses only `put_nowait` on subscriber queues.

When a client queue is full, the broadcaster removes that client's oldest queued message and inserts the newest message. This prevents a slow or disconnected browser from blocking the vision loop or consuming unbounded memory. A structured warning records the dropped-message condition without logging payload contents. Unsubscribing and shutdown are idempotent.

The default subscriber queue capacity is 64 messages. Heartbeats default to 15 seconds. Both values, plus the metrics publish interval, are typed runtime configuration with validated environment overrides.

## Publication Points

Cart publication happens only after a successful in-memory mutation:

- successful item addition;
- successful item removal, including track expiry;
- cart reset.

Each publication uses an immutable cart snapshot created after the cart's internal lock is released. Checkout activity publication uses the same successful business mutation and includes the persisted `CartEvent` when SQLite recording succeeds. Persistence failure does not suppress the live activity; the realtime payload then carries nullable persistence identifiers.

Metrics are recorded per frame exactly as before. A monotonic-clock throttle publishes at most one complete metrics snapshot per second. No per-frame SSE message is emitted.

System health transitions are intentionally not added to SSE in this phase. The existing cached health/readiness service and five-second REST polling already provide a simple, isolated operational path without meaningful request pressure.

## Thread Safety and Lock Ordering

The broadcaster never performs socket I/O. FastAPI stream coroutines consume their own queues after publication has completed. Application code follows this order:

1. mutate cart/metrics state under the existing service lock;
2. create an immutable snapshot;
3. release the service lock;
4. publish with non-blocking queue operations.

The existing checkout command lock may serialize one complete business command, but it never waits on a subscriber or network write. The broadcaster registry lock is never held while acquiring cart, metrics, persistence, or health locks. These constraints prevent a new lock cycle and preserve the current deadlock-avoidance strategy.

## SSE Connection Lifecycle

`GET /api/v1/stream` subscribes once, yields events and heartbeat comments, checks for client disconnection, and always unsubscribes in `finally`. Connection and disconnection are structured INFO events. Heartbeats are not logged at INFO.

During application shutdown, the realtime publisher closes first, rejecting new subscriptions and signaling existing subscribers to finish. The API server can then stop without streams holding shutdown open. Repeated close calls are safe. The headless API runtime follows the same lifecycle.

## Frontend Integration

`RealtimeProvider` is mounted once above the router. It owns the only `EventSource`, exposes connection state (`connecting`, `live`, `reconnecting`, `offline`), and offers a small typed subscription function. It is an event transport, not a global application store.

`useCart`, `useRecentEvents`, and `useMetrics` retain ownership of their feature state:

- perform an immediate REST load;
- consume their matching realtime event;
- ignore malformed or unrelated messages;
- reconcile once when the stream opens;
- run five-second fallback polling only while the stream is not live;
- abort requests, clear timers, and unsubscribe on unmount.

REST responses that began before a newer SSE update cannot overwrite that update. Each hook records its local realtime revision when starting a request and ignores stale completion if the revision changed while the request was in flight.

Event history stays bounded to the existing dashboard limit. Persisted event IDs are the primary deduplication key; the SSE sequence is the fallback key for activity that could not be persisted.

The dashboard and application shell show one compact realtime status indicator. EventSource's native reconnection is used; no second retry scheduler is added.

## Error Handling and Security

Malformed frontend messages are ignored with a development warning and never update feature state. Connection loss preserves the last successful data and activates slow REST fallback. Backend exceptions are not serialized into SSE payloads.

The stream uses the existing explicit CORS allowlist and adds streaming-safe cache and proxy-buffering headers. It contains application state only—never images, tensors, credentials, filesystem paths, or internal exception text. Authentication remains out of scope for this local portfolio application and is required before exposing the stream publicly.

## Testing Strategy

Backend deterministic tests cover message serialization, multiple subscribers, bounded queues, oldest-message eviction, unsubscribe cleanup, metrics throttling, publication after successful cart commands, SSE framing, disconnect cleanup, and idempotent shutdown. Tests use controlled clocks and application service calls; no camera, GUI, GPU, or YOLO inference is required.

Frontend tests use a mock `EventSource` and cover connection lifecycle, typed parsing, malformed messages, one shared connection, provider cleanup, cart/event/metrics updates, REST-first initialization, stale-response protection, deduplication, reconnect reconciliation, and fallback polling. Existing component and hook behavior remains covered.

An integration smoke test runs the real FastAPI app and browser frontend, triggers deterministic service events, verifies immediate UI updates, checks degraded connection state after backend interruption, and verifies reconciliation after restart where the local environment permits reliable restart automation.

## Alternatives Rejected

Endpoint-side state polling was rejected because it only moves polling into the server and cannot represent event timing reliably. WebSockets add unnecessary bidirectional protocol and lifecycle complexity for this server-to-browser workload. Redis and other external brokers are disproportionate for a single-process local edge demo.

## Deployment Limitation

The broadcaster is process-local. Multiple API workers or horizontally scaled application instances would not share events. A distributed deployment would replace the broadcaster internals with Redis pub/sub, NATS, or a similar broker while preserving the published contract and frontend EventSource interface.
