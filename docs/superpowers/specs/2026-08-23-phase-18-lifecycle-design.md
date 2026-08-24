# Production Phase 18: Graceful Lifecycle Design

## Goal

Make startup and shutdown deterministic across normal Q-key exit, Ctrl+C,
camera failure, FastAPI shutdown, initialization failure, and unexpected
runtime exceptions. Cleanup must be ordered, best-effort, idempotent, and must
never hide the failure that triggered shutdown.

## Scope

This phase changes lifecycle orchestration and adapter cleanup only. It does not
change YOLO inference, ByteTrack association, checkout-zone rules, cart rules,
REST business behavior, or the SQLite history schema. The unimplemented Phase
17 metrics design is not part of this work.

## Current issues

The coordinator already uses `try/finally`, but cleanup is embedded directly in
`run()` and currently stops API, camera, and UI before closing the checkout
session. Cleanup behavior cannot be invoked or tested independently, there is
no application-level repeated-cleanup guard, and the database adapter has no
explicit lifecycle close operation. A cleanup exception can also prevent later
steps because not every operation is isolated.

`BackgroundAPIServer.stop()` is mostly idempotent, but it discards its thread
reference after a timeout. That prevents a later cleanup attempt from checking
or joining the still-running thread.

## Chosen architecture

`SmartRetailApplication` remains the lifecycle owner because it is already the
composition coordinator and knows the required resource order. A separate
lifecycle framework or dependency-injection container would add indirection
without improving this local application.

Add a public `shutdown(reason, frames_processed=0) -> bool` operation. It is
protected by a dedicated non-reentrant lifecycle lock and a completion flag.
The first caller performs the ordered shutdown. Later callers return the stored
result without calling adapters again or emitting duplicate lifecycle logs.

`run()` owns only control flow and delegates cleanup to `shutdown()` from one
`finally` block.

## Startup sequence

Application composition remains in `build_application()`:

1. Load and validate configuration before component construction.
2. Configure logging.
3. Load the product catalog and initialize health state.
4. Initialize SQLite when enabled.
5. Load YOLO, create ByteTrack, event engine, cart, UI, camera adapter, and API
   server adapter.
6. If composition fails after SQLite initialization, close the initialized
   repository before re-raising the original error.

Runtime startup in `run()` is:

1. Log `application_starting` with the safe configuration summary.
2. Start FastAPI when enabled.
3. Create the active checkout session when persistence is available.
4. Open the camera.
5. Mark camera and application state ready/running.
6. Log `application_started` only after runtime startup succeeds.
7. Enter the realtime frame loop.

An API startup failure remains recoverable and the webcam application continues,
matching existing behavior. A session-creation failure disables persistence and
continues in-memory. A camera failure is fatal for the realtime application and
enters the same centralized shutdown path.

## Shutdown sequence

The first `shutdown()` call performs these steps:

1. Set application state to `STOPPING`, making new API reset commands fail.
2. Log `application_stopping` with the reason and processed-frame count.
3. Stop FastAPI so it stops accepting work and lets in-flight requests finish.
4. Close the active checkout session with one consistent final cart total. Cart
   events are already persisted synchronously when each mutation occurs; session
   close persists the required final state.
5. Release the webcam.
6. Destroy OpenCV windows.
7. Close the SQLite repository adapter.
8. Mark the application `STOPPED` and log `application_stopped`.

This ordering intentionally is not the reverse of startup. The API stops before
shared business resources close, and the session finalizes before camera/UI and
database shutdown.

## Exit and exception behavior

`run()` returns:

- `0` for Q-key exit or `KeyboardInterrupt` when cleanup completes;
- `1` for camera failure or unexpected runtime failure;
- `1` for an otherwise normal exit when one or more cleanup operations fail.

Unexpected exceptions are logged with their traceback before cleanup begins.
Shutdown catches and logs each cleanup exception, continues with later steps,
and never raises a cleanup exception over the original runtime failure. If the
runtime already failed, its reason and exit code remain authoritative.

The process never uses `os._exit` or another abrupt termination mechanism.

## Cleanup result and logging

`shutdown()` returns `True` only when every applicable cleanup step completes.
It retains this result for repeated callers.

Required successful lifecycle events are:

- `application_started`
- `application_stopping`
- `camera_released` when a capture existed
- `session_closed` when an active session finalized
- `database_closed` when an initialized repository closed
- `application_stopped`

Adapter-specific failures retain their existing ERROR logs with tracebacks.
Successful cleanup events are emitted once, not once per repeated call.

## Adapter idempotency

### Camera

`OpenCVCamera.release()` already clears its capture reference after release.
Repeated calls remain no-ops and do not emit duplicate `camera_released` logs.

### FastAPI server

`BackgroundAPIServer.stop()` remains a no-op when no thread exists. When a join
times out, it retains the live thread reference so a later call can retry. It
clears the reference only after the thread has stopped.

### Checkout session

The coordinator clears `persistence_session_id` only as part of the single
application shutdown attempt. Session finalization is not invoked again by a
repeated `shutdown()` call.

### SQLite repository

Add `SQLiteCheckoutRepository.close()`. Because every SQL operation already
uses a short-lived context-managed connection, close does not need to terminate
a shared connection. It atomically marks the adapter unavailable, emits
`database_closed` once, and makes later repository operations fail with the
existing `PersistenceError`.

### OpenCV UI

Application-level shutdown idempotency ensures `OpenCVUI.close()` is called
once. The adapter continues to use `cv2.destroyAllWindows()`.

## Build failure protection

If a later composition step such as YOLO construction fails after SQLite was
initialized, `build_application()` attempts repository close in a local
`finally`/exception boundary and re-raises the original construction exception.
A repository-close error is logged but does not replace that original error.

Resources created only inside `SmartRetailApplication.run()` are handled by the
central shutdown path.

## Thread safety

The lifecycle lock serializes concurrent or repeated `shutdown()` callers. It
is separate from the checkout-command, health, cart, notification, and
persistence-state locks.

Shutdown does not acquire the checkout-command lock. FastAPI is stopped first,
so API commands finish before session finalization. The lifecycle lock may span
slow cleanup because no frame or API operation needs it. Existing state-to-health
lock ordering remains unchanged.

## Testing

All tests use injected fakes or mocks and require no physical webcam:

- normal Q-key shutdown verifies the exact resource order and exit code;
- `KeyboardInterrupt` returns zero and performs the same cleanup;
- repeated `shutdown()` invokes every adapter at most once;
- camera initialization failure closes an already-created session and all
  applicable resources;
- unexpected vision/UI failure retains exit code one and still cleans resources;
- a failing cleanup step does not prevent later cleanup or replace the original
  failure;
- session finalization occurs before repository close;
- repository close is idempotent and rejects later operations;
- API stop is idempotent and retains a still-alive timed-out thread;
- a build failure after database initialization attempts database close.

The complete existing suite must continue to pass without weakening prior
assertions.

## Files

Create:

- `docs/LIFECYCLE.md`
- lifecycle-focused tests only where existing test files are not cohesive

Modify:

- `src/smart_retail/app.py`
- `src/smart_retail/api/server.py`
- `src/smart_retail/infrastructure/sqlite_repository.py`
- `tests/test_app.py`
- `tests/test_api.py` or a focused API-server test file if needed
- `tests/test_persistence.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/CONCURRENCY.md`
- `docs/PRODUCTION_ARCHITECTURE.md`

No new runtime dependency is required.
