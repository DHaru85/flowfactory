"""领域图 ORM 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_schema.base import Base, UUIDPrimaryKeyMixin


class GraphNode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "graph_node"
    __table_args__ = (
        Index(
            "uq_graph_node_external_ref",
            "graph_key",
            "node_type",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
    )

    graph_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    properties: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    outgoing_edges: Mapped[list["GraphEdge"]] = relationship(
        back_populates="source_node",
        foreign_keys="GraphEdge.source_node_id",
    )
    incoming_edges: Mapped[list["GraphEdge"]] = relationship(
        back_populates="target_node",
        foreign_keys="GraphEdge.target_node_id",
    )
    entity_links: Mapped[list["GraphEntityLink"]] = relationship(back_populates="node")


class GraphEdge(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "graph_edge"
    __table_args__ = (
        Index("idx_graph_edge_source", "source_node_id"),
        Index("idx_graph_edge_target", "target_node_id"),
    )

    graph_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_node.id"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_node.id"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    properties: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    source_node: Mapped["GraphNode"] = relationship(
        back_populates="outgoing_edges",
        foreign_keys=[source_node_id],
    )
    target_node: Mapped["GraphNode"] = relationship(
        back_populates="incoming_edges",
        foreign_keys=[target_node_id],
    )


class GraphEntityLink(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "graph_entity_link"
    __table_args__ = (UniqueConstraint("entity_name", "node_id", name="uq_entity_node"),)

    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_node.id"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    node: Mapped["GraphNode"] = relationship(back_populates="entity_links")
