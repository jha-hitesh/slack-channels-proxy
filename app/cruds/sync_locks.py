from datetime import datetime, timedelta
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sync_lock import SyncLock

logger = logging.getLogger(__name__)


def _get_or_create_sync_lock(db: Session, workspace_id: str) -> SyncLock:
    query = select(SyncLock).where(SyncLock.workspace_id == workspace_id)
    record = db.execute(query).scalar_one_or_none()
    if record is None:
        record = SyncLock(workspace_id=workspace_id, is_locked=False, locked_at=None)
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def try_acquire_sync_lock(
    db: Session,
    workspace_id: str,
    stale_after_minutes: int = 10,
) -> bool:
    now = datetime.utcnow()
    stale_before = now - timedelta(minutes=stale_after_minutes)
    record = _get_or_create_sync_lock(db, workspace_id=workspace_id)

    if not record.is_locked:
        record.is_locked = True
        record.locked_at = now
        db.commit()
        logger.info("crud_try_acquire_sync_lock workspace_id=%s acquired=%s reason=unlocked", workspace_id, True)
        return True

    if record.locked_at is not None and record.locked_at <= stale_before:
        record.is_locked = True
        record.locked_at = now
        db.commit()
        logger.info("crud_try_acquire_sync_lock workspace_id=%s acquired=%s reason=stale_lock", workspace_id, True)
        return True

    logger.info("crud_try_acquire_sync_lock workspace_id=%s acquired=%s reason=active_lock", workspace_id, False)
    return False


def release_sync_lock(db: Session, workspace_id: str) -> None:
    query = select(SyncLock).where(SyncLock.workspace_id == workspace_id)
    record = db.execute(query).scalar_one_or_none()
    if record is None:
        logger.info("crud_release_sync_lock workspace_id=%s released=%s reason=missing", workspace_id, False)
        return

    record.is_locked = False
    record.locked_at = None
    db.commit()
    logger.info("crud_release_sync_lock workspace_id=%s released=%s", workspace_id, True)
