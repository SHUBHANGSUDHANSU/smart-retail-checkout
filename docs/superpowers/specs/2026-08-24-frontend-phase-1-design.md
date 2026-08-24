# Frontend Phase 1 Design

## Purpose

Add a separate React operator-dashboard foundation to the existing Smart Retail
Checkout repository without changing computer-vision, tracking, checkout, cart,
or persistence behavior. Phase 1 proves one browser-to-backend integration by
showing FastAPI liveness while leaving cart, event, session, readiness, and
metrics features for later phases.

## Scope

Phase 1 includes:

- a top-level `frontend/` Vite application using React and strict TypeScript;
- declarative routes for Dashboard, Sessions, System, and Not Found;
- a responsive dark operations-dashboard shell using plain CSS;
- centralized frontend environment configuration and API access;
- one typed `GET /health` request when the Dashboard mounts;
- loading, connected, and unavailable connection states;
- an explicit, configuration-driven FastAPI development CORS allowlist;
- deterministic frontend tests, backend CORS/configuration tests, and setup
  documentation.

Phase 1 excludes cart data, session/event history, readiness details, metrics,
charts, camera streaming, WebSockets, authentication, state-management
libraries, large UI frameworks, animation libraries, and backend business-logic
changes.

## Existing Backend Contract

The FastAPI application is created by
`src/smart_retail/api/factory.py:create_api_app`. The actual liveness route is:

```http
GET /health
```

Successful response:

```json
{
  "status": "ok",
  "uptime_seconds": 125.318
}
```

The route is intentionally a liveness check. It does not prove model, camera,
database, or vision-pipeline readiness. Phase 1 labels the result as backend
connectivity, not full-system readiness.

The other existing routes remain unused by the Phase 1 frontend:

