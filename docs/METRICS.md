# Lightweight application metrics

`MetricsService` keeps a bounded, thread-safe view of realtime performance,
checkout behavior, and recoverable failures. It is local process memory only:
there is no Prometheus client, metrics database, exporter, or per-frame INFO
logging in this phase.

Inspect the current snapshot while the application is running:

```bash
curl http://127.0.0.1:8000/api/v1/metrics
```

## Metric reference

| Metric | Kind | Meaning and operational use |
|---|---|---|
| `frames_processed_total` | Counter | Frames that completed vision and checkout processing; confirms useful pipeline throughput. |
| `dropped_frames_total` | Counter | Failed camera read attempts, including retries that later recovered; highlights capture instability. |
| `detections_total` | Counter | Accepted tracked observations across processed frames; provides workload context. |
| `active_tracks` | Gauge | Unique non-null track IDs in the latest completed frame; shows current scene load. |
| `inference_latency_ms` | Rolling average | Recent YOLO/ByteTrack latency; helps identify model/device bottlenecks. |
| `frame_processing_latency_ms` | Rolling average | Recent vision-plus-checkout processing latency, excluding capture and rendering. |
| `current_fps` | Gauge | Most recently calculated loop FPS. |
| `checkout_enter_events_total` | Counter | Confirmed `OUTSIDE -> INSIDE` transitions. |
| `checkout_exit_events_total` | Counter | Confirmed `INSIDE -> OUTSIDE` transitions. |
| `cart_additions_total` | Counter | Successful exact-track cart additions; duplicates and unsupported products do not increment it. |
| `cart_removals_total` | Counter | Successful exact-track removals, including grace-period expiry. |
| `cart_resets_total` | Counter | Accepted API or keyboard resets, including reset of an empty cart. |
| `current_cart_items` | Gauge | Physical item quantity from the latest consistent cart snapshot. |
| `current_cart_total` | Gauge | Integer-currency total from that same snapshot. |
| `uptime_seconds` | Gauge | Monotonic elapsed time since metrics-service construction. |
| `camera_errors_total` | Counter | Camera initialization or exhausted-read failures caught by the coordinator. |
| `persistence_errors_total` | Counter | Actual caught SQLite initialization, read, session, close, or event-write failures. |

## Counters, gauges, and rolling averages

A **counter** only increases and answers “how many times has this happened in
this process?” A **gauge** replaces its prior value and answers “what is true
now?” Latency metrics are arithmetic means over a bounded deque containing the
most recent 60 completed frames by default. Change that bound with:

```bash
SMART_RETAIL_METRICS_ROLLING_WINDOW_SIZE=120 python app.py
```

Values below one are rejected during startup. Historical samples are evicted,
so memory use remains constant regardless of run duration.

## Measurement boundaries

Latency and uptime use `time.perf_counter`, a monotonic high-resolution clock.
Frame processing starts immediately before the vision pipeline and stops after
checkout processing. Webcam capture and OpenCV rendering are excluded. Failed
frame reads increase the drop counter but not `frames_processed_total`.

Confirmed ENTER/EXIT events increment even when a duplicate or unsupported
event cannot change the cart. Cart counters increment only after a successful
business mutation. This distinction makes tracker/zone activity comparable to
actual checkout changes.

## Thread safety

The vision loop writes metrics while FastAPI worker threads read them.
`MetricsService` uses one short, non-reentrant `threading.Lock`. Numeric updates,
bounded deque changes, and snapshot copying occur under that lock; inference,
OpenCV operations, SQLite calls, and logging do not. `get_snapshot()` returns a
frozen dataclass, so API consumers cannot mutate internal state or combine
fields from different updates.

## Future Prometheus export

A later adapter could translate each `MetricsSnapshot` counter and gauge into
Prometheus instruments and expose the Prometheus text format. The coordinator
would continue calling the same service. Labels, histograms, scraping
middleware, Grafana dashboards, and external alerting are deliberately deferred
until the local demo has a concrete deployment need.
