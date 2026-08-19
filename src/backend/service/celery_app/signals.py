"""Celery worker 信号处理：prefork 后重建连接。"""

from celery.signals import worker_process_init
from loguru import logger


@worker_process_init.connect
def rebuild_process_clients(**_kwargs: object) -> None:
    from service.cache.client import reset_redis_client
    from service.runtime.checkpointer import reset_checkpointer
    from settings.config import reset_settings

    reset_settings()
    reset_redis_client()
    from service.observability.collector import reset_observability_context

    reset_observability_context()

    async def _reset() -> None:
        from service.database.engine import dispose_engines

        await dispose_engines()
        await reset_checkpointer()

    from service.runtime.async_utils import run_coro_factory

    run_coro_factory(_reset)
    logger.info("Celery worker 子进程已重建 DB/Redis/checkpointer/观测 客户端")
