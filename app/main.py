"""FastAPI application entrypoint for the IT ticket classifier."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.llm.joey_systemone import aclose_shared_client


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Close the shared Joey client when the process stops."""
    yield
    await aclose_shared_client()


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    application = FastAPI(
        title="IT Ticket Classifier",
        version=__version__,
        description=(
            "Routes an IT ticket description to database, security, network, "
            "it_infrastructure, or unclassified."
        ),
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
