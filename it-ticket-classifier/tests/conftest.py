import os

import pytest

# Ensure tests run without live OpenAI credentials
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TEMP_DIR", "/tmp/it-ticket-classifier-test")

from app.core.config import get_settings

get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"