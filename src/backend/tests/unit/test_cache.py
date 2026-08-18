"""Redis 缓存 key 单元测试（不依赖 Redis）。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.cache.keys import CacheKeys  # noqa: E402


def test_cache_keys_format() -> None:
    assert CacheKeys.jwt_blacklist("abc") == "auth:jwt:blacklist:abc"
    assert CacheKeys.rate_limit("user", "1", "chat") == "sec:ratelimit:user:1:chat"
    assert CacheKeys.quota("org", "uuid", "tokens", "daily") == "auth:quota:org:uuid:tokens:daily"
    assert CacheKeys.flow_compiled("flow-1", 2) == "agent:flow:compiled:flow-1:2"
    assert CacheKeys.ingest_progress("job-1") == "kb:ingest:progress:job-1"
    assert CacheKeys.stream_buffer("msg-1") == "conv:stream:msg-1"
    assert CacheKeys.notify_dedupe("ep-1", "hash") == "notify:dedupe:ep-1:hash"
    assert CacheKeys.wf_run_active("run-1") == "wf:run:active:run-1"
    assert CacheKeys.hitl_notify("hitl-1") == "wf:hitl:notify:hitl-1"
    assert CacheKeys.beat_lock("beat-1") == "agent:beat:lock:beat-1"
