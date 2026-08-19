"""MinIO / S3 兼容对象存储。"""

from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from loguru import logger

from service.storage.protocol import ObjectStat
from settings.config import get_settings


class MinioObjectStore:
    """MinIO 客户端；public bucket 在无凭证时走匿名 HTTP GET。"""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
        public: bool | None = None,
    ) -> None:
        cfg = get_settings()
        self._endpoint = endpoint or cfg.minio_endpoint
        self._access_key = access_key if access_key is not None else cfg.minio_access_key
        self._secret_key = secret_key if secret_key is not None else cfg.minio_secret_key
        self._secure = cfg.minio_secure if secure is None else secure
        self._public = cfg.minio_public if public is None else public
        self._client = None

    def _scheme(self) -> str:
        return "https" if self._secure else "http"

    def _public_url(self, bucket: str, object_key: str) -> str:
        encoded = quote(object_key, safe="/")
        return f"{self._scheme()}://{self._endpoint}/{bucket}/{encoded}"

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client
        if not self._access_key or not self._secret_key:
            raise RuntimeError("MinIO 写入或鉴权读取需要 access_key / secret_key")
        from minio import Minio

        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
        )
        return self._client

    def put(self, bucket: str, object_key: str, data: bytes, content_type: str = "") -> ObjectStat:
        client = self._ensure_client()
        ctype = content_type or "application/octet-stream"
        result = client.put_object(  # type: ignore[union-attr]
            bucket,
            object_key,
            BytesIO(data),
            length=len(data),
            content_type=ctype,
        )
        etag = getattr(result, "etag", None)
        return ObjectStat(
            bucket=bucket,
            object_key=object_key,
            size_bytes=len(data),
            etag=str(etag) if etag else None,
        )

    def get(self, bucket: str, object_key: str) -> bytes:
        if self._public and (not self._access_key or not self._secret_key):
            return self._get_public(bucket, object_key)
        client = self._ensure_client()
        response = client.get_object(bucket, object_key)  # type: ignore[union-attr]
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _get_public(self, bucket: str, object_key: str) -> bytes:
        url = self._public_url(bucket, object_key)
        try:
            with urlopen(url, timeout=30) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(f"对象不存在: {bucket}/{object_key}") from exc
            logger.error("MinIO 匿名 GET 失败 status={} url={}", exc.code, url)
            raise
        except URLError as exc:
            logger.error("MinIO 匿名 GET 网络失败 url={} err={}", url, exc)
            raise

    def stat(self, bucket: str, object_key: str) -> ObjectStat | None:
        if self._public and (not self._access_key or not self._secret_key):
            try:
                data = self._get_public(bucket, object_key)
            except FileNotFoundError:
                return None
            return ObjectStat(bucket=bucket, object_key=object_key, size_bytes=len(data))
        try:
            client = self._ensure_client()
            info = client.stat_object(bucket, object_key)  # type: ignore[union-attr]
        except Exception:
            return None
        size = int(getattr(info, "size", 0) or 0)
        etag = getattr(info, "etag", None)
        return ObjectStat(
            bucket=bucket,
            object_key=object_key,
            size_bytes=size,
            etag=str(etag) if etag else None,
        )
