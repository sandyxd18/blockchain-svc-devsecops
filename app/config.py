# Centralized settings using pydantic-settings.
# Reads from environment variables or .env file.
# Fails fast at startup if required variables are missing.

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    node_env: str = "development"

    # Observability
    service_name: str = "blockchain-service"
    service_version: str = "1.0.0"
    otel_exporter_otlp_endpoint: str = "http://alloy:4317"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.node_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — loaded once at startup."""
    return Settings()