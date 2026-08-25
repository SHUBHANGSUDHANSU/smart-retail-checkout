# Frontend Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate React/Vite/TypeScript operator-dashboard foundation with one typed FastAPI liveness integration and an explicit local-development CORS allowlist.

**Architecture:** The React single-page application lives in `frontend/` and owns browser routing, layout, environment validation, and API presentation state. A central API service calls the existing `GET /health` route; FastAPI receives only the minimal configuration-driven CORS middleware needed for the two local Vite origins. Computer vision and backend business services are untouched.

**Tech Stack:** React 19.2, Vite 8, TypeScript 6 strict mode, React Router 8 declarative mode, plain CSS, Oxlint, Vitest, jsdom, React Testing Library, FastAPI CORSMiddleware, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-frontend-phase-1-design.md`

## Global Constraints

- Do not modify YOLO, ByteTrack, checkout event, cart, SQLite, health, readiness, metrics, or OpenCV behavior.
- The only real frontend data in Phase 1 is `GET /health`; all other cards use honest empty states.
- Use no Tailwind, UI framework, global state library, charting library, animation library, WebSocket, authentication, or camera-streaming dependency.
- Keep browser HTTP access in `frontend/src/services/api.ts`; React components must not call `fetch` directly.
- Use an explicit CORS origin allowlist, never `*`, and do not enable credentials.
- Use Oxlint as the only JavaScript/TypeScript linter.
- Commit `frontend/package-lock.json`; ignore `node_modules`, build output, and real dotenv files.
- Test browser behavior without live network calls, webcam hardware, GUI, MPS, or GPU.

---

### Task 1: Add typed backend CORS configuration

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `src/smart_retail/config.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: existing `load_config(environ: Mapping[str, str] | None) -> AppConfig`
- Produces: `APIConfig.cors_allowed_origins: tuple[str, ...]`
- Produces environment variable: `SMART_RETAIL_API_CORS_ALLOWED_ORIGINS`

- [ ] **Step 1: Write failing configuration tests**

Extend the existing sensible-default test with:

```python
self.assertEqual(
    config.api.cors_allowed_origins,
    ("http://localhost:5173", "http://127.0.0.1:5173"),
)
```

Add the environment override to `test_environment_overrides_every_configuration_area`:

```python
"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": (
    "https://dashboard.example.test,http://localhost:4173"
),
```

and assert:

```python
self.assertEqual(
    config.api.cors_allowed_origins,
    ("https://dashboard.example.test", "http://localhost:4173"),
)
```

Add invalid-origin cases to `test_impossible_ranges_and_values_are_rejected`:

```python
(
    {"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": "*"},
    "CORS origin",
),
(
    {"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": "ftp://localhost:5173"},
    "http or https",
),
(
    {
        "SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": (
            "http://user:password@localhost:5173"
        )
    },
    "credentials",
),
(
    {"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": "http://localhost:5173/path"},
    "origin without a path",
),
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_config.py -q
```

Expected: failures report that `APIConfig` has no `cors_allowed_origins` field
and the new environment variable is not loaded.

- [ ] **Step 3: Implement minimal immutable origin configuration**

Add `urlsplit` to `src/smart_retail/config.py` and extend `APIConfig`:

```python
from urllib.parse import urlsplit

DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True, slots=True)
class APIConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    enabled: bool = True
    cors_allowed_origins: tuple[str, ...] = DEFAULT_CORS_ALLOWED_ORIGINS

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ConfigurationError("API host cannot be empty.")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("API port must be between 1 and 65535.")
        normalized_origins = tuple(
            _normalize_cors_origin(origin) for origin in self.cors_allowed_origins
        )
        if len(set(normalized_origins)) != len(normalized_origins):
            raise ConfigurationError("API CORS origins cannot contain duplicates.")
        object.__setattr__(self, "cors_allowed_origins", normalized_origins)
```

Add the focused validator:

```python
def _normalize_cors_origin(origin: str) -> str:
    candidate = origin.strip()
    if not candidate or candidate == "*":
        raise ConfigurationError("API CORS origin must be explicit, not empty or '*'.")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise ConfigurationError(f"API CORS origin is invalid: {candidate}.") from error
    if parsed.scheme not in {"http", "https"}:
        raise ConfigurationError("API CORS origin must use http or https.")
    if parsed.hostname is None:
        raise ConfigurationError("API CORS origin must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("API CORS origin cannot include credentials.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ConfigurationError(
            "API CORS origin must be an origin without a path, query, or fragment."
        )
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    authority = f"{host}:{port}" if port is not None else host
    return f"{parsed.scheme}://{authority}"
```

