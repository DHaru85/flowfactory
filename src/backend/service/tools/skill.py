"""按 agent_skill 装配系统提示与工具集。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.agent.models import AgentSkill, AgentTool
from service.persistence.factory import get_repositories
from service.runtime.llm import ToolSpec
from service.tools.executor import ToolExecutor
from service.tools.schemas import ToolCallRequest, ToolCallResult


def _as_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except ValueError:
        return None


@dataclass
class AssembledSkills:
    extra_system: str
    tools: list[AgentTool] = field(default_factory=list)

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for tool in self.tools:
            schema = tool.schema_ if isinstance(tool.schema_, dict) else {}
            specs.append(
                ToolSpec(
                    code=tool.code,
                    name=tool.name,
                    description=str(schema.get("description") or tool.name),
                    parameters=schema,
                )
            )
        return specs


class SkillRuntime:
    """读技能行、拼提示、经 ToolExecutor 执行。"""

    def __init__(self, session: AsyncSession, executor: ToolExecutor | None = None) -> None:
        self._session = session
        self._executor = executor or ToolExecutor(session)

    async def assemble(self, skill_ids: Sequence[object]) -> AssembledSkills:
        ids: list[UUID] = []
        for raw in skill_ids:
            parsed = _as_uuid(raw)
            if parsed is not None:
                ids.append(parsed)
        if not ids:
            return AssembledSkills(extra_system="")
        repos = get_repositories(self._session)
        skills: list[AgentSkill] = []
        for skill_id in ids:
            row = await repos.agent.skill.get(skill_id)
            if row is not None:
                skills.append(row)
        sections: list[str] = []
        tool_ids: list[UUID] = []
        seen: set[UUID] = set()
        for skill in skills:
            parts = [f"技能 {skill.name}（{skill.code}）"]
            if skill.description:
                parts.append(skill.description)
            if skill.prompt_template:
                parts.append(skill.prompt_template)
            sections.append("\n".join(parts))
            for raw in skill.tool_ids or []:
                tid = _as_uuid(raw)
                if tid is not None and tid not in seen:
                    seen.add(tid)
                    tool_ids.append(tid)
        tools: list[AgentTool] = []
        for tool_id in tool_ids:
            tool = await repos.agent.tool.get(tool_id)
            if tool is not None:
                tools.append(tool)
        extra = "\n\n".join(sections)
        return AssembledSkills(extra_system=extra, tools=tools)

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        return await self._executor.execute(request)
