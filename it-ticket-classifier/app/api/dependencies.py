"""FastAPI dependency providers for settings, graph, LLM, and concurrency."""

import asyncio

from app.core.config import Settings, get_settings
from app.graph.builder import get_graph
from app.llm.client import OpenAIClassificationClient

_request_semaphore: asyncio.Semaphore | None = None


def get_app_settings() -> Settings:
    """Return cached application settings for dependency injection.

    Returns:
        Singleton ``Settings`` instance loaded from environment.
    """
    return get_settings()


def get_classification_graph():
    """Return the compiled LangGraph workflow.

    Returns:
        Compiled graph ready for ``ainvoke`` / ``invoke``.
    """
    return get_graph()


def get_llm_client(settings: Settings | None = None) -> OpenAIClassificationClient:
    """Construct an LLM client for classification and vision tasks.

    Args:
        settings: Optional settings override; defaults to global settings.

    Returns:
        Client configured for OpenAI or compatible gateways (e.g. OpenRouter).
    """
    return OpenAIClassificationClient(settings or get_settings())


def get_request_semaphore() -> asyncio.Semaphore:
    """Return a process-wide semaphore limiting concurrent classify requests.

    Returns:
        Semaphore sized from ``MAX_CONCURRENT_REQUESTS``.
    """
    global _request_semaphore
    if _request_semaphore is None:
        settings = get_settings()
        _request_semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    return _request_semaphore