"""Redis Key 命名规范（对齐 data_schema_server.md）。"""

import uuid


class CacheKeys:
    """缓存 key 构建器。"""

    @staticmethod
    def jwt_blacklist(jti: uuid.UUID | str) -> str:
        return f"auth:jwt:blacklist:{jti}"

    @staticmethod
    def jwt_revoke_before(user_id: uuid.UUID | str) -> str:
        return f"auth:jwt:revoke_before:{user_id}"

    @staticmethod
    def jwt_session_index(user_id: uuid.UUID | str) -> str:
        return f"auth:session:index:{user_id}"

    @staticmethod
    def asset(asset_type: str, asset_key: str) -> str:
        return f"auth:asset:{asset_type}:{asset_key}"

    @staticmethod
    def role_grants(role_id: uuid.UUID | str) -> str:
        return f"auth:role_grants:{role_id}"

    @staticmethod
    def quota(
        subject_type: str,
        subject_id: uuid.UUID | str,
        quota_type: str,
        period: str,
    ) -> str:
        return f"auth:quota:{subject_type}:{subject_id}:{quota_type}:{period}"

    @staticmethod
    def rate_limit(scope: str, subject: str, window: str) -> str:
        return f"sec:ratelimit:{scope}:{subject}:{window}"

    @staticmethod
    def rate_limit_config(scope: str) -> str:
        return f"sec:ratelimit:cfg:{scope}"

    @staticmethod
    def flow_compiled(flow_id: uuid.UUID | str, version: int) -> str:
        return f"agent:flow:compiled:{flow_id}:{version}"

    @staticmethod
    def beat_lock(beat_task_id: uuid.UUID | str) -> str:
        return f"agent:beat:lock:{beat_task_id}"

    @staticmethod
    def ingest_lock(doc_id: uuid.UUID | str) -> str:
        return f"kb:ingest:lock:{doc_id}"

    @staticmethod
    def ingest_progress(job_id: uuid.UUID | str) -> str:
        return f"kb:ingest:progress:{job_id}"

    @staticmethod
    def stream_buffer(message_id: uuid.UUID | str) -> str:
        return f"conv:stream:{message_id}"

    @staticmethod
    def sse_subscribers(conversation_id: uuid.UUID | str) -> str:
        return f"conv:sse:subscribers:{conversation_id}"

    @staticmethod
    def upload_parts(session_id: uuid.UUID | str) -> str:
        return f"file:upload:parts:{session_id}"

    @staticmethod
    def notify_dedupe(endpoint_id: uuid.UUID | str, payload_hash: str) -> str:
        return f"notify:dedupe:{endpoint_id}:{payload_hash}"

    @staticmethod
    def wf_run_active(run_id: uuid.UUID | str) -> str:
        return f"wf:run:active:{run_id}"

    @staticmethod
    def hitl_notify(hitl_id: uuid.UUID | str) -> str:
        return f"wf:hitl:notify:{hitl_id}"
