# Frontend Phase 6 Realtime SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace high-frequency cart, recent-event, and metrics polling with one resilient SSE connection while retaining REST snapshots, commands, history, and low-frequency health checks.

**Architecture:** Each runtime owns a thread-safe in-process broadcaster and application-level realtime publisher. FastAPI streams bounded subscriber queues through one versioned SSE endpoint, while a single React provider parses validated messages and lets feature hooks combine REST snapshots, live updates, and slow offline fallback polling.

**Tech Stack:** Python 3.11, standard-library threading/queue/dataclasses, FastAPI/Starlette StreamingResponse, Pydantic, React 19, TypeScript 6, browser EventSource, Vitest, Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-frontend-phase-6-realtime-sse-design.md`

## Global Constraints

- Do not change YOLO, ByteTrack, detection, tracking, checkout-zone behavior, or cart business rules.
- Use one SSE connection per React application instance; do not add WebSockets, Redis, external brokers, Redux, or Zustand.
- REST remains responsible for initial snapshots, reconciliation, sessions/history, session detail, health/readiness, and cart reset commands.
- Publish complete cart and metrics snapshots, never incremental cart mutations or per-frame metrics messages.
- Backend subscriber queues must be bounded and publishing must never block the vision loop.
- Health/readiness continues its existing five-second REST polling.
- All new production behavior follows test-driven development: write a focused failing test, confirm the expected failure, add the minimal implementation, then rerun the relevant suite.

---

### Task 1: Typed realtime configuration and broadcaster

**Files:**
- Modify: `src/smart_retail/config.py`
- Modify: `.env.example`
- Create: `src/smart_retail/realtime/__init__.py`
- Create: `src/smart_retail/realtime/models.py`
- Create: `src/smart_retail/realtime/broadcaster.py`
- Create: `tests/unit/test_realtime.py`
- Modify: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `RealtimeConfig(queue_capacity: int, heartbeat_seconds: float, metrics_interval_seconds: float)` on `AppConfig.realtime`.
- Produces: `RealtimeEventType` values `cart.updated`, `checkout.event`, and `metrics.updated`.
- Produces: immutable `RealtimeMessage(sequence: int, event_type: RealtimeEventType, timestamp: float, payload: RealtimePayload)`.
- Produces: `RealtimeBroadcaster.subscribe() -> RealtimeSubscription`, `publish(event_type, payload) -> RealtimeMessage`, `unsubscribe(subscription)`, `close()`, and `subscriber_count`.

- [ ] **Step 1: Write failing configuration tests**

Add tests proving defaults are queue capacity `64`, heartbeat `15.0`, and metrics interval `1.0`; environment overrides parse correctly; zero, negative, non-finite, boolean-like, and malformed values raise `ConfigurationError`.

- [ ] **Step 2: Run the configuration tests and confirm expected failures**

Run: `../../.venv/bin/python -m pytest tests/unit/test_config.py -q`

Expected: failures because `AppConfig.realtime` and its environment variables do not exist.

- [ ] **Step 3: Add minimal typed configuration**

Add `RealtimeConfig` using the validation style already established in `config.py`, load:

```python
SMART_RETAIL_REALTIME_QUEUE_CAPACITY=64
SMART_RETAIL_REALTIME_HEARTBEAT_SECONDS=15
SMART_RETAIL_REALTIME_METRICS_INTERVAL_SECONDS=1
```

Add safe examples to `.env.example` and include only non-sensitive realtime values in the startup summary.

- [ ] **Step 4: Run configuration tests to green**

Run: `../../.venv/bin/python -m pytest tests/unit/test_config.py -q`

- [ ] **Step 5: Write failing broadcaster tests**

Cover:

```python
subscription_a = broadcaster.subscribe()
subscription_b = broadcaster.subscribe()
message = broadcaster.publish(RealtimeEventType.CART_UPDATED, cart_snapshot)
assert subscription_a.get_nowait() == message
assert subscription_b.get_nowait() == message
```

Also assert monotonic sequence allocation, bounded queue size, oldest-message eviction, nonblocking publication, independent slow clients, unsubscribe cleanup, subscription closure, rejected subscription after close, and idempotent close.

- [ ] **Step 6: Run broadcaster tests and confirm expected import/API failures**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime.py -q`

- [ ] **Step 7: Implement immutable messages and the bounded broadcaster**

Use a registry `threading.Lock`, per-subscriber `queue.Queue(maxsize=capacity)`, `put_nowait`, and oldest-item eviction on `queue.Full`. Copy subscribers while holding the registry lock, release it before touching queues, and log only event type/subscriber metadata on backpressure.

