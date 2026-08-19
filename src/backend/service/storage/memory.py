"""进程内对象存储，供单测使用。"""

from service.storage.protocol import ObjectStat


class MemoryObjectStore:
    """用 dict 保存 bucket/key -> bytes。"""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, object_key: str, data: bytes, content_type: str = "") -> ObjectStat:
        del content_type
        self._objects[(bucket, object_key)] = data
        return ObjectStat(bucket=bucket, object_key=object_key, size_bytes=len(data))

    def get(self, bucket: str, object_key: str) -> bytes:
        try:
            return self._objects[(bucket, object_key)]
        except KeyError as exc:
            raise FileNotFoundError(f"对象不存在: {bucket}/{object_key}") from exc

    def stat(self, bucket: str, object_key: str) -> ObjectStat | None:
        data = self._objects.get((bucket, object_key))
        if data is None:
            return None
        return ObjectStat(bucket=bucket, object_key=object_key, size_bytes=len(data))
