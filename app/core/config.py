"""Environment-backed configuration and support-function metadata."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_FUNCTIONS = ("database", "security", "network", "it_infrastructure")
UNCLASSIFIED = "unclassified"

FUNCTION_DISPLAY_NAMES: dict[str, str] = {
    "database": "Database",
    "security": "Security",
    "network": "Network",
    "it_infrastructure": "IT-infrastructure",
}

# Defaults for the System One question. Environment variables of the same name override them.
_DEFAULT_ROUTE_INSTRUCTIONS = "Какая команда поддержки должна обработать это обращение?"
_DEFAULT_CRITERIA_DATABASE = (
    "Базы данных и СУБД (PostgreSQL, MySQL, Oracle, MS SQL, ClickHouse): запросы, "
    "производительность, репликация, блокировки, схемы и данные в БД"
)
_DEFAULT_CRITERIA_SECURITY = (
    "Информационная безопасность: антивирусная защита и вредоносное ПО, управление "
    "уязвимостями и отчёты сканеров, фишинг и почтовая безопасность, социальная инженерия, "
    "учётные записи (блокировки, подбор паролей), утечка секретов и паролей, утеря или кража "
    "устройств, доступ к системам с персональными данными, подозрительная активность на серверах"
)
_DEFAULT_CRITERIA_NETWORK = (
    "Сеть: VPN и удалённый доступ, межсетевые экраны, открытие портов и сетевых доступов "
    "между сервисами, маршрутизация, DNS"
)
_DEFAULT_CRITERIA_IT_INFRASTRUCTURE = (
    "ИТ-инфраструктура: серверы Linux (место на диске, нагрузка, SSH-доступ), Kubernetes, "
    "резервное копирование и восстановление файлов, корпоративная почта, TLS-сертификаты, "
    "файловые ресурсы и общие папки"
)
_DEFAULT_CRITERIA_UNCLASSIFIED = (
    "Обращение не относится к ИТ-поддержке или из текста невозможно понять, в чём проблема"
)


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    joey_systemone_url: str | None = Field(default=None, alias="JOEY_SYSTEMONE_URL")
    joey_systemone_api_key: str | None = Field(default=None, alias="JOEY_SYSTEMONE_API_KEY")
    baseten_api_key: str | None = Field(default=None, alias="BASETEN_API_KEY")
    # Name the System One server knows the model by: joey-1 on the self-hosted qev server,
    # decision-models/baseten-joey-2b-latest on Baseten. The old default pointed at Baseten
    # and the Spark server answered 404, which the API reported as unclassified.
    joey_decision_model: str = Field(default="joey-1", alias="JOEY_DECISION_MODEL")
    joey_timeout_seconds: int = Field(default=30, alias="JOEY_TIMEOUT_SECONDS")

    # The choice question sent to Joey. Keys stay the five decision labels; the text is the policy.
    joey_route_instructions: str = Field(
        default=_DEFAULT_ROUTE_INSTRUCTIONS,
        alias="JOEY_ROUTE_INSTRUCTIONS",
    )
    joey_criteria_database: str = Field(
        default=_DEFAULT_CRITERIA_DATABASE,
        alias="JOEY_CRITERIA_DATABASE",
    )
    joey_criteria_security: str = Field(
        default=_DEFAULT_CRITERIA_SECURITY,
        alias="JOEY_CRITERIA_SECURITY",
    )
    joey_criteria_network: str = Field(
        default=_DEFAULT_CRITERIA_NETWORK,
        alias="JOEY_CRITERIA_NETWORK",
    )
    joey_criteria_it_infrastructure: str = Field(
        default=_DEFAULT_CRITERIA_IT_INFRASTRUCTURE,
        alias="JOEY_CRITERIA_IT_INFRASTRUCTURE",
    )
    joey_criteria_unclassified: str = Field(
        default=_DEFAULT_CRITERIA_UNCLASSIFIED,
        alias="JOEY_CRITERIA_UNCLASSIFIED",
    )

    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    max_concurrent_requests: int = Field(default=10, alias="MAX_CONCURRENT_REQUESTS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")
    mask_internal_hosts: bool = Field(default=True, alias="MASK_INTERNAL_HOSTS")

    @field_validator(
        "joey_route_instructions",
        "joey_criteria_database",
        "joey_criteria_security",
        "joey_criteria_network",
        "joey_criteria_it_infrastructure",
        "joey_criteria_unclassified",
    )
    @classmethod
    def _routing_text_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("routing text must not be empty")
        return text

    @property
    def joey_route_criteria(self) -> dict[str, str]:
        """Decision label -> description sent as the System One ``choice`` criteria."""
        return {
            "database": self.joey_criteria_database,
            "security": self.joey_criteria_security,
            "network": self.joey_criteria_network,
            "it_infrastructure": self.joey_criteria_it_infrastructure,
            UNCLASSIFIED: self.joey_criteria_unclassified,
        }

    @property
    def joey_uses_systemone(self) -> bool:
        """True when a System One URL is configured. The API key is optional."""
        return bool(self.joey_systemone_url and self.joey_systemone_url.strip())

    @property
    def resolved_systemone_api_key(self) -> str | None:
        """API key for System One (JOEY_SYSTEMONE_API_KEY or BASETEN_API_KEY)."""
        for value in (self.joey_systemone_api_key, self.baseten_api_key):
            if value and value.strip():
                return value.strip()
        return None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
