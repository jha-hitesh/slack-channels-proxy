from collections.abc import Iterator
import logging
import time

import httpx

from app.utils.channel_names import normalize_channel_name

logger = logging.getLogger(__name__)


class SlackError(Exception):
    pass


class SlackNotFoundError(SlackError):
    pass


class SlackUpstreamError(SlackError):
    pass


class SlackChannelExistsError(SlackUpstreamError):
    pass


class SlackClient:
    def __init__(
        self,
        bot_token: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        max_429_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.bot_token = bot_token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_429_retries = max_429_retries
        self.retry_delay_seconds = retry_delay_seconds
        logger.info(
            "slack_client_init base_url=%s timeout_seconds=%s max_429_retries=%s retry_delay_seconds=%s token_configured=%s",
            self.base_url,
            self.timeout_seconds,
            self.max_429_retries,
            self.retry_delay_seconds,
            bool(self.bot_token),
        )

    def _request(self, method: str, path: str, params: dict | None = None) -> dict:
        status_code: int | None = None
        outcome = "unknown"
        error_code: str | None = None
        attempt = 0
        try:
            if not self.bot_token:
                outcome = "missing_token"
                raise SlackUpstreamError("Slack bot token is not configured")

            url = f"{self.base_url}/{path.lstrip('/')}"
            headers = {
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            while True:
                attempt += 1
                response = httpx.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                status_code = response.status_code
                if status_code == 429:
                    retries_remaining = self.max_429_retries - (attempt - 1)
                    if retries_remaining <= 0:
                        outcome = "rate_limited_exhausted"
                        raise SlackUpstreamError("Slack rate limit exceeded after retries")
                    retry_after_header = response.headers.get("Retry-After")
                    try:
                        retry_after = (
                            float(retry_after_header)
                            if retry_after_header is not None
                            else self.retry_delay_seconds
                        )
                    except ValueError:
                        retry_after = self.retry_delay_seconds
                    retry_after = max(retry_after, 0.0)
                    logger.warning(
                        "slack_request_rate_limited path=%s attempt=%s retry_after=%s retries_remaining=%s",
                        path,
                        attempt,
                        retry_after,
                        retries_remaining,
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                payload = response.json()

                if not payload.get("ok", False):
                    error_code = payload.get("error", "unknown_error")
                    if error_code in {"name_taken", "already_exists"}:
                        outcome = "channel_exists"
                        raise SlackChannelExistsError("Slack channel already exists")
                    outcome = "slack_api_error"
                    raise SlackUpstreamError(f"Slack API returned error: {error_code}")

                outcome = "ok"
                return payload
        except (httpx.HTTPError, ValueError) as exc:
            if outcome == "unknown":
                outcome = "request_failed"
            raise SlackUpstreamError("Slack request failed") from exc
        finally:
            logger.info(
                "slack_request method=%s path=%s status_code=%s outcome=%s error_code=%s attempts=%s",
                method,
                path,
                status_code,
                outcome,
                error_code,
                attempt,
            )

    def iter_channels(self) -> Iterator[dict]:
        cursor = ""
        page_count = 0
        channel_count = 0
        completed = False
        try:
            while True:
                params = {
                    "limit": 1000,
                    "exclude_archived": "true",
                    "types": "public_channel,private_channel",
                }
                if cursor:
                    params["cursor"] = cursor

                payload = self._request("GET", "/conversations.list", params=params)
                page_count += 1
                channels = payload.get("channels", [])
                channel_count += len(channels)
                for channel in channels:
                    yield channel

                cursor = payload.get("response_metadata", {}).get("next_cursor", "")
                if not cursor:
                    completed = True
                    return
        finally:
            logger.info(
                "slack_iter_channels pages=%s channels=%s completed=%s",
                page_count,
                channel_count,
                completed,
            )

    def get_channel_by_name(self, name: str) -> dict:
        normalized_name = normalize_channel_name(name)
        scanned = 0
        found = False
        try:
            for channel in self.iter_channels():
                scanned += 1
                channel_name = normalize_channel_name(channel.get("name", ""))
                if channel_name == normalized_name:
                    found = True
                    return channel

            raise SlackNotFoundError(f"Channel '{name}' was not found in Slack")
        finally:
            logger.info(
                "slack_get_channel_by_name name=%s normalized_name=%s found=%s scanned=%s",
                name,
                normalized_name,
                found,
                scanned,
            )

    def create_channel(self, name: str) -> dict:
        normalized_name = normalize_channel_name(name)
        payload = self._request(
            "POST",
            "/conversations.create",
            params={"name": normalized_name},
        )
        channel = payload.get("channel")
        if not isinstance(channel, dict):
            raise SlackUpstreamError("Slack create channel response missing channel payload")
        return channel
