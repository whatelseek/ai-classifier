"""FastAPI dependency providers for settings, the classifier, and concurrency."""

import asyncio

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.classifier import ClassificationService

_request_semaphore: asyncio.Semaphore | None = None


def get_app_settings() -> Settings:
    """Return cached application settings."""
    return get_settings()


def get_service(settings: Settings = Depends(get_app_settings)) -> ClassificationService:
    """Build the classifier for this request. The Joey HTTP client is shared."""
    return ClassificationService(settings)


def get_request_semaphore() -> asyncio.Semaphore:
    """Limit how many classifications run at once."""
    global _request_semaphore
    if _request_semaphore is None:
        _request_semaphore = asyncio.Semaphore(get_settings().max_concurrent_requests)
    return _request_semaphore
