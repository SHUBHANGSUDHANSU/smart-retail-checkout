# REST API

FastAPI exposes application and business state; it never performs YOLO or
ByteTrack work inside an HTTP request. OpenAPI is generated from the same route
and Pydantic definitions used at runtime.

## Running the API

The native webcam application starts an embedded API by default:

```bash
smart-retail
```

The hardware-free API service is useful for local API work and containers:

```bash
smart-retail-api
```

Both use `http://127.0.0.1:8000` by default. Override the bind address or port
through `SMART_RETAIL_API_HOST` and `SMART_RETAIL_API_PORT`. A non-loopback bind
emits a warning because authentication is intentionally absent.

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## Execution modes

The embedded API and OpenCV interface share one native
`SmartRetailApplication`. The headless entry point uses `HeadlessAPIRuntime`,
which owns a separate cart, health state, metrics service, and SQLite session.
Starting both processes does not make their in-memory carts synchronize.

Routes depend on the `APIRuntime` protocol rather than either concrete runtime.
That protocol contains only snapshot, reset, and history operations required by
the HTTP presentation layer.

## Endpoints

| Method | Path | Success | Purpose |
|---|---|---:|---|
| `GET` | `/health` | `200` | Process liveness and monotonic uptime |
| `GET` | `/ready` | `200` | Cached component readiness |
| `GET` | `/api/v1/cart` | `200` | One consistent aggregated cart snapshot |
| `POST` | `/api/v1/cart/reset` | `200` | Reset through the shared cart/checkout service |
| `GET` | `/api/v1/events?limit=50` | `200` | Newest persisted events; limit `1..200` |
| `GET` | `/api/v1/sessions?limit=20` | `200` | Newest persisted sessions; limit `1..100` |
| `GET` | `/api/v1/sessions/{session_id}` | `200` | One positive session ID and its ordered events |
| `GET` | `/api/v1/metrics` | `200` | Thread-safe current metrics snapshot |

All currency fields are integer rupees. Timestamps are serialized as UTC ISO
8601 values.

## Response examples

### Liveness

```http
GET /health
```

```json
{
  "status": "ok",
  "uptime_seconds": 125.318
}
```

Liveness only confirms that the process and API can respond. It does not probe
the camera, model, or database.

### Readiness

```http
GET /ready
```

```json
{
  "status": "ready",
  "application_state": "running",
  "components": {
    "core_services": "ready",
    "model": "ready",
    "camera": "ready",
    "vision_pipeline": "ready",
    "database": "ready"
  }
}
```

If an enabled critical component is unavailable, the same schema is returned
with status `not_ready` and HTTP `503`. Hardware components are `disabled` and
readiness-compatible in the headless service.

### Cart

```http
GET /api/v1/cart
```

```json
{
  "items": [
    {
      "product_id": "bottle",
      "product_name": "Water Bottle",
      "quantity": 2,
      "unit_price": 40,
      "subtotal": 80
    }
  ],
  "total_quantity": 2,
  "total": 80
}
```

Items and the total come from one immutable cart snapshot, so a concurrent
vision update cannot mix quantities from one version with a total from another.

### Reset

```http
POST /api/v1/cart/reset
```

```json
{
  "status": "reset",
  "removed_track_count": 2,
  "cart": {
    "items": [],
    "total_quantity": 0,
    "total": 0
  }
}
```

The endpoint uses the same synchronized reset operation as the OpenCV `R` key.
If application shutdown has started, it returns `503` rather than mutating
state. `GET` is not allowed for reset.

### Events and sessions

```http
GET /api/v1/events?limit=2
```

```json
{
  "events": [
    {
      "id": 12,
      "session_id": 4,
      "timestamp": "2026-08-24T10:15:30Z",
      "track_id": 7,
      "product_id": "bottle",
      "event_type": "ADD",
      "unit_price": 40
    }
  ],
  "limit": 2
}
```

`GET /api/v1/sessions` returns session summaries. Session detail adds that
session's events in insertion order. Unknown positive IDs return `404` with
code `session_not_found`.

### Metrics

```http
GET /api/v1/metrics
```

The response includes the counters, gauges, and rolling averages documented in
[METRICS.md](METRICS.md), including frame counts, active tracks, FPS, inference
latency, checkout/cart event counts, current cart values, and error counters.

## Error model

Expected and unexpected failures use a stable JSON shape:

```json
{
  "code": "validation_error",
  "message": "Request validation failed."
}
```

| Status | Code | Meaning |
|---:|---|---|
| `404` | `session_not_found` | The requested persisted session does not exist |
| `405` | Framework response | The HTTP method is not allowed, such as `GET` reset |
| `422` | `validation_error` | A query or path value violates its bounds or type |
| `503` | `application_not_ready` | A reset arrived outside the running lifecycle |
| `503` | `persistence_unavailable` | SQLite history is disabled or failed |
| `500` | `internal_error` | An unexpected route failure occurred |

Internal exception messages and Python tracebacks are never returned. The
server logs unexpected failures with selected fields and a traceback.

## Thread safety

API workers and the vision loop share application state in native mode.
`CartService` returns an immutable snapshot built under one lock. Reset and
checkout mutations share a command lock with deterministic ordering. Health
and metrics services use their own locks and immutable snapshots. SQLite work
uses short-lived connections and does not run under the cart lock. See
[CONCURRENCY.md](CONCURRENCY.md) for ownership and lock ordering.

## Security scope

Responses include `X-Content-Type-Options: nosniff` and
`Cache-Control: no-store`. CORS is enabled only for the explicit origins in
`SMART_RETAIL_API_CORS_ALLOWED_ORIGINS`; its defaults are
`http://localhost:5173` and `http://127.0.0.1:5173`. It does not allow
credentials. Its method allowlist supports the Frontend Phase 2 application's
`GET` health/cart reads and `POST` cart reset. This is a response-sharing policy,
not authentication or method authorization; non-browser clients do not enforce
CORS. Browsers at unlisted origins normally cannot read CORS responses, but a
simple bodyless `POST` can still reach and mutate the reset endpoint even when
its response is unreadable. There are no request-body, filesystem, inference,
command-execution, or video endpoints.

The API has no authentication, authorization, TLS, or rate limiting. In
particular, any client that can reach the service can invoke cart reset. Keep it
on a trusted local interface; see [SECURITY.md](SECURITY.md) before considering
non-local deployment.
