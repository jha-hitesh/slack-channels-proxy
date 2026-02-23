import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.cruds.sync_locks import try_acquire_sync_lock

AUTH_HEADERS = {"Authorization": "Bearer xoxb-test-token"}


def test_create_channel_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name, bot_token: {
            "id": "C99",
            "name": "engineering",
            "source": "slack",
            "exists": False,
            "sync_status": None,
        },
    )

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "Engineering"}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "id": "C99",
        "name": "engineering",
        "source": "slack",
        "exists": False,
        "sync_status": None,
    }


def test_create_channel_exists_queues_background_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import ChannelAlreadyExistsError

    calls = {"count": 0}

    def fake_background_task(workspace_id: str, bot_token: str) -> None:
        calls["count"] += 1

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name, bot_token: (_ for _ in ()).throw(ChannelAlreadyExistsError("exists")),
    )
    monkeypatch.setattr("app.api.routes.run_background_channel_sync", fake_background_task)

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"}, headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json() == {
        "id": "",
        "name": "engineering",
        "source": "sync_queued",
        "exists": True,
        "sync_status": "sync_queued",
    }
    assert calls["count"] == 1


def test_create_channel_exists_does_not_queue_when_lock_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import ChannelAlreadyExistsError

    calls = {"count": 0}

    def fake_background_task(workspace_id: str, bot_token: str) -> None:
        calls["count"] += 1

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name, bot_token: (_ for _ in ()).throw(ChannelAlreadyExistsError("exists")),
    )
    monkeypatch.setattr("app.api.routes.run_background_channel_sync", fake_background_task)

    with SessionLocal() as db:
        acquired = try_acquire_sync_lock(db=db, workspace_id="T123")
        assert acquired is True

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"}, headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json() == {
        "id": "",
        "name": "engineering",
        "source": "sync_in_progress",
        "exists": True,
        "sync_status": "sync_in_progress",
    }
    assert calls["count"] == 0


def test_create_channel_requires_authorization_header() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"})

    assert response.status_code == 401
    assert "authorization" in response.json()["detail"].lower()


def test_create_channel_surfaces_upstream_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import SlackUpstreamError

    monkeypatch.setattr("app.api.routes.resolve_workspace_id", lambda bot_token: "T123")

    def raise_upstream_error(db, workspace_id: str, name: str, bot_token: str) -> dict:
        raise SlackUpstreamError("Slack API returned error: internal_error")

    monkeypatch.setattr("app.api.routes.create_channel_in_slack", raise_upstream_error)

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"}, headers=AUTH_HEADERS)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Slack upstream request failed: Slack API returned error: internal_error"
    )
