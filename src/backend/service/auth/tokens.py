"""Refresh token 摘要与 IP 校验。"""

from __future__ import annotations

import hashlib
import ipaddress
import secrets


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sanitize_client_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return None
    return raw
