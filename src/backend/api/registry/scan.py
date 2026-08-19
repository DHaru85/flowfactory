"""扫描 api.apps 并注册 Application / Service。"""

from __future__ import annotations

import importlib
import pkgutil
from uuid import uuid4

from loguru import logger

from api.registry.application import Application, ApplicationRegistry
from api.registry.schemas import ApplicationContext, ServiceInvokeContext
from api.registry.service import ServiceRegistry


def _iter_application_classes() -> list[type[Application]]:
    import api.apps as apps_pkg

    found: list[type[Application]] = []
    seen: set[type[Application]] = set()
    for module_info in pkgutil.walk_packages(apps_pkg.__path__, apps_pkg.__name__ + "."):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if not isinstance(value, type):
                continue
            if value is Application:
                continue
            if issubclass(value, Application) and value not in seen:
                seen.add(value)
                found.append(value)
    return found


def register_discovered(apps: ApplicationRegistry, services: ServiceRegistry) -> None:
    """同步扫描注册；app_key / service_key 冲突则失败。"""
    for cls in _iter_application_classes():
        instance = cls()
        apps.register(instance)
        logger.info("已注册应用 app_key={} name={}", instance.app_key, instance.name)
        for service_cls in instance.resolve_service_types():
            existing = {item.service_key for item in services.all()}
            if service_cls.service_key in existing:
                continue
            services.register(service_cls())


async def run_startup_hooks(apps: ApplicationRegistry, services: ServiceRegistry) -> None:
    request_id = str(uuid4())
    for service in services.all():
        await service.on_startup(
            ServiceInvokeContext(
                service_key=service.service_key,
                caller_app_key="system",
                request_id=request_id,
            )
        )
    for application in apps.all():
        await application.on_startup(ApplicationContext(app_key=application.app_key, settings={}))


async def scan_and_register(
    apps: ApplicationRegistry,
    services: ServiceRegistry,
) -> None:
    register_discovered(apps, services)
    await run_startup_hooks(apps, services)
