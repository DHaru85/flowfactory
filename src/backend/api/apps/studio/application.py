from typing import ClassVar

from fastapi import APIRouter

from api.apps.studio.router import router
from api.apps.studio.services import StudioBackendService
from api.registry.application import Application
from api.registry.service import Service


class StudioApplication(Application):
    app_key = "studio"
    name = "工作流编排 Studio"
    services: ClassVar[list[type[Service]]] = [StudioBackendService]

    def build_router(self) -> APIRouter:
        return router
