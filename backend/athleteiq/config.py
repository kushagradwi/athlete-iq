from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./athleteiq.db"
    redis_url: str = "redis://localhost:6379/0"
    job_mode: str = "inline"  # "inline" (synchronous) or "queue" (Dramatiq worker)

    storage: str = "local"  # "local" or "s3"
    local_storage_dir: str = "./storage"
    s3_endpoint: str | None = None
    s3_bucket: str = "athleteiq-raw"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    gc_api_url: str = "http://localhost:12021"
    gc_athlete: str | None = None
    gc_autoimport_dir: str | None = None

    max_upload_mb: int = 100
    cors_origins: str = "http://localhost:3000"

    # Discovery ranking weights (must sum to 1)
    rank_w_novelty: float = 0.20
    rank_w_magnitude: float = 0.25
    rank_w_confidence: float = 0.25
    rank_w_goal: float = 0.15
    rank_w_action: float = 0.15


@lru_cache
def settings() -> Settings:
    return Settings()
