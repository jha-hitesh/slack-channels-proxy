import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.cruds.workspace_channels import get_channel_by_id, upsert_channel


def _slack_headers(payload: dict, secret: str, timestamp: int | None = None) -> tuple[dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    ts = str(timestamp if timestamp is not None else int(time.time()))
    base = f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8")
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return (
        {
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": signature,
            "Content-Type": "application/json",
        },
        body,
    )


def test_slack_events_url_verification(monkeypatch) -> None:
    from app.main import app

    secret = "signing-secret"
    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", secret)

    payload = {"type": "url_verification", "challenge": "abc123"}
    headers, body = _slack_headers(payload, secret)

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 200
    assert response.json() == {"challenge": "abc123"}


def test_slack_events_rejects_invalid_signature(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", "expected-secret")

    payload = {"type": "event_callback", "team_id": "T123", "event": {"type": "channel_created"}}
    headers, body = _slack_headers(payload, "wrong-secret")

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Slack request signature"


def test_slack_events_rejects_stale_timestamp(monkeypatch) -> None:
    from app.main import app

    secret = "signing-secret"
    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", secret)
    monkeypatch.setattr("app.api.slack_events.settings.slack_signature_tolerance_seconds", 300)

    payload = {"type": "event_callback", "team_id": "T123", "event": {"type": "channel_created"}}
    old_timestamp = int(time.time()) - 301
    headers, body = _slack_headers(payload, secret, timestamp=old_timestamp)

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Slack request signature"


def test_slack_events_channel_created_upserts_channel(monkeypatch) -> None:
    from app.main import app

    secret = "signing-secret"
    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", secret)

    payload = {
        "type": "event_callback",
        "team_id": "T123",
        "event": {
            "type": "channel_created",
            "channel": {"id": "C100", "name": "engineering", "is_archived": False},
        },
    }
    headers, body = _slack_headers(payload, secret)

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    with SessionLocal() as db:
        record = get_channel_by_id(db=db, workspace_id="T123", channel_id="C100")
        assert record is not None
        assert record.name == "engineering"
        assert record.is_archived is False


def test_slack_events_channel_deleted_marks_archived(monkeypatch) -> None:
    from app.main import app

    secret = "signing-secret"
    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", secret)

    with SessionLocal() as db:
        upsert_channel(db=db, workspace_id="T123", channel_id="C100", name="engineering", is_archived=False)

    payload = {
        "type": "event_callback",
        "team_id": "T123",
        "event": {
            "type": "channel_deleted",
            "channel": "C100",
        },
    }
    headers, body = _slack_headers(payload, secret)

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 200

    with SessionLocal() as db:
        record = get_channel_by_id(db=db, workspace_id="T123", channel_id="C100")
        assert record is not None
        assert record.is_archived is True


def test_slack_events_channel_rename_updates_existing_record(monkeypatch) -> None:
    from app.main import app

    secret = "signing-secret"
    monkeypatch.setattr("app.api.slack_events.settings.slack_signing_secret", secret)

    with SessionLocal() as db:
        upsert_channel(db=db, workspace_id="T123", channel_id="C100", name="eng-old", is_archived=False)

    payload = {
        "type": "event_callback",
        "team_id": "T123",
        "event": {
            "type": "channel_rename",
            "channel": {"id": "C100", "name": "engineering"},
        },
    }
    headers, body = _slack_headers(payload, secret)

    with TestClient(app) as client:
        response = client.post("/slack/events", headers=headers, content=body)

    assert response.status_code == 200

    with SessionLocal() as db:
        record = get_channel_by_id(db=db, workspace_id="T123", channel_id="C100")
        assert record is not None
        assert record.name == "engineering"
        assert record.is_archived is False
