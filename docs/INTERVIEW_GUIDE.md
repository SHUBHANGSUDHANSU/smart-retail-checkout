# Interview guide

## Explain your project.

Smart Retail Checkout is a local computer-vision checkout simulation. A webcam
feeds YOLOv8 detections into ByteTrack, which associates detections across
frames. A debounced checkout-zone state machine converts stable crossings into
domain events, and a track-ID-aware cart turns those events into quantities and
integer-currency totals. OpenCV presents the live result, SQLite records
meaningful checkout history, and FastAPI exposes thread-safe state snapshots.

The main engineering work is not simply calling a model. It is converting
noisy frame-level observations into deterministic business state while keeping
vision, domain logic, persistence, API, lifecycle, and presentation separately
testable.

## What problem does the project solve?

It converts a live webcam stream into a stateful retail-checkout simulation. It
detects supported products, follows each physical trajectory, identifies stable
checkout-zone crossings, and maintains an itemized cart without repeatedly
counting the same track.

## Why YOLO?

YOLO performs localization and classification in one inference pass, making it
well suited to an interactive webcam pipeline. Ultralytics also provides a
simple Python API and integrated ByteTrack support.

## Why YOLOv8n?

The nano model prioritizes low latency and modest memory use over maximum
accuracy. That tradeoff is appropriate for a local Mac demo and gives a clean
starting point for later fine-tuning.

## What is object detection?

Object detection predicts both *what* objects are present and *where* they are,
usually as a class label, confidence score, and bounding box for each instance.

## Detection vs. tracking?

Detection analyzes a frame independently. Tracking associates detections across
sequential frames, producing a trajectory and a persistent identity for each
object while the association remains reliable.

## Why ByteTrack?

ByteTrack is fast, practical, and already integrated with Ultralytics. It can
use lower-confidence detections during association, which helps maintain tracks
through brief weak observations without requiring a separate tracking stack.

## How does ByteTrack work conceptually?

It predicts the next locations of existing tracks, matches high-confidence
detections to them, and then uses lower-confidence detections to recover some
unmatched tracks. Unmatched observations may create new tracks, while lost
tracks remain buffered temporarily before removal.

## Why isn't YOLO alone sufficient?

YOLO does not inherently know that a bottle in frame 20 is the same bottle in
frame 21. Without tracking, every frame-level detection could look like a new
item and duplicate checkout would be difficult to prevent.

## What is a tracking ID?

A tracking ID is a temporary integer assigned to one estimated object
trajectory, such as `ID 7`. It is stable while the tracker can associate that
object, but it is not a permanent product serial number or guaranteed identity.

## How do you prevent duplicate counting?

`CartService` stores entries by tracking ID. Adding an ID that already exists is
a no-op. Separate IDs for two bottles remain separate internally and are
aggregated into one visible product row with quantity two.

## How do you determine that something entered checkout?

The system computes the bounding-box centroid and compares it with a normalized
checkout rectangle. It stores the previous stable zone state per ID and emits
`ENTER` only after an `outside` track remains inside for three consecutive
visible frames.

## Why use a checkout zone?

A visible zone turns continuous object motion into an explicit, explainable
business boundary. It keeps V1 deterministic: a confirmed outside-to-inside
transition means add, while the same tracked object moving back outside means
remove. This is much easier to demonstrate and test than trying to infer shelf
pickup, customer intent, and payment from one webcam.

## What happens during temporary occlusion?

ByteTrack buffers a lost track for up to 60 frames, while application state has
a 90-frame expiry grace period. No crossing event is generated during missing
frames. If the same ID returns, its previous zone and cart state are preserved.

## What happens when the tracking ID changes?

The application does not invent a match between old and new IDs. A new ID first
seen inside establishes a baseline without generating `ENTER`, which prevents a
likely duplicate. The old ID eventually expires. This favors deterministic
behavior over unreliable identity guessing.

## Why use centroid-based zone checking?

It is simple, fast, resolution-independent with normalized coordinates, and
less sensitive than testing whether any edge of a noisy box touches the zone.
Its limitation is that a large box can overlap the zone before its center enters.

## What is IoU?

Intersection over Union measures bounding-box overlap:

```text
IoU = intersection area / union area
```

Trackers can use overlap, motion, and confidence to decide which new detection
best matches an existing track. An IoU of 1 means identical boxes; 0 means no
overlap.

## What does confidence threshold mean?

It is the minimum detector score accepted for a purpose. This project lets
ByteTrack see detections down to `0.10` for association but requires `0.45` for
display and zone/cart logic, balancing continuity against false checkout events.

## Why separate vision and business logic?

Vision answers uncertain observational questions: which objects were detected,
where, and under which temporary track ID. Business logic answers deterministic
questions: did a stable crossing occur, is this ID already charged, and what is
the total? Keeping those layers separate means cart, event, persistence,
concurrency, health, and API behavior can be tested without Ultralytics, a
webcam, OpenCV windows, or a GPU. It also prevents model-specific tensors from
leaking throughout the application.

## Why SQLite?

