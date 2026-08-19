"""对象存储。"""

from service.storage.factory import get_object_store, set_object_store_override
from service.storage.memory import MemoryObjectStore
from service.storage.minio_store import MinioObjectStore
from service.storage.protocol import ObjectStat, ObjectStore

__all__ = [
    "ObjectStat",
    "ObjectStore",
    "MemoryObjectStore",
    "MinioObjectStore",
    "get_object_store",
    "set_object_store_override",
]
