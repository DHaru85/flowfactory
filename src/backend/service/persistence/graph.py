"""Graph 域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.graph.models import GraphEdge, GraphEntityLink, GraphNode
from service.persistence.base import Repository


class GraphRepository:
    """领域图聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.node = Repository(session, GraphNode)
        self.edge = Repository(session, GraphEdge)
        self.entity_link = Repository(session, GraphEntityLink)

    async def get_node_by_external_ref(
        self,
        graph_key: str,
        node_type: str,
        external_ref: str,
    ) -> GraphNode | None:
        stmt = select(GraphNode).where(
            GraphNode.graph_key == graph_key,
            GraphNode.node_type == node_type,
            GraphNode.external_ref == external_ref,
        )
        return await self._session.scalar(stmt)

    async def list_outgoing_edges(
        self,
        node_id: uuid.UUID,
        relation_type: str | None = None,
    ) -> list[GraphEdge]:
        stmt = select(GraphEdge).where(GraphEdge.source_node_id == node_id)
        if relation_type is not None:
            stmt = stmt.where(GraphEdge.relation_type == relation_type)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def find_nodes_by_entity(self, entity_name: str) -> list[GraphNode]:
        stmt = (
            select(GraphNode)
            .join(GraphEntityLink, GraphEntityLink.node_id == GraphNode.id)
            .where(GraphEntityLink.entity_name == entity_name)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
