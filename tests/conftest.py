from collections.abc import Generator

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal, init_db
from app.models.sync_lock import SyncLock
from app.models.workspace_channel import WorkspaceChannel


@pytest.fixture(autouse=True)
def clean_tables() -> Generator[None, None, None]:
    init_db()
    with SessionLocal() as db:
        db.execute(delete(WorkspaceChannel))
        db.execute(delete(SyncLock))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(WorkspaceChannel))
        db.execute(delete(SyncLock))
        db.commit()
