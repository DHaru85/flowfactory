"""Knowledge、文件与检索索引 ORM 模型。"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_schema.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# 默认向量维度，与常见 embedding 模型对齐；可按 collection.embedding_model 调整写入逻辑
DEFAULT_EMBEDDING_DIM = 1536


class FileStorageObject(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "file_storage_object"
    __table_args__ = (UniqueConstraint("bucket", "object_key", name="uq_storage_bucket_key"),)

    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    file_versions: Mapped[list["FileVersion"]] = relationship(back_populates="storage_object")
    knowledge_docs: Mapped[list["KnowledgeDoc"]] = relationship(back_populates="storage_object")


class FileRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "file_record"

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_user.id"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    versions: Mapped[list["FileVersion"]] = relationship(back_populates="file")


class FileVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "file_version"
    __table_args__ = (UniqueConstraint("file_id", "version_no", name="uq_file_version_no"),)

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_record.id"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_storage_object.id"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_user.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    file: Mapped["FileRecord"] = relationship(back_populates="versions")
    storage_object: Mapped["FileStorageObject"] = relationship(back_populates="file_versions")


class FileUploadSession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "file_upload_session"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_user.id"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_storage_object.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )


class KnowledgeCollection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "kb_collection"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_organization.id"),
        nullable=True,
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    docs: Mapped[list["KnowledgeDoc"]] = relationship(back_populates="collection")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="collection")
    ingestion_jobs: Mapped[list["KnowledgeIngestionJob"]] = relationship(
        back_populates="collection"
    )


class KnowledgeDoc(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "kb_doc"
    __table_args__ = (Index("idx_kb_doc_collection", "collection_id"),)

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collection.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_storage_object.id"),
        nullable=True,
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    collection: Mapped["KnowledgeCollection"] = relationship(back_populates="docs")
    storage_object: Mapped["FileStorageObject | None"] = relationship(
        back_populates="knowledge_docs"
    )
    sections: Mapped[list["KnowledgeSection"]] = relationship(back_populates="doc")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="doc")


class KnowledgeSection(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "kb_section"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_doc.id"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    doc: Mapped["KnowledgeDoc"] = relationship(back_populates="sections")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="section")


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index("idx_kb_chunk_collection", "collection_id"),
        Index("idx_kb_chunk_tsv", "content_tsv", postgresql_using="gin"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collection.id"),
        nullable=False,
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_doc.id"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_section.id"),
        nullable=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[object | None] = mapped_column(TSVECTOR, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIM),
        nullable=True,
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )

    collection: Mapped["KnowledgeCollection"] = relationship(back_populates="chunks")
    doc: Mapped["KnowledgeDoc"] = relationship(back_populates="chunks")
    section: Mapped["KnowledgeSection | None"] = relationship(back_populates="chunks")


class KnowledgeIngestionJob(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "kb_ingestion_job"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collection.id"),
        nullable=False,
    )
    doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_doc.id"),
        nullable=True,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stats: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    collection: Mapped["KnowledgeCollection"] = relationship(back_populates="ingestion_jobs")
