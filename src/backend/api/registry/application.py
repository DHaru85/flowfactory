"""Application Protocol 与进程内注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from fastapi import APIRouter

from api.registry.schemas import ApplicationContext
from api.registry.service import Service


class Application(ABC):
    """一类交互场景对应一个 Application。"""

    app_key: ClassVar[str]
    name: ClassVar[str]
    services: ClassVar[list[type[Service]]] = []

    @abstractmethod
    def build_router(self) -> APIRouter:
        """挂载本应用 REST / SSE 路由。"""

    async def on_startup(self, ctx: ApplicationContext) -> None:
        return None

    def resolve_service_types(self) -> list[type[Service]]:
        return list(self.services)


class ApplicationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Application] = {}

    def register(self, app: Application) -> None:
        key = app.app_key
        if key in self._items:
            raise ValueError(f"app_key 冲突: {key}")
        self._items[key] = app

    def get(self, app_key: str) -> Application:
        if app_key not in self._items:
            raise KeyError(f"未注册应用: {app_key}")
        return self._items[app_key]

    def list_keys(self) -> list[str]:
        return list(self._items.keys())

    def all(self) -> list[Application]:
        return list(self._items.values())
