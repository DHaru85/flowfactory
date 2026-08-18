"""Session 上下文与依赖注入。"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from service.database.engine import get_session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """事务上下文：成功 commit，异常 rollback。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级 session。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
