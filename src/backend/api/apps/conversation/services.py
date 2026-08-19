"""会话应用声明的服务引用。"""

from api.registry.service import Service


class ConversationBackendService(Service):
    service_key = "conversation"
    name = "会话与 SSE"

    async def health_check(self) -> bool:
        return True


class WorkflowRuntimeBackendService(Service):
    service_key = "workflow_runtime"
    name = "工作流运行时"

    async def health_check(self) -> bool:
        return True