- [ ] **Step 8: Run focused broadcaster and configuration tests**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime.py tests/unit/test_config.py -q`

- [ ] **Step 9: Commit the core realtime primitives**

```bash
git add .env.example src/smart_retail/config.py src/smart_retail/realtime tests/unit/test_config.py tests/unit/test_realtime.py
git commit -m "feat: add bounded realtime broadcaster"
```

### Task 2: Application realtime publisher and mutation integration

**Files:**
- Create: `src/smart_retail/realtime/publisher.py`
- Modify: `src/smart_retail/app.py`
- Modify: `src/smart_retail/api/service.py`
- Modify: `src/smart_retail/api/dependencies.py`
- Modify: `tests/unit/test_realtime.py`
- Modify: `tests/integration/test_application_services.py`
- Modify: `tests/integration/test_lifecycle.py`
- Modify: `tests/integration/test_headless_service.py`

**Interfaces:**
- Consumes: `RealtimeBroadcaster`, immutable `CartSnapshot`, `MetricsSnapshot`, and successful ADD/REMOVE/RESET activity.
- Produces: `RealtimePublisher.publish_cart(snapshot)`, `publish_checkout_event(activity)`, `publish_metrics_if_due(snapshot) -> bool`, `subscribe()`, and idempotent `close()`.
- Produces: `RealtimeCheckoutActivity` with optional persisted `event_id`/`session_id`, timestamp, track ID, product ID, event type, and unit price.
- Extends: `APIRuntime.subscribe_realtime() -> RealtimeSubscription`.

- [ ] **Step 1: Write failing publisher tests**

Use a controllable monotonic clock to prove the first metrics snapshot publishes, subsequent calls before one second coalesce, the first call at/after one second publishes the newest snapshot, cart publication is immediate, checkout activity is explicit, and close ends all subscriptions.

- [ ] **Step 2: Run publisher tests and confirm expected failures**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime.py -q`

- [ ] **Step 3: Implement the minimal publisher**

The publisher delegates queue behavior to the broadcaster, owns only metrics cadence and activity construction, and accepts injected wall/monotonic clocks for deterministic tests.

- [ ] **Step 4: Write failing application publication tests**

Assert that:

- a successful ENTER publishes one `cart.updated` and one `checkout.event`;
- a duplicate ENTER publishes nothing;
- EXIT and track expiry publish updated full-cart snapshots;
- reset from OpenCV and API publishes empty cart plus RESET activity;
- persistence failure still publishes activity with nullable persistence identifiers;
- per-frame metrics calls publish no faster than configured cadence;
- publication occurs with immutable snapshots and never invokes subscriber I/O;
- repeated shutdown closes realtime once without changing existing resource order guarantees.

- [ ] **Step 5: Run application tests and confirm expected failures**

Run: `../../.venv/bin/python -m pytest tests/integration/test_application_services.py tests/integration/test_lifecycle.py tests/integration/test_headless_service.py -q`

- [ ] **Step 6: Integrate publisher into both runtimes**

Give `SmartRetailApplication` and `HeadlessAPIRuntime` explicit publisher dependencies with local defaults for test ergonomics. Make `_record_cart_event` return the persisted `CartEvent | None`; create the realtime activity regardless of persistence success. Generate cart snapshots while the cart lock is held internally, then publish after it is released. Call the metrics throttle after `record_frame`. Close realtime before API/database teardown and reject new subscriptions during stopping.

- [ ] **Step 7: Run publisher and application integration tests to green**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime.py tests/integration/test_application_services.py tests/integration/test_lifecycle.py tests/integration/test_headless_service.py -q`

- [ ] **Step 8: Commit application publication**

```bash
git add src/smart_retail/app.py src/smart_retail/api/dependencies.py src/smart_retail/api/service.py src/smart_retail/realtime/publisher.py tests/unit/test_realtime.py tests/integration/test_application_services.py tests/integration/test_lifecycle.py tests/integration/test_headless_service.py
git commit -m "feat: publish realtime checkout state"
```

### Task 3: Versioned FastAPI SSE endpoint

**Files:**
- Create: `src/smart_retail/api/routes/realtime.py`
- Modify: `src/smart_retail/api/routes/__init__.py`
- Modify: `src/smart_retail/api/factory.py`
- Modify: `src/smart_retail/api/models.py`
- Create: `tests/unit/test_realtime_api.py`
- Modify: `tests/integration/test_api.py`
- Modify: `docs/API.md`

**Interfaces:**
- Consumes: `APIRuntime.subscribe_realtime()` and configured heartbeat interval.
- Produces: `GET /api/v1/stream` with `text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`.
- Produces: explicit Pydantic response models and `encode_sse_message(message) -> str`.

- [ ] **Step 1: Write failing schema and encoder tests**

Assert exact JSON-safe representations for cart, checkout activity, and metrics payloads; ISO UTC timestamps; SSE `id`, `event`, and one-line JSON `data`; and heartbeat output equal to `: heartbeat\n\n`.

- [ ] **Step 2: Run encoder tests and confirm expected failures**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime_api.py -q`

