"""Prompt 脱敏单元测试。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.observability.redact import hash_content, redact_text  # noqa: E402


def test_redact_email_phone_id_card() -> None:
    text = "联系 a@b.com 手机 13812345678 证 110101199001011234 卡 6222021234567890123"
    redacted = redact_text(text)
    assert "a@b.com" not in redacted
    assert "13812345678" not in redacted
    assert "110101199001011234" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_ID]" in redacted
    assert "[REDACTED_CARD]" in redacted


def test_content_hash_stable() -> None:
    assert hash_content("hello") == hash_content("hello")
    assert hash_content("hello") != hash_content("world")
    assert len(hash_content("hello")) == 64
