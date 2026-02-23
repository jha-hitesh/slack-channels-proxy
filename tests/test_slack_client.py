import pytest
from slack_sdk.errors import SlackApiError

from app.clients.slack import (
    SlackChannelExistsError,
    SlackClient,
    SlackUnauthorizedError,
    SlackUpstreamError,
)


class DummySlackResponse(dict):
    def __init__(self, status_code: int, data: dict) -> None:
        super().__init__(data)
        self.status_code = status_code


def test_request_uses_slack_response_data_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api")

    class FakeSlackResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.data = {"ok": True, "team_id": "T123"}

        def __iter__(self):  # pragma: no cover - guard against dict(payload) regressions
            return iter(["broken"])

    monkeypatch.setattr(client.client, "api_call", lambda **kwargs: FakeSlackResponse())

    payload = client._request("GET", "/auth.test")

    assert payload == {"ok": True, "team_id": "T123"}


def test_client_uses_sdk_retry_handler_and_ssl_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeHandler:
        def __init__(self, max_retry_count: int) -> None:
            self.max_retry_count = max_retry_count

    class FakeWebClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def api_call(self, **kwargs: object) -> dict:
            return {"ok": True}

    monkeypatch.setattr("app.clients.slack.RateLimitErrorRetryHandler", FakeHandler)
    monkeypatch.setattr("app.clients.slack.WebClient", FakeWebClient)

    SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api")

    assert captured["ssl"] is None
    assert len(captured["retry_handlers"]) == 1
    assert captured["retry_handlers"][0].max_retry_count == 5


def test_request_maps_invalid_auth_to_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api")

    def raise_unauthorized(**kwargs: object) -> dict:
        response = DummySlackResponse(200, {"ok": False, "error": "invalid_auth"})
        raise SlackApiError(message="unauthorized", response=response)

    monkeypatch.setattr(client.client, "api_call", raise_unauthorized)

    with pytest.raises(SlackUnauthorizedError):
        client._request("GET", "/auth.test")


def test_request_maps_name_taken_to_channel_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api")

    def raise_name_taken(**kwargs: object) -> dict:
        response = DummySlackResponse(200, {"ok": False, "error": "name_taken"})
        raise SlackApiError(message="name taken", response=response)

    monkeypatch.setattr(client.client, "api_call", raise_name_taken)

    with pytest.raises(SlackChannelExistsError):
        client._request("POST", "/conversations.create", params={"name": "general"})


def test_request_maps_unknown_error_to_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api")

    def raise_unknown(**kwargs: object) -> dict:
        response = DummySlackResponse(500, {"ok": False, "error": "internal_error"})
        raise SlackApiError(message="boom", response=response)

    monkeypatch.setattr(client.client, "api_call", raise_unknown)

    with pytest.raises(SlackUpstreamError, match="Slack API returned error: internal_error"):
        client._request("GET", "/conversations.list")
