"""SQLAlchemy 引擎工厂。"""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from settings.config import Settings, get_settings


@lru_cache
def get_engine(settings: Settings | None = None) -> Engine:
    """获取同步引擎（连接池）。"""
    cfg = settings or get_settings()
    return create_engine(
        cfg.database_url,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        echo=cfg.db_echo,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory(settings: Settings | None = None) -> sessionmaker:
    """获取 Session 工厂。"""
    return sessionmaker(bind=get_engine(settings), autoflush=False, autocommit=False)


def dispose_engines() -> None:
    """释放连接池（测试或进程退出时调用）。"""
    try:
        get_engine().dispose()
    finally:
        get_engine.cache_clear()
        get_session_factory.cache_clear()
