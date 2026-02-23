import pytest

from app.core.db import SessionLocal
from app.cruds.workspace_channels import upsert_channel
from app.services.channels import sync_channels_from_slack_if_empty


def test_startup_sync_skips_when_cache_has_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as db:
        upsert_channel(db=db, workspace_id="default-workspace", channel_id="C1", name="general")

    def fail_if_called() -> None:
        raise AssertionError("Slack should not be called when cache already has channels")

    monkeypatch.setattr("app.services.channels.get_slack_client", fail_if_called)

    with SessionLocal() as db:
        triggered, synced = sync_channels_from_slack_if_empty(db=db, workspace_id="default-workspace")

    assert triggered is False
    assert synced == 0
