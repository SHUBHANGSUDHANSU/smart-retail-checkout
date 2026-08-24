# Production Phase 18 Graceful Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize predictable startup and idempotent ordered shutdown for the webcam, FastAPI, checkout session, OpenCV UI, SQLite adapter, and application state.

**Architecture:** `SmartRetailApplication` remains the lifecycle owner and gains one locked `shutdown()` operation. Adapters keep concrete cleanup behavior: camera release, retryable API stop, and repository close. `run()` preserves the original reason/exit code and delegates cleanup exactly once from `finally`.

**Tech Stack:** Python 3.11, standard `threading` and `logging`, OpenCV, FastAPI/Uvicorn, SQLite, and `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-18-lifecycle-design.md`

## Global Constraints

- Do not implement the Phase 17 metrics design.
- Do not change YOLO, ByteTrack, checkout-zone, cart, API-business, or SQLite-schema behavior.
- Do not add dependencies or use `os._exit`.
- Cleanup continues after one step fails and never replaces the original runtime error.
- Tests use injected adapters and do not require webcam hardware or a live port.
- Use strict red-green-refactor for every behavior.
- This repository has no Git `HEAD` and all application files are untracked. Do not create partial initial commits; use passing verification checkpoints.

---

### Task 1: Idempotent SQLite repository close

**Files:**
- Modify: `src/smart_retail/infrastructure/sqlite_repository.py`
- Modify: `tests/test_persistence.py`

**Interfaces:**
- Consumes: existing `SQLiteCheckoutRepository.initialize()` and `_require_initialized()`.
- Produces: `SQLiteCheckoutRepository.close() -> None`; repeated calls are no-ops and later operations raise `PersistenceError`.

- [ ] **Step 1: Write the failing repository lifecycle test**

```python
def test_close_is_idempotent_and_rejects_later_operations(self) -> None:
    with self.assertLogs(
        "smart_retail.infrastructure.sqlite_repository", level="INFO"
    ) as captured:
        self.repository.close()
        self.repository.close()

    self.assertFalse(self.repository.is_ready())
    with self.assertRaisesRegex(PersistenceError, "not been initialized"):
        self.repository.get_recent_sessions(limit=1)
    closed_logs = [line for line in captured.output if "database_closed" in line]
    self.assertEqual(len(closed_logs), 1)
```

This catches a missing closed-state transition or duplicate successful-close logs.

- [ ] **Step 2: Run the focused test and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_persistence.py' -v
```

Expected: FAIL because `SQLiteCheckoutRepository.close` does not exist.

- [ ] **Step 3: Implement minimal repository close**

Add `self._lifecycle_lock = threading.Lock()` in the constructor and:

```python
def close(self) -> None:
    """Mark this per-operation SQLite adapter closed exactly once."""
    with self._lifecycle_lock:
        if not self._initialized:
            return
        self._initialized = False
    log_event(
        LOGGER,
        logging.INFO,
        "database_closed",
        "SQLite checkout history closed",
        database=self.database_path.name,
    )
```

Do not add a persistent connection; existing operations already scope and close their own connections.

- [ ] **Step 4: Run the persistence suite and verify GREEN**

Run the Step 2 command. Expected: every persistence test passes.

- [ ] **Step 5: Record a verification checkpoint**

Record the passing count. Do not create a partial initial commit.

---

### Task 2: Retry-safe background API shutdown

**Files:**
- Modify: `src/smart_retail/api/server.py`
- Create: `tests/test_api_server.py`

**Interfaces:**
- Consumes: existing `BackgroundAPIServer.stop() -> None`.
- Produces: the same signature, retaining ownership of a live timed-out thread so a later stop can retry.

- [ ] **Step 1: Write failing API-server stop tests**

```python
class FakeThread:
    def __init__(self, alive_results: list[bool]) -> None:
        self._alive_results = iter(alive_results)
        self.join_calls = 0

    def join(self, timeout: float) -> None:
        self.join_calls += 1

    def is_alive(self) -> bool:
        return next(self._alive_results)


