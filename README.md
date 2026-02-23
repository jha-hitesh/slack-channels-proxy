# Slack Proxy

A backend proxy server between clients and Slack focused on channel operations, backed by local SQLite persistence for workspace channels.

## Features (Initial Scope)
- `GET /channels/{name}` channel lookup by name.
- `POST /channels` create channel by name.
- Existing-channel handling on create:
  - fetch all channels from Slack,
  - upsert into local SQLite,
  - return existing channel id.

## Tech Stack
- Python 3.11
- FastAPI
- SQLite (local persistence for workspace channels)
- Alembic (migrations)
- Docker Compose for local development
- `uv` for Python dependency management

## Planned Project Structure
```text
.
├── AGENTS.md
├── plan.md
├── flow.md
├── README.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── alembic/
├── app/
│   ├── api/
│   ├── core/
│   ├── cruds/
│   ├── models/
│   ├── schemas/
│   ├── scripts/
│   └── utils/
└── tests/
```

## Local Development Setup
1. Create environment file:
```bash
cp .env.example .env
```

2. Set required environment variables in `.env`:
- `SLACK_BOT_TOKEN`
- `SLACK_BASE_URL` (optional, defaults to `https://slack.com/api`)
- `DATABASE_URL` (default: `sqlite:///./data/slack_proxy.db`)
- `DOCS_USERNAME`
- `DOCS_PASSWORD`

3. Start the stack:
```bash
docker-compose up --build -d
```
This mounts `./data` into the app container and persists the SQLite file at `data/slack_proxy.db`.

4. Check service logs:
```bash
docker-compose logs --no-color --tail=100 app
```

## Testing
Run tests in the app container:
```bash
docker-compose run --rm --build app uv run pytest
```

Target test coverage for initial implementation:
- local DB hit/miss behavior for `GET /channels/{name}`
- create success and already-exists flow for `POST /channels`
- SQLite upsert behavior after Slack list sync
- docs auth protection

## API Behavior Summary
- `GET /channels/{name}`
  - returns local persisted channel if available.
  - on local miss, fetches from Slack and upserts local DB.
- `POST /channels`
  - creates channel when absent.
  - if channel exists, performs Slack full-channel sync, upserts local DB, and returns existing channel id.

## Current Status
This repository is initialized with planning and workflow documents and starter app structure.

## Helm Deployment
Chart path:
- `helm/slack-proxy`

Basic install:
```bash
helm upgrade --install slack-proxy ./helm/slack-proxy \
  --set image.repository=<your-image-repo> \
  --set image.tag=<your-image-tag> \
  --set env.slackBotToken=<your-slack-bot-token>
```

Notes:
- The chart creates one Deployment and one PVC-backed volume mounted at `/app/data` for SQLite persistence.
- Default DB path is `sqlite:///./data/slack_proxy.db`, which maps to the mounted `/app/data/slack_proxy.db`.
- You can override Slack env vars using:
  - `env.slackBaseUrl`
  - `env.slackWorkspaceId`
