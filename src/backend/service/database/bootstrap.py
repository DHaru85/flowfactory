"""创建 flowfactory 数据库（若不存在）。"""

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from settings.config import Settings, get_settings


def ensure_database_exists(settings: Settings | None = None) -> None:
    """连接 admin 库，CREATE DATABASE flowfactory（同步，一次性运维操作）。"""
    cfg = settings or get_settings()
    admin_engine = create_engine(
        cfg.admin_database_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": cfg.pg_database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{cfg.pg_database}"'))
    finally:
        admin_engine.dispose()


async def verify_connection(engine: AsyncEngine | None = None) -> bool:
    """探测数据库连通性（异步）。"""
    from service.database.engine import get_async_engine

    eng = engine or get_async_engine()
    async with eng.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar() == 1
