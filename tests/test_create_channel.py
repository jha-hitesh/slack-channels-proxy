import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.cruds.sync_locks import try_acquire_sync_lock


def test_create_channel_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", lambda db, workspace_id: (False, 0))
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name: {"id": "C99", "name": "engineering", "source": "slack"},
    )

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "Engineering"})

    assert response.status_code == 200
    assert response.json() == {"id": "C99", "name": "engineering", "source": "slack"}


def test_create_channel_exists_queues_background_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import ChannelAlreadyExistsError

    calls = {"count": 0}

    def fake_background_task(workspace_id: str) -> None:
        calls["count"] += 1

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", lambda db, workspace_id: (False, 0))
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name: (_ for _ in ()).throw(ChannelAlreadyExistsError("exists")),
    )
    monkeypatch.setattr("app.api.routes.run_background_channel_sync", fake_background_task)

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"})

    assert response.status_code == 200
    assert response.json() == {"id": "", "name": "engineering", "source": "sync_queued"}
    assert calls["count"] == 1


def test_create_channel_exists_does_not_queue_when_lock_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services.channels import ChannelAlreadyExistsError

    calls = {"count": 0}

    def fake_background_task(workspace_id: str) -> None:
        calls["count"] += 1

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", lambda db, workspace_id: (False, 0))
    monkeypatch.setattr(
        "app.api.routes.create_channel_in_slack",
        lambda db, workspace_id, name: (_ for _ in ()).throw(ChannelAlreadyExistsError("exists")),
    )
    monkeypatch.setattr("app.api.routes.run_background_channel_sync", fake_background_task)

    with SessionLocal() as db:
        acquired = try_acquire_sync_lock(db=db, workspace_id="default-workspace")
        assert acquired is True

    with TestClient(app) as client:
        response = client.post("/channels", json={"name": "engineering"})

    assert response.status_code == 200
    assert response.json() == {"id": "", "name": "engineering", "source": "sync_in_progress"}
    assert calls["count"] == 0
