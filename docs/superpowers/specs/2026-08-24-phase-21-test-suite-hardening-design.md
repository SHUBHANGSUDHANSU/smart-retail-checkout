# Production Phase 21 Test-Suite Hardening Design

## Goal

Reorganize and strengthen the deterministic test suite around domain,
subsystem, and integration boundaries without testing Ultralytics itself or
requiring a network, webcam, GUI, accelerator, model weights, or cloud service.

## Current baseline

- Pytest collects 133 tests and 36 `unittest` subtests.
- The complete suite passes locally on Python 3.11.
- Combined branch-aware coverage is 86.73 percent.
- Required cart, zone/event, persistence, API, and concurrency scenarios are
  substantially covered, but the files are flat and some tests mix unit,
  adapter, orchestration, and persistence responsibilities.
- Domain validation in `domain/events.py` and `domain/models.py`, product
  catalog failure handling, selected SQLite failure branches, and application
  service error paths are weaker than the central cart/event behavior.
- Vision detector coverage is intentionally lower because Phase 21 must not
  test Ultralytics or load a model.
- The repository has no initial commit or valid `HEAD`, so the design and
  implementation remain in the working tree unless repository initialization
  is authorized later.

## Selected approach

Use a targeted directory reorganization rather than rewriting every test.
Existing valuable assertions remain, while high-value files are split at real
responsibility boundaries and repetitive setup becomes pytest fixtures.

Rejected alternatives:

1. A complete conversion from `unittest` to pytest would create large review
   noise without improving behavior coverage proportionally.
2. Pytest markers without directories would leave subsystem ownership less
   discoverable and would not satisfy the requested unit/integration structure
   as clearly.

## Test structure

The suite will use this responsibility-based layout:

```text
tests/
├── conftest.py
├── unit/
│   ├── test_cart.py
│   ├── test_zone.py
│   ├── test_events.py
│   ├── test_catalog.py
│   ├── test_config.py
│   ├── test_metrics.py
│   ├── test_health.py
│   ├── test_logging.py
│   ├── test_api_server.py
│   ├── test_vision.py
│   └── test_ui.py
├── integration/
│   ├── test_database.py
│   ├── test_api.py
│   ├── test_application_services.py
│   ├── test_application.py
│   ├── test_concurrency.py
│   └── test_lifecycle.py
└── contracts/
    ├── test_ci_configuration.py
    └── test_containerization.py
```

`contracts/` is retained because Docker and workflow policy tests are neither
domain units nor runtime integrations. The folder is small and has a concrete
responsibility rather than being an empty abstraction.

## Fixture strategy

`tests/conftest.py` will provide only broadly reusable, deterministic fixtures:

- a literal product catalog, independent of JSON loading;
- a fresh `CartService` per test;
- a tracked-object factory with literal bounding boxes;
- a standard checkout zone and event engine with an injected clock.

`tests/integration/conftest.py` will own boundary fixtures that require cleanup:

- a repository initialized against pytest's temporary path;
- a configured API/application service using a temporary SQLite database;
- in-process FastAPI clients where reuse makes route tests clearer.

Fixtures will use function scope unless an immutable value is safe to share.
No fixture will expose mutable state across tests or perform network/hardware
work.

## Unit behavior coverage

### Cart

Tests will explicitly demonstrate:

- one physical tracked item is added once;
- duplicate additions for the same track do not change quantity or total;
- removing the exact track updates the aggregate;
- removing an unknown track returns safely;
- two tracks of the same class aggregate to quantity two;
- reset clears membership and totals;
- unsupported detector classes are ignored;
- returned snapshots remain internally consistent and detached.

### Zone and event engine

Pure zone geometry stays in `test_zone.py`. Event state-machine behavior moves
to `test_events.py` and covers:

- OUTSIDE to INSIDE produces one ENTER;
- remaining INSIDE produces no event;
- INSIDE to OUTSIDE produces one EXIT;
- confirmation frames and geometric hysteresis suppress boundary jitter;
- missing tracks retain state during the grace window and expire at the exact
  configured frame;
- reappearance resets expiry and missing frames clear pending transitions;
- reset removes stable, pending, and expiry state;
- observations without IDs never invent state.

### Domain and catalog validation