Load the environment value in `load_config`:

```python
cors_allowed_origins=_env_csv(
    environment,
    "API_CORS_ALLOWED_ORIGINS",
    DEFAULT_CORS_ALLOWED_ORIGINS,
),
```

Add this safe example under the existing API settings in `.env.example`:

```dotenv
SMART_RETAIL_API_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

- [ ] **Step 4: Run the focused tests and verify green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_config.py -q
```

Expected: all configuration tests pass.

- [ ] **Step 5: Commit the configuration slice**

```bash
git add src/smart_retail/config.py tests/unit/test_config.py .env.example
git commit -m "feat: configure frontend CORS origins"
```

---

### Task 2: Wire the explicit CORS allowlist into FastAPI

**Files:**
- Modify: `tests/integration/test_api.py`
- Modify: `src/smart_retail/api/factory.py`
- Modify: `src/smart_retail/app.py`
- Modify: `src/smart_retail/api/service.py`

**Interfaces:**
- Consumes: `APIConfig.cors_allowed_origins`
- Changes: `create_api_app(runtime, *, allowed_origins=(), lifespan=None) -> FastAPI`
- Preserves: every existing endpoint, response model, security header, and runtime protocol

- [ ] **Step 1: Write failing allowed-origin and hostile-origin tests**

In `tests/integration/test_api.py`, create a client with an explicit allowlist
inside each new test so the existing test fixture remains unchanged:

```python
def test_configured_frontend_origin_receives_cors_header(self) -> None:
    client = TestClient(
        create_api_app(
            self.runtime,
            allowed_origins=("http://localhost:5173",),
        )
    )
    try:
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
    finally:
        client.close()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(
        response.headers["access-control-allow-origin"],
        "http://localhost:5173",
    )


def test_unlisted_origin_receives_no_cors_permission(self) -> None:
    client = TestClient(
        create_api_app(
            self.runtime,
            allowed_origins=("http://localhost:5173",),
        )
    )
    try:
        response = client.get(
            "/health",
            headers={"Origin": "https://example.invalid"},
        )
    finally:
        client.close()

    self.assertEqual(response.status_code, 200)
    self.assertNotIn("access-control-allow-origin", response.headers)
```

Add a preflight contract for the configured read method:

```python
def test_configured_frontend_origin_can_preflight_health_get(self) -> None:
    client = TestClient(
        create_api_app(
            self.runtime,
            allowed_origins=("http://localhost:5173",),
        )
    )
    try:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    finally:
        client.close()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.headers["access-control-allow-methods"], "GET")
```

- [ ] **Step 2: Run the CORS tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_api.py -q -k cors
```

Expected: `create_api_app` rejects the unknown `allowed_origins` keyword.

- [ ] **Step 3: Add the minimal FastAPI middleware**

In `src/smart_retail/api/factory.py`, import `Sequence` and
`CORSMiddleware`, then extend the factory:

```python
from collections.abc import Callable, Sequence
from fastapi.middleware.cors import CORSMiddleware


def create_api_app(
    runtime: APIRuntime,
    *,
    allowed_origins: Sequence[str] = (),
    lifespan: Lifespan | None = None,
) -> FastAPI:
```

After assigning `application.state.runtime`, install middleware only when the
validated allowlist is non-empty:

```python
if allowed_origins:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept"],
    )
```

Pass configuration at the two real composition points:

```python
create_api_app(
    application,
    allowed_origins=config.api.cors_allowed_origins,
)
```

and:

```python
create_api_app(
    runtime,
    allowed_origins=runtime_config.api.cors_allowed_origins,
    lifespan=lifespan,
)
```

- [ ] **Step 4: Run focused API and lifecycle tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/integration/test_api.py \
  tests/integration/test_application.py \
  tests/integration/test_lifecycle.py \
  tests/integration/test_headless_service.py -q
```

Expected: all selected tests pass, including existing security-header and
application lifecycle assertions.

- [ ] **Step 5: Commit the API wiring slice**

```bash
git add src/smart_retail/api/factory.py src/smart_retail/app.py \
  src/smart_retail/api/service.py tests/integration/test_api.py
git commit -m "feat: allow configured frontend origin"
```

---

### Task 3: Scaffold the current Vite React TypeScript toolchain

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/.oxlintrc.json`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/src/setupTests.ts`
- Modify: `.gitignore`
- Modify: `.dockerignore`

