# Production Phase 19 Containerization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a non-root, lightweight headless FastAPI/SQLite container while preserving the native macOS webcam application as the supported vision demo.

**Architecture:** A new `HeadlessAPIRuntime` implements the state interface already consumed by existing FastAPI routes and owns its SQLite session through FastAPI lifespan. A multi-stage Python 3.11 slim image installs only API dependencies, runs focused hardware-free tests in a test target, and starts the service as an unprivileged user in the production target.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic, SQLite, standard logging, unittest, Docker Desktop.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-19-containerization-design.md`

## Global Constraints

- Native `python app.py` webcam/YOLO/ByteTrack behavior must remain unchanged.
- The production container must not install or initialize OpenCV, Ultralytics, PyTorch, NumPy, YOLO, ByteTrack, MPS, or a camera.
- The headless service must reuse `CartService`, `SQLiteCheckoutRepository`, `HealthService`, `MetricsService`, and the existing API routes.
- No Docker Compose, external database, broker, video streaming, authentication, or cloud service.
- No secrets, `.env`, model artifacts, datasets, caches, or local databases in image layers.
- Use red-green-refactor for Python behavior. Docker configuration is verified through focused artifact tests plus real image build/run checks.
- The repository has no Git `HEAD`; use passing verification checkpoints rather than creating partial initial commits.

---

### Task 1: Intentionally disabled health components

**Files:**
- Modify: `src/smart_retail/health.py`
- Modify: `tests/test_health.py`

**Interfaces:**
- Consumes: `HealthService(database_enabled: bool, clock=...)`.
- Produces: `HealthService(..., disabled_components: Iterable[HealthComponent] = ())`.
- Desktop callers that omit the new argument retain current behavior.

- [ ] **Step 1: Write the failing headless-readiness test**

Add a test constructing:

```python
service = HealthService(
    database_enabled=True,
    disabled_components=(
        HealthComponent.MODEL,
        HealthComponent.CAMERA,
        HealthComponent.VISION_PIPELINE,
    ),
)
service.mark_ready(HealthComponent.CORE_SERVICES)
service.mark_ready(HealthComponent.DATABASE)
service.set_application_state(ApplicationState.RUNNING)
snapshot = service.get_readiness()
```

Assert readiness is true and the three vision statuses are `disabled` rather
than `ready` or `unavailable`. Add a validation test proving `CORE_SERVICES` and
`DATABASE` cannot be supplied through `disabled_components`; the existing
`database_enabled` flag remains the sole database-disable switch.

- [ ] **Step 2: Run the health suite and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_health.py' -v
```

Expected: constructor rejects the unknown keyword argument.

- [ ] **Step 3: Implement minimal disabled-component initialization**

Import `Iterable`, validate that the set is a subset of `MODEL`, `CAMERA`, and
`VISION_PIPELINE`, and initialize those statuses to `ComponentStatus.DISABLED`.
Keep `CORE_SERVICES` initializing and retain the current database-enabled logic.

- [ ] **Step 4: Run focused and full health/concurrency tests**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_health.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_concurrency.py' -v
```

Expected: all tests pass with existing desktop readiness semantics unchanged.

---

### Task 2: Headless API runtime and FastAPI lifespan

**Files:**
- Create: `src/smart_retail/api/service.py`
- Create: `tests/test_api_service.py`
- Modify: `src/smart_retail/api/factory.py`

**Interfaces:**
- Produces: `HeadlessAPIRuntime(config, logger, products, repository)`.
- Produces: idempotent `start() -> None` and `stop() -> None`.
- Produces: `create_service_app(config: AppConfig | None = None, logger: logging.Logger | None = None) -> FastAPI`.
- Produces: `main() -> int`, invoked by `python -m smart_retail.api.service`.
- Extends: `create_api_app(runtime, *, lifespan=None) -> FastAPI` without changing existing callers.

- [ ] **Step 1: Write failing service-lifecycle API tests**

Use a temporary SQLite path and `TestClient(create_service_app(config, logger))`
as a context manager. Assert inside lifespan:

- `/health` returns 200;
- `/ready` returns 200 with model, camera, and vision pipeline disabled;
- `/api/v1/cart` is empty and total zero;
- `POST /api/v1/cart/reset` returns 200, persists one RESET, and increments
  `cart_resets_total`;
- `/api/v1/sessions` exposes the active session;
- `/api/v1/metrics` returns the shared metrics snapshot.

After the TestClient context closes, open SQLite directly or use a fresh
repository instance and assert the session has `ended_at` and `final_total=0`.
Add a direct runtime test calling `stop()` twice and proving only one session
close occurs.

- [ ] **Step 2: Run the focused test and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_api_service.py' -v
```

