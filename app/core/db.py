from collections.abc import Generator
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.settings import settings

Base = declarative_base()
logger = logging.getLogger(__name__)

_engine_kwargs: dict = {"future": True}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        logger.info("db_session_closed")
        db.close()


def init_db() -> None:
    # Import models before create_all so metadata is populated.
    from app.models import workspace_channel  # noqa: F401
    from app.models import sync_lock  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("db_initialized")