- [ ] **Step 3: Add deliberate realtime response schemas and encoder**

Reuse `CartResponse` and `MetricsResponse`; add a dedicated `RealtimeCheckoutEventResponse` and typed envelope models. Never serialize dataclasses with arbitrary `__dict__` access.

- [ ] **Step 4: Write failing stream lifecycle tests**

Test subscription, one published event, content type/headers, multiple clients, heartbeat when idle, disconnect cleanup in generator `finally`, client cancellation, closed-broadcaster termination, and no leaked subscribers after application shutdown. Use controlled subscriptions/request doubles so tests never wait for real heartbeat time.

- [ ] **Step 5: Run stream tests and confirm expected failures**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime_api.py tests/integration/test_api.py -q`

- [ ] **Step 6: Implement `/api/v1/stream`**

Use `StreamingResponse` over an async generator. Retrieve bounded queue items through `asyncio.to_thread` with a short timeout so disconnect/shutdown checks remain responsive. Always unsubscribe in `finally`; log `realtime.client_connected` and `realtime.client_disconnected` without payloads.

- [ ] **Step 7: Run API tests to green**

Run: `../../.venv/bin/python -m pytest tests/unit/test_realtime_api.py tests/integration/test_api.py -q`

- [ ] **Step 8: Update API documentation and commit**

```bash
git add src/smart_retail/api docs/API.md tests/unit/test_realtime_api.py tests/integration/test_api.py
git commit -m "feat: expose realtime SSE stream"
```

### Task 4: Typed frontend EventSource transport

**Files:**
- Create: `frontend/src/types/realtime.ts`
- Create: `frontend/src/services/realtime.ts`
- Create: `frontend/src/services/realtime.test.ts`
- Modify: `frontend/src/config.ts`
- Modify: `frontend/src/config.test.ts`

**Interfaces:**
- Consumes: `appConfig.apiBaseUrl` and `GET /api/v1/stream`.
- Produces: discriminated `RealtimeEvent` union and `RealtimeConnectionState = 'connecting' | 'live' | 'reconnecting' | 'offline'`.
- Produces: `parseRealtimeEvent(value: unknown) -> RealtimeEvent | null` and `RealtimeClient` with `connect()`, `subscribe(listener)`, and idempotent `close()`.

- [ ] **Step 1: Write failing runtime-validation tests**

Provide valid fixtures for all three events and malformed fixtures for unknown types, invalid timestamps/sequences, incomplete cart rows, invalid checkout activity, negative metrics, and non-object JSON. Assert invalid input returns `null` without throwing.

- [ ] **Step 2: Run parser tests and confirm expected failures**

Run: `npm test -- --run src/services/realtime.test.ts`

- [ ] **Step 3: Implement strict typed parsing**

Move reusable API validators from `services/api.ts` into narrowly exported validator helpers only where necessary, or duplicate no schema logic. The parser accepts `unknown`, validates every field, and returns the discriminated union without `any`.

- [ ] **Step 4: Write failing EventSource lifecycle tests**

With an injected EventSource factory, assert one connection, open/error state transitions, native reconnect preservation, listener fan-out, unrelated named event handling, malformed JSON warnings, listener unsubscribe, and `close()` cleanup.

- [ ] **Step 5: Run lifecycle tests and confirm expected failures**

Run: `npm test -- --run src/services/realtime.test.ts`

- [ ] **Step 6: Implement the centralized client**

Register named listeners for `cart.updated`, `checkout.event`, and `metrics.updated`; do not build a custom reconnect timer. Add frontend constants for five-second fallback cadence and offline-state delay instead of scattering values.

- [ ] **Step 7: Run realtime service/config tests to green**

Run: `npm test -- --run src/services/realtime.test.ts src/config.test.ts`

- [ ] **Step 8: Commit the frontend transport**

```bash
git add frontend/src/config.ts frontend/src/config.test.ts frontend/src/types/realtime.ts frontend/src/services/realtime.ts frontend/src/services/realtime.test.ts
git commit -m "feat: add typed EventSource client"
```

### Task 5: One application-level realtime provider and status UI

**Files:**
- Create: `frontend/src/realtime/RealtimeProvider.tsx`
- Create: `frontend/src/realtime/RealtimeProvider.test.tsx`
- Create: `frontend/src/hooks/useRealtime.ts`
- Create: `frontend/src/components/RealtimeStatus.tsx`
- Create: `frontend/src/components/RealtimeStatus.test.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/layouts/AppLayout.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: one `RealtimeClient`.
- Produces: context `{ status, connectionRevision, subscribe }`.
- Produces: `useRealtime()` and a compact, text-labeled `RealtimeStatus` indicator.

