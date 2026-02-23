import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal


def test_get_channel_db_hit_returns_cached_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.cruds.workspace_channels import upsert_channel

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", lambda db, workspace_id: (False, 0))

    with SessionLocal() as db:
        upsert_channel(db, workspace_id="default-workspace", channel_id="C1", name="general")

    with TestClient(app) as client:
        response = client.get("/channels/ General ")

    assert response.status_code == 200
    assert response.json() == {"id": "C1", "name": "general", "source": "db"}


def test_get_channel_db_miss_returns_404_without_slack_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", lambda db, workspace_id: (False, 0))

    def fail_if_called() -> None:
        raise AssertionError("Slack should not be called during request lookup")

    monkeypatch.setattr("app.services.channels.get_slack_client", fail_if_called)

    with TestClient(app) as client:
        response = client.get("/channels/unknown")

    assert response.status_code == 404
    assert "local cache" in response.json()["detail"].lower()


def test_startup_sync_populates_db_for_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.cruds.workspace_channels import upsert_channel

    def fake_sync(db, workspace_id: str) -> tuple[bool, int]:
        upsert_channel(db, workspace_id=workspace_id, channel_id="C2", name="engineering")
        return (True, 1)

    monkeypatch.setattr("app.main.sync_channels_from_slack_if_empty", fake_sync)

    with TestClient(app) as client:
        response = client.get("/channels/Engineering")

    assert response.status_code == 200
    assert response.json() == {"id": "C2", "name": "engineering", "source": "db"}
