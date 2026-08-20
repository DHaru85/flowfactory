from api.registry.service import Service


class AgentConfigBackendService(Service):
    service_key = "agent_config"
    name = "Profile / 技能 / 工具 / MCP / Beat"

    async def health_check(self) -> bool:
        return True
