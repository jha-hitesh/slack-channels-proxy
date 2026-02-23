import logging

from sqlalchemy.orm import Session

from app.clients.slack import SlackChannelExistsError, SlackClient, SlackUpstreamError
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


def get_slack_client() -> SlackClient:
    client = SlackClient(
        bot_token=settings.slack_bot_token,
        base_url=settings.slack_base_url,
    )
    logger.info("service_get_slack_client base_url=%s", settings.slack_base_url)
    return client


def sync_channels_from_slack(db: Session, workspace_id: str) -> int:
    synced = 0
    slack_client = get_slack_client()
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


def sync_channels_from_slack_if_empty(db: Session, workspace_id: str) -> tuple[bool, int]:
    existing_count = count_channels(db=db, workspace_id=workspace_id)
    if existing_count > 0:
        logger.info(
            "service_sync_channels_from_slack_if_empty workspace_id=%s should_sync=%s existing_count=%s",
            workspace_id,
            False,
            existing_count,
        )
        return (False, 0)

    synced = sync_channels_from_slack(db=db, workspace_id=workspace_id)
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


def create_channel_in_slack(db: Session, workspace_id: str, name: str) -> ChannelResponse:
    normalized_name = normalize_channel_name(name)
    slack_client = get_slack_client()
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


def run_background_channel_sync(workspace_id: str) -> None:
    outcome = "ok"
    synced = 0
    with SessionLocal() as db:
        try:
            synced = sync_channels_from_slack(db=db, workspace_id=workspace_id)
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
    "SlackUpstreamError",
    "create_channel_in_slack",
    "get_channel_by_name_from_db",
    "run_background_channel_sync",
    "sync_channels_from_slack",
    "sync_channels_from_slack_if_empty",
    "try_schedule_background_sync",
]
