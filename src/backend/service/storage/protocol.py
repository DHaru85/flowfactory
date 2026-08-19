"""对象存储协议。"""

from typing import Protocol


class ObjectStat:
    __slots__ = ("bucket", "object_key", "size_bytes", "etag")

    def __init__(
        self,
        bucket: str,
        object_key: str,
        size_bytes: int,
        etag: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.object_key = object_key
        self.size_bytes = size_bytes
        self.etag = etag


class ObjectStore(Protocol):
    def put(self, bucket: str, object_key: str, data: bytes, content_type: str = "") -> ObjectStat:
        """写入对象。"""

    def get(self, bucket: str, object_key: str) -> bytes:
        """读取对象字节。"""

    def stat(self, bucket: str, object_key: str) -> ObjectStat | None:
        """对象元数据；不存在返回 None。"""
