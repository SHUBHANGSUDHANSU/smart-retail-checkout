# Containerization

## Scope

The Docker image provides a reproducible, hardware-free deployment for:

- FastAPI and generated OpenAPI documentation
- the thread-safe in-memory cart service
- health/readiness and metrics snapshots
- SQLite checkout sessions and cart-event history
- API integration tests

It intentionally excludes OpenCV, Ultralytics, PyTorch, NumPy, model weights,
and the realtime webcam loop. The live demo remains native on macOS:

```bash
source .venv/bin/activate
python app.py
```

Docker Desktop on macOS runs Linux containers inside a virtual machine and is
not the primary supported route for direct Mac webcam passthrough. Keeping the
vision process native preserves the working camera-permission and OpenCV-window
behavior.

## Image design

`Dockerfile` uses three stages:

| Stage | Purpose |
|---|---|
| `api-base` | Python 3.11 slim, API-only dependencies, installed package, catalog, writable data directory |
| `test` | Adds the `dev` extra and runs vision-free FastAPI/SQLite integration tests |
| `production` | Non-root runtime, port metadata, liveness health check, headless API command |

The default final stage is `production`. The process runs as the unprivileged
`smartretail` user. Python output is unbuffered, and standard logging writes to
stdout/stderr unless an explicit log file is configured.

The image installs the base project directly from `pyproject.toml`, so it gets
the API runtime without the optional `vision` dependencies. This prevents the
container from downloading large vision packages it cannot use while keeping
one dependency source. `.dockerignore` removes Git state, virtual environments,
secrets, caches, local databases, logs, model artifacts, datasets, and training
runs from the build context.

## Build and test

From the repository root:

```bash
docker build --target test -t smart-retail-api:test .
docker run --rm smart-retail-api:test

docker build --target production -t smart-retail-api:local .
```

The test target exercises FastAPI lifespan, readiness, cart reset, metrics,
SQLite persistence, and session finalization without requiring a camera.

## Run

Use a named volume so checkout history survives container replacement:

```bash
docker volume create smart-retail-data
docker run --rm --name smart-retail-api \
  -p 8000:8000 \
  -v smart-retail-data:/app/data \
  smart-retail-api:local
```

Available inspection endpoints:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/v1/cart
curl http://127.0.0.1:8000/api/v1/metrics
```

Swagger UI is at `http://127.0.0.1:8000/docs`.

The image health check calls `/health` using Python's standard library. It
checks process liveness, while `/ready` additionally requires core services and
SQLite. Because this runtime intentionally has no vision hardware, `model`,
`camera`, and `vision_pipeline` are reported as `disabled`; that is an
acceptable readiness state rather than a false claim that they are loaded.

## Configuration

Configuration remains environment-based and uses the same validated
`SMART_RETAIL_` variables as native execution. Container defaults are:

| Variable | Container default |
|---|---|
| `SMART_RETAIL_API_HOST` | `0.0.0.0` |
| `SMART_RETAIL_API_PORT` | `8000` |
| `SMART_RETAIL_DATABASE_PATH` | `/app/data/smart_retail.db` |
| `SMART_RETAIL_LOG_FILE_PATH` | empty (stdout/stderr only) |

The product catalog and ByteTrack YAML are package data installed with
`smart_retail`; the container does not maintain duplicate config copies.
`SMART_RETAIL_PRODUCTS_CONFIG_PATH` and `SMART_RETAIL_TRACKER_CONFIG_PATH`
remain available when a custom file is deliberately mounted.

Example override:

```bash
docker run --rm -p 8080:8080 \
  -e SMART_RETAIL_API_PORT=8080 \
  -e SMART_RETAIL_LOG_LEVEL=DEBUG \
  -e SMART_RETAIL_LOG_JSON=true \
  -v smart-retail-data:/app/data \
  smart-retail-api:local
```

Do not put secrets in the Dockerfile or image. Pass future sensitive values at
runtime through an environment-management mechanism. This phase introduces no
secrets and no authentication.

## Runtime behavior and limitations

- The container API owns its own cart and checkout session.
- It does not communicate with or mirror the in-memory state of a separately
  running native webcam process.
- It exposes business-state endpoints only; there is no video streaming or
  inference endpoint.
- SQLite is reliable for this one-container local demo. Multiple replicas
  sharing one volume are not supported.
- No Docker Compose file is needed because the deployment has one service and
  no external database, broker, or monitoring stack.
