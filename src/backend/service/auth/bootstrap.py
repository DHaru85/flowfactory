"""应用资产启动登记。"""

from __future__ import annotations

from collections.abc import Sequence

from data_schema.permission.models import Asset
from service.database.session import session_scope
from service.persistence.factory import get_repositories


async def ensure_application_assets(apps: Sequence[tuple[str, str]]) -> None:
    """幂等写入 sys_asset(application, app_key)。"""
    async with session_scope() as session:
        repos = get_repositories(session)
        for app_key, name in apps:
            existing = await repos.permission.get_asset_by_key("application", app_key)
            if existing is None:
                await repos.permission.asset.add(
                    Asset(
                        asset_type="application",
                        asset_key=app_key,
                        name=name,
                        metadata_={},
                    )
                )
                continue
            existing.name = name
