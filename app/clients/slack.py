from collections.abc import Iterator
import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError, SlackRequestError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from app.utils.channel_names import normalize_channel_name

logger = logging.getLogger(__name__)


class SlackError(Exception):
    pass


class SlackNotFoundError(SlackError):
    pass


class SlackUpstreamError(SlackError):
    pass


class SlackUnauthorizedError(SlackUpstreamError):
    pass


class SlackChannelExistsError(SlackUpstreamError):
    pass


class SlackClient:
    def __init__(
        self,
        bot_token: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        max_429_retries: int = 5,
    ) -> None:
        self.bot_token = bot_token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_429_retries = max_429_retries

        ssl_context = None
        rate_limit_handler = RateLimitErrorRetryHandler(max_retry_count=self.max_429_retries)

        self.client = WebClient(
            token=self.bot_token,
            base_url=f"{self.base_url}/",
            timeout=self.timeout_seconds,
            ssl=ssl_context,
            retry_handlers=[rate_limit_handler],
        )

        logger.info(
            "slack_client_init base_url=%s timeout_seconds=%s max_429_retries=%s token_configured=%s",
            self.base_url,
            self.timeout_seconds,
            self.max_429_retries,
            bool(self.bot_token),
        )

    def _request(self, method: str, path: str, params: dict | None = None) -> dict:
        status_code: int | None = None
        outcome = "unknown"
        error_code: str | None = None

        try:
            if not self.bot_token:
                outcome = "missing_token"
                raise SlackUpstreamError("Slack bot token is not configured")

            payload = self.client.api_call(
                api_method=path.lstrip("/"),
                http_verb=method.upper(),
                params=params,
            )
            status_code = payload.status_code
            outcome = "ok"
            payload_data = getattr(payload, "data", payload)
            if not isinstance(payload_data, dict):
                raise SlackUpstreamError("Slack response payload is invalid")
            return payload_data
        except SlackApiError as exc:
            status_code = exc.response.status_code
            error_code = exc.response.get("error", "unknown_error")
            if error_code in {"invalid_auth", "not_authed", "account_inactive", "token_revoked"}:
                outcome = "unauthorized"
                raise SlackUnauthorizedError("Slack token is invalid or unauthorized") from exc
            if error_code in {"name_taken", "already_exists"}:
                outcome = "channel_exists"
                raise SlackChannelExistsError("Slack channel already exists") from exc

            outcome = "slack_api_error"
            raise SlackUpstreamError(f"Slack API returned error: {error_code}") from exc
        except (SlackRequestError, ValueError) as exc:
            outcome = "request_failed"
            raise SlackUpstreamError(f"Slack request failed: {exc}") from exc
        finally:
            logger.info(
                "slack_request method=%s path=%s status_code=%s outcome=%s error_code=%s",
                method,
                path,
                status_code,
                outcome,
                error_code,
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

    def auth_test(self) -> dict:
        payload = self._request("GET", "/auth.test")
        if not isinstance(payload, dict):
            raise SlackUpstreamError("Slack auth test response is invalid")
        return payload