**Interfaces:**
- Produces scripts: `npm run dev`, `npm run build`, `npm run preview`, `npm run lint`, `npm test`, `npm run test:watch`
- Produces Vitest environment: jsdom with `@testing-library/jest-dom`
- No application UI behavior is implemented in this task

- [ ] **Step 1: Generate the official current scaffold**

From the repository root, run:

```bash
npm create vite@9.2.0 frontend -- --template react-ts --no-interactive
```

Do not use an absolute project-name argument; `create-vite` treats its project
argument as repository-relative.

- [ ] **Step 2: Install and lock only the approved dependencies**

From `frontend/`, run:

```bash
npm install
npm install --save-exact react@19.2.8 react-dom@19.2.8 react-router@8.3.0
npm install --save-dev --save-exact \
  @testing-library/jest-dom@7.0.1 \
  @testing-library/react@16.3.2 \
  jsdom@30.0.1 \
  vitest@4.1.11
```

Retain the scaffold's Vite 8, TypeScript 6, React plugin, React types, Node
types, and Oxlint dependencies. Do not install ESLint.

- [ ] **Step 3: Add deterministic test configuration**

Keep the generated application intact until the route test in Task 6 provides
the failing behavior that replaces it. Replace `frontend/vite.config.ts` with:

Replace the generated `frontend/vite.config.ts` with:

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    clearMocks: true,
    restoreMocks: true,
  },
})
```

Create `frontend/src/setupTests.ts`:

```ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
```

Create `frontend/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

Add `"strict": true` to `compilerOptions` in both
`frontend/tsconfig.app.json` and `frontend/tsconfig.node.json`. Retain the
generated unused-local, unused-parameter, bundler-resolution, and no-emit
checks.

Update scripts in `frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "oxlint",
    "test": "vitest run",
    "test:watch": "vitest",
    "preview": "vite preview"
  }
}
```

- [ ] **Step 4: Extend artifact ignore policies**

Add these repository-level rules to `.gitignore`:

```gitignore
node_modules/
frontend/dist/
```

Add these build-context rules to `.dockerignore`:

```dockerignore
frontend/node_modules/
frontend/dist/
frontend/.env
frontend/.env.*
!frontend/.env.example
```

- [ ] **Step 5: Verify the generated toolchain boundary**

Run from `frontend/`:

```bash
npm run lint
npm run build
```

Expected: the current Vite-generated application passes Oxlint, TypeScript, and
the production build before custom application behavior begins.

- [ ] **Step 6: Commit the toolchain slice**

```bash
git add frontend .gitignore .dockerignore
git commit -m "build: add React frontend toolchain"
```

---

### Task 4: Build validated frontend configuration and API service with TDD

**Files:**
- Create: `frontend/.env.example`
- Create: `frontend/src/config.test.ts`
- Create: `frontend/src/config.ts`
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/services/api.test.ts`
- Create: `frontend/src/services/api.ts`

**Interfaces:**
- Produces: `resolveApiBaseUrl(value?: string): string`
- Produces: immutable `appConfig.apiBaseUrl: string`
- Produces: `HealthResponse`
- Produces: `getHealth(signal?: AbortSignal): Promise<HealthResponse>`
- Produces: `ApiError`

- [ ] **Step 1: Write failing URL configuration tests**

Create `frontend/src/config.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { resolveApiBaseUrl } from './config'

describe('resolveApiBaseUrl', () => {
  it('uses the documented local development default', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('http://localhost:8000')
  })

  it('normalizes whitespace and a trailing slash', () => {
    expect(resolveApiBaseUrl(' https://api.example.test/ ')).toBe(
      'https://api.example.test',
    )
  })

  it.each([
    'not-a-url',
    'ftp://localhost:8000',
    'http://user:secret@localhost:8000',
    'http://localhost:8000/api',
    'http://localhost:8000?debug=true',
  ])('rejects an unsafe API base URL: %s', (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow('VITE_API_BASE_URL')
  })
})
```

- [ ] **Step 2: Run the configuration test and verify red**

Run from `frontend/`:

```bash
npm test -- src/config.test.ts
```

Expected: the test fails because `src/config.ts` does not exist.

- [ ] **Step 3: Implement the minimal validated configuration**

Create `frontend/src/config.ts`:

```ts
const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export function resolveApiBaseUrl(value: string | undefined): string {
  const candidate = value?.trim() || DEFAULT_API_BASE_URL
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    throw new Error('VITE_API_BASE_URL must be a valid absolute URL.')
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('VITE_API_BASE_URL must use HTTP or HTTPS.')
  }
  if (parsed.username || parsed.password) {
    throw new Error('VITE_API_BASE_URL cannot contain credentials.')
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('VITE_API_BASE_URL must contain an origin without a path.')
  }
  return parsed.origin
}