def test_stop_retains_timed_out_thread_for_retry(self) -> None:
    server = BackgroundAPIServer(FastAPI(), "127.0.0.1", 8000)
    thread = FakeThread([True, False])
    server._thread = thread

    server.stop()
    server.stop()

    self.assertEqual(thread.join_calls, 2)
    self.assertIsNone(server._thread)


def test_stop_without_started_thread_is_idempotent(self) -> None:
    server = BackgroundAPIServer(FastAPI(), "127.0.0.1", 8000)
    server.stop()
    server.stop()
    self.assertIsNone(server._thread)
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_api_server.py' -v
```

Expected: the retry test fails because the first stop clears `_thread` while it is still alive.

- [ ] **Step 3: Retain the live thread after timeout**

Implement this branch behavior:

```python
if thread.is_alive():
    log_event(
        LOGGER,
        logging.WARNING,
        "api_server_stop_timed_out",
        "FastAPI server did not stop within the timeout",
        host=self.host,
        port=self.port,
    )
    return
log_event(
    LOGGER,
    logging.INFO,
    "api_server_stopped",
    "FastAPI server stopped",
    host=self.host,
    port=self.port,
)
self._thread = None
```

- [ ] **Step 4: Run focused and existing API tests**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_api_server.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_api.py' -v
```

Expected: both suites pass without binding a network port.

- [ ] **Step 5: Record a verification checkpoint**

Record the focused counts. Do not create a partial initial commit.

---

### Task 3: Centralized application shutdown contract

**Files:**
- Modify: `src/smart_retail/app.py`
- Create: `tests/test_lifecycle.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `BackgroundAPIServer.stop()`, `SQLiteCheckoutRepository.close()`, `OpenCVCamera.release()`, `OpenCVUI.close()`, and `HealthService`.
- Produces: `SmartRetailApplication.shutdown(reason: str, frames_processed: int = 0) -> bool`.
- Produces: `SmartRetailApplication.run() -> int` with cleanup-aware exit codes.

- [ ] **Step 1: Create the ordered lifecycle fixture**

Create `tests/test_lifecycle.py`. Use a real `CartService` and `HealthService`; fake only external resources. Each fake cleanup appends a literal step name:

```python
def quiet_logger() -> logging.Logger:
    logger = logging.Logger("test.lifecycle")
    logger.propagate = False
    logger.addHandler(logging.NullHandler())
    return logger


def initialized_health(database_enabled: bool) -> HealthService:
    health = HealthService(database_enabled=database_enabled)
    health.mark_ready(HealthComponent.CORE_SERVICES)
    health.mark_ready(HealthComponent.MODEL)
    if database_enabled:
        health.mark_ready(HealthComponent.DATABASE)
    return health


def make_application(order: list[str]) -> SmartRetailApplication:
    config = load_config({"SMART_RETAIL_API_ENABLED": "false"})
    products = load_product_catalog(config.products_config_path)
    repository = MagicMock()
    repository.create_session.return_value = CheckoutSession(7, 100.0, None, None)
    repository.close_session.side_effect = lambda *args, **kwargs: order.append(
        "session"
    )
    repository.close.side_effect = lambda: order.append("database")
    camera = MagicMock()
    camera.read.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    camera.release.side_effect = lambda: order.append("camera")
    ui = MagicMock()
    ui.poll_key.return_value = ord("q")
    ui.close.side_effect = lambda: order.append("ui")
    api_server = MagicMock()
    api_server.stop.side_effect = lambda: order.append("api")
    return SmartRetailApplication(
        config=config,
        logger=quiet_logger(),
        camera=camera,
        vision=MagicMock(
            device="cpu",
            process=MagicMock(return_value=VisionResult((), 5.0)),
        ),
        event_engine=MagicMock(
            process_frame=MagicMock(return_value=CheckoutUpdate((), ())),
        ),
        cart=CartService(products),
        ui=ui,
        health=initialized_health(config.database.enabled),
        persistence=repository,
        persistence_session_id=7,
        api_server=api_server,
    )
