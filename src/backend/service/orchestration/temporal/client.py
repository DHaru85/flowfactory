"""Temporal 客户端。"""

from __future__ import annotations

from temporalio.client import Client

from settings.config import get_settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is not None:
        return _client
    cfg = get_settings()
    _client = await Client.connect(cfg.temporal_host, namespace=cfg.temporal_namespace)
    return _client


def reset_temporal_client() -> None:
    global _client
    _client = None
