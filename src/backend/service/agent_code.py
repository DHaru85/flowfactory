"""Agent 族内部 code：图拓扑指针，由服务层生成。"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

AgentCodeKind = Literal["llm", "profile", "skill", "tool", "mcp", "flow", "beat"]


def generate_agent_code(kind: AgentCodeKind) -> str:
    return f"{kind}-{uuid4().hex[:8]}"
