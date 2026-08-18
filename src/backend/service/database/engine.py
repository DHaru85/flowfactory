"""SQLAlchemy 异步引擎工厂。"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings.config import Settings, get_settings


@lru_cache
def get_async_engine(settings: Settings | None = None) -> AsyncEngine:
    """获取异步引擎（连接池，默认最大 20 连接）。"""
    cfg = settings or get_settings()
    return create_async_engine(
        cfg.async_database_url,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        echo=cfg.db_echo,
        pool_pre_ping=True,
    )


@lru_cache
def get_async_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """获取 AsyncSession 工厂。"""
    return async_sessionmaker(
        bind=get_async_engine(settings),
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


async def dispose_engines() -> None:
    """释放连接池（测试或进程退出时调用）。"""
    try:
        await get_async_engine().dispose()
    finally:
        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()
