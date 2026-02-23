import httpx
import pytest

from app.clients.slack import SlackClient, SlackUpstreamError


def _make_response(status_code: int, *, json_payload: dict | None = None, headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://slack.test/api/conversations.list")
    if json_payload is None:
        return httpx.Response(status_code, headers=headers, request=request)
    return httpx.Response(status_code, json=json_payload, headers=headers, request=request)


def test_request_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _make_response(429, headers={"Retry-After": "0"}),
        _make_response(200, json_payload={"ok": True, "channels": []}),
    ]
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_request(*args: object, **kwargs: object) -> httpx.Response:
        index = calls["count"]
        calls["count"] += 1
        return responses[index]

    monkeypatch.setattr("app.clients.slack.httpx.request", fake_request)
    monkeypatch.setattr("app.clients.slack.time.sleep", lambda delay: sleeps.append(delay))

    client = SlackClient(bot_token="xoxb-test", base_url="https://slack.test/api", max_429_retries=3)
    payload = client._request("GET", "/conversations.list")

    assert payload["ok"] is True
    assert calls["count"] == 2
    assert sleeps == [0.0]


def test_request_raises_after_429_retries_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_request(*args: object, **kwargs: object) -> httpx.Response:
        calls["count"] += 1
        return _make_response(429)

    monkeypatch.setattr("app.clients.slack.httpx.request", fake_request)
    monkeypatch.setattr("app.clients.slack.time.sleep", lambda delay: sleeps.append(delay))

    client = SlackClient(
        bot_token="xoxb-test",
        base_url="https://slack.test/api",
        max_429_retries=2,
        retry_delay_seconds=0.25,
    )

    with pytest.raises(SlackUpstreamError, match="rate limit exceeded"):
        client._request("GET", "/conversations.list")

    assert calls["count"] == 3
    assert sleeps == [0.25, 0.25]
