from typing import ClassVar

from fastapi import APIRouter

from api.apps.conversation.router import router
from api.apps.conversation.services import ConversationBackendService, WorkflowRuntimeBackendService
from api.registry.application import Application
from api.registry.service import Service


class ConversationApplication(Application):
    app_key = "conversation"
    name = "会话"
    services: ClassVar[list[type[Service]]] = [
        ConversationBackendService,
        WorkflowRuntimeBackendService,
    ]

    def build_router(self) -> APIRouter:
        return router