Expected: import failure because `smart_retail.api.service` does not exist.

- [ ] **Step 3: Extend the API factory with optional lifespan**

Add a keyword-only lifespan argument and pass it to `FastAPI(...)`. Existing
desktop `create_api_app(application)` calls must remain valid and unchanged.

- [ ] **Step 4: Implement `HeadlessAPIRuntime`**

The runtime owns a `CartService`, `HealthService`, `MetricsService`, optional
repository/session ID, one state lock, one reset lock, and idempotent lifecycle
flags. Implement the exact route-facing methods already present on
`SmartRetailApplication`:

```python
get_cart_snapshot()
reset_checkout(source: str)
get_liveness_snapshot()
get_readiness_snapshot()
get_metrics_snapshot()
get_recent_cart_events(limit: int)
get_recent_checkout_sessions(limit: int)
get_checkout_session_history(session_id: int)
```

`start()` initializes SQLite, creates a session, marks core/database ready, and
sets `ApplicationState.RUNNING`. `stop()` sets stopping, finalizes the session
with one cart snapshot total, closes repository ownership, and sets stopped.
Persistence failures increment metrics, update readiness, log a traceback, and
raise `PersistenceError`; they never expose a partially mutated container.

`reset_checkout()` must require running state for API calls, use
`CartService.clear()`, return `CartResetResult`, record one metrics reset, and
append a RESET event when persistence is enabled. It must not invent track IDs
or copy add/remove rules.

- [ ] **Step 5: Implement the application factory and module entry point**

`create_service_app()` loads or accepts configuration, configures or accepts a
logger, loads products, creates the repository when enabled, builds the runtime,
and passes an async lifespan context to `create_api_app`. `main()` calls
`uvicorn.run()` with configured host/port, no separate log configuration, and
returns a normal status when Uvicorn exits.

- [ ] **Step 6: Run focused and existing API suites**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_api_service.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_api.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_persistence.py' -v
```

Expected: all tests pass and no webcam/model is initialized.

---

### Task 3: Production image and build-context controls

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `requirements-api.txt`
- Create: `tests/test_containerization.py`

**Interfaces:**
- Produces Docker target `test` with focused headless test command.
- Produces default Docker target `production` running
  `python -m smart_retail.api.service`.
- Exposes TCP port 8000 and stores SQLite data under `/app/data`.

- [ ] **Step 1: Write failing container-artifact tests**

Read repository files as text and assert:

- `Dockerfile` starts from `python:3.11-slim`, contains named `test` and
  `production` stages, `USER smartretail`, `EXPOSE 8000`, `HEALTHCHECK`, and the
  service module command;
- the production dependency file contains FastAPI, Pydantic, and Uvicorn but
  not OpenCV, Ultralytics, torch, or NumPy;
- `.dockerignore` excludes `.git`, `.venv`, `.env`, Python caches, SQLite files,
  `*.pt`, datasets, models, and training runs.

- [ ] **Step 2: Run artifact tests and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_containerization.py' -v
```

Expected: missing Docker artifacts.

- [ ] **Step 3: Add pinned API-only dependencies**

Create `requirements-api.txt` with the existing compatible pins:

