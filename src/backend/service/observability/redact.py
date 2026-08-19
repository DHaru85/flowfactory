"""Prompt 入库前脱敏。不承诺绝对无 PII。"""

from __future__ import annotations

import hashlib
import re

from settings.config import get_settings

_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CN_MOBILE = re.compile(r"1[3-9]\d{9}")
_CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")


def _extra_patterns() -> list[re.Pattern[str]]:
    raw = get_settings().obs_redact_extra_patterns.strip()
    if not raw:
        return []
    compiled: list[re.Pattern[str]] = []
    for part in raw.split(","):
        expr = part.strip()
        if not expr:
            continue
        compiled.append(re.compile(expr))
    return compiled


def redact_text(text: str) -> str:
    """替换常见身份与联系方式为占位符。"""
    result = _EMAIL.sub("[REDACTED_EMAIL]", text)
    result = _CN_ID.sub("[REDACTED_ID]", result)
    result = _CN_MOBILE.sub("[REDACTED_PHONE]", result)
    result = _BANK_CARD.sub("[REDACTED_CARD]", result)
    for pattern in _extra_patterns():
        result = pattern.sub("[REDACTED]", result)
    return result


def hash_content(text: str) -> str:
    """原文 SHA-256 hex，便于去重审计。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
