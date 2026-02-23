from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.cruds.sync_locks import try_acquire_sync_lock
from app.models.sync_lock import SyncLock


def test_sync_lock_reacquires_when_stale() -> None:
    with SessionLocal() as db:
        first = try_acquire_sync_lock(db=db, workspace_id="default-workspace")
        assert first is True

        record = db.query(SyncLock).filter(SyncLock.workspace_id == "default-workspace").one()
        record.is_locked = True
        record.locked_at = datetime.utcnow() - timedelta(minutes=11)
        db.commit()

        second = try_acquire_sync_lock(db=db, workspace_id="default-workspace")
        assert second is True
