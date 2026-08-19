"""FastAPI 依赖：Session、当前用户、工作流入口。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import http_error
from data_schema.permission.models import User
from service.auth.errors import AuthError
from service.auth.schemas import TokenClaims
from service.auth.service import AuthService
from service.database.session import get_db_session, session_scope
from service.persistence.factory import get_repositories
from service.runtime.schemas import StartRunRequest
from service.runtime.service import WorkflowRuntimeService

_bearer = HTTPBearer(auto_error=False)

_runtime_override: WorkflowRuntimeService | None = None


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    organization_id: UUID
    username: str
    roles: list[str]
    claims: TokenClaims


def set_workflow_runtime_override(service: WorkflowRuntimeService | None) -> None:
    global _runtime_override
    _runtime_override = service


def get_workflow_runtime() -> WorkflowRuntimeService:
    if _runtime_override is not None:
        return _runtime_override
    return WorkflowRuntimeService()


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise http_error(401, "token_missing", "缺少 Bearer Token")
    auth = AuthService(session)
    try:
        claims = await auth.verify_access_token(credentials.credentials)
    except AuthError as exc:
        raise http_error(401, exc.code, exc.message) from exc
    repos = get_repositories(session)
    user: User | None = await repos.permission.user.get(claims.sub)
    if user is None:
        raise http_error(401, "token_revoked", "用户不存在")
    return CurrentUser(
        id=user.id,
        organization_id=user.organization_id,
        username=user.username,
        roles=list(claims.roles),
        claims=claims,
    )


async def get_current_user_detached(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """短会话鉴权：供 SSE 使用，避免请求级 Session 占到连接结束。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise http_error(401, "token_missing", "缺少 Bearer Token")
    async with session_scope() as session:
        auth = AuthService(session)
        try:
            claims = await auth.verify_access_token(credentials.credentials)
        except AuthError as exc:
            raise http_error(401, exc.code, exc.message) from exc
        repos = get_repositories(session)
        user = await repos.permission.user.get(claims.sub)
        if user is None:
            raise http_error(401, "token_revoked", "用户不存在")
        return CurrentUser(
            id=user.id,
            organization_id=user.organization_id,
            username=user.username,
            roles=list(claims.roles),
            claims=claims,
        )


class FakeWorkflowRuntime(WorkflowRuntimeService):
    """测试替身：不入队 Celery。"""

    def __init__(self) -> None:
        self.requests: list[StartRunRequest] = []

    async def start(self, request: StartRunRequest) -> UUID:
        self.requests.append(request)
        return uuid4()
