from typing import ClassVar

from fastapi import APIRouter

from api.apps.agent_config.router import router
from api.apps.agent_config.services import AgentConfigBackendService
from api.registry.application import Application
from api.registry.service import Service


class AgentConfigApplication(Application):
    app_key = "agent_config"
    name = "Agent 配置"
    services: ClassVar[list[type[Service]]] = [AgentConfigBackendService]

    def build_router(self) -> APIRouter:
        return router
