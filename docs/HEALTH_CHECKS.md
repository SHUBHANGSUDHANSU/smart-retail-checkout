# Health and readiness checks

## Why there are two checks

Liveness and readiness answer different operational questions:

- **Liveness:** Is this application process running and able to answer HTTP?
- **Readiness:** Can this instance currently provide the realtime checkout
  service with all enabled critical dependencies?

A working HTTP server does not prove that the webcam opened, the YOLO model
loaded, a frame completed the vision pipeline, or SQLite initialized. Keeping
these checks separate prevents a dependency problem from being mistaken for a
dead process.

## `GET /health`: liveness

`/health` always returns HTTP `200` while the API process can handle the
request:

```json
{
  "status": "ok",
  "uptime_seconds": 125.042
}
```

Uptime uses a monotonic clock, so system-clock corrections cannot make it jump
backward. This endpoint reads no camera frames, runs no YOLO inference, and
performs no database query. A component can be unavailable while liveness
remains `ok`.

## `GET /ready`: readiness

`/ready` returns one thread-safe cached snapshot:

```json
{
  "status": "ready",
  "application_state": "running",
  "components": {
    "core_services": "ready",
    "model": "ready",
    "camera": "ready",
    "vision_pipeline": "ready",
    "database": "ready"
  }
}
```

It returns HTTP `200` only when the application state is `running` and every
component is either `ready` or intentionally `disabled`. Otherwise it returns
HTTP `503` with `status: "not_ready"` and the same component map. Possible
component values are:

| Value | Meaning |
|---|---|
| `initializing` | Startup has not confirmed the component yet. |
| `ready` | The latest lifecycle operation confirmed availability. |
| `unavailable` | Initialization or an operational action failed. |
| `disabled` | Configuration intentionally disabled the dependency. |

SQLite can be disabled with `SMART_RETAIL_DATABASE_ENABLED=false`. In that
case `database` is `disabled`, which is acceptable for readiness because the
application is explicitly operating as an in-memory demo.

## Component transitions

The application records status where the real lifecycle operation occurs:

| Component | Becomes ready | Becomes unavailable |
|---|---|---|
| `core_services` | Composition of cart, event engine, UI, and adapters completes | A fatal application state makes overall readiness fail. |
| `model` | YOLO model construction succeeds | Model construction fails. |
| `camera` | OpenCV opens the configured camera | Initialization/read failure or shutdown. |
| `vision_pipeline` | The first frame completes YOLO/ByteTrack processing | Frame processing raises an unexpected error. |
| `database` | SQLite initialization or a later repository operation succeeds | Initialization, session/history access, or event write fails. |

The model and camera are deliberately separate from `vision_pipeline`. A
runtime processing failure does not falsely claim that the already-loaded model
was never initialized.

## Thread safety and cost

`HealthService` uses one small `threading.Lock` for application and component
state. Updates and readiness copies hold it only around in-memory assignments.
The returned component mapping is read-only and detached from later changes.

No health lock is held during camera capture, inference, rendering, file I/O,
or database work. HTTP handlers consume snapshots instead of importing or
probing OpenCV, Ultralytics, or the SQLite repository.

## Deployment use

In a deployed process supervisor or container platform:

- Use `/health` as the liveness probe. Repeated failure means the process is
  wedged or unreachable and may need restarting.
- Use `/ready` as the readiness probe. HTTP `503` should remove the instance
  from traffic while it initializes or while a critical component is down.

For this local V1, Uvicorn runs inside the webcam process. A fatal main-loop
error shuts down that embedded server, after recording the failed component and
application state for in-flight checks and logs. A future independently hosted
API could keep serving `503` readiness after the vision worker fails, but that
separation is intentionally outside the current phase.
