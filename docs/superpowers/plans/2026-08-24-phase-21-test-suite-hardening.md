# Production Phase 21 Test-Suite Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize and strengthen deterministic unit, integration, and contract tests while preserving the working application and excluding live YOLO, webcam, GUI, network, and accelerator behavior.

**Architecture:** Move existing tests into responsibility-based directories, then add small pytest fixtures and focused tests at domain and subsystem boundaries. Keep the 85 percent combined branch-coverage gate, use temporary SQLite databases and in-process FastAPI clients, and update CI to execute the new directory boundaries.

**Tech Stack:** Python 3.11, pytest 9.1.1, pytest-cov 7.1.0, FastAPI TestClient/httpx2, SQLite, Ruff 0.16.4

**Spec:** `docs/superpowers/specs/2026-08-24-phase-21-test-suite-hardening-design.md`

## Global Constraints

- Do not test Ultralytics YOLO itself or download/load model weights.
- No network calls, physical webcam, visible GUI, MPS, CUDA, GPU, or cloud service.
- Every test must be independent of execution order and mutable cross-test state.
- SQLite tests use pytest temporary directories only.
- Concurrency tests use `Barrier`, `Event`, futures, and bounded joins; no arbitrary sleep or retry plugin.
- Mock camera, model, OpenCV window, uvicorn, or failure-injection boundaries only; keep business logic real.
- Keep combined branch coverage at or above 85 percent without excluding important business modules.
- Do not rewrite working production code unless a focused failing regression test proves a real defect.
- The repository currently has no valid `HEAD`; retain changes in the working tree instead of attempting commits until Git is initialized.

---

### Task 1: Establish the test directory boundaries and CI contract

**Files:**
- Create: `tests/unit/`
- Create: `tests/integration/`
- Create: `tests/contracts/`
- Move: `tests/test_cart.py` -> `tests/unit/test_cart.py`
- Move: `tests/test_zone.py` -> `tests/unit/test_events.py`
- Move: `tests/test_config.py` -> `tests/unit/test_config.py`
- Move: `tests/test_metrics.py` -> `tests/unit/test_metrics.py`
- Move: `tests/test_health.py` -> `tests/unit/test_health.py`
- Move: `tests/test_logging.py` -> `tests/unit/test_logging.py`
- Move: `tests/test_api_server.py` -> `tests/unit/test_api_server.py`
- Move: `tests/test_detector.py` -> `tests/unit/test_vision.py`
- Move: `tests/test_ui.py` -> `tests/unit/test_ui.py`
- Move: `tests/test_persistence.py` -> `tests/integration/test_database.py`
- Move: `tests/test_api.py` -> `tests/integration/test_api.py`
- Move: `tests/test_api_service.py` -> `tests/integration/test_application_services.py`
- Move: `tests/test_app.py` -> `tests/integration/test_application.py`
- Move: `tests/test_concurrency.py` -> `tests/integration/test_concurrency.py`
- Move: `tests/test_lifecycle.py` -> `tests/integration/test_lifecycle.py`
- Move: `tests/test_ci_configuration.py` -> `tests/contracts/test_ci_configuration.py`
- Move: `tests/test_containerization.py` -> `tests/contracts/test_containerization.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/contracts/test_ci_configuration.py`

**Interfaces:**
- Consumes: pytest recursive discovery under `tests/` and Phase 20 combined coverage.
- Produces: `tests/unit`, `tests/integration`, and `tests/contracts` as stable CI execution boundaries.

- [ ] **Step 1: Move the existing tests without changing their assertions**

Create the three directories, then perform each exact move listed above. Do not
create `__init__.py`; pytest can collect these unique module names directly.

- [ ] **Step 2: Change the CI policy test before changing the workflow**

In `tests/contracts/test_ci_configuration.py`, replace the old ignored-file
expectations with these durable path expectations:

```python
for required in (
    "python -m pytest tests/unit tests/contracts",
    "python -m pytest tests/integration",
    "--cov-append",
    "--fail-under=85",
):
    self.assertIn(required, workflow)

for obsolete in (
    "--ignore=tests/test_api.py",
    "tests/test_api_service.py",
    "tests/test_persistence.py",
):
    self.assertNotIn(obsolete, workflow)
```

