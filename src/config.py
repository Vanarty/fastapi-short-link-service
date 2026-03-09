from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/linkshortener"
    redis_url: str = "redis://redis:6379/0"
    secret_key: str = "change-me-to-random-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    short_code_length: int = 6
    cache_ttl_seconds: int = 3600
    unused_link_days: int = 90
    cleanup_interval_minutes: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
