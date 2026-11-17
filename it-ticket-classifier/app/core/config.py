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
        openai_api_key: API key for the OpenAI API.
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
    # Extra attempts after the first model call. LangGraph retries the node;
    # the OpenAI SDK client is created with max_retries=0.
    openai_max_retries: int = Field(default=2, alias="OPENAI_MAX_RETRIES")
    openai_max_input_tokens: int = Field(default=12000, alias="OPENAI_MAX_INPUT_TOKENS")
    openai_max_output_tokens: int = Field(default=128, alias="OPENAI_MAX_OUTPUT_TOKENS")
    classify_extract_request_body: bool = Field(default=True, alias="CLASSIFY_EXTRACT_REQUEST_BODY")

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
    docling_api_url: str | None = Field(default=None, alias="DOCLING_API_URL")
    docling_timeout_seconds: int = Field(default=120, alias="DOCLING_TIMEOUT_SECONDS")

    @property
    def openai_configured(self) -> bool:
        """Whether LLM calls can be made (API key and/or OpenAI-compatible proxy)."""
        has_key = bool(self.openai_api_key and self.openai_api_key.strip())
        has_proxy = bool(self.openai_base_url and self.openai_base_url.strip())
        return has_key or has_proxy

    @property
    def uses_openai_compatible_proxy(self) -> bool:
        """Route LLM traffic through Chat Completions (vLLM / Envoy), not Responses API."""
        return bool(self.openai_base_url and self.openai_base_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Returns:
        Process-wide settings singleton.
    """
    return Settings()