# Testing and Continuous Integration

The deterministic test suite exercises the checkout system without loading a
model, touching hardware, or starting a network server. GitHub Actions uses
Python 3.11 and the same lint, test, and combined coverage policy described
here.

## Test taxonomy

| Directory | Scope |
| --- | --- |
| `tests/unit` | Pure domain/service behavior and mocked adapter behavior. |
| `tests/integration` | SQLite, FastAPI, orchestration, lifecycle, and concurrency scenarios. |
| `tests/contracts` | Packaging, CI, and container policy artifacts, plus wheel-resource and security checks. |

Run an individual category when working on that area:

```bash
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests/integration -q
.venv/bin/python -m pytest tests/contracts -q
```

The primary full-suite command is:

```bash
.venv/bin/python -m pytest tests -q
```

## Fixture isolation

Fixtures that expose mutable carts, event engines, zones, catalog data, and
temporary SQLite repositories are function-scoped. Each test receives fresh
state, and the SQLite fixture creates its database beneath pytest's `tmp_path`
and closes it after `yield`. Tests must not depend on execution order, shared
mutable objects, a pre-existing database, or an external service.

Concurrency tests use real application state with `Barrier`, `Event`, futures,
and bounded joins to coordinate progress. They do not use arbitrary sleeps or
retries to make a result eventually pass.

## Local CI-equivalent checks

Install the pinned test and CI tools with the native vision dependencies:

```bash
.venv/bin/python -m pip install --editable ".[vision,dev]"
```

The local CI-equivalent workflow is no-retry: an intermittent failure is a
failure to investigate, not a reason to use a retry plugin or rerun flag.
Run Ruff exactly as CI does:

```bash
.venv/bin/python -m ruff check app.py src tests training
.venv/bin/python -m ruff format --check app.py src tests training
```

The CI policy first runs unit and contract tests, then integration tests, and
only then enforces the combined 85% branch-aware coverage gate:

```bash
.venv/bin/python -m coverage erase
.venv/bin/python -m pytest tests/unit tests/contracts -q \
  --cov=smart_retail \
  --cov-branch \
  --cov-fail-under=0 \
  --cov-report=
.venv/bin/python -m pytest tests/integration -q \
  --cov=smart_retail \
  --cov-branch \
  --cov-append \
  --cov-fail-under=0 \
  --cov-report=
.venv/bin/python -m coverage xml -o coverage.xml
.venv/bin/python -m coverage report --show-missing --fail-under=85
```

The first shard has no threshold because integration coverage has not yet been
appended. No important business modules are excluded merely to increase the
percentage.

The packaging contract builds a wheel with `--no-deps --no-build-isolation` and
asserts that the default product catalog and ByteTrack YAML are present. This
keeps the test offline while catching the difference between a working source
checkout and a broken installed console command.

## Stability check

Run the full suite three separate times. These are independent no-retry suite
runs: do not use a retry plugin, a rerun flag, or a loop that hides an
intermittent failure.

```bash
.venv/bin/python -m pytest tests -q
```

```bash
.venv/bin/python -m pytest tests -q
```

```bash
.venv/bin/python -m pytest tests -q
```

## Intentional exclusions and manual smoke coverage

The deterministic suite intentionally does not test Ultralytics internals,
download or load YOLO weights, or perform live inference in
`src/smart_retail/vision/detector.py`. It also excludes a physical webcam, a
visible GUI/OpenCV window, MPS/GPU/CUDA device execution, and live Uvicorn
server startup in `src/smart_retail/api/server.py`. These boundaries are mocked
at the adapter edge so the business behavior remains deterministic.

Test the native demo manually on macOS when changing those paths:

1. Grant Terminal or the IDE camera permission.
2. Run `python app.py`.
3. Confirm the webcam and OpenCV window remain responsive.
4. Verify detections, stable tracking IDs, checkout ENTER/EXIT behavior, cart
   updates, reset with `R`, debug toggle with `D`, and clean exit with `Q`.

## Weak deterministic coverage areas

The fresh combined branch-coverage report identifies these current below-85%
deterministic modules. They are useful targets for focused tests, not a reason
to chase 100% or invent a final percentage:

- `src/smart_retail/infrastructure/logging_config.py` (55% reported):
  process-global handler replacement and warnings routing are intentionally
  exercised in a subprocess so the test cannot remove or close pytest's parent
  logging handlers. Parent-process `pytest-cov` therefore does not observe the
  child execution of those lines, even though the subprocess test verifies the
  rotating handler, JSON file event, and console event.
- `src/smart_retail/api/service.py`: defensive headless-runtime lifecycle and
  persistence-cleanup failures, plus exceptional persistence-read paths.
- `src/smart_retail/app.py`: deterministic orchestration branches for a second
  concurrent frame loop, cart expiry without a cart entry, persistence-read
  failures, and track-debug logging.
- `src/smart_retail/infrastructure/sqlite_repository.py`: low-level SQLite
  connection/read failures and defensive event-field validation branches beyond
  the temporary-database success, rollback, and recovery scenarios.

## What CI executes

The workflow in `.github/workflows/ci.yml` runs on pushes to `main` and
`develop`, pull requests, and manual dispatch. A lightweight job installs the
base package, proves vision packages are absent, resolves the API entrypoint,
and runs the vision-free headless service integration tests. The main job
installs the pinned tools, runs Ruff lint and formatting, runs
`tests/unit tests/contracts`, then runs `tests/integration`, generates
`coverage.xml`, and enforces the combined 85% branch-coverage threshold. It has
read-only repository permissions, needs no secrets, and uploads the coverage
report as a short-lived artifact.
