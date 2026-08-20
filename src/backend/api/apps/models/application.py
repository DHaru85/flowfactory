from typing import ClassVar

from fastapi import APIRouter

from api.apps.models.router import router
from api.apps.models.services import ModelsBackendService
from api.registry.application import Application
from api.registry.service import Service


class ModelsApplication(Application):
    app_key = "models"
    name = "模型管理"
    services: ClassVar[list[type[Service]]] = [ModelsBackendService]

    def build_router(self) -> APIRouter:
        return router