export const appConfig = Object.freeze({
  apiBaseUrl: resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
})
```

Create `frontend/.env.example`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 4: Run the configuration test and verify green**

```bash
npm test -- src/config.test.ts
```

Expected: all URL cases pass.

- [ ] **Step 5: Write failing API service tests**

Create `frontend/src/services/api.test.ts` with a fetch boundary stub:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, getHealth } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('getHealth', () => {
  it('returns the typed backend liveness response', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', uptime_seconds: 12.5 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getHealth()).resolves.toEqual({
      status: 'ok',
      uptime_seconds: 12.5,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('rejects a non-success response without exposing its body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response('internal detail', { status: 503 }),
      ),
    )

    const request = getHealth()
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toEqual(
      expect.objectContaining({
        message: 'Backend request failed.',
        statusCode: 503,
      }),
    )
  })

  it('rejects malformed liveness data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok', uptime_seconds: 'fast' }), {
          status: 200,
        }),
      ),
    )

    await expect(getHealth()).rejects.toThrow('invalid health data')
  })
})
```

- [ ] **Step 6: Run the API test and verify red**

```bash
npm test -- src/services/api.test.ts
```

Expected: the test fails because `src/services/api.ts` does not exist.

- [ ] **Step 7: Implement the typed API boundary**

Create `frontend/src/types/api.ts`:

```ts
export interface HealthResponse {
  status: string
  uptime_seconds: number
}
```

Create `frontend/src/services/api.ts`:

```ts
import { appConfig } from '../config'
import type { HealthResponse } from '../types/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly statusCode?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return (
    typeof record.status === 'string' &&
    typeof record.uptime_seconds === 'number' &&
    Number.isFinite(record.uptime_seconds) &&
    record.uptime_seconds >= 0
  )
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${appConfig.apiBaseUrl}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new ApiError('Backend request failed.', response.status)
  }

  const payload: unknown = await response.json()
  if (!isHealthResponse(payload)) {
    throw new ApiError('Backend returned invalid health data.')
  }
  return payload
}
```

- [ ] **Step 8: Run service tests and commit**

```bash
npm test -- src/config.test.ts src/services/api.test.ts
git add frontend/.env.example frontend/src/config.ts \
  frontend/src/config.test.ts frontend/src/types/api.ts \
  frontend/src/services/api.ts frontend/src/services/api.test.ts
git commit -m "feat: add typed frontend health client"
```

Expected: all configuration and API service tests pass.

---

### Task 5: Implement loading, connected, and unavailable Dashboard states

**Files:**
- Create: `frontend/src/hooks/useBackendHealth.ts`
- Create: `frontend/src/components/DashboardCard.tsx`
- Create: `frontend/src/components/ConnectionStatus.tsx`
- Create: `frontend/src/pages/DashboardPage.test.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`

**Interfaces:**
- Produces: discriminated `BackendHealthState`
- Produces: `useBackendHealth() -> BackendHealthState`
- Consumes: `getHealth(signal)`
- Produces visible copy: `Checking backend...`, `Backend Connected`, `Backend Unavailable`, and `Unable to connect to backend.`

- [ ] **Step 1: Write failing Dashboard state tests**

Create `frontend/src/pages/DashboardPage.test.tsx` using the real hook and API
service with only `fetch` mocked:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from './DashboardPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DashboardPage backend connection', () => {
  it('shows a loading state while health is pending', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Checking backend...')).toBeInTheDocument()
  })

  it('shows Backend Connected after a successful health response', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', uptime_seconds: 4.2 }), {
        status: 200,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Backend Connected')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows a friendly unavailable state when fetch fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Backend Unavailable')).toBeInTheDocument()
    expect(screen.getByText('Unable to connect to backend.')).toBeInTheDocument()
  })

  it('aborts the pending health request when unmounted', () => {
    let requestSignal: AbortSignal | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((_input, init) => {
        requestSignal = init?.signal ?? null
        return new Promise<Response>(() => undefined)
      }),
    )

    const view = render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
    expect(requestSignal).not.toBeNull()

    view.unmount()

    expect(requestSignal?.aborted).toBe(true)
  })
})
```

- [ ] **Step 2: Run the Dashboard test and verify red**

```bash
npm test -- src/pages/DashboardPage.test.tsx
```

Expected: failure because `DashboardPage` and its state components do not
exist.

- [ ] **Step 3: Implement the hook and reusable cards**

Create `frontend/src/hooks/useBackendHealth.ts`:

```ts
import { useEffect, useState } from 'react'

