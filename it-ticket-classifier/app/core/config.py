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
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @property
    def prefer_chat_completions(self) -> bool:
        """OpenRouter and most third-party gateways use /chat/completions, not Responses."""
        if self.openai_base_url:
            return True
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()