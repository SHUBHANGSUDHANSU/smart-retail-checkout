# Concurrency and shared-state ownership

## Why shared mutable state exists

The application has two execution contexts in one Python process:

- The main thread captures frames, runs YOLO and ByteTrack, converts tracked
  objects into checkout events, and renders OpenCV output.
- Uvicorn serves synchronous FastAPI routes in worker threads. Several API
  requests may execute concurrently with each other and with the main thread.

Both contexts need the current cart, readiness information, checkout reset, and
SQLite history. Shared state is therefore intentional, but it is exposed only
through synchronized operations and immutable snapshots.

## Ownership audit

| State or component | Ownership | Protection |
|---|---|---|
| Camera capture and BGR frame | Vision thread only | No lock required |
| YOLO model and ByteTrack internals | Vision thread only | No lock required |
| Frame number, FPS, debug flag, inference timing | Vision thread only | No lock required |
| Current `TrackedObject` tuple | Vision thread only and immutable | No lock required |
| FastAPI request objects and Pydantic responses | API request only | No lock required |
| Cart track membership | Shared | Internal `CartService` lock |
| Checkout stable/pending/expiry track state | Vision processing and API reset | Checkout-command lock |
| Application/component health state | Shared | Internal `HealthService` lock |
| Metrics counters, gauges, and latency window | Shared | Internal `MetricsService` lock and immutable snapshot |
| Active persistence repository and session ID | Shared | Runtime-state lock |
| OpenCV notification value | Vision rendering and API reset | Notification lock |
| Product catalog | Shared but immutable after startup | No lock required |
| SQLite event/session history | Shared durable state | Separate connections and SQLite transactions |
| API-server lifecycle fields | Main-thread lifecycle plus Uvicorn internals | Owned by server adapter |
| Frame-loop stop/finished signals | Main thread and lifecycle callers | Events plus lifecycle lock |

There is no in-memory event-history list. The REST event and session endpoints
read SQLite directly, so they cannot observe a partially appended Python
container.

## Synchronization choices

### Cart lock

`CartService` uses a non-reentrant `threading.Lock`. `add_item()`,
`remove_item()`, `contains_track()`, `product_for_track()`, `clear()`,
`get_items()`, `get_total()`, and `get_snapshot()` synchronize access to exact
track membership.

`get_snapshot()` aggregates items and calculates total while holding that lock
once. It returns a frozen `CartSnapshot` containing a tuple of frozen
`CartItem` values. Consequently, an API response cannot combine quantities from
one cart version with a total from another or mutate service internals.

### Checkout-command lock

`SmartRetailApplication.process_checkout_frame()` and `reset_checkout()` share
one non-reentrant checkout-command lock. It serializes event-engine state and
cart commands, including the matching meaningful SQLite write. Keeping the
write in this command order is deliberate: a confirmed `ADD` that linearizes
before a `RESET` must not be inserted after that reset in durable history.

The command lock does not protect cart reads. `GET /api/v1/cart` uses the cart's
own short lock and remains responsive while SQLite commits an event. Frames,
YOLO/ByteTrack inference, OpenCV drawing, health reads, and SQLite history
queries also do not acquire the command lock.

### Health and runtime-state locks

`HealthService` owns a non-reentrant lock around application state and component
status transitions. `/ready` receives one copied, read-only component mapping,
so it cannot combine values from different transitions. `/health` calculates
uptime from an immutable monotonic start time and does not need this lock.

The coordinator has a separate non-reentrant runtime-state lock for the current
repository and session ID. History endpoints copy the repository reference and
perform SQLite work only after releasing that lock. A successful operation can
publish `database=ready` only while holding the runtime-state lock and confirming
that the same repository is still current. Therefore a stale in-flight read
cannot overwrite a newer persistence-disable transition. A disable operation
publishes `database=unavailable` before it clears the repository reference, so
there is no window containing a missing adapter and stale ready status. Health
routes never call SQLite: database readiness changes only when a normal
repository operation succeeds or fails.

### Notification lock

An API reset can publish an OpenCV notification while the main thread draws the
current one. `OpenCVUI` uses a small lock only to replace, inspect, or expire the
immutable notification value. It never holds the lock while drawing.

