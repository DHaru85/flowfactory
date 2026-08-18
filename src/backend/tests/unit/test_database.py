"""连接与 metadata 冒烟测试。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema import Base  # noqa: E402
from service.database.bootstrap import verify_connection  # noqa: E402
from service.database.engine import get_async_engine  # noqa: E402

EXPECTED_TABLES = {
    "sys_organization",
    "sys_department",
    "sys_user",
    "sys_role",
    "sys_user_role",
    "sys_asset",
    "sys_role_asset_grant",
    "sys_quota",
    "sys_refresh_token",
    "sys_ldap_sync_job",
    "sys_external_identity",
    "conv_conversation",
    "conv_message",
    "wf_thread_snapshot",
    "wf_run_snapshot",
    "wf_hitl_pending",
    "wf_celery_task_record",
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_connection() -> None:
    assert await verify_connection() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expected_tables_exist() -> None:
    engine = get_async_engine()
    async with engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
    missing = EXPECTED_TABLES - tables
    assert not missing, f"缺少表: {missing}"


def test_metadata_registers_models() -> None:
    assert len(Base.metadata.tables) >= len(EXPECTED_TABLES)


def test_async_engine_pool_size_default() -> None:
    from settings.config import get_settings

    settings = get_settings()
    assert settings.db_pool_size == 20
    assert settings.db_max_overflow == 0
    assert "psycopg_async" in settings.async_database_url