import { getHealth } from '../services/api'
import type { HealthResponse } from '../types/api'

export type BackendHealthState =
  | { status: 'loading' }
  | { status: 'connected'; health: HealthResponse }
  | { status: 'unavailable' }

export function useBackendHealth(): BackendHealthState {
  const [state, setState] = useState<BackendHealthState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void getHealth(controller.signal)
      .then((health) => {
        if (!controller.signal.aborted) {
          setState({ status: 'connected', health })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        console.warn('Backend health request failed.', error)
        setState({ status: 'unavailable' })
      })
    return () => controller.abort()
  }, [])

  return state
}
```

Create `frontend/src/components/DashboardCard.tsx`:

```tsx
import type { ReactNode } from 'react'

interface DashboardCardProps {
  title: string
  eyebrow?: string
  children: ReactNode
}

export function DashboardCard({ title, eyebrow, children }: DashboardCardProps) {
  return (
    <section className="dashboard-card">
      <div className="dashboard-card__heading">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
      </div>
      <div className="dashboard-card__content">{children}</div>
    </section>
  )
}
```

Create `frontend/src/components/ConnectionStatus.tsx`:

```tsx
import type { BackendHealthState } from '../hooks/useBackendHealth'

interface ConnectionStatusProps {
  state: BackendHealthState
}

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  const content =
    state.status === 'loading'
      ? {
          label: 'Checking backend...',
          detail: 'Waiting for the local FastAPI service.',
        }
      : state.status === 'connected'
        ? {
            label: 'Backend Connected',
            detail: 'FastAPI is responding.',
          }
        : {
            label: 'Backend Unavailable',
            detail: 'Unable to connect to backend.',
          }

  return (
    <div
      className={`connection-status connection-status--${state.status}`}
      role="status"
      aria-live="polite"
    >
      <span className="connection-status__dot" aria-hidden="true" />
      <div>
        <strong>{content.label}</strong>
        <p>{content.detail}</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Implement the Phase 1 Dashboard**

Create `frontend/src/pages/DashboardPage.tsx` with one `h1`, the approved
description, and a four-card grid:

```tsx
import { ConnectionStatus } from '../components/ConnectionStatus'
import { DashboardCard } from '../components/DashboardCard'
import { useBackendHealth } from '../hooks/useBackendHealth'

export function DashboardPage() {
  const backendHealth = useBackendHealth()
  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Operations overview</p>
        <h1>Smart Retail Checkout</h1>
        <p>Realtime cashierless checkout monitoring dashboard</p>
      </header>
      <div className="dashboard-grid">
        <DashboardCard title="Current Cart">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
        <DashboardCard title="System Status">
          <ConnectionStatus state={backendHealth} />
        </DashboardCard>
        <DashboardCard title="Recent Events">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
        <DashboardCard title="Live Metrics">
          <p className="empty-copy">No data loaded yet</p>
        </DashboardCard>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Run Dashboard and API tests and verify green**

```bash
npm test -- src/pages/DashboardPage.test.tsx src/services/api.test.ts
```

Expected: all loading, success, failure, and service tests pass without React
act warnings.

- [ ] **Step 6: Commit the Dashboard state slice**

```bash
git add frontend/src/hooks frontend/src/components frontend/src/pages/DashboardPage*
git commit -m "feat: show backend connection status"
```

---

### Task 6: Add routing, application shell, responsive CSS, and entrypoint

**Files:**
- Create: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/layouts/AppLayout.tsx`
- Create: `frontend/src/pages/SessionsPage.tsx`
- Create: `frontend/src/pages/SystemPage.tsx`
- Create: `frontend/src/pages/NotFoundPage.tsx`
- Create: `frontend/src/styles/global.css`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/index.html`
- Delete: `frontend/src/App.css`
- Delete: `frontend/src/index.css`
- Move out of workspace: `frontend/src/assets/`
- Move out of workspace: `frontend/public/`

**Interfaces:**
- Produces routes: `/`, `/sessions`, `/system`, and `*`
- Produces semantic navigation with active and focus-visible states
- Consumes: `DashboardPage`

- [ ] **Step 1: Write failing route and navigation tests**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

afterEach(() => vi.unstubAllGlobals())

function renderRoute(route: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)),
  )
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  )
}

describe('application routing', () => {
  it.each([
    ['/', 'Smart Retail Checkout'],
    ['/sessions', 'Checkout Sessions'],
    ['/system', 'System'],
  ])('renders %s', (route, heading) => {
    renderRoute(route)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('renders a useful Not Found page', () => {
    renderRoute('/missing')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to Dashboard' })).toHaveAttribute(
      'href',
      '/',
    )
  })

  it('marks the active navigation link', () => {
    renderRoute('/sessions')
    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
```

- [ ] **Step 2: Run the routing test and verify red**

```bash
npm test -- src/App.test.tsx
```

Expected: assertions fail because the generated Vite demo does not implement
the approved routes or page headings.

- [ ] **Step 3: Implement declarative routing and page shells**

Move the generated static demo directories to a recoverable temporary location:

```bash
vite_starter_archive=$(mktemp -d /tmp/smart-retail-vite-starter.XXXXXX)
mv frontend/src/assets "$vite_starter_archive/assets"
mv frontend/public "$vite_starter_archive/public"
```

Use `apply_patch` to delete `frontend/src/App.css` and
`frontend/src/index.css`. Replace `frontend/src/App.tsx` with nested routes
beneath `AppLayout`:

```tsx
import { Route, Routes } from 'react-router'

import { AppLayout } from './layouts/AppLayout'
import { DashboardPage } from './pages/DashboardPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SessionsPage } from './pages/SessionsPage'
import { SystemPage } from './pages/SystemPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
```

Create `frontend/src/layouts/AppLayout.tsx`:

```tsx
import { NavLink, Outlet } from 'react-router'

const navigation = [
  { label: 'Dashboard', to: '/' },
  { label: 'Sessions', to: '/sessions' },
  { label: 'System', to: '/system' },
]

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <header className="brand-block">
          <span className="brand-mark" aria-hidden="true">SR</span>
          <div>
            <p className="brand-name">Smart Retail Checkout</p>
            <p className="brand-caption">Operations console</p>
          </div>
        </header>
        <nav aria-label="Primary navigation" className="primary-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `nav-link${isActive ? ' nav-link--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
```

Create `frontend/src/pages/SessionsPage.tsx`:

```tsx
export function SessionsPage() {
  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Checkout history</p>
        <h1>Checkout Sessions</h1>
        <p>Session history will be connected in a later frontend phase.</p>
      </header>
      <section className="dashboard-card">
        <h2>Sessions</h2>
        <p className="empty-copy">No data loaded yet</p>
      </section>
    </div>
  )
}
```

Create `frontend/src/pages/SystemPage.tsx`:

```tsx
export function SystemPage() {
  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">Runtime overview</p>
        <h1>System</h1>
        <p>Detailed readiness and metrics will be connected in a later phase.</p>
      </header>
      <section className="dashboard-card">
        <h2>System details</h2>
        <p className="empty-copy">No data loaded yet</p>
      </section>
    </div>
  )
}
```

Create `frontend/src/pages/NotFoundPage.tsx`:

```tsx
import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <div className="page-stack">
      <header className="page-heading">
        <p className="eyebrow">404</p>
        <h1>Page not found</h1>
        <p>The requested operator-dashboard page does not exist.</p>
      </header>
      <Link className="text-link" to="/">Return to Dashboard</Link>
    </div>
  )
}
```

- [ ] **Step 4: Implement the browser entrypoint without StrictMode**

Replace `frontend/src/main.tsx` with:

```tsx
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import './styles/global.css'

