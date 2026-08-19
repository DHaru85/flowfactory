from typing import ClassVar

from fastapi import APIRouter

from api.apps.auth.router import router
from api.apps.auth.services import AuthBackendService
from api.registry.application import Application
from api.registry.service import Service


class AuthApplication(Application):
    app_key = "auth"
    name = "鉴权"
    services: ClassVar[list[type[Service]]] = [AuthBackendService]

    def build_router(self) -> APIRouter:
        return router