- [ ] **Step 1: Write failing provider tests**

Assert one client is created for multiple consumers, connection state is exposed, messages fan out, each successful open increments `connectionRevision`, unsubscribed consumers stop receiving events, and provider unmount closes the client exactly once.

- [ ] **Step 2: Run provider tests and confirm expected failures**

Run: `npm test -- --run src/realtime/RealtimeProvider.test.tsx`

- [ ] **Step 3: Implement the minimal provider**

Mount it once inside `BrowserRouter` and above `App`. Keep only transport state in context; do not store cart, event history, or metrics there.

- [ ] **Step 4: Write failing status component tests**

Assert visible labels for Live, Connecting, Reconnecting, and Offline; accessible status semantics; and no color-only meaning.

- [ ] **Step 5: Run status tests and confirm expected failures**

Run: `npm test -- --run src/components/RealtimeStatus.test.tsx`

- [ ] **Step 6: Add compact status presentation**

Place the indicator in the existing application shell without displacing primary navigation. Add token-based state styles, visible focus behavior where interactive, and reduced-motion-safe transitions.

- [ ] **Step 7: Run provider/layout tests to green**

Run: `npm test -- --run src/realtime/RealtimeProvider.test.tsx src/components/RealtimeStatus.test.tsx src/App.test.tsx`

- [ ] **Step 8: Commit provider and status UI**

```bash
git add frontend/src/realtime frontend/src/hooks/useRealtime.ts frontend/src/components/RealtimeStatus.tsx frontend/src/components/RealtimeStatus.test.tsx frontend/src/main.tsx frontend/src/layouts/AppLayout.tsx frontend/src/styles/global.css
git commit -m "feat: add shared realtime provider"
```

### Task 6: Migrate cart, events, and metrics hooks from normal polling

**Files:**
- Modify: `frontend/src/hooks/useCart.ts`
- Modify: `frontend/src/hooks/useCart.test.ts`
- Modify: `frontend/src/hooks/useRecentEvents.ts`
- Modify: `frontend/src/hooks/useRecentEvents.test.ts`
- Modify: `frontend/src/hooks/useMetrics.ts`
- Modify: `frontend/src/hooks/useMetrics.test.ts`
- Modify: `frontend/src/components/cart/CurrentCart.test.tsx`
- Modify: `frontend/src/components/events/RecentEvents.test.tsx`
- Modify: `frontend/src/components/observability/LiveMetrics.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/pages/SystemPage.test.tsx`

**Interfaces:**
- Consumes: `useRealtime()` status, connection revision, and typed subscription.
- Preserves: existing hook return contracts and REST reset behavior.
- Removes: normal 1.5-second cart, 2-second event, and 2-second metrics polling loops.
- Adds: five-second fallback polling only while realtime is not live.

- [ ] **Step 1: Rewrite cart tests for REST-first plus SSE**

Assert immediate REST load, full `cart.updated` replacement, no regular polling while live, five-second fallback while disconnected, fallback cancellation on reconnect, one reconciliation fetch per connection revision, stale REST response rejection after a newer SSE message, reset response use, reset reconciliation, and cleanup.

- [ ] **Step 2: Run cart hook tests and confirm failures against polling implementation**

Run: `npm test -- --run src/hooks/useCart.test.ts`

- [ ] **Step 3: Implement cart SSE consumption and fallback**

Keep reset as POST REST. Track a realtime revision ref; a REST completion updates state only if no newer cart event arrived since request start. Do not run SSE and fallback polling simultaneously.

- [ ] **Step 4: Rewrite recent-event tests for live activity**

Assert immediate REST load, newest-first live insertion, bounded length eight, persisted-ID deduplication, SSE-sequence fallback deduplication, reconnect reconciliation, merge safety around in-flight REST, five-second fallback, and cleanup.