- `GET /ready`
- `GET /api/v1/cart`
- `POST /api/v1/cart/reset`
- `GET /api/v1/events`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/metrics`

## Technology Choices

The frontend uses the stable toolchain available at implementation time and
commits `package-lock.json` for reproducibility:

- React 19.2
- Vite 8
- TypeScript 6 in strict mode
- React Router 8 in declarative mode
- plain CSS
- Oxlint as the only JavaScript/TypeScript linter
- Vitest, jsdom, and React Testing Library for deterministic frontend tests

The local Node.js 22.12 runtime satisfies Vite 8's supported runtime floor.
Runtime and development dependencies remain separate in `package.json`.

No CSS framework, component library, application state library, charting
library, or animation package is added.

## Frontend Structure

```text
frontend/
├── src/
│   ├── components/
│   │   ├── DashboardCard.tsx
│   │   └── ConnectionStatus.tsx
│   ├── hooks/
│   │   └── useBackendHealth.ts
│   ├── layouts/
│   │   └── AppLayout.tsx
│   ├── pages/
│   │   ├── DashboardPage.tsx
│   │   ├── NotFoundPage.tsx
│   │   ├── SessionsPage.tsx
│   │   └── SystemPage.tsx
│   ├── services/
│   │   └── api.ts
│   ├── styles/
│   │   └── global.css
│   ├── types/
│   │   └── api.ts
│   ├── App.tsx
│   ├── config.ts
│   ├── main.tsx
│   ├── setupTests.ts
│   └── vite-env.d.ts
├── .env.example
├── .oxlintrc.json
├── index.html
├── package.json
├── package-lock.json
├── README.md
├── tsconfig.app.json
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts
```

Tests are colocated with the behavior they exercise, for example
`src/services/api.test.ts` and `src/pages/DashboardPage.test.tsx`. No empty
directories or placeholder modules are created. A `public/` directory is added
only when a real static asset requires it.

## Routing and Layout

`App.tsx` declares these routes:

| Path | Page | Phase 1 content |
|---|---|---|
| `/` | Dashboard | Intro, four cards, and real backend connectivity |
| `/sessions` | Sessions | Honest feature-ready empty state |
| `/system` | System | Honest feature-ready empty state |
| `*` | Not Found | Explanation and semantic link back to Dashboard |

`AppLayout` owns the application shell and renders an `Outlet`. It contains a
semantic navigation element with the brand `Smart Retail Checkout` and links to
Dashboard, Sessions, and System. Active and keyboard-focus states are visually
distinct.

Desktop and laptop layouts use a compact left navigation rail and flexible main
content. At tablet widths the navigation becomes a horizontal header and the
card grid collapses to one column as needed. The layout uses fluid dimensions
and does not require horizontal scrolling at the supported viewports.

## Visual Language

The shell is an internal retail-operations dashboard, not a storefront:

- dark neutral page background;
- slightly lighter cards and navigation surfaces;
- restrained green only for successful connectivity;
- muted neutral treatment for loading;
- clear red treatment for unavailable connectivity;
- subtle borders, moderate corner radius, and consistent spacing;
- system-font stack for fast local loading;
- readable contrast and visible `:focus-visible` outlines;
- no gradients, neon effects, oversized animation, or fabricated data.

The Dashboard heading is `Smart Retail Checkout` with the description
`Realtime cashierless checkout monitoring dashboard`. The four cards are:

- Current Cart — `No data loaded yet`
- System Status — real backend connection state
- Recent Events — `No data loaded yet`
- Live Metrics — `No data loaded yet`

Sessions and System use short empty-state copy that explains those views will be
connected in a later phase without showing fake operational values.

## Frontend Configuration

`frontend/.env.example` contains:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

`src/config.ts` is the only module that reads `import.meta.env`. It uses the
documented local URL when the variable is absent, trims a trailing slash, and
rejects malformed values, credentials, or schemes other than HTTP/HTTPS.
Consumers import an immutable application configuration object instead of
reading environment variables directly.

A real `frontend/.env` remains ignored by the repository's existing `.env`
rules. The root `.gitignore` gains Node/Vite artifacts such as `node_modules/`
without duplicating a second ignore policy.

## API Client and Health State

`src/types/api.ts` defines the exact liveness payload:

```ts
export interface HealthResponse {
  status: string;
  uptime_seconds: number;
}
```

`src/services/api.ts` owns browser HTTP access. `getHealth`:

1. builds `${apiBaseUrl}/health`;
2. sends one `GET` request with JSON acceptance and an optional abort signal;
3. rejects non-success HTTP responses;
4. parses JSON as `unknown` and validates the response shape before returning a
   `HealthResponse`;
5. exposes a short typed error suitable for the presentation boundary without
   placing raw response bodies or stack traces in the UI.

No React component calls `fetch` directly.

`useBackendHealth` owns the one-request-on-mount lifecycle and aborts its request
when unmounted. It exposes a discriminated union:

- `loading`
- `connected`, with the validated health payload
- `unavailable`

The Dashboard maps those states to `Checking backend...`, `Backend Connected`,
and `Backend Unavailable`. Failures display `Unable to connect to backend.` and
may log a concise development diagnostic to the console. There is no polling,
retry loop, or global state store in Phase 1.

React development `StrictMode` is not used because it intentionally replays
effects in development and would make the single on-load connectivity request
appear twice. This decision can be revisited if request caching is introduced.

## Backend CORS Integration

The current backend has no CORS middleware, so a Vite page on port 5173 cannot
read the API on port 8000. The smallest durable change is an explicit allowlist
in the existing typed API configuration.

`APIConfig` gains immutable `cors_allowed_origins`. The default and example are:

```dotenv
SMART_RETAIL_API_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Startup validation requires every configured origin to:

- use `http` or `https`;
- include a hostname;
- contain no credentials, query, fragment, or non-root path;
- be an origin rather than a wildcard.

`create_api_app` accepts the already-validated origins and installs FastAPI's
`CORSMiddleware` with:

- the explicit origins only;
- `allow_credentials=False`;
- `allow_methods=["GET"]` for Phase 1;
- `allow_headers=["Accept"]`.

