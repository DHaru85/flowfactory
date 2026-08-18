"""仓储层单元测试（不依赖数据库）。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema import Base  # noqa: E402


def test_new_domain_models_registered() -> None:
    expected = {
        "agent_llm",
        "agent_mcp_server",
        "agent_skill",
        "agent_tool",
        "agent_profile",
        "agent_flow",
        "agent_beat_task",
        "agent_checkpoint_schema",
        "kb_collection",
        "kb_doc",
        "kb_section",
        "kb_chunk",
        "kb_ingestion_job",
        "file_record",
        "file_storage_object",
        "file_version",
        "file_upload_session",
        "audit_asset_obtain",
        "audit_asset_consume",
        "audit_activity",
        "graph_node",
        "graph_edge",
        "graph_entity_link",
        "sec_guardrail_rule",
        "sec_policy_violation",
        "obs_trace",
        "obs_span",
        "obs_llm_call",
        "obs_tool_invocation",
        "obs_prompt_snapshot",
        "notify_webhook_endpoint",
        "notify_delivery_log",
    }
    tables = set(Base.metadata.tables.keys())
    missing = expected - tables
    assert not missing, f"缺少表定义: {missing}"
