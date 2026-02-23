# Project Agent Constraints

## Runtime and Services
- Backend runtime: Python 3.11.
- Web framework: FastAPI.
- Database: local SQLite.
- DB migrations: Alembic.
- Packaging: `pyproject.toml` and `uv`.

## Containerization
- Provide a `Dockerfile` for the app server and a `.dockerignore` file.
- Provide a `docker-compose.yml` with an `app` service.
- Services must share a common Docker network named `localnet` so `docker compose up` runs locally in one command.

## Folder Structure
- Top-level folders: `alembic`, `app`, `tests`.
- `app` subfolders: `core`, `models`, `cruds`, `schemas`, `utils`, `scripts`, `api`.

## API Scope For This Project
- Expose channel-proxy endpoints for:
  - `GET /channels/{name}`: return channel info by name using Slack API and SQLite persistence.
  - `POST /channels`: create channel by name via Slack API.
- If create is called for an existing channel, fetch all channels from Slack, upsert into SQLite, and return the existing channel id.

## API Docs Access
- Swagger UI and `openapi.json` must be protected by basic auth.

## Configuration
- Prefer environment variables with sensible defaults in code instead of hardcoded values.
- Required env vars should include Slack bot token and optional Slack base URL.
- SQLite should be the default persistence for workspace channels (for example: `sqlite:///./data/slack_proxy.db`).

## Updating Flow.md
- Always ensure a mermaid diagram is inside fenced ```mermaid blocks.
- You can have multiple diagrams in the same file.

## Feature Change Process
- Plan each feature into smaller subtasks with possible test cases.
- Update `plan.md` and `flow.md` for behavior changes.
- Add code and tests for each subtask.
- Execute test loop until all tests pass.

## Testing
- Start stack with `docker-compose up --build -d`.
- Check logs with `docker-compose logs --no-color --tail=100 app`.
- Run tests with `docker-compose run --rm --build app uv run pytest`.
- If tests fail, fix and rerun until green.

## Git Operations
- Before commit, stage all files in the current folder except ignored files.
- Commit message format: `<ACTION>:<short description>` where action is `ADD`, `UPDATE`, or `FIX`.

## ReadMe Update
- the readme is for humans on why this project exists, what this project does and how it is useful to them
- list out basic project setup options available for local as well as production
- add contrinution guidelines including how to develop in this repo using coding agents
