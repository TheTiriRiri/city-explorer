"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # External APIs
    openweathermap_api_key: str = "your_key_here"
    geonames_username: str = "your_username_here"

    # Cache TTLs (seconds)
    cache_ttl_countries: int = 86400
    cache_ttl_cities: int = 43200
    cache_ttl_wiki: int = 86400
    cache_ttl_weather: int = 600

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
