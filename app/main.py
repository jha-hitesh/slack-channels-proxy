import logging

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.api.routes import router as api_router
from app.api.slack_events import router as slack_events_router
from app.core.db import init_db
from app.core.docs_auth import verify_docs_auth
from app.core.settings import settings

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
app.include_router(slack_events_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("startup_completed env=%s database_url=%s", settings.app_env, settings.database_url)


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
