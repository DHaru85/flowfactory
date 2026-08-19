"""鉴权应用声明的服务引用。"""

from api.registry.service import Service


class AuthBackendService(Service):
    service_key = "auth"
    name = "用户鉴权"

    async def health_check(self) -> bool:
        return True
