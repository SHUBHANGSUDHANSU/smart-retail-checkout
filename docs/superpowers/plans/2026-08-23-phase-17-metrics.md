# Production Phase 17 Lightweight Metrics Implementation Plan

**Goal:** Add bounded, thread-safe runtime and business metrics with a read-only FastAPI endpoint, without changing checkout behavior.

**Architecture:** A framework-independent `MetricsService` owns counters, gauges, bounded latency samples, and immutable snapshots. The application coordinator records metrics at existing camera, vision, checkout, cart, and persistence boundaries. FastAPI reads one consistent snapshot through the application-state protocol.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-17-metrics-design.md`

## Task 1: Metrics service and configuration

**Files:** create `src/smart_retail/metrics.py`, create `tests/test_metrics.py`, modify `src/smart_retail/config.py`, `tests/test_config.py`, `.env.example`.

- [ ] Write failing tests for counter increments, gauge replacement, bounded rolling latency averages, injected monotonic uptime, invalid rolling-window configuration, and concurrent snapshots.
- [ ] Implement frozen `MetricsSnapshot` and locked `MetricsService` with operation-oriented update methods.
- [ ] Add immutable `MetricsConfig`, environment parsing, validation, and safe-summary output.
- [ ] Run focused metrics and configuration tests.

## Task 2: Camera, application, and business instrumentation

**Files:** modify `src/smart_retail/infrastructure/camera.py`, `src/smart_retail/app.py`, `tests/test_app.py`, and focused fixtures as needed.

- [ ] Write failing tests for failed-read callbacks, successful frame recording, checkout/cart/reset counters, camera errors, and persistence errors.
- [ ] Inject an optional dropped-frame callback into the camera adapter.
- [ ] Create one metrics service in `build_application` and pass it explicitly to the coordinator.
- [ ] Time vision-plus-checkout processing with `time.perf_counter`; do not include capture or rendering.
- [ ] Record accepted detections, unique active track IDs, current FPS, successful cart mutations, resets, and caught system errors.
- [ ] Keep metric updates outside expensive locks and avoid per-frame INFO logs.
- [ ] Run focused application, camera, persistence, and concurrency tests.

## Task 3: Metrics API

**Files:** create `src/smart_retail/api/routes/metrics.py`, modify `src/smart_retail/api/models.py`, `src/smart_retail/api/factory.py`, `src/smart_retail/application_state.py`, and `tests/test_api.py`.

- [ ] Write a failing endpoint test covering the complete JSON snapshot and OpenAPI path.
- [ ] Add a Pydantic response model and `GET /api/v1/metrics` route.
- [ ] Read exactly one immutable application snapshot; do not query hardware or SQLite.
- [ ] Run focused API tests.

## Task 4: Documentation and verification

**Files:** create `docs/METRICS.md`; modify `README.md`, `docs/ARCHITECTURE.md`, `docs/CONCURRENCY.md`, and `docs/PRODUCTION_ARCHITECTURE.md` where relevant.

- [ ] Document every metric, counter versus gauge semantics, the rolling window, thread safety, and a future Prometheus adapter path.
- [ ] Update configuration and API examples.
- [ ] Run syntax/import checks and the complete test suite.
- [ ] Inspect the diff for vision/tracking behavioral changes and remove any accidental scope expansion.

## Constraints

- Do not add monitoring dependencies, exporters, labels, or metric persistence.
- Do not store unbounded frame history.
- Do not alter YOLO, ByteTrack, zone, cart, or readiness algorithms.
- Use strict red-green-refactor for each behavior.
- The repository has no Git `HEAD`; use passing verification checkpoints instead of partial commits.
