"""Redis 客户端工厂。"""

from functools import lru_cache

import redis

from settings.config import Settings, get_settings


@lru_cache
def get_redis_client(settings: Settings | None = None) -> redis.Redis:
    """获取 Redis 客户端（decode_responses=True）。"""
    cfg = settings or get_settings()
    return redis.Redis.from_url(
        cfg.redis_url,
        decode_responses=True,
    )


def reset_redis_client() -> None:
    get_redis_client.cache_clear()
