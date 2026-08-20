"""HTTP 应用权限依赖。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser, db_session, get_current_user, get_current_user_detached
from api.errors import http_error
from service.auth.access import AccessControl
from service.auth.errors import AuthError
from service.database.session import session_scope

AppDep = Callable[..., Awaitable[CurrentUser]]


def require_app(app_key: str, *, control: bool = False) -> AppDep:
    async def _inner(
        current: CurrentUser = Depends(get_current_user),
        session: AsyncSession = Depends(db_session),
    ) -> CurrentUser:
        access = AccessControl(session)
        try:
            allowed = (
                await access.can_control_app(current.id, app_key)
                if control
                else await access.can_use_app(current.id, app_key)
            )
        except AuthError as exc:
            raise http_error(401, exc.code, exc.message) from exc
        if not allowed:
            raise http_error(403, "app_forbidden", "无权访问该应用")
        return current

    return _inner


def require_app_detached(app_key: str, *, control: bool = False) -> AppDep:
    """SSE 等短会话：不占用请求级 Session。"""

    async def _inner(
        current: CurrentUser = Depends(get_current_user_detached),
    ) -> CurrentUser:
        async with session_scope() as session:
            access = AccessControl(session)
            try:
                allowed = (
                    await access.can_control_app(current.id, app_key)
                    if control
                    else await access.can_use_app(current.id, app_key)
                )
            except AuthError as exc:
                raise http_error(401, exc.code, exc.message) from exc
        if not allowed:
            raise http_error(403, "app_forbidden", "无权访问该应用")
        return current

    return _inner


async def require_platform_admin(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> CurrentUser:
    access = AccessControl(session)
    if not await access.is_platform_admin(current.id):
        raise http_error(403, "app_forbidden", "需要平台管理员")
    return current
