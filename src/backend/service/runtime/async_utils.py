"""在 Celery prefork / eager 场景下安全执行协程。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Callable, Coroutine
from typing import TypeVar

T = TypeVar("T")


def run_coro_factory(factory: Callable[[], Coroutine[object, object, T]]) -> T:
    """在独立事件循环中运行 factory() 产生的协程，避免跨 loop 绑定。"""

    def _in_new_loop() -> T:
        return asyncio.run(factory())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _in_new_loop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_in_new_loop).result()
