"""各域 Redis 存储操作。"""

import uuid

import redis

from service.cache.keys import CacheKeys


class JwtCacheStore:
    """JWT 黑名单与会话索引。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def blacklist_jti(self, jti: uuid.UUID | str, ttl_seconds: int) -> None:
        self._client.setex(CacheKeys.jwt_blacklist(jti), ttl_seconds, "1")

    def is_jti_blacklisted(self, jti: uuid.UUID | str) -> bool:
        return self._client.exists(CacheKeys.jwt_blacklist(jti)) == 1

    def set_revoke_before(self, user_id: uuid.UUID | str, timestamp: int) -> None:
        self._client.set(CacheKeys.jwt_revoke_before(user_id), str(timestamp))

    def get_revoke_before(self, user_id: uuid.UUID | str) -> int | None:
        value = self._client.get(CacheKeys.jwt_revoke_before(user_id))
        return int(value) if value is not None else None

    def add_session_refresh(self, user_id: uuid.UUID | str, refresh_jti: str, ttl: int) -> None:
        key = CacheKeys.jwt_session_index(user_id)
        pipe = self._client.pipeline()
        pipe.sadd(key, refresh_jti)
        pipe.expire(key, ttl)
        pipe.execute()

    def remove_session_refresh(self, user_id: uuid.UUID | str, refresh_jti: str) -> None:
        self._client.srem(CacheKeys.jwt_session_index(user_id), refresh_jti)

    def clear_user_sessions(self, user_id: uuid.UUID | str) -> None:
        self._client.delete(CacheKeys.jwt_session_index(user_id))


class GrantCacheStore:
    """角色授权与 Asset 热缓存。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def set_role_grants(self, role_id: uuid.UUID | str, payload: str, ttl: int = 300) -> None:
        self._client.setex(CacheKeys.role_grants(role_id), ttl, payload)

    def get_role_grants(self, role_id: uuid.UUID | str) -> str | None:
        return self._client.get(CacheKeys.role_grants(role_id))

    def invalidate_role_grants(self, role_id: uuid.UUID | str) -> None:
        self._client.delete(CacheKeys.role_grants(role_id))

    def set_asset(
        self,
        asset_type: str,
        asset_key: str,
        mapping: dict[str, str],
        ttl: int = 300,
    ) -> None:
        key = CacheKeys.asset(asset_type, asset_key)
        pipe = self._client.pipeline()
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, ttl)
        pipe.execute()

    def get_asset(self, asset_type: str, asset_key: str) -> dict[str, str]:
        return self._client.hgetall(CacheKeys.asset(asset_type, asset_key))


class RateLimitCacheStore:
    """接口限流计数。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def increment(
        self,
        scope: str,
        subject: str,
        window: str,
        window_seconds: int,
    ) -> int:
        key = CacheKeys.rate_limit(scope, subject, window)
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        result = pipe.execute()
        return int(result[0])

    def get_count(self, scope: str, subject: str, window: str) -> int:
        value = self._client.get(CacheKeys.rate_limit(scope, subject, window))
        return int(value) if value is not None else 0

    def set_config(self, scope: str, limit: int, window_seconds: int) -> None:
        key = CacheKeys.rate_limit_config(scope)
        self._client.hset(
            key,
            mapping={"limit": str(limit), "window_seconds": str(window_seconds)},
        )

    def get_config(self, scope: str) -> tuple[int, int] | None:
        key = CacheKeys.rate_limit_config(scope)
        data = self._client.hgetall(key)
        if not data:
            return None
        return int(data["limit"]), int(data["window_seconds"])


class QuotaCacheStore:
    """配额热读计数。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def increment_usage(
        self,
        subject_type: str,
        subject_id: uuid.UUID | str,
        quota_type: str,
        period: str,
        amount: int,
        ttl_seconds: int,
    ) -> int:
        key = CacheKeys.quota(subject_type, subject_id, quota_type, period)
        pipe = self._client.pipeline()
        pipe.incrby(key, amount)
        pipe.expire(key, ttl_seconds)
        result = pipe.execute()
        return int(result[0])

    def get_usage(
        self,
        subject_type: str,
        subject_id: uuid.UUID | str,
        quota_type: str,
        period: str,
    ) -> int:
        value = self._client.get(
            CacheKeys.quota(subject_type, subject_id, quota_type, period)
        )
        return int(value) if value is not None else 0