`RLock` is not needed. No operation intentionally reacquires the same lock.

### Lifecycle coordination

An external shutdown request first sets a thread-safe stop event. The main loop
finishes its current frame, observes the event before requesting another frame,
and performs ordered cleanup itself. An external caller waits on the loop's
finished event and therefore cannot release the camera, finalize the session,
or close SQLite underneath active frame processing. Lifecycle state, the loop
owner ID, completed cleanup steps, and retry status share one short lock; the
lock is never held while waiting for the frame loop.

### Metrics lock

The vision loop and failure boundaries update `MetricsService`; API workers read
one frozen `MetricsSnapshot`. One non-reentrant lock protects numeric updates
and the two bounded latency deques. Expensive inference, rendering, database
work, and logging happen outside it. Metrics never acquire cart, checkout,
health, or runtime-state locks while holding their own lock, avoiding a new
lock-order cycle.

## Immutable presentation snapshots

The event engine copies its stable track-state mapping into a read-only
`CheckoutStateSnapshot`. The coordinator pairs that value with one
`CartSnapshot` after a frame command completes. OpenCV renders those snapshots
after releasing the checkout lock.

The result may be one frame old if an API reset occurs immediately afterward,
but it is internally consistent and cannot race with dictionary mutation. The
next frame reflects the reset.

## Reset ordering

Lock acquisition is the linearization point for concurrent reset and crossing
commands:

1. If a confirmed `ENTER` obtains the lock first, its item and `ADD` history
   entry complete first. Reset then clears event-engine and cart state, records
   `RESET`, and returns an empty snapshot.
2. If reset obtains the lock first, it clears state and records `RESET`. A track
   then observed inside is a new baseline, so it does not immediately produce a
   duplicate `ENTER`.

Both orders leave the cart empty for the specific reset-versus-entry race. The
API response always describes the state created by its own reset command.

## SQLite concurrency

The repository opens a new SQLite connection for every operation. Connections
are created and consumed in the calling thread, avoiding cross-thread use of a
single `sqlite3.Connection`. Every write uses a transaction, parameterized SQL,
foreign keys, and the configured busy timeout.

API history reads use their own short-lived connections and do not acquire an
application lock. SQLite supplies statement-level read consistency and
coordinates those reads with event writes. The webcam loop never queries
history per frame; it writes only meaningful `ADD`, `REMOVE`, and `RESET`
commands.

## Lock scope and deadlock avoidance

- Frame capture and YOLO/ByteTrack inference occur before any shared-state lock.
- OpenCV rendering and window operations use immutable snapshots outside locks.
- Health snapshots perform no adapter I/O or database queries.
- SQLite history queries occur outside runtime-state and health locks.
- Cart aggregation holds only the cart lock and performs no I/O.
- Notification drawing copies the notification before calling OpenCV.
- No code acquires the checkout-command lock while holding the application-state
  lock.
- A checkout command may briefly acquire the application-state or cart lock;
  the reverse acquisition order is never used.
- SQLite repository methods do not call back into the application or cart.

These rules prevent circular waits while keeping critical sections limited to
the state that must move atomically.

## Test coverage

`tests/test_concurrency.py` verifies without camera hardware:

- simultaneous cart readers and writers;
- quantity/subtotal/total invariants for every snapshot;
- independent immutable snapshots during repeated concurrent reads;
- deterministic reset-versus-entry behavior and persisted ordering;
- concurrent SQLite history reads and vision-event writes;
- a deliberately blocked OpenCV renderer does not block cart reads.
- a stale successful SQLite read cannot overwrite a concurrent disable event.
- database unavailability is published before the repository is cleared.

`tests/test_health.py` additionally races component transitions against repeated
readiness snapshots and checks every snapshot invariant. API tests verify that
health routes do not invoke the SQLite readiness probe.

`tests/test_metrics.py` runs concurrent frame updates and snapshot reads,
verifies counter relationships, and proves the rolling windows remain bounded.

The normal cart, zone, API, persistence, UI, and application tests remain in the
full suite to protect existing behavior.