```text
fastapi==0.141.1
pydantic==2.13.4
uvicorn==0.52.1
```

The test stage installs `httpx==0.28.1` for FastAPI `TestClient`; it is not
installed in the production target.

- [ ] **Step 4: Create the multi-stage Dockerfile**

Use `python:3.11-slim` as the shared base, set `PYTHONUNBUFFERED=1` and
`PYTHONDONTWRITEBYTECODE=1`, create the `smartretail` user/group, install
API-only dependencies before copying source for layer reuse, copy package
metadata/source/configs, and run `pip install --no-deps .`.

Set container defaults for host `0.0.0.0`, port `8000`, database
`/app/data/smart_retail.db`, `/app/configs/products.json`, and
`/app/configs/bytetrack_retail.yaml`. Create/chown `/app/data` before switching
to `USER smartretail`.

The test target temporarily installs `httpx==0.28.1`, copies
`tests/test_api_service.py`, and runs it through unittest. The production target
contains no tests or test client. Add a standard-library `urllib.request`
health check for `/health`, expose 8000, and use the module entry point as CMD.

- [ ] **Step 5: Create `.dockerignore`**

Exclude every artifact named in the spec while retaining source, configs,
package metadata, README, API requirements, and focused test source used by the
test stage.

- [ ] **Step 6: Run artifact and native regression tests**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_containerization.py' -v
.venv/bin/python -m unittest discover -s tests -q
```

Expected: the artifact suite and complete native suite pass.

---

### Task 4: Documentation and real container verification

**Files:**
- Create: `docs/CONTAINERIZATION.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PRODUCTION_ARCHITECTURE.md`

**Interfaces:**
- Documents native webcam command and headless container command as separate
  supported modes.

- [ ] **Step 1: Document exact commands and limitations**

Document:

```bash
docker build --target test -t smart-retail-checkout:test .
docker run --rm smart-retail-checkout:test
docker build -t smart-retail-checkout:latest .
docker volume create smart-retail-data
docker run --name smart-retail-api -p 8000:8000 \
  -v smart-retail-data:/app/data smart-retail-checkout:latest
```

Include environment override examples, stdout/stderr logs, `/health`, `/ready`,
Swagger, graceful `docker stop`, non-root operation, SQLite volume behavior,
and the explicit macOS limitation that the webcam demo remains native.

- [ ] **Step 2: Start Docker Desktop if required**

Check `docker info`. If the local daemon is unavailable, start Docker Desktop
with `open -a Docker` and poll `docker info` in short intervals while reporting
progress. Do not treat daemon startup delay as a code defect.

- [ ] **Step 3: Build and run the container test target**

```bash
docker build --target test -t smart-retail-checkout:test .
docker run --rm smart-retail-checkout:test
```

Expected: focused headless runtime tests pass inside Linux without webcam,
OpenCV, Ultralytics, or model downloads.

- [ ] **Step 4: Build and inspect the production image**

```bash
docker build -t smart-retail-checkout:latest .
docker image inspect smart-retail-checkout:latest --format '{{.Config.User}}'
```

Expected: build succeeds and configured user is `smartretail`.

- [ ] **Step 5: Verify live API, readiness, healthcheck, and shutdown**

Run the image on an unused host port such as 18080 with a specifically named
verification volume/container. Poll `/health`, then assert `/ready` returns 200
with vision components disabled and `/openapi.json` contains `/api/v1/metrics`.
Inspect Docker health status, stop gracefully, capture logs containing service
startup/session close/database close, and remove only the explicitly named
verification container and volume.

- [ ] **Step 6: Run final verification**

```bash
.venv/bin/python -m compileall -q app.py src tests training
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

Expected: compilation succeeds, the complete test suite passes, and the native
environment reports no broken requirements.

- [ ] **Step 7: Review scope**

Confirm no files under `src/smart_retail/vision/` or checkout algorithms changed,
no Docker Compose or infrastructure service was introduced, the production
image has no desktop vision dependencies, and README commands match the image.