- [ ] **Step 5: Run event hook tests and confirm failures**

Run: `npm test -- --run src/hooks/useRecentEvents.test.ts`

- [ ] **Step 6: Implement bounded event merging**

Use persisted event ID when present; otherwise use the envelope sequence. Preserve display-compatible fields and never infer identity from product text.

- [ ] **Step 7: Rewrite metrics tests for live snapshots**

Assert immediate REST load, full `metrics.updated` replacement, no regular live polling, five-second disconnected fallback, reconnect reconciliation, stale REST protection, and cleanup.

- [ ] **Step 8: Run metrics hook tests and confirm failures**

Run: `npm test -- --run src/hooks/useMetrics.test.ts`

- [ ] **Step 9: Implement metrics SSE consumption and fallback**

Preserve the existing hook/component return contracts so Dashboard and System presentation need no business-data duplication.

- [ ] **Step 10: Run all changed hook and component tests**

Run: `npm test -- --run src/hooks/useCart.test.ts src/hooks/useRecentEvents.test.ts src/hooks/useMetrics.test.ts src/components/cart/CurrentCart.test.tsx src/components/events/RecentEvents.test.tsx src/components/observability/LiveMetrics.test.tsx src/pages/DashboardPage.test.tsx src/pages/SystemPage.test.tsx`

- [ ] **Step 11: Commit polling migration**

```bash
git add frontend/src/hooks frontend/src/components frontend/src/pages
git commit -m "feat: consume live checkout updates"
```

### Task 7: Documentation, integration verification, and full quality gate

**Files:**
- Create: `docs/REALTIME.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONCURRENCY.md`
- Modify: `docs/LIFECYCLE.md`
- Modify: `README.md`
- Modify: `frontend/README.md`
- Modify: `docs/TESTING.md`
- Modify: `tests/integration/test_api.py` only if a final transport regression needs coverage

**Interfaces:**
- Documents: `/api/v1/stream`, event contracts, REST/SSE split, reconnect/fallback behavior, backpressure, lifecycle, security, and single-process limitation.

- [ ] **Step 1: Write realtime and architecture documentation**

Explain why SSE fits one-way updates, why reset stays REST, why health/readiness stays low-frequency REST, exact event types, one-second metrics throttle, 64-message queue capacity, oldest-message eviction, heartbeat comments, frontend reconciliation, authentication limitation, and future external-broker replacement.

- [ ] **Step 2: Update user-facing run documentation**

Add the stream endpoint and browser connection status to root/frontend READMEs without overstating public-deployment readiness.

- [ ] **Step 3: Run backend lint and formatting checks**

Run:

```bash
../../.venv/bin/python -m ruff check app.py src tests training
../../.venv/bin/python -m ruff format --check app.py src tests training
```

- [ ] **Step 4: Run complete backend tests and coverage**

Run:

```bash
../../.venv/bin/python -m pytest tests/unit tests/contracts tests/integration -q --cov=smart_retail --cov-branch --cov-report=term-missing --cov-fail-under=85
```

- [ ] **Step 5: Run complete frontend verification**

Run:

```bash
npm run lint
npm test -- --run
npm run build
```

- [ ] **Step 6: Perform real backend/frontend integration smoke test**

Start the headless FastAPI service and Vite frontend. Open one browser app, confirm exactly one stream request, trigger deterministic cart/event/metrics publication through runtime service calls, and verify immediate UI updates. Stop/restart the backend, verify Reconnecting/Offline state and five-second REST fallback, then verify reconnection reconciliation. Record any environmental limitation rather than claiming unobserved behavior.

- [ ] **Step 7: Inspect resource and request behavior**

Confirm no leaked subscribers after browser navigation/refresh, no unbounded frontend history, no duplicate EventSource instances, controlled one-second metrics publication, no normal live cart/event/metrics polling, and clean backend shutdown.

- [ ] **Step 8: Run diff and secret hygiene checks**

Run:

```bash
git diff --check
git status --short
git diff --stat origin/main...HEAD
```

Inspect all changed files for accidental credentials, generated output, model artifacts, databases, logs, and caches.

- [ ] **Step 9: Commit documentation and final adjustments**

```bash
git add README.md frontend/README.md docs
git commit -m "docs: document realtime SSE architecture"
```

- [ ] **Step 10: Request code review and apply only evidence-backed fixes**

Use `superpowers:requesting-code-review`, address actionable findings with focused failing tests first, and rerun the full quality gate after any change.