const root = document.getElementById('root')
if (root === null) {
  throw new Error('Application root element was not found.')
}

createRoot(root).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
)
```

Set the HTML title to `Smart Retail Checkout` in `frontend/index.html`.

- [ ] **Step 5: Add responsive, accessible plain CSS**

Create `frontend/src/styles/global.css`:

```css
:root {
  color-scheme: dark;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
  color: #f3f5f4;
  background: #0d1110;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  --background: #0d1110;
  --surface: #141a18;
  --surface-raised: #19211e;
  --border: #2a3531;
  --text: #f3f5f4;
  --muted: #9ba8a3;
  --healthy: #45c486;
  --unavailable: #ef7070;
  --focus: #8de8b9;
}

* {
  box-sizing: border-box;
}

html {
  min-width: 320px;
  background: var(--background);
}

body {
  min-width: 320px;
  min-height: 100vh;
  margin: 0;
  background: var(--background);
  color: var(--text);
}

button,
a {
  font: inherit;
}

a {
  color: inherit;
}

a:focus-visible,
button:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}

p,
h1,
h2 {
  overflow-wrap: anywhere;
}

.app-shell {
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 1.5rem 1rem;
  border-right: 1px solid var(--border);
  background: #101513;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem;
}

.brand-mark {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  place-items: center;
  border: 1px solid #38634e;
  border-radius: 0.75rem;
  color: var(--healthy);
  background: #17231e;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.brand-name,
.brand-caption,
.eyebrow,
.connection-status p,
.page-heading p,
.empty-copy {
  margin: 0;
}

.brand-name {
  font-size: 0.9rem;
  font-weight: 700;
}

.brand-caption {
  margin-top: 0.2rem;
  color: var(--muted);
  font-size: 0.75rem;
}

.primary-nav {
  display: grid;
  gap: 0.35rem;
  margin-top: 2rem;
}

.nav-link {
  padding: 0.75rem 0.9rem;
  border: 1px solid transparent;
  border-radius: 0.6rem;
  color: var(--muted);
  text-decoration: none;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.nav-link:hover {
  color: var(--text);
  background: var(--surface);
}

.nav-link--active {
  border-color: var(--border);
  color: var(--text);
  background: var(--surface-raised);
}

.main-content {
  min-width: 0;
  padding: clamp(1.5rem, 4vw, 3.5rem);
}

.page-stack {
  display: grid;
  gap: 2rem;
  width: min(100%, 76rem);
  margin: 0 auto;
}

.page-heading {
  display: grid;
  gap: 0.65rem;
}

.page-heading h1 {
  margin: 0;
  font-size: clamp(2rem, 5vw, 3.5rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.page-heading > p:last-child {
  max-width: 44rem;
  color: var(--muted);
  line-height: 1.7;
}

.eyebrow {
  color: var(--healthy);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.dashboard-card {
  min-height: 12rem;
  padding: 1.25rem;
  border: 1px solid var(--border);
  border-radius: 0.9rem;
  background: var(--surface);
}

.dashboard-card h2 {
  margin: 0;
  font-size: 1rem;
}

.dashboard-card__heading {
  display: grid;
  gap: 0.4rem;
}

.dashboard-card__content {
  margin-top: 2.5rem;
}

.empty-copy {
  color: var(--muted);
}

.connection-status {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.connection-status__dot {
  width: 0.65rem;
  height: 0.65rem;
  margin-top: 0.3rem;
  border-radius: 50%;
  background: var(--muted);
}

.connection-status strong {
  display: block;
}

.connection-status p {
  margin-top: 0.35rem;
  color: var(--muted);
  line-height: 1.5;
}

.connection-status--connected .connection-status__dot {
  background: var(--healthy);
}

.connection-status--connected strong {
  color: var(--healthy);
}

.connection-status--unavailable .connection-status__dot {
  background: var(--unavailable);
}

.connection-status--unavailable strong {
  color: var(--unavailable);
}

.text-link {
  width: fit-content;
  color: var(--healthy);
  font-weight: 700;
}

@media (max-width: 900px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    display: flex;
    height: auto;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .primary-nav {
    display: flex;
    flex-wrap: wrap;
    margin-top: 0;
  }
}

@media (max-width: 640px) {
  .sidebar {
    align-items: flex-start;
    flex-direction: column;
  }

  .main-content {
    padding: 1.25rem;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-link {
    transition: none;
  }
}
```

- [ ] **Step 6: Run route, Dashboard, lint, and build checks**

```bash
npm test
npm run lint
npm run build
```

Expected: all frontend tests pass, Oxlint reports no findings, TypeScript is
strictly valid, and Vite creates `frontend/dist/`.

- [ ] **Step 7: Commit the shell slice**

```bash
git add frontend/src frontend/index.html
git commit -m "feat: add retail operations dashboard shell"
```

---

### Task 7: Document the frontend and corrected CORS posture

**Files:**
- Create: `frontend/README.md`
- Modify: `README.md`
- Modify: `docs/API.md`
- Modify: `docs/SECURITY.md`

**Interfaces:**
- Documents separate native backend/computer-vision and React frontend commands
- Documents `VITE_API_BASE_URL` and `SMART_RETAIL_API_CORS_ALLOWED_ORIGINS`
- Preserves the local trusted-machine security limitation

- [ ] **Step 1: Write `frontend/README.md`**

Document:

- Node.js 22.12 or newer compatible release;
- `cd frontend` and `npm ci`;
- `cp .env.example .env` as optional local setup;
- `VITE_API_BASE_URL=http://localhost:8000`;
- backend startup using `smart-retail` for shared webcam state or
  `smart-retail-api` for hardware-free API development;
- `npm run dev`, `npm test`, `npm run lint`, `npm run build`, and
  `npm run preview`;
- routes `/`, `/sessions`, and `/system`;
- only `/health` is connected in Phase 1;
- a real `.env` is local and must not be committed.

- [ ] **Step 2: Make the minimal root README updates**

Add:

- React, Vite, TypeScript, React Router, and Oxlint to the technology list;
- `frontend/` to the structure tree;
- a short `Frontend` section with separate backend and frontend terminal
  commands;
- `SMART_RETAIL_API_CORS_ALLOWED_ORIGINS` to the configuration table;
- an explicit statement that Phase 1 reads only `/health` and does not replace
  the OpenCV interface.

Do not restructure unrelated README sections.

- [ ] **Step 3: Correct API and security documentation**

Replace statements that CORS is disabled with the exact new posture:

- only configured local development origins are allowed;
- defaults are `http://localhost:5173` and `http://127.0.0.1:5173`;
- credentials are disabled;
- only `GET` is allowed cross-origin in Phase 1;
- unlisted origins receive no permission;
- this does not make the unauthenticated API safe for public exposure.

- [ ] **Step 4: Verify documentation and artifact contracts**

Run:

```bash
rg -n "VITE_API_BASE_URL|API_CORS_ALLOWED_ORIGINS|npm run dev" \
  README.md frontend/README.md docs/API.md docs/SECURITY.md .env.example \
  frontend/.env.example
git check-ignore --no-index frontend/.env frontend/node_modules/index.js \
  frontend/dist/index.html
git diff --check
```

Expected: both environment variables and run commands are documented, local
artifacts are ignored, and no whitespace errors exist.

- [ ] **Step 5: Commit the documentation slice**

```bash
git add README.md frontend/README.md docs/API.md docs/SECURITY.md
git commit -m "docs: add frontend development guide"
```

---

### Task 8: Run complete Phase 1 verification

**Files:**
- Verify only; modify files only if a failing check reveals a scoped defect

**Interfaces:**
- Verifies frontend online/offline state, build, routes, and development server
- Verifies backend CORS, existing deterministic behavior, and clean repository state

- [ ] **Step 1: Perform a clean frontend installation**

Move the existing `frontend/node_modules` directory to a temporary directory
rather than deleting it, then run from `frontend/`:

```bash
npm ci
npm ls --depth=0
```

Expected: dependency installation succeeds from `package-lock.json` and no
invalid direct dependency is reported.

- [ ] **Step 2: Run all frontend quality gates**

```bash
npm test
npm run lint
npm run build
```

Expected: all tests pass, Oxlint is clean, TypeScript emits no errors, and the
production Vite build completes.

- [ ] **Step 3: Verify the bounded development server**

Start the frontend from `frontend/` on a non-conflicting loopback port:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

In a second command, verify:

```bash
curl --fail --silent --show-error http://127.0.0.1:5173/
curl --fail --silent --show-error http://127.0.0.1:5173/sessions
curl --fail --silent --show-error http://127.0.0.1:5173/system
```

Use browser verification to confirm the shell renders, navigation changes
pages, focus is visible, the tablet layout does not overflow, and the backend
offline state is friendly. Stop the development server normally afterward.

- [ ] **Step 4: Verify backend-online connectivity and CORS**

Start the hardware-free backend in a separate process:

```bash
.venv/bin/smart-retail-api
```

Verify the real response and configured origin:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error --include \
  -H 'Origin: http://localhost:5173' \
  http://127.0.0.1:8000/health
```

Refresh the Dashboard once and verify `Backend Connected`. Confirm one health
request in the browser network panel. Stop the headless backend normally.

- [ ] **Step 5: Run focused and complete backend verification**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_config.py \
  tests/integration/test_api.py \
  tests/integration/test_application.py \
  tests/integration/test_headless_service.py \
  tests/integration/test_lifecycle.py -q

.venv/bin/python -m ruff check app.py src tests training
.venv/bin/python -m ruff format --check app.py src tests training
.venv/bin/python -m pytest -q --cov=smart_retail --cov-branch \
  --cov-report=term --cov-fail-under=85
```

Expected: focused tests, Ruff, full deterministic backend suite, and the 85%
coverage threshold pass without webcam, GUI, MPS, GPU, or YOLO inference.

- [ ] **Step 6: Inspect final scope and status**

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
git diff --check origin/main...HEAD
```

Confirm no computer-vision, tracking, checkout, cart, database, metrics, or
OpenCV implementation file changed. Confirm generated `node_modules`, `dist`,
real `.env`, local database, and model files are absent from Git status.
