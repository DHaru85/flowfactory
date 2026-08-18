"""创建 flowfactory 数据库（若不存在）。"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from settings.config import Settings, get_settings


def ensure_database_exists(settings: Settings | None = None) -> None:
    """连接 admin 库，CREATE DATABASE flowfactory。"""
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


def verify_connection(engine: Engine | None = None) -> bool:
    """探测数据库连通性。"""
    from service.database.engine import get_engine

    eng = engine or get_engine()
    with eng.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar() == 1
