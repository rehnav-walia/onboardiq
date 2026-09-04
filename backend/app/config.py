from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunable values live here and are sourced from the environment.

    Nothing in this module hardcodes a threshold, timeout, path, or secret —
    see CLAUDE.md conventions.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./data/onboarding.db"
    storage_root: str = "./storage"
    max_upload_size_mb: int = 10
    allowed_origins: str = "http://localhost:5173"
    reference_id_prefix: str = "ONB"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
