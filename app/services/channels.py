import logging

from sqlalchemy.orm import Session

from app.clients.slack import (
    SlackChannelExistsError,
    SlackClient,
    SlackUnauthorizedError,
    SlackUpstreamError,
)
from app.core.db import SessionLocal
from app.core.settings import settings
from app.cruds.sync_locks import release_sync_lock, try_acquire_sync_lock
from app.cruds.workspace_channels import count_channels, get_channel_by_name, upsert_channel
from app.schemas.channel import ChannelResponse
from app.utils.channel_names import normalize_channel_name

logger = logging.getLogger(__name__)


class ChannelNotFoundError(Exception):
    pass


class ChannelAlreadyExistsError(Exception):
    pass


class WorkspaceResolutionError(Exception):
    pass


def get_slack_client(bot_token: str) -> SlackClient:
    client = SlackClient(
        bot_token=bot_token,
        base_url=settings.slack_base_url,
    )
    logger.info("service_get_slack_client base_url=%s token_provided=%s", settings.slack_base_url, bool(bot_token))
    return client


def resolve_workspace_id(bot_token: str) -> str:
    slack_client = get_slack_client(bot_token=bot_token)
    payload = slack_client.auth_test()
    workspace_id = payload.get("team_id") or payload.get("enterprise_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise WorkspaceResolutionError("Unable to resolve workspace from Slack token")
    logger.info("service_resolve_workspace_id workspace_id=%s", workspace_id)
    return workspace_id


def sync_channels_from_slack(db: Session, workspace_id: str, bot_token: str) -> int:
    synced = 0
    slack_client = get_slack_client(bot_token=bot_token)
    for channel in slack_client.iter_channels():
        upsert_channel(
            db=db,
            workspace_id=workspace_id,
            channel_id=channel["id"],
            name=channel["name"],
            is_archived=channel.get("is_archived", False),
        )
        synced += 1
    logger.info("service_sync_channels_from_slack workspace_id=%s synced=%s", workspace_id, synced)
    return synced


def sync_channels_from_slack_if_empty(db: Session, workspace_id: str, bot_token: str) -> tuple[bool, int]:
    existing_count = count_channels(db=db, workspace_id=workspace_id)
    if existing_count > 0:
        logger.info(
            "service_sync_channels_from_slack_if_empty workspace_id=%s should_sync=%s existing_count=%s",
            workspace_id,
            False,
            existing_count,
        )
        return (False, 0)

    synced = sync_channels_from_slack(db=db, workspace_id=workspace_id, bot_token=bot_token)
    logger.info(
        "service_sync_channels_from_slack_if_empty workspace_id=%s should_sync=%s synced=%s",
        workspace_id,
        True,
        synced,
    )
    return (True, synced)


def get_channel_by_name_from_db(db: Session, workspace_id: str, name: str) -> ChannelResponse:
    normalized_name = normalize_channel_name(name)
    db_channel = get_channel_by_name(db, workspace_id=workspace_id, name=normalized_name)
    found = db_channel is not None
    logger.info(
        "service_get_channel_by_name_from_db workspace_id=%s normalized_name=%s found=%s",
        workspace_id,
        normalized_name,
        found,
    )
    if db_channel is None:
        raise ChannelNotFoundError(f"Channel '{normalized_name}' was not found in local cache")

    return ChannelResponse(id=db_channel.channel_id, name=db_channel.name, source="db")


def create_channel_in_slack(db: Session, workspace_id: str, name: str, bot_token: str) -> ChannelResponse:
    normalized_name = normalize_channel_name(name)
    slack_client = get_slack_client(bot_token=bot_token)
    try:
        channel = slack_client.create_channel(normalized_name)
    except SlackChannelExistsError as exc:
        raise ChannelAlreadyExistsError(f"Channel '{normalized_name}' already exists in Slack") from exc

    persisted = upsert_channel(
        db=db,
        workspace_id=workspace_id,
        channel_id=channel["id"],
        name=channel["name"],
        is_archived=channel.get("is_archived", False),
    )
    return ChannelResponse(id=persisted.channel_id, name=persisted.name, source="slack")


def try_schedule_background_sync(db: Session, workspace_id: str) -> bool:
    return try_acquire_sync_lock(db=db, workspace_id=workspace_id, stale_after_minutes=10)


def run_background_channel_sync(workspace_id: str, bot_token: str) -> None:
    outcome = "ok"
    synced = 0
    with SessionLocal() as db:
        try:
            synced = sync_channels_from_slack(db=db, workspace_id=workspace_id, bot_token=bot_token)
        except SlackUpstreamError:
            outcome = "upstream_error"
            logger.exception("background_channel_sync_failed workspace_id=%s", workspace_id)
        finally:
            release_sync_lock(db=db, workspace_id=workspace_id)
            logger.info(
                "background_channel_sync_completed workspace_id=%s outcome=%s synced=%s",
                workspace_id,
                outcome,
                synced,
            )


__all__ = [
    "ChannelAlreadyExistsError",
    "ChannelNotFoundError",
    "SlackUnauthorizedError",
    "SlackUpstreamError",
    "WorkspaceResolutionError",
    "create_channel_in_slack",
    "get_channel_by_name_from_db",
    "resolve_workspace_id",
    "run_background_channel_sync",
    "sync_channels_from_slack",
    "sync_channels_from_slack_if_empty",
    "try_schedule_background_sync",
]
