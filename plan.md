# Slack Proxy Project Plan

## Goal
Build a backend proxy between clients and Slack that supports channel lookup and creation while persisting workspace channel metadata in SQLite.

## Scope
- Proxy endpoints for fetching and creating Slack channels.
- SQLite persistence for workspace channel records.
- Per-request workspace resolution from Slack bearer token.
- Background Slack sync trigger with SQLite lock table for existing-channel create conflicts.
- Local Docker-based development and test workflow.

## Milestones

### 1) Project bootstrap
- Create FastAPI app structure, config management, and health endpoint.
- Wire SQLite and Slack client configs.
- Add Dockerfile and docker-compose service (`app`).

### 2) Slack integration layer
- Implement Slack API client wrappers:
  - list channels
  - get channel by name
  - create channel
- Standardize Slack errors into internal exceptions.

### 3) Persistence layer
- Implement SQLite helpers for:
  - get channel by workspace + normalized name
  - upsert channel records
  - channel count by workspace
  - sync lock acquisition/release with stale lock window

### 4) Channel endpoints
- `GET /channels/{name}` behavior:
  - serve only from local SQLite cache
  - return 404 on cache miss
  - do not call Slack during request lookup
- `POST /channels` behavior:
  - attempt Slack create
  - if Slack returns already-exists: queue background Slack sync when lock is available
  - background sync lock can be reacquired when lock is stale (>10 minutes)
  - return cached id when present, otherwise return sync pending/in-progress source

### 5) Security and docs protection
- Add basic auth middleware/dependency for `/docs` and `/openapi.json`.

### 6) Observability
- Add structured logs for local DB lookup and Slack API outcomes.

### 7) Testing
- Unit tests for Slack client, SQLite CRUD helpers, and endpoint logic.
- Integration tests for success and existing-channel-create path.
- Smoke test with docker-compose stack.

## Initial Task Breakdown With Test Cases

### Task A: Config and app skeleton
- Deliverables:
  - `app/main.py`, `app/core/settings.py`, dependency wiring.
- Test cases:
  - app starts with required env vars.
  - health endpoint returns 200.

### Task B: GET channel proxy
- Deliverables:
  - endpoint + service + SQLite read/write.
- Test cases:
  - local DB hit returns without Slack call.
  - local DB miss returns 404.
  - request requires `Authorization: Bearer <token>`.

## Feature Plan: `get_channel_by_name`

### Objective
Implement `GET /channels/{name}` so it resolves workspace from bearer token and returns channel metadata strictly from SQLite for that workspace.

### Subtasks

#### B1) Route contract and dependency wiring
- Add dependencies in `app/api/routes.py`:
  - DB session via `get_db`.
  - bearer token extraction from `Authorization` header.
- Define response and errors:
  - `200` with `ChannelResponse`.
  - `404` when channel cannot be found locally.
  - `401` when token is missing/invalid or workspace cannot be resolved.
- Test cases:
  - route returns `200` schema with `id`, `name`, `source`.
  - route returns `404` for non-existent channel in local cache.

#### B2) Channel-name normalization
- Add a shared helper in `app/utils` for normalizing lookup names (trim + lowercase) used by local lookup and Slack comparisons.
- Ensure CRUD and route use consistent normalized name inputs.
- Test cases:
  - `"General"`, `" general "`, and `"GENERAL"` resolve to same lookup key.

#### B3) Local-first lookup path
- Read channel from `workspace_channels` by `workspace_id` + normalized name.
- If found, return response with `source="db"`.
- If missing, return not found from service/route path.
- Test cases:
  - DB hit path returns stored `channel_id`.
  - request lookup does not call Slack.

#### B4) Workspace resolution path
- Resolve workspace per request by calling Slack `auth.test` with the bearer token.
- Ensure lookup and create both use the resolved workspace id.
- Test cases:
  - valid token resolves workspace id and scopes DB reads correctly.
  - invalid Slack token returns 401.
  - Slack upstream failures return 502.

#### B5) Documentation and flow alignment
- Confirm flow in `flow.md` reflects token-based workspace resolution and DB-only reads.
- Update API docs examples to show `source="db"` for reads.
- Test cases:
  - OpenAPI includes endpoint and response examples.

### Acceptance Criteria
- `GET /channels/{name}` is DB-only and never falls back to Slack at request time.
- Workspace id is resolved per request using Slack bearer token.
- Error semantics are deterministic (`404` on cache miss).
- Endpoint behavior and workspace resolution path are covered by automated tests.

## Feature Plan: Slack 429 Retry

### Objective
Handle Slack `429 Too Many Requests` responses by retrying with bounded attempts before surfacing an upstream failure.