Both the native application and headless API entrypoint pass their loaded API
configuration to the factory. Existing endpoint behavior, response models,
security headers, and business services remain unchanged. A hostile or
unlisted origin receives no access-control allow-origin header.

When a later frontend phase needs cart reset, that phase may explicitly add
`POST` after testing the mutation flow. Phase 1 does not pre-authorize it.

## Error Handling

Configuration errors fail at frontend startup with a concise configuration
message. HTTP failures, invalid JSON, invalid response shapes, network errors,
and an offline backend all resolve to the unavailable UI state. Raw stack traces,
backend exception details, response bodies, and webcam data are never rendered.

An aborted request during unmount does not attempt to update React state and is
not presented as an outage.

## Accessibility

- The layout uses `header`, `nav`, `main`, `section`, and heading elements.
- Navigation uses links, not clickable containers.
- Heading order starts at one page-level `h1` and descends logically.
- Connection status includes text and does not rely on color alone.
- Active navigation uses `aria-current` through `NavLink`.
- Focus indicators remain visible for keyboard users.
- Text and status colors are chosen for readable contrast on dark surfaces.
- Motion is not required to understand any state.

## Testing Strategy

Frontend deterministic tests use Vitest and jsdom without network access:

- configuration accepts the development default and normalizes a trailing
  slash;
- configuration rejects malformed or unsafe URLs;
- `getHealth` returns a typed result for a valid successful response;
- `getHealth` rejects non-success responses and invalid payloads;
- Dashboard initially displays the loading state;
- a successful mocked fetch displays `Backend Connected`;
- a rejected mocked fetch displays `Backend Unavailable` and the friendly
  message;
- navigation and Not Found routing resolve to the intended pages.

The browser `fetch` boundary is mocked; internal rendering and state logic are
not mocked.

Backend tests cover:

- default and environment-overridden CORS origins;
- invalid and wildcard origins rejected during configuration loading;
- an allowed Vite origin receives the exact access-control header;
- an unlisted origin receives no access-control header;
- existing health response and security headers remain intact.

Verification commands include frontend install, tests, lint, TypeScript build,
production build, a bounded Vite development-server HTTP smoke check, focused
backend tests, and the full backend suite because shared startup configuration
and the API factory are touched.

Backend-online behavior is verified against a local API process. Backend-offline
behavior is verified deterministically by tests and by confirming the frontend
still renders when its configured API port is unreachable.

## Documentation

`frontend/README.md` documents Node prerequisites, installation, environment
setup, `npm run dev`, tests, lint, production build, preview, the expected
FastAPI URL, and `VITE_API_BASE_URL`.

The root README receives only the changes needed to identify the Python
backend/computer-vision application and the separate React frontend, show their
development commands, include `frontend/` in the structure, and document the
new CORS setting. `docs/API.md` and `docs/SECURITY.md` are corrected so they no
longer claim CORS is entirely disabled.

## Acceptance Criteria

Phase 1 is complete when:

1. `frontend/` installs reproducibly from `package-lock.json`.
2. Frontend tests, Oxlint, TypeScript checking, and the Vite production build
   pass.
3. The development server responds and renders the application shell.
4. Dashboard, Sessions, System, and Not Found routes work directly.
5. With FastAPI available, Dashboard displays `Backend Connected`.
6. With FastAPI unavailable, Dashboard stays usable and displays
   `Backend Unavailable` with a friendly explanation.
7. CORS allows only configured development origins and does not use a wildcard.
8. Focused and full backend tests pass.
9. No computer-vision, tracking, checkout, cart, or persistence algorithm is
   modified.

## Intentional Deferrals

Phase 2 may connect the existing cart, readiness, event, session, and metrics
contracts and decide whether bounded polling or another refresh strategy is
appropriate. It may also add the already-existing cart reset command after
expanding and testing CORS methods. Camera streaming, WebSockets,
authentication, charts, global state libraries, and large UI frameworks remain
outside Phase 1.
