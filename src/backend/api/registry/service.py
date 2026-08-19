"""Service Protocol 与进程内注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from api.registry.schemas import ServiceInvokeContext


class Service(ABC):
    """应用层对服务层能力的声明式引用（不落绑定表）。"""

    service_key: ClassVar[str]
    name: ClassVar[str]

    async def on_startup(self, ctx: ServiceInvokeContext) -> None:
        return None

    @abstractmethod
    async def health_check(self) -> bool:
        """就绪探针。"""


class ServiceRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Service] = {}

    def register(self, service: Service) -> None:
        key = service.service_key
        if key in self._items:
            raise ValueError(f"service_key 冲突: {key}")
        self._items[key] = service

    def get(self, service_key: str) -> Service:
        if service_key not in self._items:
            raise KeyError(f"未注册服务: {service_key}")
        return self._items[service_key]

    def list_keys(self) -> list[str]:
        return list(self._items.keys())

    def all(self) -> list[Service]:
        return list(self._items.values())
