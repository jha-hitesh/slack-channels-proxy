import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.settings import settings
from app.cruds.workspace_channels import get_channel_by_name as get_channel_by_name_record
from app.schemas.channel import CreateChannelRequest, ChannelResponse
from app.services.channels import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    SlackUpstreamError,
    create_channel_in_slack,
    get_channel_by_name_from_db,
    run_background_channel_sync,
    try_schedule_background_sync,
)
from app.utils.channel_names import normalize_channel_name

router = APIRouter(prefix="/channels", tags=["channels"])
logger = logging.getLogger(__name__)


@router.get(
    "/{name}",
    response_model=ChannelResponse,
    responses={
        200: {
            "description": "Channel was resolved from local DB cache",
            "content": {
                "application/json": {
                    "examples": {
                        "from_db": {"value": {"id": "C01ABCDEF", "name": "general", "source": "db"}},
                    }
                }
            },
        },
        404: {"description": "Channel not found in local cache"},
    },
)
def get_channel_by_name(
    name: str = Path(min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> ChannelResponse:
    outcome = "unknown"
    try:
        response = get_channel_by_name_from_db(
            db=db,
            workspace_id=settings.slack_workspace_id,
            name=name,
        )
        outcome = f"ok:{response.source}"
        return response
    except ChannelNotFoundError as exc:
        outcome = "not_found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    finally:
        logger.info("route_get_channel_by_name name=%s outcome=%s", name, outcome)


@router.post("", response_model=ChannelResponse)
def create_channel(
    payload: CreateChannelRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ChannelResponse:
    normalized_name = normalize_channel_name(payload.name)
    outcome = "unknown"
    try:
        response = create_channel_in_slack(
            db=db,
            workspace_id=settings.slack_workspace_id,
            name=normalized_name,
        )
        outcome = "created"
        return response
    except ChannelAlreadyExistsError:
        existing = get_channel_by_name_record(
            db=db,
            workspace_id=settings.slack_workspace_id,
            name=normalized_name,
        )
        if existing is not None:
            outcome = "exists_cached"
            return ChannelResponse(id=existing.channel_id, name=existing.name, source="db")

        lock_acquired = try_schedule_background_sync(db=db, workspace_id=settings.slack_workspace_id)
        if lock_acquired:
            background_tasks.add_task(run_background_channel_sync, settings.slack_workspace_id)
        outcome = "exists_sync_queued" if lock_acquired else "exists_sync_in_progress"
        source = "sync_queued" if lock_acquired else "sync_in_progress"
        return ChannelResponse(id="", name=normalized_name, source=source)
    except SlackUpstreamError as exc:
        outcome = f"upstream_error:{exc}"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack upstream request failed",
        ) from exc
    finally:
        logger.info("route_create_channel name=%s outcome=%s", normalized_name, outcome)
