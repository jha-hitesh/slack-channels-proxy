import logging

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if authorization is None:
        logger.info("slack_auth_checked auth_ok=%s reason=missing_header", False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    auth_ok = scheme.lower() == "bearer" and bool(token.strip())
    logger.info("slack_auth_checked auth_ok=%s reason=%s", auth_ok, "ok" if auth_ok else "invalid_format")
    if not auth_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be in format: Bearer <token>",
        )
    return token.strip()