```

- [ ] **Step 2: Write the failing shutdown ordering test**

```python
def test_shutdown_is_ordered_and_idempotent(self) -> None:
    order: list[str] = []
    application = make_application(order)

    first = application.shutdown("user_quit", frames_processed=12)
    second = application.shutdown("repeated", frames_processed=99)

    self.assertTrue(first)
    self.assertTrue(second)
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])
    self.assertEqual(
        application.get_readiness_snapshot().application_state,
        ApplicationState.STOPPED,
    )
```

This catches wrong ordering, duplicate cleanup, and missing terminal state.

- [ ] **Step 3: Write the failing cleanup-isolation test**

```python
def test_cleanup_failure_does_not_skip_later_resources(self) -> None:
    order: list[str] = []
    application = make_application(order)

    def fail_camera_release() -> None:
        order.append("camera")
        raise RuntimeError("release failed")

    application.camera.release.side_effect = fail_camera_release

    self.assertFalse(application.shutdown("unexpected_error"))
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])
```

- [ ] **Step 4: Run lifecycle tests and verify RED**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_lifecycle.py' -v
```

Expected: ERROR because `SmartRetailApplication.shutdown()` does not exist.

- [ ] **Step 5: Add lifecycle state and ordered shutdown**

Add these dataclass fields:

```python
_lifecycle_lock: AbstractContextManager[None] = field(
    default_factory=threading.Lock,
    init=False,
    repr=False,
)
_shutdown_complete: bool = field(default=False, init=False, repr=False)
_shutdown_success: bool = field(default=True, init=False, repr=False)
```

Implement `shutdown()` with one lifecycle lock. Return the stored result after `_shutdown_complete`. Otherwise:

1. set `ApplicationState.STOPPING`;
2. emit `application_stopping`;
3. run the exact steps `api_server`, `checkout_session`, `camera`, `opencv_ui`, `database`;
4. catch each `Exception`, append the step name, log its traceback, and continue;
5. set `ApplicationState.STOPPED`;
6. store success/completion and emit `application_stopped` with `cleanup_success` and failed steps.

The cleanup sequence literal is:

```python
cleanup_steps = (
    ("api_server", self._stop_api_server),
    ("checkout_session", self._close_persistence_session),
    ("camera", self.camera.release),
    ("opencv_ui", self.ui.close),
    ("database", self._close_database),
)
```

- [ ] **Step 6: Make session and database cleanup composable**

Refactor `_close_persistence_session()` to copy repository/session under `_state_lock`, call `close_session()` outside locks using one `CartSnapshot.total`, clear the session ID in `finally`, emit `session_closed` only on success, and re-raise `PersistenceError` after marking database unavailable.

Add:

```python
def _close_database(self) -> None:
    with self._state_lock:
        repository = self.persistence
    if repository is None:
        return
    repository.close()
    with self._state_lock:
        if self.persistence is repository:
            self.persistence = None
    self.health.mark_unavailable(HealthComponent.DATABASE)
```

- [ ] **Step 7: Run lifecycle tests and verify GREEN**

Run the Step 4 command. Expected: all lifecycle tests pass.

- [ ] **Step 8: Write failing run-path tests one at a time**

Add these tests, running the lifecycle suite after each addition to observe the expected failure:

```python
def test_keyboard_interrupt_performs_clean_shutdown(self) -> None:
    order: list[str] = []
    application = make_application(order)
    application.camera.read.side_effect = KeyboardInterrupt

    self.assertEqual(application.run(), 0)
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

def test_camera_initialization_failure_closes_started_session(self) -> None:
    order: list[str] = []
    application = make_application(order)
    application.camera.open.side_effect = CameraError("camera unavailable")

    self.assertEqual(application.run(), 1)
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

def test_unexpected_vision_failure_keeps_exit_one_when_cleanup_also_fails(self) -> None:
    order: list[str] = []
    application = make_application(order)
    application.vision.process.side_effect = RuntimeError("vision failed")

    def fail_camera_release() -> None:
        order.append("camera")
        raise RuntimeError("release failed")

    application.camera.release.side_effect = fail_camera_release

    self.assertEqual(application.run(), 1)
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])

def test_normal_exit_returns_one_when_cleanup_is_incomplete(self) -> None:
    order: list[str] = []
    application = make_application(order)

    def fail_ui_close() -> None:
        order.append("ui")
        raise RuntimeError("window close failed")

    application.ui.close.side_effect = fail_ui_close

    self.assertEqual(application.run(), 1)
    self.assertEqual(order, ["api", "session", "camera", "ui", "database"])
```

