# Application lifecycle

The desktop process owns the webcam loop, the background FastAPI server, the
active checkout session, OpenCV windows, and the SQLite repository. One
`SmartRetailApplication` coordinator initializes and releases those resources
so normal exits and failures follow the same contract.

## Startup sequence

1. Load and validate immutable configuration.
2. Configure console and optional rotating-file logging.
3. Load the product catalog and initialize SQLite when enabled.
4. Load YOLO, configure ByteTrack, and compose checkout, cart, UI, health, and
   API services.
5. Start the background API server.
6. Create the active checkout-history session.
7. Open the camera and mark the application running.
8. Emit `application_started` and begin processing frames.

If composition fails after SQLite initialization, the repository is closed
before the original exception is re-raised. If camera initialization fails,
the already-started API and session still enter the normal shutdown sequence.

## Shutdown sequence

Normal `Q`, `Ctrl+C`, camera failure, vision failure, and unexpected exceptions
all call the same idempotent `shutdown()` method:

1. Signal the realtime loop to stop after its current frame and wait for that
   frame owner when shutdown was requested from another thread.
2. Mark the application stopping so new API reset work is rejected.
3. Stop FastAPI from accepting/processing additional requests.
4. Finalize the active checkout session with one consistent cart total.
5. Release the webcam.
6. Destroy OpenCV windows.
7. Close repository ownership.
8. Mark the application stopped and emit the final lifecycle event.

Every cleanup step is isolated. A failure is logged with its traceback and the
remaining resources are still released. A runtime error keeps exit status `1`;
a normally successful run also returns `1` if cleanup was incomplete, making
the operational failure visible without hiding its original cause.

## Idempotency

After a successful application shutdown, repeated calls return the stored result
without finalizing a session or releasing a resource twice. If an individual
step fails, the application remains `stopping`; a later call retries only the
failed step and skips every completed cleanup operation. Camera release, OpenCV
window cleanup, and repository close are independently safe to repeat. The API
adapter raises on a stop timeout and retains the live thread, so the coordinator
reports incomplete cleanup without closing any downstream service under an
active server. A failed session finalization retains its session ID and
repository; camera/window cleanup may continue, but database close waits until
the session retry succeeds.

## Lifecycle logs

- `application_starting`: composition succeeded and runtime startup began.
- `application_started`: camera is initialized and frame processing can run.
- `application_stopping`: ordered cleanup started, including its reason.
- `session_closed`: the active checkout session was finalized.
- `camera_released`: OpenCV released the capture handle.
- `database_closed`: repository ownership was closed.
- `application_stopped`: cleanup finished, with success and failed-step fields.

Graceful shutdown matters because a webcam is an exclusive OS resource, OpenCV
owns native windows, Uvicorn runs in another thread, and checkout history needs
a final total. Predictable ownership prevents a later run from inheriting a
busy camera, an orphan API thread, or an incomplete session without explanation.
