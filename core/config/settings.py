from __future__ import annotations

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def load_docker_secrets(cls, data: dict) -> dict:
        """Carga secretos desde Docker Secrets (/run/secrets) si existen."""

        def get_secret(name: str) -> str | None:
            path = f"/run/secrets/{name}"
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except OSError as exc:
                    raise ValueError(
                        f"No se pudo leer el secreto Docker '{name}'."
                    ) from exc
            return None

        # Reemplazar secretos simples si existen en archivos de secretos
        secret_keys = ["jwt_secret", "admin_api_key", "telegram_bot_token"]
        for key in secret_keys:
            val = get_secret(key)
            if val:
                data[key] = val

        # Ajuste de base de datos
        db_pass = get_secret("db_password")
        if db_pass:
            db_url = (
                data.get("database_url")
                or os.environ.get("DATABASE_URL")
                or "postgresql://shared:shared_secret@127.0.0.1:5433/chatbot"
            )
            if db_url and "@" in db_url and "://" in db_url:
                try:
                    proto, rest = db_url.split("://", 1)
                    auth, host_db = rest.split("@", 1)
                    user = auth.split(":", 1)[0] if ":" in auth else auth
                    data["database_url"] = f"{proto}://{user}:{db_pass}@{host_db}"
                except ValueError as exc:
                    raise ValueError(
                        "No se pudo reconstruir DATABASE_URL con el secreto db_password."
                    ) from exc

        return data

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "postgresql://shared:shared_secret@127.0.0.1:5433/chatbot"
    db_echo: bool = False

    # ── LLM (OpenRouter via LiteLlm, patrón wmill) ───────────────
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    groq_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_thinking: str = "disabled"
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

    # ── ARQ Worker / Jobs ────────────────────────────────────────
    arq_enabled: bool = True
    arq_queue_name: str = "chatbot:jobs"
    arq_job_timeout_seconds: int = 300
    arq_job_max_tries: int = 5
    arq_job_result_ttl_seconds: int = 3600
    arq_health_check_key: str = "chatbot:jobs:health"

    # ── Business configuration ─────────────────────────────────
    business_name: str = "Mi Negocio"
    business_email: str = "contacto@minegocio.com"
    business_phone: str = "+56912345678"
    business_address: str = "Calle Principal 123"
    business_city: str = "Santiago"
    business_website: str = ""
    business_hours: str = ""
    reset_demo_catalog_on_start: bool = False

    # ── App ──────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    ui_language: str = "es-CL"

    # ── Security & Channels ──────────────────────────────────────
    telegram_bot_token: str = ""
    admin_api_key: str = ""
    jwt_secret: str = ""
    allowed_origins: str = "http://localhost:8083"
    tenant_invite_ttl_hours: int = 6
    tenant_access_token_ttl_minutes: int = 15
    tenant_refresh_token_ttl_days: int = 14
    tenant_access_cookie_name: str = "tenant_access_token"
    tenant_refresh_cookie_name: str = "tenant_refresh_token"

    @model_validator(mode="after")
    def validate_production_cors(self) -> "Settings":
        """Impide configuraciones CORS inseguras cuando la app corre en producción."""
        origins = [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]
        if self.is_production and "*" in origins:
            raise ValueError("APP_ENV=production no permite ALLOWED_ORIGINS='*'")
        return self

    @property
    def is_production(self) -> bool:
        """Indica si la aplicación está ejecutándose en modo producción."""
        return self.app_env == "production"

    @property
    def use_redis_sessions(self) -> bool:
        """Indica si el backend de sesiones efectivo debe usar Redis."""
        return self.session_backend.lower() == "redis"

    @property
    def secure_cookies(self) -> bool:
        """Activa cookies seguras cuando la app no corre en localhost de desarrollo."""
        return self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Construye y cachea la configuración global desde variables de entorno."""
    return Settings()


settings = get_settings()
