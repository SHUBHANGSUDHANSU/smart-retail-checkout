# Smart Retail Checkout Frontend

The React operator dashboard for Smart Retail Checkout. It is intentionally a
separate process from the native Python webcam application: the browser reads
state from the FastAPI service while YOLO, ByteTrack, checkout events, and the
OpenCV window stay in the backend process.

## Prerequisites

- Node.js `^20.19.0`, `^22.12.0`, or `>=24.0.0`
- The Python backend installed according to the root [README](../README.md)

## Install and configure

From this directory:

```bash
npm ci
```

The dashboard defaults to `http://localhost:8000`. To override it locally,
create an ignored environment file:

```bash
cp .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

`VITE_API_BASE_URL` must be an absolute HTTP or HTTPS origin without a path or
credentials. The local `.env` file is not committed; use `.env.example` as the
safe reference.

## Run the backend

For the full shared webcam, OpenCV, and API experience, start the native
application from the repository root:

```bash
smart-retail
```

For hardware-free API development, use the separate headless service instead:

```bash
smart-retail-api
```

The headless service owns its own in-memory cart and session, so it does not
share live state with a separately running webcam process.

## Run the dashboard

```bash
npm run dev
```

Vite serves the dashboard at `http://localhost:5173` by default. The backend
shares CORS responses with the configured local development origins
`http://localhost:5173` and `http://127.0.0.1:5173` by default. Change that
browser-origin allowlist with `SMART_RETAIL_API_CORS_ALLOWED_ORIGINS` when using
a different local frontend origin. This policy is not API authentication;
the frontend uses `GET /health`, `GET /ready`, `GET /api/v1/metrics`,
`GET /api/v1/cart`, `POST /api/v1/cart/reset`, and the checkout-history
endpoints described below.

Useful commands:

```bash
npm test
npm run lint
npm run build
npm run preview
```

The `preview` script is pinned to port `5173`, matching the backend's default
CORS allowlist. Stop the development server before starting preview because
both commands use the same port.

## Current Cart

The Dashboard loads the shared backend cart immediately and then polls
`GET /api/v1/cart` every 1.5 seconds. Polls are scheduled only after the prior
request settles, so slow requests do not overlap. The card preserves its last
successful snapshot during background failures and offers a manual retry.

Reset uses `POST /api/v1/cart/reset`, the same synchronized operation used by
the OpenCV `R` key. The frontend asks for confirmation, prevents duplicate
submissions, uses the returned server snapshot immediately, and performs one
follow-up read to reconcile state. The reset endpoint remains unauthenticated
and is suitable only for this trusted local demo.

## Checkout history

The Dashboard loads `GET /api/v1/events?limit=8` immediately and refreshes it
every two seconds. Like cart polling, the next timer starts only after the
current request settles. Existing events remain visible if a background
refresh fails, and a compact retry action is available.

`GET /api/v1/sessions?limit=20` supplies the Sessions page. It is loaded once
when the page opens because the backend provides a bounded newest-first list,
not pagination. Active sessions are identified by the backend's
`ended_at: null` state; completed sessions display the persisted final total.

Selecting a session opens `/sessions/:sessionId`, backed by
`GET /api/v1/sessions/{session_id}`. The page shows persisted session metadata
and its insertion-ordered event history. A backend `404` becomes a clean
"Session not found" state; unavailable history shows a retryable local error.
Timestamps remain ISO strings at the API boundary and are formatted in the
browser's local timezone for display.

The event API exposes persisted `product_id` values rather than catalog display
names. The frontend converts separators and capitalization for readability but
does not invent product metadata.

## Health, readiness, and metrics

The Dashboard and System page read the backend's real observability endpoints:

- `GET /health` reports process liveness and uptime.
- `GET /ready` reports overall readiness, application lifecycle state, and the
  backend-provided component map. A structured `503` response is displayed as
  a not-ready/degraded state rather than being reduced to a network error.
- `GET /api/v1/metrics` reports the current thread-safe metrics snapshot.

Metrics refresh every two seconds. Health and readiness refresh together every
five seconds. Each polling loop waits for its current request to settle before
scheduling the next one, aborts work when its page unmounts, and preserves the
last successful data during a background failure.

The Dashboard shows a concise status and vision-metrics summary. `/system`
shows liveness, readiness, application state, every component returned by the
backend, and all available vision, checkout, and runtime metrics. Missing data
uses an em dash or a clear unavailable state; the frontend does not invent
performance thresholds. Current-value cards are used because the backend does
not expose time-series history.

The headless `smart-retail-api` mode reports model, camera, and vision pipeline
as `disabled`; this is distinct from `unavailable`. Run `smart-retail` to see
live FPS, inference, detection, track, and camera metrics from the native vision
pipeline.

## Current scope

Routes are available at:

- `/` — Dashboard
- `/sessions` — persisted checkout-session history
- `/sessions/:sessionId` — one session and its event history
- `/system` — detailed health, readiness, component, and metrics view

Backend health/readiness, Current Cart, Recent Events, Sessions, and metrics all
use real API data. Historical charts, camera streaming, WebSockets,
authentication, and global client-state management remain deferred.
