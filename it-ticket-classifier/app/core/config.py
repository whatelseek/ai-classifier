"""Environment-backed configuration and support-function metadata."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_FUNCTIONS = ("network", "linux", "security", "database")

FUNCTION_DISPLAY_NAMES: dict[str, str] = {
    "network": "Network Infrastructure",
    "linux": "Linux Administration",
    "security": "Information Security",
    "database": "Database Administration",
}


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and ``.env``.

    Attributes:
        openai_api_key: API key for OpenAI or OpenAI-compatible providers.
        openai_base_url: Optional gateway base URL (e.g. OpenRouter).
        openai_text_model: Model ID for text classification.
        openai_vision_model: Model ID for image analysis.
        max_file_size_bytes: Maximum size of a single uploaded attachment.
        max_total_upload_bytes: Maximum combined upload size per request.
        request_timeout_seconds: Wall-clock limit for one classification request.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_text_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_TEXT_MODEL")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_timeout_seconds: int = Field(default=60, alias="OPENAI_TIMEOUT_SECONDS")
    openai_max_retries: int = Field(default=2, alias="OPENAI_MAX_RETRIES")
    openai_max_input_tokens: int = Field(default=12000, alias="OPENAI_MAX_INPUT_TOKENS")

    max_file_size_bytes: int = Field(default=20 * 1024 * 1024, alias="MAX_FILE_SIZE_BYTES")
    max_attachments: int = Field(default=10, alias="MAX_ATTACHMENTS")
    max_total_upload_bytes: int = Field(default=50 * 1024 * 1024, alias="MAX_TOTAL_UPLOAD_BYTES")
    request_timeout_seconds: int = Field(default=180, alias="REQUEST_TIMEOUT_SECONDS")
    max_classification_retries: int = Field(default=2, alias="MAX_CLASSIFICATION_RETRIES")
    max_concurrent_requests: int = Field(default=10, alias="MAX_CONCURRENT_REQUESTS")
    max_concurrent_extraction: int = Field(default=4, alias="MAX_CONCURRENT_EXTRACTION")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")
    mask_internal_hosts: bool = Field(default=True, alias="MASK_INTERNAL_HOSTS")
    temp_dir: Path = Field(default=Path("/tmp/it-ticket-classifier"), alias="TEMP_DIR")

    @property
    def openai_configured(self) -> bool:
        """Whether a non-empty API key is present."""
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @property
    def prefer_chat_completions(self) -> bool:
        """Whether to use chat completions instead of the Responses API.

        OpenRouter and most third-party gateways expose ``/chat/completions`` only.
        """
        return bool(self.openai_base_url)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Returns:
        Process-wide settings singleton.
    """
    return Settings()