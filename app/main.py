import logging

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.api.routes import router as api_router
from app.core.db import SessionLocal, init_db
from app.core.docs_auth import verify_docs_auth
from app.core.settings import settings
from app.services.channels import SlackUpstreamError, sync_channels_from_slack_if_empty

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Slack Proxy",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    sync_outcome = "ok"
    sync_triggered = False
    synced_channels = 0
    with SessionLocal() as db:
        try:
            sync_triggered, synced_channels = sync_channels_from_slack_if_empty(
                db=db,
                workspace_id=settings.slack_workspace_id,
            )
        except SlackUpstreamError:
            sync_outcome = "upstream_error"
            logger.exception("startup_channel_sync_failed")
    logger.info("startup_completed env=%s database_url=%s", settings.app_env, settings.database_url)
    logger.info(
        "startup_channel_sync_completed outcome=%s sync_triggered=%s synced_channels=%s",
        sync_outcome,
        sync_triggered,
        synced_channels,
    )


@app.get("/docs", dependencies=[Depends(verify_docs_auth)], response_class=HTMLResponse)
def docs() -> HTMLResponse:
    response = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - Swagger UI",
    )
    logger.info("docs_requested")
    return response


@app.get("/openapi.json", dependencies=[Depends(verify_docs_auth)])
def openapi_schema() -> dict:
    schema = app.openapi()
    logger.info("openapi_schema_requested")
    return schema


@app.get("/health")
def health() -> dict[str, str]:
    payload = {"status": "ok", "env": settings.app_env}
    logger.info("health_requested env=%s", settings.app_env)
    return payload