- [ ] **Step 3: Run the focused contract and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest tests/contracts/test_ci_configuration.py -q
```

Expected: FAIL because `.github/workflows/ci.yml` still names the flat Phase 20
paths.

- [ ] **Step 4: Update the workflow to use directory boundaries**

Use these two commands in the existing coverage steps:

```yaml
- name: Run unit and deterministic contract tests
  run: |
    python -m pytest tests/unit tests/contracts -q \
      --cov=smart_retail \
      --cov-branch \
      --cov-fail-under=0 \
      --cov-report=

- name: Run integration tests
  run: |
    python -m pytest tests/integration -q \
      --cov=smart_retail \
      --cov-branch \
      --cov-append \
      --cov-fail-under=0 \
      --cov-report=
```

Keep XML generation, the explicit 85 percent gate, artifact upload, environment
isolation, and action versions unchanged.

- [ ] **Step 5: Verify collection and the updated CI contract**

Run:

```bash
.venv/bin/python -m pytest --collect-only tests -q
.venv/bin/python -m pytest tests/contracts/test_ci_configuration.py -q
```

Expected: 133 tests and 36 subtests remain discoverable before new tests are
added; the CI contract passes.

---

### Task 2: Add reusable deterministic fixtures and harden cart behavior

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/unit/test_cart.py`

**Interfaces:**
- Consumes: `Product`, `CartService`, `CheckoutZone`, `CheckoutEventEngine`, and `TrackedObject`.
- Produces: fixtures `product_catalog`, `cart_service`, `checkout_zone`, `event_engine`, and `make_tracked_object` for later test files.

- [ ] **Step 1: Add shared function-scoped fixtures**

Create `tests/conftest.py` with these interfaces:

```python
from collections.abc import Callable

import pytest

from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.domain.models import Product, TrackedObject


@pytest.fixture
def product_catalog() -> dict[str, Product]:
    return {
        "bottle": Product("bottle", "Water Bottle", 40),
        "apple": Product("apple", "Apple", 45),
    }


@pytest.fixture
def cart_service(product_catalog: dict[str, Product]) -> CartService:
    return CartService(product_catalog)


@pytest.fixture
def checkout_zone() -> CheckoutZone:
    return CheckoutZone(0.70, 0.05, 0.98, 0.95, hysteresis=0.01)


@pytest.fixture
def event_engine(checkout_zone: CheckoutZone) -> CheckoutEventEngine:
    return CheckoutEventEngine(
        checkout_zone,
        confirmation_frames=2,
        expiry_grace_frames=3,
        clock=lambda: 123.5,
    )


@pytest.fixture
def make_tracked_object() -> Callable[..., TrackedObject]:
    def make(
        track_id: int | None,
        center_x: float,
        center_y: float = 250.0,
        class_name: str = "bottle",
    ) -> TrackedObject:
        return TrackedObject(
            track_id=track_id,
            class_name=class_name,
            confidence=0.90,
            bbox=(
                round(center_x - 10),
                round(center_y - 10),
                round(center_x + 10),
                round(center_y + 10),
            ),
        )

    return make
```

- [ ] **Step 2: Convert the cart setup to fixtures and make each required scenario direct**

Retain the existing catalog-price and notification assertions. Express the
required core behavior as separate pytest functions, including:

```python
def test_same_track_is_charged_once(cart_service: CartService) -> None:
    assert cart_service.add_item(7, "bottle") is True
    assert cart_service.add_item(7, "bottle") is False
    assert cart_service.get_snapshot().total_quantity == 1
    assert cart_service.get_snapshot().total == 40


def test_two_tracks_of_same_class_aggregate_quantity(
    cart_service: CartService,
) -> None:
    cart_service.add_item(7, "bottle")
    cart_service.add_item(19, "bottle")
    snapshot = cart_service.get_snapshot()
    assert snapshot.items[0].quantity == 2
    assert snapshot.total == 80


def test_remove_and_reset_are_safe(cart_service: CartService) -> None:
    cart_service.add_item(7, "bottle")
    assert cart_service.remove_item(999) is False
    assert cart_service.remove_item(7) is True
    cart_service.add_item(19, "bottle")
    assert cart_service.clear() == 1
    assert cart_service.get_snapshot().items == ()
    assert cart_service.get_snapshot().total == 0
```

- [ ] **Step 3: Verify the cart tests protect real mutations**

Temporarily change `CartService.remove_item` to return `False` without popping,
run `test_remove_and_reset_are_safe`, and confirm it fails on the retained
track. Restore the original method immediately, then run:

```bash
.venv/bin/python -m pytest tests/unit/test_cart.py -q
```

Expected: all cart tests pass with production code restored.

---

