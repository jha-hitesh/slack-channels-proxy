import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workspace_channel import WorkspaceChannel
from app.utils.channel_names import normalize_channel_name

logger = logging.getLogger(__name__)


def get_channel_by_name(db: Session, workspace_id: str, name: str) -> WorkspaceChannel | None:
    normalized_name = normalize_channel_name(name)
    record: WorkspaceChannel | None = None
    query = select(WorkspaceChannel).where(
        WorkspaceChannel.workspace_id == workspace_id,
        WorkspaceChannel.name == normalized_name,
    )
    record = db.execute(query).scalar_one_or_none()
    logger.info(
        "crud_get_channel_by_name workspace_id=%s normalized_name=%s found=%s",
        workspace_id,
        normalized_name,
        record is not None,
    )
    return record


def upsert_channel(
    db: Session,
    workspace_id: str,
    channel_id: str,
    name: str,
    is_archived: bool = False,
) -> WorkspaceChannel:
    normalized_name = normalize_channel_name(name)
    record = get_channel_by_name(db, workspace_id=workspace_id, name=normalized_name)
    created = False
    if record is None:
        created = True
        record = WorkspaceChannel(
            workspace_id=workspace_id,
            channel_id=channel_id,
            name=normalized_name,
            is_archived=is_archived,
        )
        db.add(record)
    else:
        record.channel_id = channel_id
        record.is_archived = is_archived

    db.commit()
    db.refresh(record)
    logger.info(
        "crud_upsert_channel workspace_id=%s normalized_name=%s channel_id=%s created=%s archived=%s",
        workspace_id,
        normalized_name,
        channel_id,
        created,
        is_archived,
    )
    return record


def count_channels(db: Session, workspace_id: str) -> int:
    query = select(func.count()).select_from(WorkspaceChannel).where(
        WorkspaceChannel.workspace_id == workspace_id
    )
    count = db.execute(query).scalar_one()
    logger.info("crud_count_channels workspace_id=%s count=%s", workspace_id, count)
    return int(count)
