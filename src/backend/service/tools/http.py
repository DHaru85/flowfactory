"""HTTP 工具传输：URL 仅来自配置。"""

from __future__ import annotations

import json
from typing import Protocol

import httpx
from loguru import logger

from settings.config import get_settings


class HttpToolTransport(Protocol):
    async def request(
        self,
        config: dict[str, object],
        arguments: dict[str, object],
    ) -> tuple[int, object]:
        """返回 HTTP 状态码与解析后的 body。"""


class HttpxToolTransport:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def request(
        self,
        config: dict[str, object],
        arguments: dict[str, object],
    ) -> tuple[int, object]:
        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("HTTP 工具未配置 url")
        method = str(config.get("method") or "POST").upper()
        headers_raw = config.get("headers")
        headers: dict[str, str] = {}
        if isinstance(headers_raw, dict):
            headers = {str(key): str(value) for key, value in headers_raw.items()}
        param_in = str(config.get("param_in") or "body")
        cfg = get_settings()
        timeout = cfg.tool_http_timeout_seconds
        max_bytes = cfg.tool_http_max_body_bytes
        kwargs: dict[str, object] = {"headers": headers, "timeout": timeout}
        if param_in == "query":
            kwargs["params"] = {str(k): _query_value(v) for k, v in arguments.items()}
        else:
            kwargs["json"] = arguments
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient()
        try:
            response = await client.request(method, url, **kwargs)  # type: ignore[arg-type]
        finally:
            if owns_client:
                await client.aclose()
        body = response.content[:max_bytes]
        parsed: object
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = body.decode("utf-8", errors="replace")
        if response.status_code >= 400:
            logger.warning("HTTP 工具失败 status={} url={}", response.status_code, url)
        return response.status_code, parsed


def _query_value(value: object) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


_override: HttpToolTransport | None = None


def set_http_transport_override(transport: HttpToolTransport | None) -> None:
    global _override
    _override = transport


def get_http_transport() -> HttpToolTransport:
    if _override is not None:
        return _override
    return HttpxToolTransport()