### Task 3: Separate zone geometry, event lifecycle, and domain invariants

**Files:**
- Create: `tests/unit/test_zone.py`
- Modify: `tests/unit/test_events.py`

**Interfaces:**
- Consumes: shared `checkout_zone`, `event_engine`, and `make_tracked_object` fixtures.
- Produces: direct coverage of zone geometry, event transitions, expiry, and persisted-domain invariants.

- [ ] **Step 1: Move pure geometry assertions into `test_zone.py`**

Keep normalized-to-pixel, inside/outside, invalid dimension, coordinate,
hysteresis, and resolution tests in this file. Include literal boundary checks:

```python
def test_hysteresis_uses_different_entry_and_exit_bounds(
    checkout_zone: CheckoutZone,
) -> None:
    assert checkout_zone.classify_for_previous_state(
        (705.0, 250.0), 1000, 500, ZoneState.OUTSIDE
    ) is ZoneState.OUTSIDE
    assert checkout_zone.classify_for_previous_state(
        (695.0, 250.0), 1000, 500, ZoneState.INSIDE
    ) is ZoneState.INSIDE
```

- [ ] **Step 2: Keep event-engine behavior in `test_events.py`**

Use the shared fixtures and preserve the existing independent-track, missing-ID,
reset, snapshot, and missing-frame tests. Make the central flow explicit:

```python
def test_enter_hold_and_exit_emit_one_event_per_transition(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800)

    assert event_engine.process_frame([outside], 1000, 500, 0).events == ()
    assert event_engine.process_frame([inside], 1000, 500, 1).events == ()
    entered = event_engine.process_frame([inside], 1000, 500, 2).events
    assert [event.event_type for event in entered] == [CheckoutEventType.ENTER]
    assert event_engine.process_frame([inside], 1000, 500, 3).events == ()
    assert event_engine.process_frame([outside], 1000, 500, 4).events == ()
    exited = event_engine.process_frame([outside], 1000, 500, 5).events
    assert [event.event_type for event in exited] == [CheckoutEventType.EXIT]
```

- [ ] **Step 3: Add literal invariant cases for persisted domain models**

Use `pytest.mark.parametrize` with explicit invalid values:

```python
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"event_id": 0}, "IDs must be positive"),
        ({"event_type": CartEventType.RESET, "track_id": 7}, "cannot reference"),
        ({"event_type": CartEventType.ADD, "unit_price": None}, "require product"),
        ({"event_type": CartEventType.ADD, "unit_price": -1}, "cannot be negative"),
    ],
)
def test_cart_event_rejects_invalid_history(kwargs, message) -> None:
    values = {
        "event_id": 1,
        "session_id": 1,
        "timestamp": 100.0,
        "track_id": 7,
        "product_id": "bottle",
        "event_type": CartEventType.ADD,
        "unit_price": 40,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        CartEvent(**values)
```

Add equivalent literal cases for empty `Product` identifiers/names, non-integer
or negative prices, nonpositive session IDs, end-before-start, negative total,
and half-closed sessions.

- [ ] **Step 4: Mutation-check and run focused unit tests**

Temporarily reverse the ENTER/EXIT selection in `CheckoutEventEngine`, verify
`test_enter_hold_and_exit_emit_one_event_per_transition` fails on the literal
event types, then restore the code. Run:

```bash
.venv/bin/python -m pytest tests/unit/test_zone.py tests/unit/test_events.py -q
```

Expected: all zone/event/domain tests pass after restoration.

---

### Task 4: Cover the product-catalog input boundary

**Files:**
- Create: `tests/unit/test_catalog.py`

**Interfaces:**
- Consumes: `load_product_catalog(path: str | Path) -> dict[str, Product]`.
- Produces: deterministic coverage of file, JSON-shape, name, and integer-price failures.

- [ ] **Step 1: Add table-driven invalid catalog tests**

Create temporary JSON files using `tmp_path` and literal inputs:

```python
import json

import pytest

from smart_retail.infrastructure.repository import (
    ProductCatalogError,
    load_product_catalog,
)


def test_missing_and_malformed_catalogs_are_rejected(tmp_path) -> None:
    with pytest.raises(ProductCatalogError, match="Could not read"):
        load_product_catalog(tmp_path / "missing.json")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ProductCatalogError, match="not valid JSON"):
        load_product_catalog(malformed)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "at least one product"),
        ([], "at least one product"),
        ({"bottle": []}, "map a class name to an object"),
        ({"bottle": {"name": "", "price": 40}}, "nonempty name"),
        ({"bottle": {"name": "Water", "price": True}}, "nonnegative integer"),
        ({"bottle": {"name": "Water", "price": -1}}, "nonnegative integer"),
    ],
)
def test_invalid_catalog_shapes_are_rejected(tmp_path, payload, message) -> None:
    path = tmp_path / "products.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProductCatalogError, match=message):
        load_product_catalog(path)
```