Each test catches a distinct wrong branch or wrong exit-code transition.

- [ ] **Step 9: Rewrite `run()` around one final shutdown call**

Use local `exit_code`, `shutdown_reason`, and `frame_number`. Replace early returns with loop exits or assigned codes. Preserve the dedicated vision failure log. The outer control flow becomes:

```python
exit_code = 0
shutdown_reason = "normal"
self._log_starting()
debug_enabled = self.config.ui.debug_display
previous_frame_time = time.perf_counter()
try:
    self._start_api_server()
    self._start_persistence_session()
    self.camera.open()
    self.health.mark_ready(HealthComponent.CAMERA)
    self.health.set_application_state(ApplicationState.RUNNING)
    self._log_started()
    while True:
        frame = self.camera.read()
        try:
            vision_result = self.vision.process(frame)
        except Exception as error:
            self.health.mark_unavailable(HealthComponent.VISION_PIPELINE)
            log_event(
                self.logger,
                logging.ERROR,
                "vision_pipeline_failed",
                "YOLO/ByteTrack processing failed",
                exc_info=True,
                error_type=type(error).__name__,
            )
            exit_code = 1
            shutdown_reason = "vision_pipeline_error"
            break
        frame_height, frame_width = frame.shape[:2]
        checkout_frame = self.process_checkout_frame(
            vision_result.tracked_objects,
            frame_width,
            frame_height,
            frame_number,
        )
        frame_number += 1
        current_frame_time = time.perf_counter()
        elapsed = current_frame_time - previous_frame_time
        fps = 1.0 / elapsed if elapsed > 0 else 0.0
        previous_frame_time = current_frame_time
        self.ui.render(
            frame,
            vision_result.tracked_objects,
            checkout_frame.checkout,
            checkout_frame.cart,
            fps,
            self.vision.device,
            vision_result.inference_time_ms,
            debug_enabled,
        )
        self.ui.present(frame)
        if self.ui.poll_key() in (ord("q"), ord("Q")):
            shutdown_reason = "user_quit"
            break
except CameraError as error:
    exit_code = 1
    shutdown_reason = "camera_error"
    self.health.mark_unavailable(HealthComponent.CAMERA)
    log_event(self.logger, logging.ERROR, "camera_error", str(error))
except KeyboardInterrupt:
    shutdown_reason = "keyboard_interrupt"
    log_event(
        self.logger,
        logging.INFO,
        "shutdown_requested",
        "Keyboard interrupt received",
        source="keyboard_interrupt",
    )
except Exception as error:
    exit_code = 1
    shutdown_reason = "unexpected_error"
    log_event(
        self.logger,
        logging.CRITICAL,
        "application_runtime_failed",
        "Unexpected application failure",
        exc_info=True,
        error_type=type(error).__name__,
    )
finally:
    cleanup_success = self.shutdown(shutdown_reason, frame_number)
return 1 if exit_code == 0 and not cleanup_success else exit_code
```

Rename the current startup logger to `_log_starting()`. Add `_log_started()` after successful camera initialization so `application_started` means the runtime is actually usable.

- [ ] **Step 10: Make each run-path test GREEN**

After each minimal adjustment, run:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_lifecycle.py' -v
```

Expected: all Q, Ctrl+C, initialization failure, unexpected failure, and cleanup-failure cases pass.

- [ ] **Step 11: Update existing tests without weakening assertions**

Strengthen existing application and persistence tests to assert:

- session close precedes camera release;
- repository `close()` occurs once;
- final state is `stopped` after success or failure;
- successful session finalization emits `session_closed`;
- `application_started`, `application_stopping`, and `application_stopped` appear in order.

- [ ] **Step 12: Run all lifecycle-adjacent suites**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_lifecycle.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_app.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_persistence.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_concurrency.py' -v
```

