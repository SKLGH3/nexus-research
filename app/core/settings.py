"""Application settings and integration readiness helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    debug: bool
    cors_origins: tuple[str, ...]
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str
    tavily_api_key: str
    ragflow_api_url: str
    ragflow_api_key: str
    database_driver: str
    sqlite_path: Path
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_charset: str
    mysql_collation: str
    mysql_sql_mode: str
    max_upload_mb: int
    app_database_path: Path
    auth_secret: str
    auth_token_hours: int
    allow_registration: bool
    admin_email: str
    admin_password: str
    admin_name: str
    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_model and self.llm_api_key)

    @property
    def search_ready(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def ragflow_ready(self) -> bool:
        return bool(self.ragflow_api_url and self.ragflow_api_key)

    @property
    def database_ready(self) -> bool:
        if self.database_driver == "sqlite":
            return True
        return bool(self.mysql_user and self.mysql_database)

    def public_summary(self) -> dict:
        return {
            "app_name": self.app_name,
            "version": self.app_version,
            "environment": self.environment,
            "model": {
                "provider": self.llm_provider,
                "name": self.llm_model or "未配置",
                "base_url": self.llm_base_url or "供应商默认地址",
                "ready": self.llm_ready,
            },
            "integrations": {
                "database": {
                    "driver": self.database_driver,
                    "ready": self.database_ready,
                },
                "web_search": {"provider": "tavily", "ready": self.search_ready},
                "knowledge_base": {"provider": "ragflow", "ready": self.ragflow_ready},
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    sqlite_default = APP_DIR / "data" / "nexus_demo.db"
    return Settings(
        app_name=os.getenv("APP_NAME", "NEXUS Research"),
        app_version=os.getenv("APP_VERSION", "2.0.0"),
        environment=os.getenv("APP_ENV", "development"),
        debug=_env_bool("APP_DEBUG", True),
        cors_origins=_env_list(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_model=(
            os.getenv("LLM_MODEL")
            or os.getenv("LLM_MODEL_NAME")
            or os.getenv("LLM_QWEN_MAX", "")
        ),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        ragflow_api_url=os.getenv("RAGFLOW_API_URL", ""),
        ragflow_api_key=os.getenv("RAGFLOW_API_KEY", ""),
        database_driver=os.getenv("DATABASE_DRIVER", "sqlite").strip().lower(),
        sqlite_path=Path(os.getenv("SQLITE_PATH", str(sqlite_default))).expanduser().resolve(),
        mysql_host=os.getenv("MYSQL_HOST", "localhost"),
        mysql_port=int(os.getenv("MYSQL_PORT", "3307")),
        mysql_user=os.getenv("MYSQL_USER", "root"),
        mysql_password=os.getenv("MYSQL_PASSWORD", "root"),
        mysql_database=os.getenv("MYSQL_DATABASE", "nexus_research"),
        mysql_charset=os.getenv("MYSQL_CHARSET", "utf8mb4"),
        mysql_collation=os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        mysql_sql_mode=os.getenv("MYSQL_SQL_MODE", "TRADITIONAL"),
        max_upload_mb=max(1, int(os.getenv("MAX_UPLOAD_MB", "20"))),
        app_database_path=Path(
            os.getenv("APP_DATABASE_PATH", str(APP_DIR / "data" / "nexus_app.db"))
        ).expanduser().resolve(),
        auth_secret=os.getenv("AUTH_SECRET", "change-this-local-development-secret"),
        auth_token_hours=max(1, int(os.getenv("AUTH_TOKEN_HOURS", "24"))),
        allow_registration=_env_bool("AUTH_ALLOW_REGISTRATION", True),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@nexus.local").strip().lower(),
        admin_password=os.getenv("ADMIN_PASSWORD", "Nexus@2026"),
        admin_name=os.getenv("ADMIN_NAME", "NEXUS 管理员"),
    )


def configure_openai_compat_env(settings: Settings | None = None) -> None:
    """Expose generic LLM settings to OpenAI-compatible client libraries."""
    current = settings or get_settings()
    if current.llm_api_key:
        os.environ["OPENAI_API_KEY"] = current.llm_api_key
    if current.llm_base_url:
        os.environ["OPENAI_BASE_URL"] = current.llm_base_url



