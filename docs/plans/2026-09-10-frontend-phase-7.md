# Frontend Phase 7 Implementation Plan

**Goal:** Add a truthful, isolated hardware-free demo path and finish the repository's portfolio presentation without changing vision behavior.

**Architecture:** Extend the headless runtime with demo-only commands that reuse cart, SQLite, metrics, and SSE. Register the demo router only when typed configuration enables it. Let React discover that router, present an explicit global mode label, and invoke server-side commands from a small Dashboard panel.

**Technology:** Python 3.11, FastAPI/Pydantic, SQLite, pytest, React 19, TypeScript, Vite, Vitest, browser EventSource, shell startup helper.

## Task 1: Typed demo configuration

- Add failing configuration tests for the disabled default and environment parsing.
- Add immutable `DemoConfig` and `SMART_RETAIL_DEMO_MODE` loading.
- Add the setting to `.env.example` and safe startup summary.
- Run focused configuration tests.

## Task 2: Demo application service and conditional API

- Add failing integration tests showing demo routes are absent normally and available only in demo mode.
- Add typed demo manifest/product/mutation responses.
- Extend the headless runtime with locked add/remove operations using unique negative track IDs.
- Reuse persistence, metrics, logging, cart snapshots, and SSE publication after the state lock is released.
- Register the demo router conditionally in the API factory/service composition.
- Run focused API, service, persistence, and realtime tests.

## Task 3: Frontend demo discovery and controls

- Add failing API and component tests for normal mode, demo badge, controls, busy/error states, and SSE reconciliation.
- Add typed demo contracts and centralized API functions.
- Add a lightweight demo-mode provider shared by the application shell and Dashboard.
- Add accessible demo controls populated from the backend manifest.
- Preserve the existing cart/event/metrics realtime flow.
- Run frontend unit tests and lint.

## Task 4: Easy startup and preflight presentation

- Add `scripts/run-demo.sh` with explicit demo mode, isolated SQLite path, frontend/backend startup, and signal-safe cleanup.
- Improve API-only startup logging with mode, database, API URL, frontend URL, and disabled vision status.
- Verify shell syntax and a real demo API/frontend smoke run.

## Task 5: Portfolio documentation

- Reorganize `README.md` around demo, architecture, quick start, decisions, tests, and truthful limitations.
- Create `docs/DEMO.md`, `docs/PROJECT_STATUS.md`, and `docs/images/README.md`.
- Update architecture, API, security, testing, realtime, and interview documentation.
- Add one-line resume copy, three bullets, and a 60-second explanation.
- Reconcile `.env.example`, frontend environment documentation, commands, and endpoint names.

## Task 6: Cleanup and full verification

- Audit dead files, stale commands, dependencies, generated artifacts, and ignore rules; remove only clearly obsolete content.
- Run Ruff lint and format check, all backend tests with coverage, frontend lint/tests/build, shell checks, and headless install tests.
- Run demo-mode end-to-end API/SSE/browser checks and responsive checks at 1440, 1024, 768, and 390 px.
- Attempt real vision smoke testing only when camera access is available, and report it separately.
- Review the final diff, commit the completed phase, and leave `codex/frontend-phase-7` unmerged.
