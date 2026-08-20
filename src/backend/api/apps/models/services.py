from api.registry.service import Service


class ModelsBackendService(Service):
    service_key = "models"
    name = "模型目录与解析"

    async def health_check(self) -> bool:
        return True
