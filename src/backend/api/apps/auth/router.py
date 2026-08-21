"""鉴权路由：登录 / 刷新 / 登出 / 当前用户 / 应用可见性。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.access import require_app, require_platform_admin
from api.apps.agent_config.access import load_bindings, save_bindings
from api.apps.agent_config.schemas import BindingItem, BindingPutBody
from api.apps.auth.schemas import (
    AppVisibilityOut,
    LoginBody,
    LogoutBody,
    RefreshBody,
    RegisterBody,
    UserOut,
    UserStatusPatch,
)
from api.deps import CurrentUser, db_session, get_current_user
from api.errors import auth_error_to_http, http_error
from api.registry.application import ApplicationRegistry
from data_schema.permission.models import Asset, User
from service.auth.access import AccessControl
from service.auth.errors import AuthError
from service.auth.schemas import (
    LoginCredentials,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPairResponse,
)
from service.auth.service import AuthService
from service.persistence.factory import get_repositories

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_ctrl_auth = require_app("auth", control=True)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return None
    return request.client.host


async def _require_app_asset_id(
    session: AsyncSession,
    apps: ApplicationRegistry,
    app_key: str,
) -> UUID:
    if app_key not in apps.list_keys():
        raise http_error(404, "app_not_found", "应用不存在")
    repos = get_repositories(session)
    asset = await repos.permission.get_asset_by_key("application", app_key)
    if asset is None:
        application = apps.get(app_key)
        await repos.permission.asset.add(
            Asset(
                asset_type="application",
                asset_key=app_key,
                name=application.name,
                metadata_={},
            )
        )
        await session.flush()
        asset = await repos.permission.get_asset_by_key("application", app_key)
        if asset is None:
            raise http_error(404, "app_not_found", "应用不存在")
    return asset.id


def _user_out(row: User) -> UserOut:
    return UserOut(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        status=row.status,
        organization_id=row.organization_id,
        department_id=row.department_id,
        is_superuser=bool(row.is_superuser),
        last_login_at=row.last_login_at,
    )


async def _actor_scope(
    session: AsyncSession, current: CurrentUser
) -> tuple[User, UUID | None, UUID | None]:
    access = AccessControl(session)
    actor = await access.load_user(current.id)
    if actor.is_superuser:
        return actor, None, None
    return actor, actor.organization_id, actor.department_id


def _assert_target_in_scope(actor: User, target: User) -> None:
    if actor.is_superuser:
        return
    if target.organization_id != actor.organization_id:
        raise http_error(404, "user_not_found", "用户不存在")
    if actor.department_id is not None and target.department_id != actor.department_id:
        raise http_error(404, "user_not_found", "用户不存在")


@router.post("/register", response_model=TokenPairResponse)
async def register(
    body: RegisterBody,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> TokenPairResponse:
    auth = AuthService(session)
    try:
        return await auth.register(
            RegisterRequest(
                username=body.username,
                password=body.password,
                display_name=body.display_name,
                user_agent=request.headers.get("user-agent"),
                client_ip=_client_ip(request),
            )
        )
    except AuthError as exc:
        raise auth_error_to_http(exc) from exc


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
async def me(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    access = AccessControl(session)
    user = await access.load_user(current.id)
    return {
        "id": str(current.id),
        "username": current.username,
        "organization_id": str(current.organization_id),
        "roles": current.roles,
        "is_superuser": bool(user.is_superuser),
        "status": user.status,
    }


@router.get("/apps", response_model=list[AppVisibilityOut])
async def list_visible_apps(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[AppVisibilityOut]:
    apps: ApplicationRegistry = request.app.state.apps
    access = AccessControl(session)
    result: list[AppVisibilityOut] = []
    for item in apps.all():
        can_use = item.app_key == "auth" or await access.can_use_app(current.id, item.app_key)
        if not can_use:
            continue
        can_control = await access.can_control_app(current.id, item.app_key)
        result.append(
            AppVisibilityOut(
                app_key=item.app_key,
                name=item.name,
                can_use=True,
                can_control=can_control,
            )
        )
    return result


@router.get("/users", response_model=list[UserOut])
async def list_users(
    current: CurrentUser = Depends(_ctrl_auth),
    session: AsyncSession = Depends(db_session),
    offset: int = 0,
    limit: int = 50,
) -> list[UserOut]:
    actor, org_id, dept_id = await _actor_scope(session, current)
    _ = actor
    repos = get_repositories(session)
    rows = await repos.permission.list_users_in_scope(
        organization_id=org_id,
        department_id=dept_id,
        offset=offset,
        limit=min(limit, 100),
    )
    return [_user_out(row) for row in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user_status(
    user_id: UUID,
    body: UserStatusPatch,
    current: CurrentUser = Depends(_ctrl_auth),
    session: AsyncSession = Depends(db_session),
) -> UserOut:
    actor, _org, _dept = await _actor_scope(session, current)
    repos = get_repositories(session)
    target = await repos.permission.user.get(user_id)
    if target is None or target.deleted_at is not None:
        raise http_error(404, "user_not_found", "用户不存在")
    _assert_target_in_scope(actor, target)
    if target.id == actor.id:
        raise http_error(400, "user_self_status", "不可修改自己的授权状态")
    if target.is_superuser and not actor.is_superuser:
        raise http_error(403, "user_forbidden", "不可变更平台管理员状态")
    target.status = body.status
    if body.status != "active":
        await AuthService(session).revoke_all_sessions(target.id)
    logger.info("更新用户状态 id={} status={}", target.id, body.status)
    return _user_out(target)


@router.get("/apps/{app_key}/bindings", response_model=list[BindingItem])
async def get_app_bindings(
    app_key: str,
    request: Request,
    _admin: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    asset_id = await _require_app_asset_id(session, request.app.state.apps, app_key)
    return await load_bindings(session, "application", asset_id)


@router.put("/apps/{app_key}/bindings", response_model=list[BindingItem])
async def put_app_bindings(
    app_key: str,
    body: BindingPutBody,
    request: Request,
    _admin: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(db_session),
) -> list[BindingItem]:
    asset_id = await _require_app_asset_id(session, request.app.state.apps, app_key)
    return await save_bindings(session, "application", asset_id, body.bindings)
