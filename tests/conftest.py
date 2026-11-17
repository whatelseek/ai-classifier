"""Pytest fixtures and environment defaults for the test suite."""

import pytest

from app.core.config import get_settings
from app.llm.joey_systemone import reset_shared_client

get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _fresh_joey_client():
    """Each test gets its own Joey client, so a monkeypatched transport is used."""
    reset_shared_client()
    yield
    reset_shared_client()