- [ ] **Step 2: Add a success case with exact values**

Write two literal products and assert returned keys, names, integer prices, and
catalog order. Do not use the loader itself to construct expected values.

- [ ] **Step 3: Run the catalog tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_catalog.py -q
```

Expected: all catalog cases pass without reading repository configuration.

---

### Task 5: Isolate SQLite fixtures and preserve rollback semantics

**Files:**
- Create: `tests/integration/conftest.py`
- Modify: `tests/integration/test_database.py`
- Modify: `tests/integration/test_application_services.py`

**Interfaces:**
- Consumes: root `product_catalog` fixture and `tmp_path`.
- Produces: function-scoped `sqlite_repository` fixture yielding an initialized `SQLiteCheckoutRepository`.

- [ ] **Step 1: Add the temporary SQLite fixture**

Create `tests/integration/conftest.py`:

```python
from collections.abc import Iterator

import pytest

from smart_retail.domain.models import Product
from smart_retail.infrastructure.sqlite_repository import SQLiteCheckoutRepository


@pytest.fixture
def sqlite_repository(
    tmp_path,
    product_catalog: dict[str, Product],
) -> Iterator[SQLiteCheckoutRepository]:
    repository = SQLiteCheckoutRepository(tmp_path / "checkout.db")
    repository.initialize(product_catalog)
    yield repository
    repository.close()
```

- [ ] **Step 2: Separate repository tests from application persistence tests**

Keep only `SQLiteCheckoutRepositoryTests` behavior in `test_database.py` and
move application-level persistence/metrics/session assertions into
`test_application_services.py`. Replace manual temporary-directory setup in
new pytest-style repository tests with `sqlite_repository`.

- [ ] **Step 3: Make rollback and recovery observable**

Use a real foreign-key violation and assert both no partial row and successful
reuse:

```python
def test_failed_event_write_rolls_back_and_repository_recovers(
    sqlite_repository: SQLiteCheckoutRepository,
) -> None:
    session = sqlite_repository.create_session(started_at=100.0)
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        sqlite_repository.record_cart_event(
            session.session_id,
            CartEventType.ADD,
            timestamp=101.0,
            track_id=7,
            product_id="not-a-product",
            unit_price=10,
        )
    assert sqlite_repository.get_session_events(session.session_id) == []

    recorded = sqlite_repository.record_cart_event(
        session.session_id,
        CartEventType.ADD,
        timestamp=102.0,
        track_id=7,
        product_id="bottle",
        unit_price=40,
    )
    assert recorded.track_id == 7
```

The test must exercise the real SQLite transaction and foreign-key constraint,
not a mocked connection.

- [ ] **Step 4: Run database and application-service tests**

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_database.py tests/integration/test_application_services.py -q
```

Expected: all persistence round-trip, rollback, recovery, session, and
application-service tests pass against isolated temporary files.

---

### Task 6: Make API and concurrency scenario coverage explicit

**Files:**
- Modify: `tests/integration/test_api.py`
- Modify: `tests/integration/test_concurrency.py`
- Modify: `tests/integration/test_application.py`
- Modify: `tests/integration/test_lifecycle.py`

**Interfaces:**
- Consumes: in-process FastAPI application state, temporary SQLite repository, real cart/event/health/metrics services, and mocked hardware/server adapters.
- Produces: direct endpoint and shared-state acceptance tests matching Phase 21.

- [ ] **Step 1: Retain one direct assertion for every required endpoint**

Ensure `test_api.py` directly calls and validates:

```python
endpoint_expectations = (
    ("GET", "/health", 200),
    ("GET", "/ready", 200),
    ("GET", "/api/v1/cart", 200),
    ("GET", "/api/v1/events?limit=10", 200),
    ("GET", "/api/v1/sessions?limit=10", 200),
    ("GET", "/api/v1/metrics", 200),
    ("POST", "/api/v1/cart/reset", 200),
)
```

Assert route-specific payload fields in the existing dedicated tests rather
than asserting status codes alone.

- [ ] **Step 2: Preserve validation and unknown-session behavior**