class AgentCacheStore:
    """Agent Flow 编译缓存与 Beat 锁。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def set_compiled_flow(
        self,
        flow_id: uuid.UUID | str,
        version: int,
        payload: str,
        ttl: int = 3600,
    ) -> None:
        self._client.setex(CacheKeys.flow_compiled(flow_id, version), ttl, payload)

    def get_compiled_flow(self, flow_id: uuid.UUID | str, version: int) -> str | None:
        return self._client.get(CacheKeys.flow_compiled(flow_id, version))

    def acquire_beat_lock(self, beat_task_id: uuid.UUID | str, ttl: int) -> bool:
        return bool(
            self._client.set(CacheKeys.beat_lock(beat_task_id), "1", nx=True, ex=ttl)
        )


class KnowledgeCacheStore:
    """知识库入库锁与进度。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def acquire_ingest_lock(self, doc_id: uuid.UUID | str, ttl: int = 3600) -> bool:
        return bool(self._client.set(CacheKeys.ingest_lock(doc_id), "1", nx=True, ex=ttl))

    def release_ingest_lock(self, doc_id: uuid.UUID | str) -> None:
        self._client.delete(CacheKeys.ingest_lock(doc_id))

    def set_ingest_progress(
        self,
        job_id: uuid.UUID | str,
        field: str,
        value: str,
        ttl: int = 3600,
    ) -> None:
        key = CacheKeys.ingest_progress(job_id)
        pipe = self._client.pipeline()
        pipe.hset(key, field, value)
        pipe.expire(key, ttl)
        pipe.execute()


class ConversationCacheStore:
    """会话流式与 SSE 订阅。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def append_stream_delta(self, message_id: uuid.UUID | str, delta: str, ttl: int = 600) -> None:
        key = CacheKeys.stream_buffer(message_id)
        pipe = self._client.pipeline()
        pipe.append(key, delta)
        pipe.expire(key, ttl)
        pipe.execute()

    def get_stream_buffer(self, message_id: uuid.UUID | str) -> str:
        return self._client.get(CacheKeys.stream_buffer(message_id)) or ""

    def add_sse_subscriber(
        self,
        conversation_id: uuid.UUID | str,
        connection_id: str,
        ttl: int,
    ) -> None:
        key = CacheKeys.sse_subscribers(conversation_id)
        pipe = self._client.pipeline()
        pipe.sadd(key, connection_id)
        pipe.expire(key, ttl)
        pipe.execute()


class WorkflowCacheStore:
    """Run 热状态与 HITL 提醒去重。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def set_run_active(
        self,
        run_id: uuid.UUID | str,
        status: str,
        last_event_at: str,
        ttl: int = 86400,
    ) -> None:
        key = CacheKeys.wf_run_active(run_id)
        pipe = self._client.pipeline()
        pipe.hset(key, mapping={"status": status, "last_event_at": last_event_at})
        pipe.expire(key, ttl)
        pipe.execute()

    def get_run_active(self, run_id: uuid.UUID | str) -> dict[str, str]:
        data = self._client.hgetall(CacheKeys.wf_run_active(run_id))
        return dict(data) if data else {}

    def clear_run_active(self, run_id: uuid.UUID | str) -> None:
        self._client.delete(CacheKeys.wf_run_active(run_id))

    def mark_hitl_notify(self, hitl_id: uuid.UUID | str, ttl: int) -> bool:
        return bool(
            self._client.set(CacheKeys.hitl_notify(hitl_id), "1", nx=True, ex=ttl)
        )


class NotificationCacheStore:
    """Webhook 投递去重。"""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def mark_dedupe(
        self,
        endpoint_id: uuid.UUID | str,
        payload_hash: str,
        ttl: int = 86400,
    ) -> bool:
        return bool(
            self._client.set(
                CacheKeys.notify_dedupe(endpoint_id, payload_hash),
                "1",
                nx=True,
                ex=ttl,
            )
        )
