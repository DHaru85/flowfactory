"""Studio 应用声明的服务引用。"""

from api.registry.service import Service


class StudioBackendService(Service):
    service_key = "studio"
    name = "工作流编排 Studio"

    async def health_check(self) -> bool:
        return True