Expected: all focused suites pass with no leaked thread or cleanup warning.

- [ ] **Step 13: Record a verification checkpoint**

Record all focused counts. Do not create a partial initial commit.

---

### Task 4: Composition-failure cleanup

**Files:**
- Modify: `src/smart_retail/app.py`
- Modify: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `SQLiteCheckoutRepository.close()` from Task 1.
- Produces: `build_application()` closes initialized persistence when later composition fails and re-raises the original exception.

- [ ] **Step 1: Write the failing composition test**

```python
@patch("smart_retail.app.SQLiteCheckoutRepository")
@patch("smart_retail.app.YOLODetector", side_effect=RuntimeError("model failed"))
def test_build_failure_closes_database_without_hiding_model_error(
    self,
    detector_factory,
    repository_factory,
) -> None:
    repository = repository_factory.return_value
    config = load_config({"SMART_RETAIL_API_ENABLED": "false"})

    with self.assertRaisesRegex(RuntimeError, "model failed"):
        build_application(config, quiet_logger())

    repository.initialize.assert_called_once()
    repository.close.assert_called_once_with()
```

- [ ] **Step 2: Run and verify RED**

Run the lifecycle suite. Expected: `repository.close()` was not called.

- [ ] **Step 3: Add the composition exception boundary**

After persistence initialization, wrap all later composition in `try/except`. On failure, call `persistence.close()` when it exists. Catch and log close failure with traceback, then use bare `raise` to preserve the original exception and traceback.

- [ ] **Step 4: Add the cleanup-error regression**

Set `repository.close.side_effect = RuntimeError("close failed")`, keep the detector failure, and assert the raised exception still matches `model failed`. Capture logs and verify the close error is reported.

- [ ] **Step 5: Run lifecycle and application tests**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_lifecycle.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_app.py' -v
```

Expected: both suites pass.

- [ ] **Step 6: Record a verification checkpoint**

Record passing results. Do not create a partial initial commit.

---

### Task 5: Lifecycle documentation and final verification

**Files:**
- Create: `docs/LIFECYCLE.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CONCURRENCY.md`
- Modify: `docs/PRODUCTION_ARCHITECTURE.md`

**Interfaces:**
- Consumes: the lifecycle contract from Tasks 1-4.
- Produces: accurate human-facing startup, shutdown, idempotency, and error-preservation documentation.

- [ ] **Step 1: Create `docs/LIFECYCLE.md`**

Document composition/runtime startup, ordered shutdown, Q/Ctrl+C/failure behavior, resource-specific idempotency, exit-code rules, original-error preservation, and why graceful shutdown prevents locked cameras, orphan API threads, and open sessions without final totals.

- [ ] **Step 2: Update repository documentation**

Add `LIFECYCLE.md` to the README tree and architecture references. State that session close occurs before camera, UI, and database close. Do not describe Phase 17 metrics as implemented.

- [ ] **Step 3: Search for stale lifecycle claims**

```bash
rg -n "application_shutdown|checkout_session_closed|camera.*session|session.*camera|LIFECYCLE" README.md docs src tests
```

Review every match and replace stale event names or ordering descriptions.

- [ ] **Step 4: Run complete verification**

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app.py src tests training
.venv/bin/python -m pip check
```

Expected: zero failures, successful compilation, and `No broken requirements found.`

- [ ] **Step 5: Run a hardware-free lifecycle smoke test**

Compose `SmartRetailApplication` with injected camera/UI/API/repository fakes, call `shutdown()` twice, and assert the literal sequence `api, session, camera, ui, database` appears once.

- [ ] **Step 6: Request final code review**

Review against the Phase 18 spec, emphasizing exceptions between every cleanup step, repeated/concurrent shutdown, API timeout ownership, session-before-database order, original-error preservation, and no computer-vision behavior changes.

- [ ] **Step 7: Fix findings test-first and repeat verification**

For each behavior finding, add a failing regression test, implement the minimal fix, then rerun the complete Step 4 command before reporting completion.
