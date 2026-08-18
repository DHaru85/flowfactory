"""持久化仓储统一入口。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from service.persistence.agent import AgentConfigRepository
from service.persistence.audit import AuditRepository
from service.persistence.conversation import ConversationRepository
from service.persistence.graph import GraphRepository
from service.persistence.knowledge import KnowledgeRepository
from service.persistence.notification import NotificationRepository
from service.persistence.observability import ObservabilityRepository
from service.persistence.permission import PermissionRepository
from service.persistence.security import SecurityRepository
from service.persistence.workflow import WorkflowRepository


@dataclass
class Repositories:
    """单次 Session 绑定的全域仓储集合。"""

    permission: PermissionRepository
    conversation: ConversationRepository
    workflow: WorkflowRepository
    agent: AgentConfigRepository
    knowledge: KnowledgeRepository
    audit: AuditRepository
    graph: GraphRepository
    security: SecurityRepository
    observability: ObservabilityRepository
    notification: NotificationRepository


def get_repositories(session: AsyncSession) -> Repositories:
    """工厂：从 Session 构建全部仓储。"""
    return Repositories(
        permission=PermissionRepository(session),
        conversation=ConversationRepository(session),
        workflow=WorkflowRepository(session),
        agent=AgentConfigRepository(session),
        knowledge=KnowledgeRepository(session),
        audit=AuditRepository(session),
        graph=GraphRepository(session),
        security=SecurityRepository(session),
        observability=ObservabilityRepository(session),
        notification=NotificationRepository(session),
    )