The demo is a single local edge process that writes only meaningful cart and
session events. SQLite provides transactions, constraints, foreign keys, and
portable inspection without running a database server. The realtime cart stays
in memory, so SQLite is not queried on every frame. A client/server database
would become appropriate for multiple writers, multiple application instances,
centralized operations, or high-volume analytics.

## Why FastAPI?

FastAPI makes the local state API small and typed. Pydantic validates inputs and
serializes stable response schemas, while OpenAPI and Swagger documentation are
generated automatically. Crucially, handlers only read or command application
services; they never run YOLO inference. The API depends on a small structural
runtime protocol shared by the native and headless modes.

## What race condition existed?

One concrete readiness race involved an in-flight SQLite history read. A
concurrent persistence failure could disable and remove the repository, after
which the older successful read could incorrectly mark the database ready
again. The fix copies the repository reference under the runtime-state lock and
marks readiness successful only if that exact repository is still current.
Disabling persistence publishes `unavailable` under the same lock before
clearing the reference, closing the opposite stale-ready window.

The cart also had a general consistency risk once API workers and the vision
loop shared it: reading quantity and total in separate critical sections could
combine different versions. The current snapshot calculates all related fields
under one cart lock.

## How did you make cart state thread-safe?

`CartService` owns a short non-reentrant lock around its track-ID membership.
Mutations and snapshot construction happen inside that lock, and consumers get
frozen `CartSnapshot` and `CartItem` values rather than the internal dictionary.
A separate checkout-command lock serializes zone-driven mutations with API
reset so one command has a deterministic order. Inference, rendering, logging,
and history reads do not run inside the cart lock.

## Liveness vs. readiness?

Liveness answers “is this process responsive?” and returns uptime without
probing dependencies. Readiness answers “can this instance perform its intended
work?” using cached thread-safe component state for core services, model,
camera, vision pipeline, and database. A process can therefore be live but not
ready—for example, after camera failure. Health requests do not open the camera,
query SQLite, or run inference.

## What metrics do you monitor?

Vision metrics include processed and dropped frames, detections, active tracks,
FPS, inference latency, and total frame-processing latency. Business metrics
include checkout entries/exits, successful cart additions/removals, resets,
current item count, and total. System metrics include uptime plus camera and
persistence error counters. Counters are cumulative, current values are gauges,
and latency uses a bounded rolling average rather than retaining every frame.

## What happens during graceful shutdown?

The application first stops accepting or processing new work and lets the frame
loop finish its current unit of work. It then closes the active checkout session
with the final total, releases the camera, destroys OpenCV windows, closes
database ownership, stops the API/service resources, and records the stopped
state. Cleanup steps are idempotent and isolated so a cleanup failure is logged
without hiding the original exception.

## How do you test without a webcam in CI?

Deterministic tests exercise domain models, cart rules, zone hysteresis,
tracking-result translation, event expiry, SQLite transactions, API responses,
metrics, lifecycle, and concurrency using real in-process services and
temporary databases. Only hardware or external-library boundaries—camera
capture, YOLO model execution, OpenCV windows, and Uvicorn socket startup—are
replaced. CI neither downloads weights nor requires a display, GPU, MPS, cloud
service, or network call. Native webcam behavior remains a documented manual
smoke test.

## What are the largest limitations?

The COCO model detects broad classes rather than SKUs, a single camera struggles
with overlap and handoffs, ByteTrack lacks appearance re-identification, zone
logic is a simplified checkout policy, and SQLite history has no payment or
sensor-based verification. The local API exposes business state only; it has no
authentication, remote-deployment hardening, or video streaming.

## How would this scale into a real retail environment?

A production design would need calibrated multi-camera coverage, SKU-specific
training data, cross-camera identity association, shelf or weight sensor fusion,
event reconciliation, persistent transactions, observability, privacy controls,
and extensive testing against store-specific failure cases.

It would also require authenticated customer/session identity, payment and
refund workflows, durable multi-instance event processing, stronger database
and retention controls, model/data monitoring, security hardening, human review
for ambiguous events, and store-operational fallback procedures.

## Why is this only an Amazon-Go-style simulation?

It demonstrates the concept of automatically translating observed movement into
cart state, but Amazon-Go-style stores rely on substantially broader sensing,
calibration, identity, distributed infrastructure, and operational safeguards.
This project uses one webcam, a small class set, and a deliberately simplified
zone-crossing rule.

## Short project pitch

> I built a local real-time checkout simulation using YOLOv8, ByteTrack, and
> OpenCV. Detection says what and where; tracking supplies continuity through an
> ID; a hysteresis-based zone state machine converts stable crossings into cart
> events. The cart keys entries by track ID to prevent duplicate charging and
> aggregates identical product classes for display. I added explicit handling
> for missing detections, temporary occlusion, MPS fallback, camera failures,
> reset behavior, and boundary jitter, with unit tests around deterministic
> state logic.

The truthful boundary is important: this demonstrates an Amazon-Go-style event
flow, not Amazon Go equivalence. A single RGB webcam and motion tracker cannot
provide production-grade SKU identity, customer association, sensor fusion, or
loss-prevention accuracy.
