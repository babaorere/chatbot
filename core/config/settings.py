from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "sqlite:///./chatbot.db"
    db_echo: bool = False

    # ── LLM (OpenRouter via LiteLlm, patrón wmill) ───────────────
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    groq_api_key: str = ""
    model_name: str = "nvidia_nim/google/gemma-4-31b-it"
    model_display: str = "gemma-4-31b-it"
    fallback_model_1: str = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    fallback_model_2: str = "groq/llama3-8b-8192"

    # ── Session backend ──────────────────────────────────────────
    session_backend: str = "redis"

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_namespace: str = "chatbot:adk:v1"
    redis_session_ttl_seconds: int = 86400
    redis_lock_timeout_seconds: int = 15
    redis_lock_blocking_timeout_seconds: float = 5.0
    redis_health_check_interval: int = 30
    redis_socket_timeout_seconds: float = 5.0
    redis_socket_connect_timeout_seconds: float = 5.0
    redis_max_connections: int = 100
    redis_retry_attempts: int = 3

    # ── App ──────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def use_redis_sessions(self) -> bool:
        return self.session_backend.lower() == "redis"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
