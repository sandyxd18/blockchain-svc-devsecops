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

    # CORS — comma-separated origins. Falls back to localhost defaults.
    cors_allowed_origins: str = "http://localhost,http://localhost:80,http://localhost:8081,http://localhost:5173,http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS into a list of origin strings."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.node_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — loaded once at startup."""
    return Settings()