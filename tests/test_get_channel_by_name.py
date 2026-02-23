import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.cruds.sync_locks import try_acquire_sync_lock

AUTH_HEADERS = {"Authorization": "Bearer xoxb-test-token"}


def test_get_channel_db_hit_returns_cached_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.cruds.workspace_channels import upsert_channel

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")

    with SessionLocal() as db:
        upsert_channel(db, workspace_id="T123", channel_id="C1", name="general")

    with TestClient(app) as client:
        response = client.get("/channels/ General ", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "id": "C1",
        "name": "general",
        "source": "db",
        "exists": True,
        "sync_status": None,
    }


def test_get_channel_returns_sync_status_when_lock_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.cruds.workspace_channels import upsert_channel

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")

    with SessionLocal() as db:
        upsert_channel(db, workspace_id="T123", channel_id="C1", name="general")
        acquired = try_acquire_sync_lock(db=db, workspace_id="T123")
        assert acquired is True

    with TestClient(app) as client:
        response = client.get("/channels/general", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "id": "C1",
        "name": "general",
        "source": "db",
        "exists": True,
        "sync_status": "sync_in_progress",
    }


def test_get_channel_db_miss_returns_404_without_slack_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")

    def fail_if_called() -> None:
        raise AssertionError("Slack should not be called during request lookup")

    monkeypatch.setattr("app.services.channels.get_slack_client", fail_if_called)

    with TestClient(app) as client:
        response = client.get("/channels/unknown", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json() == {
        "id": "",
        "name": "unknown",
        "source": "db",
        "exists": False,
        "sync_status": None,
    }


def test_get_channel_requires_authorization_header() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/channels/engineering")

    assert response.status_code == 401
    assert "authorization" in response.json()["detail"].lower()


def test_get_channel_surfaces_upstream_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import SlackUpstreamError

    def raise_upstream_error(bot_token: str) -> str:
        raise SlackUpstreamError("Slack API returned error: team_access_not_granted")

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", raise_upstream_error)

    with TestClient(app) as client:
        response = client.get("/channels/engineering", headers=AUTH_HEADERS)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Slack upstream request failed: Slack API returned error: team_access_not_granted"
    )
