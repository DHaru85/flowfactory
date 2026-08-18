"""SQLAlchemy 异步引擎工厂。"""

import threading

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings.config import Settings, get_settings

_thread_state = threading.local()


def get_async_engine(settings: Settings | None = None) -> AsyncEngine:
    """获取当前线程的异步引擎（连接池，默认最大 20 连接）。"""
    engine = getattr(_thread_state, "engine", None)
    if engine is None:
        cfg = settings or get_settings()
        engine = create_async_engine(
            cfg.async_database_url,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            echo=cfg.db_echo,
            pool_pre_ping=True,
        )
        _thread_state.engine = engine
    return engine


def get_async_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """获取当前线程的 AsyncSession 工厂。"""
    factory = getattr(_thread_state, "session_factory", None)
    if factory is None:
        factory = async_sessionmaker(
            bind=get_async_engine(settings),
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )
        _thread_state.session_factory = factory
    return factory


async def dispose_engines() -> None:
    """释放当前线程连接池。"""
    engine = getattr(_thread_state, "engine", None)
    try:
        if engine is not None:
            await engine.dispose()
    finally:
        _thread_state.engine = None
        _thread_state.session_factory = None
