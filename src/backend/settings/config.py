"""应用配置：数据库等。"""

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

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0

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
