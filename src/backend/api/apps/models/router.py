"""公共模型目录 REST。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.access import require_app
from api.apps.models.schemas import LlmCreateBody, LlmOut, LlmPatchBody, redact_llm_config
from api.deps import CurrentUser, db_session
from api.errors import http_error
from data_schema.agent.models import AgentLlm
from service.persistence.factory import get_repositories

router = APIRouter(prefix="/api/v1/models", tags=["models"])

_use_models = require_app("models")
_ctrl_models = require_app("models", control=True)

_PROVIDERS = frozenset({"openai", "azure", "local"})


def _to_out(row: AgentLlm) -> LlmOut:
    cfg = dict(row.config) if isinstance(row.config, dict) else {}
    public, has_key = redact_llm_config(cfg)
    return LlmOut(
        id=row.id,
        code=row.code,
        provider=row.provider,
        model_name=row.model_name,
        is_active=row.is_active,
        config=public,
        has_api_key=has_key,
    )


def _require_provider(provider: str) -> None:
    if provider not in _PROVIDERS:
        raise http_error(400, "provider_invalid", "provider 须为 openai / azure / local")


def _require_config_base_url(config: dict[str, object]) -> None:
    raw = config.get("base_url")
    if raw is None:
        return
    if not isinstance(raw, str) or not (
        raw.startswith("http://") or raw.startswith("https://")
    ):
        raise http_error(
            400, "llm_base_url_invalid", "config.base_url 须以 http:// 或 https:// 开头"
        )


@router.get("/llms", response_model=list[LlmOut])
async def list_llms(
    _current: CurrentUser = Depends(_use_models),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
    is_active: bool | None = Query(default=None),
) -> list[LlmOut]:
    repos = get_repositories(session)
    rows = await repos.agent.list_llms(offset=offset, limit=min(limit, 100), is_active=is_active)
    return [_to_out(row) for row in rows]


@router.post("/llms", response_model=LlmOut)
async def create_llm(
    body: LlmCreateBody,
    _current: CurrentUser = Depends(_ctrl_models),
    session: AsyncSession = Depends(db_session),
) -> LlmOut:
    _require_provider(body.provider)
    _require_config_base_url(dict(body.config))
    repos = get_repositories(session)
    row = AgentLlm(
        code=body.code,
        provider=body.provider,
        model_name=body.model_name,
        config=dict(body.config),
        is_active=body.is_active,
    )
    try:
        await repos.agent.llm.add(row)
        await session.flush()
    except IntegrityError as exc:
        raise http_error(409, "llm_code_conflict", "LLM code 已存在") from exc
    logger.info("创建 LLM id={} code={}", row.id, row.code)
    return _to_out(row)


@router.get("/llms/{llm_id}", response_model=LlmOut)
async def get_llm(
    llm_id: UUID,
    _current: CurrentUser = Depends(_use_models),
    session: AsyncSession = Depends(db_session),
) -> LlmOut:
    repos = get_repositories(session)
    row = await repos.agent.llm.get(llm_id)
    if row is None:
        raise http_error(404, "llm_not_found", "模型不存在")
    return _to_out(row)


@router.patch("/llms/{llm_id}", response_model=LlmOut)
async def patch_llm(
    llm_id: UUID,
    body: LlmPatchBody,
    _current: CurrentUser = Depends(_ctrl_models),
    session: AsyncSession = Depends(db_session),
) -> LlmOut:
    repos = get_repositories(session)
    row = await repos.agent.llm.get(llm_id)
    if row is None:
        raise http_error(404, "llm_not_found", "模型不存在")
    if body.provider is not None:
        _require_provider(body.provider)
        row.provider = body.provider
    if body.model_name is not None:
        row.model_name = body.model_name
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.config is not None:
        old = dict(row.config) if isinstance(row.config, dict) else {}
        merged = dict(body.config)
        incoming_key = merged.get("api_key")
        if "api_key" not in body.config or incoming_key is None or incoming_key == "":
            old_key = old.get("api_key")
            if isinstance(old_key, str) and old_key:
                merged["api_key"] = old_key
            else:
                merged.pop("api_key", None)
        row.config = merged
        _require_config_base_url(merged)
    return _to_out(row)


@router.post("/llms/{llm_id}/deactivate", response_model=LlmOut)
async def deactivate_llm(
    llm_id: UUID,
    _current: CurrentUser = Depends(_ctrl_models),
    session: AsyncSession = Depends(db_session),
) -> LlmOut:
    repos = get_repositories(session)
    row = await repos.agent.llm.get(llm_id)
    if row is None:
        raise http_error(404, "llm_not_found", "模型不存在")
    row.is_active = False
    logger.info("停用 LLM id={}", row.id)
    return _to_out(row)