`test_events.py` will cover invalid `CartEvent`, `CheckoutSession`, and product
invariants that protect persisted history. `test_catalog.py` will use temporary
JSON files to verify unreadable, malformed, empty, wrong-shaped, nameless, and
invalid-price catalogs. These are deterministic business/infrastructure
boundaries currently under-tested.

### Configuration and metrics

Existing range, type, immutability, environment override, counter, gauge,
rolling-average, and concurrent snapshot tests remain. Expected values stay
literal and clocks remain injected.

## Integration behavior coverage

### SQLite

`test_database.py` will retain and clarify tests for initialization, session
creation, event recording, closing, retrieval, ordering, parameterized values,
catalog synchronization, and idempotent close. Failure tests will verify that
a transaction error leaves no partial event and the same repository remains
usable afterward, using only a temporary database.

### API and application services

In-process FastAPI tests will cover `/health`, `/ready`, cart, events,
sessions, session detail, metrics, and reset. They will retain bounds validation,
safe unknown-session responses, readiness failures, persistence failures, and
safe unexpected-error responses. Application service tests will use real cart,
health, metrics, and temporary SQLite components while mocking only camera,
model, window, or server boundaries.

### Concurrency

Existing lock and snapshot tests remain, using `Barrier`, `Event`, futures, and
bounded joins rather than arbitrary sleep. Assertions will cover concurrent
reads/writes, immutable snapshots, reset racing with an ENTER, SQLite reads
during event writes, persistence disable ordering, and slow rendering outside
cart locks.

## Coverage policy

Keep the Phase 20 combined branch-coverage threshold at 85 percent. Phase 21
will report weak modules and improve deterministic domain/service boundaries,
but will not chase 100 percent or exclude important business modules.

Low coverage in these areas is acceptable when documented:

- actual Ultralytics model construction and inference;
- physical camera and visible OpenCV window behavior;
- live uvicorn thread/process behavior that deterministic adapters cannot
  exercise without creating fragile tests.

High-value new tests will include a mutation check: identify the production
branch each test protects, temporarily introduce that mutation, confirm the
focused test fails for the expected reason, restore the branch, and confirm the
test passes. Production behavior is not changed merely to increase coverage.

## CI changes

Update `.github/workflows/ci.yml` to run:

1. `tests/unit` and `tests/contracts` as the deterministic unit/contract shard;
2. `tests/integration` as the integration shard with appended coverage;
3. the same explicit post-combination 85 percent gate and coverage artifact.

No CI step may run `app.py`, load a checkpoint, invoke live inference, open a
camera/window, use network services, or depend on MPS/GPU.

CI policy tests will validate the new paths without depending on brittle full
workflow snapshots.

## Repeatability and flakiness check

After focused tests and the full suite pass, run the complete suite at least
three independent times from the same working tree. Do not add retry plugins or
rerun failed tests automatically. Any inconsistent result is investigated and
fixed using deterministic synchronization or isolated state.

## Documentation

Update `docs/TESTING.md` with:

- the new directory taxonomy;
- fixture and isolation policy;
- exact unit, integration, full-suite, lint, and coverage commands;
- the three-run flakiness procedure;
- known intentionally untested hardware/Ultralytics paths;
- the final weak deterministic modules identified by coverage.

Update README test references only where paths or commands change.

## Explicit non-goals

- No test of Ultralytics correctness or model accuracy.
- No model download or YOLO inference.
- No physical webcam or visible GUI test.
- No external HTTP/network service.
- No new test retry behavior.
- No production architecture rewrite.
- No pursuit of 100 percent coverage.

## Acceptance criteria

Phase 21 is complete when:

1. Tests are organized into clear unit, integration, and contract boundaries.
2. Every required cart, event, persistence, API, and concurrency scenario has a
   direct deterministic test.
3. Shared fixtures reduce setup without leaking mutable state.
4. SQLite tests use temporary databases and verify rollback/recovery.
5. CI uses the reorganized paths and remains hardware/network independent.
6. Branch coverage remains at or above 85 percent and weak deterministic areas
   are reported rather than hidden.
7. Three consecutive complete-suite runs pass without retries.
8. `docs/TESTING.md` accurately documents the final strategy and commands.
