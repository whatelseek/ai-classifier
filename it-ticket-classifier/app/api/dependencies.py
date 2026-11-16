import asyncio

from app.core.config import Settings, get_settings
from app.graph.builder import get_graph
from app.llm.client import OpenAIClassificationClient

_request_semaphore: asyncio.Semaphore | None = None


def get_app_settings() -> Settings:
    return get_settings()


def get_classification_graph():
    return get_graph()


def get_llm_client(settings: Settings | None = None) -> OpenAIClassificationClient:
    return OpenAIClassificationClient(settings or get_settings())


def get_request_semaphore() -> asyncio.Semaphore:
    global _request_semaphore
    if _request_semaphore is None:
        settings = get_settings()
        _request_semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    return _request_semaphore