Keep literal cases for `limit=0`, limits above route maxima, invalid noninteger
limits, and `/api/v1/sessions/999999`. Assert 422 for query validation, 404 for
the missing session, and safe JSON details without internal exception text.

- [ ] **Step 3: Audit concurrency tests for scheduling assumptions**

Keep all state-changing starts behind `Barrier` or `Event`. Retain bounded
future results and joins only as failure deadlines. Verify no `time.sleep` or
retry loop exists with:

```bash
rg -n "time\.sleep|sleep\(|rerun|retry" tests/integration/test_concurrency.py
```

Expected: no arbitrary sleep/retry implementation. Injected camera sleep mocks
in `test_application.py` remain allowed because they do not wait.

- [ ] **Step 4: Run all integration tests**

Run:

```bash
.venv/bin/python -m pytest tests/integration -q
```

Expected: API, application, lifecycle, database, and concurrency tests pass
without camera, GUI, YOLO inference, or external network use.

---

### Task 7: Update test documentation and repository references

**Files:**
- Modify: `docs/TESTING.md`
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/contracts/test_ci_configuration.py`

**Interfaces:**
- Consumes: final test structure and exact local commands.
- Produces: accurate developer instructions and CI policy checks.

- [ ] **Step 1: Update `docs/TESTING.md`**

Document:

```text
tests/unit          pure domain/service and mocked adapter behavior
tests/integration   SQLite, FastAPI, orchestration, lifecycle, concurrency
tests/contracts     CI and container policy artifacts
```

Add exact commands for each directory, the full suite, Ruff, split coverage,
and three independent full-suite runs. Explain function-scoped fixture
isolation and list the intentionally untested Ultralytics, webcam, GUI, MPS/GPU,
and live uvicorn paths. Include the final per-module weak deterministic areas
from the coverage output.

- [ ] **Step 2: Update README test references**

Keep `python -m pytest tests -q` as the primary command and link to the revised
testing guide. Update only project-structure entries and CI wording affected by
the new directory names.

- [ ] **Step 3: Run the contract tests**

Run:

```bash
.venv/bin/python -m pytest tests/contracts -q
```

Expected: workflow, coverage, documentation, Docker, and ignore-policy
contracts pass.

---

### Task 8: Verify coverage and repeatability without retries

**Files:**
- Generated and ignored: `.coverage`
- Generated and ignored: `coverage.xml`

**Interfaces:**
- Consumes: completed test suite and Phase 20 coverage configuration.
- Produces: final lint, test-count, coverage, and flakiness evidence.

- [ ] **Step 1: Run Ruff and environment checks**

Run:

```bash
.venv/bin/python -m ruff check app.py src tests training
.venv/bin/python -m ruff format --check app.py src tests training
.venv/bin/python -m pip check
```

Expected: all commands exit zero.

- [ ] **Step 2: Run split branch coverage exactly as CI does**

Run each command separately:

```bash
.venv/bin/python -m coverage erase
.venv/bin/python -m pytest tests/unit tests/contracts -q --cov=smart_retail --cov-branch --cov-fail-under=0 --cov-report=
.venv/bin/python -m pytest tests/integration -q --cov=smart_retail --cov-branch --cov-append --cov-fail-under=0 --cov-report=
.venv/bin/python -m coverage xml -o coverage.xml
.venv/bin/python -m coverage report --show-missing --fail-under=85
```

Expected: all tests pass and combined branch coverage is at least 85 percent.
Record the weakest deterministic modules separately from deliberately untested
model/hardware code.

- [ ] **Step 3: Run the complete suite three independent times**

Run this command three times as separate processes, without retry flags:

```bash
.venv/bin/python -m pytest tests -q
```

Expected: identical test/subtest counts and zero failures on runs one, two, and
three. If any run fails, stop and use systematic debugging; do not rerun until
the race, leak, or order dependency is understood and fixed.

- [ ] **Step 4: Perform scope and hardware-isolation inspection**

Run:

```bash
rg -n "YOLO\(|model\.predict|model\.track|VideoCapture\(|imshow\(" tests
```

Review every match. Only tests that assert mocked adapter call contracts or
source-policy text may contain these names; no call may reach real model,
camera, or GUI behavior.

- [ ] **Step 5: Request independent code review**

Ask a read-only reviewer to compare the final suite with the Phase 21 spec,
verify required scenarios, inspect fixture isolation and concurrency
synchronization, and confirm no Critical or Important findings remain.