### Subtasks

#### R1) Add 429 retry loop in Slack client
- Detect HTTP `429` in `SlackClient._request`.
- Read `Retry-After` header when present; otherwise use a default delay.
- Retry with a fixed maximum attempt count to avoid infinite loops.
- Test cases:
  - first `429`, second `200` returns successful payload.
  - repeated `429` responses stop at max retries and raise `SlackUpstreamError`.

#### R2) Logging and observability updates
- Log each rate-limit retry attempt with delay and remaining retries.
- Include total attempts in final request log event.
- Test cases:
  - request retry path is exercised by unit tests for reliable behavior.

## Feature Plan: Slack SDK Migration

### Objective
Use the official Python Slack SDK (`slack_sdk.WebClient`) with built-in rate-limit retry handling and explicit SSL context wiring.

### Subtasks

#### S1) Replace custom HTTP client with Slack SDK
- Migrate `SlackClient` internals from custom `httpx` requests to `WebClient.api_call`.
- Preserve existing domain exceptions (`SlackUnauthorizedError`, `SlackChannelExistsError`, `SlackUpstreamError`).
- Test cases:
  - successful SDK payload is returned as a dict.
  - Slack API errors map to project exceptions.

#### S2) Configure retry and SSL behavior
- Configure `RateLimitErrorRetryHandler(max_retry_count=5)` on SDK client.
- Set `ssl_context = None` and pass it to SDK client as `ssl`.
- Test cases:
  - SDK client is created with `ssl=None`.
  - retry handler is attached with max retry count set to `5`.

### Task C: POST create channel proxy
- Deliverables:
  - endpoint + service using Slack create flow and background sync lock.
- Test cases:
  - new channel created and persisted in SQLite.
  - existing-channel error triggers background sync when lock is free.
  - existing-channel error does not queue extra tasks while lock is active.
  - stale lock older than 10 minutes can be reacquired.

### Task D: Docs protection
- Deliverables:
  - basic auth guard for docs/openapi routes.
- Test cases:
  - unauthorized docs access returns 401.
  - authorized docs access returns 200.

### Task E: Docker and CI-ready test loop
- Deliverables:
  - compose stack + test command documentation.
- Test cases:
  - stack boots without startup errors.
  - `pytest` passes in containerized run.

## Feature Plan: Upstream Error Transparency

### Objective
Return actionable upstream failure details to clients for `502` responses on channel endpoints.

### Subtasks

#### U1) Route error detail propagation
- Include the original `SlackUpstreamError` message in `HTTP 502` details for:
  - `GET /channels/{name}`
  - `POST /channels`
- Test cases:
  - GET upstream failure returns `502` with prefixed Slack detail message.
  - POST upstream failure returns `502` with prefixed Slack detail message.

#### U2) Slack client transport error clarity
- Include HTTP status/body preview for Slack non-2xx transport failures.
- Include request exception text for network/timeouts and JSON decode issues.
- Test cases:
  - Existing retry behavior still works for `429` responses.

## Feature Plan: Helm Chart Setup

### Objective
Provide Kubernetes Helm deployment assets for the Slack Proxy app with persistent SQLite storage and Slack configuration via environment variables.

### Subtasks

#### H1) Add Helm chart skeleton
- Deliverables:
  - `helm/slack-proxy/Chart.yaml`
  - `helm/slack-proxy/values.yaml`
  - `helm/slack-proxy/templates/*`
- Test cases:
  - `helm lint helm/slack-proxy` passes.
  - `helm template slack-proxy helm/slack-proxy` renders valid manifests.

#### H2) Deployment + SQLite persistence
- Deliverables:
  - single `Deployment` with one app container.
  - one mounted volume (`/app/data`) backed by a PVC for SQLite file persistence.
- Test cases:
  - rendered deployment includes `volumeMounts` for `/app/data`.
  - rendered deployment references PVC-backed `volumes` entry.

#### H3) Slack and app env wiring
- Deliverables:
  - Helm values and deployment env vars for:
    - `SLACK_BASE_URL`
    - `DATABASE_URL`
    - app/docs settings (`APP_*`, `DOCS_*`)
- Test cases:
  - all required env vars are visible in rendered deployment container spec.

#### H4) Ingress exposure
- Deliverables:
  - optional `Ingress` template controlled by Helm values.
  - host/path routing to the app Service.
- Test cases:
  - ingress manifest is not rendered when `ingress.enabled=false`.
  - ingress manifest is rendered with configured host/path when `ingress.enabled=true`.

## Out of Scope (initialization phase)
- Slack events/webhooks.
- Advanced invalidation strategies.
