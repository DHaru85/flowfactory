"""鉴权路由：登录 / 刷新 / 登出 / 当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.apps.auth.schemas import LoginBody, LogoutBody, RefreshBody
from api.deps import CurrentUser, db_session, get_current_user
from api.errors import auth_error_to_http
from service.auth.errors import AuthError
from service.auth.schemas import (
    LoginCredentials,
    LogoutRequest,
    RefreshTokenRequest,
    TokenPairResponse,
)
from service.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return None
    return request.client.host


@router.post("/login", response_model=TokenPairResponse)
async def login(
    body: LoginBody,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> TokenPairResponse:
    auth = AuthService(session)
    try:
        return await auth.login(
            LoginCredentials(
                username=body.username,
                password=body.password,
                user_agent=request.headers.get("user-agent"),
                client_ip=_client_ip(request),
            )
        )
    except AuthError as exc:
        raise auth_error_to_http(exc) from exc


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshBody,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> TokenPairResponse:
    auth = AuthService(session)
    try:
        return await auth.refresh(
            RefreshTokenRequest(
                refresh_token=body.refresh_token,
                user_agent=request.headers.get("user-agent"),
                client_ip=_client_ip(request),
            )
        )
    except AuthError as exc:
        raise auth_error_to_http(exc) from exc


@router.post("/logout")
async def logout(
    body: LogoutBody,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    auth = AuthService(session)
    try:
        await auth.logout(
            LogoutRequest(
                access_jti=current.claims.jti,
                refresh_token=body.refresh_token,
                access_exp=current.claims.exp,
            )
        )
    except AuthError as exc:
        raise auth_error_to_http(exc) from exc
    return {"status": "ok"}


@router.get("/me")
async def me(current: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    return {
        "id": str(current.id),
        "username": current.username,
        "organization_id": str(current.organization_id),
        "roles": current.roles,
    }
