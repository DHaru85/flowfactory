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
    celery_eager_join: bool = False
    rabbitmq_url: str = "amqp://admin:Hisign123@192.168.129.53:5672/"
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
    planner_max_steps: int = 8

    minio_endpoint: str = "192.168.129.53:9400"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "flowfactory"
    minio_secure: bool = False
    minio_public: bool = True

    embedding_base_url: str = "http://192.168.129.53:9997/v1"
    embedding_api_key: str = ""
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32

    kb_chunk_strategy: str = "recursive"
    kb_chunk_size: int = 800
    kb_chunk_overlap: int = 120
    kb_fts_config: str = "simple"
    kb_retrieve_top_k: int = 20
    kb_rrf_k: int = 60
    kb_rerank_top_n: int = 10
    kb_rerank_onnx_path: str = ""
    kb_rerank_tokenizer_path: str = ""
    kb_rerank_max_length: int = 512

    celery_queue_ingest: str = "kb.ingest"

    stream_exchange: str = "ff.stream"
    stream_prefetch: int = 4
    stream_queue_maxsize: int = 256
    stream_connect_timeout_seconds: float = 8.0
    stream_publish_timeout_seconds: float = 0.2

    jwt_secret: str = "flowfactory-dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1_209_600
    jwt_issuer: str = "flowfactory"

    ldap_enabled: bool = False
    ldap_host: str = ""
    ldap_port: int = 389
    ldap_use_tls: bool = False
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_group_search_base: str = ""
    ldap_user_filter: str = "(uid={username})"
    ldap_username_attr: str = "uid"
    ldap_default_org_code: str = ""
    ldap_sync_beat_enabled: bool = False

    otel_service_name: str = "flowfactory"
    otel_enabled: bool = True
    otel_otlp_endpoint: str = ""

    langfuse_enabled: bool = False
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    obs_redact_extra_patterns: str = ""

    tool_http_timeout_seconds: float = 30.0
    tool_http_max_body_bytes: int = 1_048_576

    guardrail_enabled: bool = True
    guardrail_builtin_rules: bool = True
    guardrail_policy_url: str = ""
    guardrail_policy_timeout_seconds: float = 2.0
    guardrail_excerpt_max_chars: int = 200

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
    def embedding_api_key_or_empty_placeholder(self) -> str:
        return self.embedding_api_key if self.embedding_api_key else "EMPTY"

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
