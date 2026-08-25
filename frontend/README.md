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
Frontend Phase 2 uses `GET /health`, `GET /api/v1/cart`, and
`POST /api/v1/cart/reset`.

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

## Phase 2 scope

Routes are available at:

- `/` — Dashboard
- `/sessions` — Sessions placeholder
- `/system` — System placeholder

Backend health and the Current Cart use real API data. Session history, recent
events, metrics, charts, camera streaming, and richer system status are
deferred.
