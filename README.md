# Slack Proxy

Slack Proxy is a lightweight service that exposes a stable API for Slack channel operations while caching workspace channel data in SQLite.

## Why This Project Exists
- Give internal tools a simple, controlled API for Slack channel reads/creates.
- Reduce repeated Slack lookups by persisting workspace channel records locally.
- Provide a predictable backend pattern (FastAPI + SQLite + Docker) that is easy to run and extend.

## What It Does
- `GET /channels/{name}`: returns channel info by name from local persistence for the calling workspace.
- `POST /channels`: creates a channel by name through Slack API.
- Existing channel create behavior:
  - fetches channels from Slack,
  - upserts records into SQLite,
  - returns the existing channel id.
- Protects Swagger UI and `openapi.json` with Basic Auth.

## Why It Is Useful
- Faster, safer integration point than coupling every client directly to Slack endpoints.
- Local channel cache supports repeat reads and sync recovery patterns.
- Easy to deploy locally for development and to container platforms for production.

## Tech Stack
- Python 3.11
- FastAPI
- SQLite
- Alembic
- `uv`
- Docker / Docker Compose

## Environment Configuration
Create your environment file:
```bash
cp .env.example .env
```

Key variables:
- `SLACK_BASE_URL` (optional, default: `https://slack.com/api`)
- `DATABASE_URL` (optional, default: `sqlite:///./data/slack_proxy.db`)
- `SYNC_LOCK_STALE_AFTER_MINUTES` (optional, default: `10`)
- `DOCS_USERNAME` (required for API docs auth)
- `DOCS_PASSWORD` (required for API docs auth)

Slack bot token is passed per request via `Authorization: Bearer <token>`.

## Setup Options

### Local Setup (Docker Compose)
1. Build and start:
```bash
docker-compose up --build -d
```
2. Check logs:
```bash
docker-compose logs --no-color --tail=100 app
```
3. Run tests:
```bash
docker-compose run --rm --build app uv run pytest
```

### Local Setup (Without Docker)
1. Install dependencies:
```bash
uv sync
```
2. Run the API:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
3. Run tests:
```bash
uv run pytest
```

### Production Setup Options
- Container runtime:
  - Build image from `Dockerfile`.
  - Run with environment variables and a persistent volume mounted at `/app/data` for SQLite.
- Kubernetes via Helm:
  - Chart: `helm/slack-proxy`
  - Example:
```bash
helm upgrade --install slack-proxy ./helm/slack-proxy \
  --set image.repository=<your-image-repo> \
  --set image.tag=<your-image-tag>
```
  - Optional ingress:
```bash
helm upgrade --install slack-proxy ./helm/slack-proxy \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=your-host.example.com
```

## API Behavior Summary
- `GET /channels/{name}`
  - resolves workspace from Slack `auth.test` using bearer token.
  - serves persisted channel info for that workspace by channel name.
  - returns `404` on local miss.
- `POST /channels`
  - resolves workspace from Slack `auth.test`.
  - creates channel when absent.
  - on "already exists", syncs workspace channels from Slack, upserts local DB, then returns existing id.

## Repository Layout
```text
.
├── alembic/
├── app/
│   ├── api/
│   ├── core/
│   ├── cruds/
│   ├── models/
│   ├── schemas/
│   ├── scripts/
│   └── utils/
├── tests/
├── flow.md
├── plan.md
└── AGENTS.md
```

## Contributing
- Fork/branch from the latest default branch.
- Keep changes small and tied to a specific feature or fix.
- Add or update tests with behavior changes.
- Ensure Docker-based test flow passes before opening a PR:
```bash
docker-compose up --build -d
docker-compose logs --no-color --tail=100 app
docker-compose run --rm --build app uv run pytest
```
- Use commit format: `<ACTION>:<short description>` where action is `ADD`, `UPDATE`, or `FIX`.

## Developing With Coding Agents
- Read `AGENTS.md` before starting; it defines architecture, workflow, and test requirements.
- For behavior changes:
  - update `plan.md`,
  - update `flow.md` (use fenced `mermaid` diagrams),
  - implement code and tests,
  - run the full test loop until green.
- Do not bypass API docs auth, Slack integration rules, or SQLite persistence defaults without updating docs and tests.
