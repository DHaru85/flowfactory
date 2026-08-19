"""对象存储工厂。"""

from __future__ import annotations

from service.storage.memory import MemoryObjectStore
from service.storage.minio_store import MinioObjectStore
from service.storage.protocol import ObjectStore

_override: ObjectStore | None = None


def set_object_store_override(store: ObjectStore | None) -> None:
    global _override
    _override = store


def get_object_store() -> ObjectStore:
    if _override is not None:
        return _override
    return MinioObjectStore()


__all__ = [
    "ObjectStore",
    "MemoryObjectStore",
    "MinioObjectStore",
    "get_object_store",
    "set_object_store_override",
]
