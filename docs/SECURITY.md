# Security

## Threat model

Smart Retail Checkout is a local, single-user portfolio application. Its default
trust boundary is one developer account on one machine:

- API clients are expected to be local and trusted.
- Environment variables and configuration files are operator-controlled input.
- Query and path parameters received over HTTP are untrusted input.
- Webcam frames stay in process and are not exposed by the API or written to
  SQLite.

The current design does not attempt to protect against a compromised local user,
a compromised Python dependency, or hostile clients on a public network. The
API must not be exposed directly to the internet.

## Safeguards

### Configuration and secrets

- The API binds to `127.0.0.1` by default. A non-loopback bind emits the
  `api_externally_reachable` warning because no authentication is present.
- `.env`, `.env.local`, `.env.production`, and other `.env.*` variants are
  ignored by Git. `.env.example` is the only exception and contains
  non-sensitive development defaults.
- The application does not automatically load dotenv files. Values are supplied
  explicitly by the launching shell or container runtime.
- Startup validation rejects empty hosts and paths, invalid ports, negative
  camera indices, invalid probability thresholds, and impossible zone bounds.
- The safe startup summary reports operational settings and file names only; it
  does not dump the environment or configuration-file contents.

There are currently no passwords, tokens, credentials, or API keys required by
the application. If a future integration requires one, its value must stay in
an ignored local file or deployment secret store and must never be added to
`.env.example`.

### API

- FastAPI and Pydantic validate all exposed query and path parameters.
- History limits are bounded (`events` at 200 and `sessions` at 100), and session
  IDs must be positive integers.
- The API has no file upload, file download, arbitrary query, command execution,
  model-loading, or video-streaming endpoint.
- Central exception handlers return stable error codes and generic messages.
  Unexpected exception details and Python tracebacks are logged server-side,
  never returned to clients.
- Responses include `X-Content-Type-Options: nosniff` and
  `Cache-Control: no-store`.
- State-changing reset uses `POST`; `GET /api/v1/cart/reset` is rejected.
- CORS permits only the configured origins in
  `SMART_RETAIL_API_CORS_ALLOWED_ORIGINS`. The local defaults are
  `http://localhost:5173` and `http://127.0.0.1:5173`; wildcard origins are
  rejected during configuration validation. CORS credentials are disabled and
  the method allowlist rejects non-`GET` browser preflight requests. The Phase 1
  frontend only calls `GET /health`. CORS governs whether browser JavaScript may
  read a response; it is not authentication, authorization, or a server-side
  method firewall. A simple cross-origin `POST` may still reach reset, and
  command-line or other non-browser clients do not enforce CORS. An unlisted
  browser origin normally cannot read the response.

No current endpoint accepts a request body. Request-size middleware would add
complexity without protecting a body-consuming route. A future upload or
write API must add explicit body limits at both the reverse proxy and
application boundary.

### Reset endpoint

`POST /api/v1/cart/reset` intentionally remains unauthenticated for the local
demo. It calls the same synchronized application service used by the keyboard
reset; it does not duplicate or bypass cart rules. Any process that can reach
the API can reset the active cart. This includes a simple cross-origin browser
request even though non-`GET` preflight requests are rejected. That exposure is
acceptable only under the local, trusted-client threat model.

Binding the API to `0.0.0.0`, a LAN address, or another externally reachable
interface expands the threat boundary. The startup warning makes that change
visible, but does not make it secure. The explicit local CORS allowlist does
not make this unauthenticated API safe for public exposure.

### SQLite and filesystem

- SQL statements are application-owned. Runtime values use SQLite parameters;
  HTTP clients cannot supply arbitrary SQL.
- Schema creation and the schema-version pragma use fixed source constants, not
  request data.
- Writes use SQLite transaction contexts. A failed event write rolls back and
  is logged. Native webcam mode disables persistence for the remainder of that
  run; headless API mode marks readiness unavailable and returns a safe `503`.
- Database, log, model, tracker, product-catalog, and training paths come only
  from trusted startup configuration. No API parameter is converted into a
  filesystem path.
- Local databases, sidecar files, logs, downloaded weights, datasets, caches,
  and training outputs are excluded from Git and the Docker build context.

Operator-configured paths are deliberately not sandboxed: a local developer may
place a database or model outside the repository. This is safe only because the
operator environment is inside the stated trust boundary. Do not map untrusted
HTTP input into these configuration values.

### Logging and webcam privacy

Logs use explicitly selected structured fields. They include event names,
track IDs, product names, quantities, totals, component states, and exception
types where operationally useful. They do not include:

- environment dumps or credentials;
- request bodies or full request headers;
- YOLO tensors or raw detector results;
- webcam frames or encoded images.

Unexpected failures retain server-side tracebacks for diagnosis. Rotating file
logs are optional; console output remains the default and is appropriate for
containers.

### Dependencies

`pyproject.toml` is the single dependency declaration. The base API runtime and
optional vision/development dependencies are separated and exactly pinned.
Every declared direct package has an application, vision, testing, or tooling
responsibility; no unused direct package was identified during this review.

This phase does not perform automatic major-version upgrades or claim a live
CVE audit. Dependency upgrades should be reviewed, installed in an isolated
environment, and validated with Ruff, the deterministic test suite, the Docker
build, and the manual webcam smoke test. A public deployment should add an
automated advisory scanner and a regular patching policy.

## Known limitations

- There is no authentication, authorization, user identity, rate limiting, or
  audit identity for reset calls.
- Swagger UI, ReDoc, OpenAPI, cart state, metrics, and checkout history are
  visible to every client that can reach the API.
- HTTP is unencrypted. Loopback traffic is assumed; TLS termination is absent.
- Security headers are intentionally minimal. HSTS is inappropriate for this
  local HTTP service, and a strict browser content-security policy would need
  explicit testing with Swagger UI.
- SQLite files and optional log files use the permissions of the launching OS
  account; application-level encryption is not provided.
- Pinned versions improve reproducibility but still require periodic advisory
  review.

## Public or cloud deployment

Before exposing this service beyond a trusted local machine:

1. Put it behind TLS and a hardened reverse proxy or managed ingress.
2. Add authentication and authorization, especially for cart reset and history.
3. Disable or protect API documentation outside development.
4. Configure an explicit allowlist of browser origins only if a browser client
   needs CORS; never combine wildcard origins with credentials.
5. Add proxy and application request-size limits, rate limiting, and timeouts.
6. Store credentials in a deployment secret manager and redact sensitive log
   fields.
7. Restrict database/model paths and container filesystem permissions.
8. Add automated dependency, secret, container-image, and source scanning.
9. Define retention, deletion, backup, and privacy policies for checkout data.
10. Revisit SQLite if concurrent writers, replicas, or multi-instance service
    operation become requirements.

These changes are intentionally outside the current local-demo scope.
