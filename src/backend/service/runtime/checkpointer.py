"""LangGraph Postgres / 内存 checkpointer 工厂。"""

from __future__ import annotations

import threading

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from settings.config import get_settings

_thread_state = threading.local()
_override: BaseCheckpointSaver | None = None


def set_checkpointer_override(saver: BaseCheckpointSaver | None) -> None:
    """测试注入 MemorySaver 等。"""
    global _override
    _override = saver


async def get_checkpointer() -> BaseCheckpointSaver:
    if _override is not None:
        return _override
    return await get_postgres_checkpointer()


async def get_postgres_checkpointer() -> AsyncPostgresSaver:
    saver = getattr(_thread_state, "saver", None)
    if saver is not None:
        return saver
    cfg = get_settings()
    pool = AsyncConnectionPool(
        conninfo=cfg.postgres_dsn,
        min_size=1,
        max_size=cfg.checkpoint_pool_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=False,
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    setup_done = getattr(_thread_state, "setup_done", False)
    if not setup_done:
        await saver.setup()
        _thread_state.setup_done = True
        logger.info("LangGraph Postgres checkpointer 表已就绪")
    _thread_state.pool = pool
    _thread_state.saver = saver
    return saver


def new_memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


async def reset_checkpointer() -> None:
    global _override
    _override = None
    pool = getattr(_thread_state, "pool", None)
    if pool is not None:
        await pool.close()
    _thread_state.pool = None
    _thread_state.saver = None
    _thread_state.setup_done = False
