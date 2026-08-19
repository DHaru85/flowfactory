"""Application / Service 进程内注册表。"""

from api.registry.application import Application, ApplicationRegistry
from api.registry.scan import register_discovered, scan_and_register
from api.registry.schemas import ApplicationContext, ServiceInvokeContext
from api.registry.service import Service, ServiceRegistry

__all__ = [
    "Application",
    "ApplicationContext",
    "ApplicationRegistry",
    "Service",
    "ServiceInvokeContext",
    "ServiceRegistry",
    "scan_and_register",
    "register_discovered",
]
