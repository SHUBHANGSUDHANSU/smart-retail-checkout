# Frontend Phase 7 Design

## Objective

Make the completed Smart Retail Checkout project straightforward to demonstrate without weakening the distinction between real computer vision and controlled synthetic activity.

## Demo runtime

`SMART_RETAIL_DEMO_MODE` is a validated, disabled-by-default application setting. When enabled with the API-only entrypoint, the runtime does not initialize the camera, YOLO, ByteTrack, or the OpenCV window. A demo-only API router is registered conditionally, so mutation endpoints do not exist in normal mode or normal OpenAPI output.

The demo runtime generates unique negative track IDs server-side. Add and remove commands use the same thread-safe cart service, persistence repository, metrics service, structured logging, and realtime publisher used by the real application. Full cart snapshots and persisted checkout events continue to reach React through the existing SSE connection. Synthetic events are identified by the global demo-mode presentation and an isolated demo database selected by the startup helper; the domain event schema is not changed.

The supported controls are:

- inspect demo mode and supported products;
- add one physical demo item for a selected product;
- remove one active demo item for a selected product;
- reset through the existing cart-reset API.

Completing a session remains a lifecycle operation: graceful API shutdown closes the session, and the next demo start creates a new session. This avoids adding an artificial session lifecycle solely for presentation.

## API and frontend

The demo router is available only while demo mode is enabled. It exposes a typed manifest and narrowly scoped product mutation commands. Product choices come from the backend catalog rather than frontend constants.

React loads the manifest once through the centralized API client. A `404` means normal mode. In demo mode, the application shell displays an explicit `DEMO MODE` badge and explains that computer vision is inactive. Dashboard controls invoke backend commands and rely on existing REST reconciliation plus SSE updates; they never edit cart state directly.

## Startup experience

Normal entrypoints remain unchanged:

- `smart-retail` for camera/vision mode;
- `smart-retail-api` for API-only mode;
- `npm run dev` for React.

`scripts/run-demo.sh` starts the API in demo mode with `data/smart_retail_demo.db`, starts Vite, prints both URLs, and forwards termination signals so both child processes stop cleanly. Configuration and health services remain the source of startup truth.

## Documentation and portfolio assets

The root README is reorganized around the demo, architecture, quick start, engineering decisions, verification, and limitations. `docs/DEMO.md` provides a 30–60 second recording script and screenshot checklist. `docs/images/README.md` reserves predictable asset names without committing fabricated screenshots. `docs/PROJECT_STATUS.md`, architecture, API, security, testing, and interview documentation are updated to describe the final system accurately.

## Testing and safety

Backend tests cover disabled-by-default behavior, conditional route registration, unique demo tracks, duplicate product quantity aggregation, removal, unsupported products, persistence, metrics, and SSE publication. Frontend tests cover mode discovery, badge visibility, controls, request failures, busy states, and realtime reconciliation. Full lint, formatting, coverage, frontend tests/build, headless installation, API/demo smoke tests, responsive browser checks, and CI-equivalent commands are required before completion.

The demo publisher remains single-process, demo endpoints are unauthenticated only because they are local and disabled by default, and real-camera verification is reported separately from demo verification.
