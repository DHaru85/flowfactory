"""应用配置：数据库等。"""

import uuid
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行时配置，支持环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="FLOWFACTORY_",
        env_file=".env",
        extra="ignore",
    )

    pg_host: str = "192.168.129.53"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = "Hisign123"
    pg_database: str = "flowfactory"
    pg_admin_database: str = "postgres"

    db_pool_size: int = 20
    db_max_overflow: int = 0
    db_echo: bool = False
    checkpoint_pool_size: int = 10

    redis_host: str = "192.168.129.53"
    redis_port: int = 6479
    redis_password: str | None = None
    redis_db: int = 4

    celery_eager: bool = True
    rabbitmq_url: str = ""
    celery_queue_run: str = "wf.run"
    celery_queue_beat: str = "wf.beat"
    celery_worker_concurrency: int = 4
    celery_task_time_limit: int = 3600
    celery_task_soft_time_limit: int = 3300

    temporal_enabled: bool = False
    temporal_host: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "flowfactory-saga"

    beat_system_user_id: str | None = None
    beat_tick_seconds: int = 60
    hitl_default_ttl_seconds: int = 86400

    llm_base_url: str = "http://192.168.129.50:8122/v1"
    llm_api_key: str = ""
    llm_model_name: str = "qwen35_122b_a10b"

    @property
    def postgres_dsn(self) -> str:
        """psycopg / LangGraph checkpointer 使用的 DSN。"""
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def beat_system_user_uuid(self) -> uuid.UUID | None:
        if not self.beat_system_user_id:
            return None
        return uuid.UUID(self.beat_system_user_id)

    @property
    def celery_broker_url(self) -> str:
        if self.rabbitmq_url:
            return self.rabbitmq_url
        return "memory://"

    @property
    def llm_api_key_or_empty_placeholder(self) -> str:
        """vLLM 不校验 key；OpenAI SDK 不允许空字符串。"""
        return self.llm_api_key if self.llm_api_key else "EMPTY"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@{self.redis_host}:"
                f"{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def sync_database_url(self) -> str:
        """同步连接 URL（Alembic、bootstrap 等）。"""
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def async_database_url(self) -> str:
        """异步连接 URL（FastAPI 运行时）。"""
        return (
            f"postgresql+psycopg_async://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def database_url(self) -> str:
        """兼容 Alembic env：等同 sync_database_url。"""
        return self.sync_database_url

    @property
    def admin_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_admin_database}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """测试或 worker fork 后清除配置缓存。"""
    get_settings.cache_clear()
