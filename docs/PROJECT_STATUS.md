# Project status

Smart Retail Checkout is feature-complete for its stated local portfolio scope.
The project is a technically defensible simulation, not a production store
checkout product.

## Implemented

- webcam capture, mirroring, retries, and clean release on macOS;
- YOLOv8 detection with class filtering, confidence configuration, MPS/CPU
  selection, and one-time model loading;
- ByteTrack association with persistent IDs and short-occlusion buffering;
- normalized checkout zone, centroid evaluation, hysteresis, confirmation
  frames, and track expiry;
- exact track-ID cart membership, quantity aggregation, deterministic integer
  currency, remove, reset, and duplicate prevention;
- native OpenCV overlay, notifications, FPS, status, and keyboard controls;
- immutable domain snapshots and separation from framework/infrastructure code;
- thread-safe shared cart, health, metrics, lifecycle, and API coordination;
- SQLite product, checkout-session, and meaningful cart-event history;
- FastAPI REST, liveness/readiness, safe errors, CORS, and generated OpenAPI;
- bounded single-process SSE publication with heartbeats, backpressure, and
  reconnect/reconciliation behavior;
- React/Vite/TypeScript dashboard for cart, events, sessions, system status,
  operational metrics, and accessible responsive interaction;
- structured logging, rotating file option, graceful startup/shutdown, tests,
  coverage, packaging, Docker support for headless services, and GitHub CI;
- disabled-by-default, clearly labeled hardware-free demo mode that reuses
  application services, SQLite, metrics, and SSE.

## Deferred by design

- browser video, WebRTC, and multi-camera streaming;
- authentication, authorization, payments, refunds, and customer identity;
- a distributed event broker and horizontally scaled API instances;
- cloud deployment, Kubernetes, and centralized observability;
- a custom SKU detector and production dataset/model monitoring;
- appearance-based re-identification and cross-camera handoff;
- product catalog administration and inventory integration.

## Known limitations

- COCO categories are not individual retail SKUs.
- ByteTrack does not use appearance embeddings; long occlusion or similar
  nearby objects can fragment or switch IDs.
- A new tracking ID cannot be safely linked to an old one without stronger
  evidence, so the application deliberately avoids guessing.
- Centroid crossing is explainable but does not infer shelf pickup, intent,
  customer ownership, or fraud.
- One camera and local lighting/background conditions limit detection quality.
- SQLite and the in-process broadcaster target one local application instance.
- The API and demo controls are unauthenticated and must remain on a trusted
  local interface.
- Demo mode validates application behavior, not computer-vision accuracy.

## Readiness assessment

The repository is ready for GitHub review, local demonstrations, and software
engineering interviews once the presenter captures verified screenshots or a
short video. Deterministic business, API, persistence, concurrency, lifecycle,
and frontend behavior run in headless CI. A real webcam smoke test remains the
appropriate final verification for machine-specific vision performance.
