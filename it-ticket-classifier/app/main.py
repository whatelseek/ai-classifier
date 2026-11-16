"""FastAPI application entrypoint for the IT ticket classifier.

Exposes the HTTP API and wires logging, settings, and route registration.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prepare runtime resources on startup and release them on shutdown.

    Args:
        _app: FastAPI application instance (unused).
    """
    settings = get_settings()
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        Configured FastAPI app with routes, logging, and lifespan hooks.
    """
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="IT Ticket Classifier",
        version=__version__,
        description="AI-powered IT support ticket classification agent",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()