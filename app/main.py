from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.issues import router as issues_router
from app.core.config import get_settings, validate_required_settings
from app.core.logging import configure_logging, log_requests


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    if settings.app_env != "local":
        validate_required_settings(settings)

    app = FastAPI(
        title="Backlog Cloud Run Bridge",
        version="0.1.0",
    )
    app.state.settings = settings
    app.middleware("http")(log_requests)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(issues_router)
    return app


app = create_app()
