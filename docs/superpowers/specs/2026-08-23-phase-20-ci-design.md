# Production Phase 20 Continuous Integration Design

## Goal

Validate code quality, deterministic behavior, integration boundaries, and
coverage on every pull request and on pushes to `main` or `develop`, without
requiring camera hardware, a GUI display, Apple MPS, a GPU, live inference,
model-weight downloads, secrets, or external application services.

## Current repository constraints

- Python 3.11 is the supported runtime.
- Tests are written with `unittest` classes but are compatible with pytest
  collection.
- Camera, OpenCV-window, detector, tracker, lifecycle, and concurrency behavior
  already use mocks, injected adapters, or synthetic frames.
- SQLite integration tests use temporary local databases.
- FastAPI tests use an in-process test client.
- The repository has no Git remote, so a correct GitHub Actions badge URL
  cannot be derived. The README will document CI without adding a speculative
  badge.
- The repository has no initial Git commit or valid `HEAD`; Phase 20 files will
  remain in the working tree unless the user later authorizes repository
  initialization and commits.

## Recommended workflow

Create `.github/workflows/ci.yml` with one Linux job. A single job keeps the
pipeline understandable and allows unit and integration coverage to be
combined without cross-job artifacts.

The workflow triggers on:

- every pull request;
- pushes to `main`;
- pushes to `develop`;
- manual `workflow_dispatch` runs for troubleshooting.

It grants only `contents: read`, cancels an obsolete run when a newer commit is
pushed to the same branch or pull request, and has a finite job timeout.

Use these actions by stable major version:

- `actions/checkout@v6`;
- `actions/setup-python@v6` with Python 3.11 and pip caching;
- `actions/upload-artifact@v7` for the generated coverage XML report.

No action or workflow step receives a secret.

## Dependency strategy

Add a `ci` optional dependency group in `pyproject.toml` containing pinned
versions of:

- pytest;
- pytest-cov;
- Ruff.

CI installs the editable package with `vision`, `test`, and `ci` extras. The
vision libraries are required because deterministic detector, camera, and UI
tests import those adapters. Their hardware interactions are mocked or use
synthetic arrays. Installing Ultralytics must not invoke the model or download
`yolov8n.pt`.

This approach gives broader regression coverage than excluding the vision
adapter tests. It is heavier than an API-only job because PyTorch arrives as an
Ultralytics dependency, but pip caching and a single job keep it reasonable.
Splitting a second lightweight job would duplicate installation and reporting
without increasing behavioral coverage.

## Code-quality policy

Configure Ruff in `pyproject.toml` for Python 3.11. Use Ruff alone for:

- lint checks with `ruff check`;
- deterministic formatting checks with `ruff format --check`.

Do not add Flake8, Black, isort, or another overlapping formatter/linter. Scope
checks to application source, tests, the training script, and the root launcher.
If existing files fail formatting, apply Ruff's mechanical formatter and then
rerun the complete deterministic suite to prove behavior was preserved.

## Test and coverage execution

Pytest collects the existing `unittest` suite without rewriting business tests.
CI separates execution into named steps while accumulating one coverage data
set:

1. Unit/deterministic adapter tests run while explicitly ignoring the API and
   SQLite integration modules.
2. API/database integration tests run for `test_api.py`,
   `test_api_service.py`, and `test_persistence.py` and append coverage.
3. Coverage XML and a terminal summary are generated from the combined data.

All tests remain hardware-free. The suite may import OpenCV and Ultralytics,
but it must never open a real camera, create a visible window, probe MPS/GPU,
run model inference, or download model weights.

Coverage measures the complete `smart_retail` package with branch coverage.
Important business modules are not omitted. Standard non-executable guards such
as `if TYPE_CHECKING` and `if __name__ == "__main__"` may be excluded from line
reporting. The approved suite produced an 87 percent local branch-coverage
baseline across 129 tests and 36 subtests. CI therefore enforces an 85 percent
threshold, leaving only a two-point margin for normal platform differences or
small new code paths.

## Configuration contract tests

Add `tests/test_ci_configuration.py` before creating the workflow. It will
verify that:

- the workflow exists and names the expected action versions;
- Python 3.11, Ruff checks, pytest, coverage failure enforcement, and coverage
  artifact upload are present;
- no webcam command, application launcher, model-weight filename, or secret
  interpolation is present;
- the README does not add a badge while no remote repository is configured;
- the CI optional dependency group includes pytest, pytest-cov, and Ruff.

The test intentionally validates durable policy rather than every YAML line so
normal workflow maintenance does not require rewriting brittle snapshots.

## Documentation

Create `docs/TESTING.md` explaining:

- unit tests for domain, zone, cart, event, configuration, health, metrics, and
  deterministic adapters;
- integration tests for SQLite and FastAPI;
- native hardware smoke tests that remain manual;
- exact local commands matching CI;
- what GitHub Actions runs and intentionally skips;
- coverage scope, threshold, and report locations.

Update README installation/testing sections to point to the CI extra and
testing guide. Do not add a badge until the repository has a known GitHub
owner/name and workflow URL.

## Failure behavior

The job fails when:

- Ruff linting reports a violation;
- Ruff formatting differs;
- either pytest phase fails;
- combined coverage is below the configured threshold;
- coverage XML generation fails.

Pytest failures retain their normal tracebacks. Coverage XML is uploaded even
when the coverage gate fails when practical, but artifact upload must not hide
a prior lint or test failure.

## Explicit non-goals

- No physical webcam or OpenCV GUI tests in GitHub Actions.
- No MPS, CUDA, GPU, or accelerator setup.
- No YOLO inference or checkpoint download.
- No Docker image build in this phase.
- No deployment, package publishing, Codecov, SonarCloud, or external service.
- No secrets or write-capable GitHub token permissions.
- No rewrite of working vision, tracking, zone, cart, API, or persistence logic.

## Acceptance criteria

Phase 20 is complete when:

1. The workflow and configuration tests exist.
2. Ruff lint and formatting checks pass locally.
3. Unit and integration pytest phases pass locally.
4. Combined branch coverage meets the selected threshold.
5. No test accesses camera hardware or downloads model weights.
6. `docs/TESTING.md` and README accurately describe the commands.
7. The complete pre-existing deterministic suite remains green.
