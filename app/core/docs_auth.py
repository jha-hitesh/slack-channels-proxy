import secrets
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.settings import settings

security = HTTPBasic()
logger = logging.getLogger(__name__)


def verify_docs_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    user_ok = secrets.compare_digest(credentials.username, settings.docs_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.docs_password)
    auth_ok = user_ok and pass_ok
    try:
        if not auth_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid documentation credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username
    finally:
        logger.info("docs_auth_checked username=%s auth_ok=%s", credentials.username, auth_ok)
