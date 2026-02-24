import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.settings import settings
from app.core.slack_signature import verify_slack_signature
from app.services.channels import handle_slack_channel_event

router = APIRouter(prefix="/slack", tags=["slack-events"])
logger = logging.getLogger(__name__)


@router.post("/events")
async def slack_events(request: Request, db: Session = Depends(get_db)) -> dict[str, str | bool]:
    raw_body = await request.body()
    signature = request.headers.get("X-Slack-Signature")
    timestamp = request.headers.get("X-Slack-Request-Timestamp")

    verified = verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=timestamp,
        signature=signature,
        body=raw_body,
        tolerance_seconds=settings.slack_signature_tolerance_seconds,
    )
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack request signature",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    event_type = payload.get("type")
    if event_type == "url_verification":
        challenge = payload.get("challenge", "")
        logger.info("slack_url_verification_received")
        return {"challenge": str(challenge)}

    if event_type != "event_callback":
        logger.info("slack_event_ignored type=%s", event_type)
        return {"ok": True}

    handle_slack_channel_event(db=db, payload=payload)
    return {"ok": True}
