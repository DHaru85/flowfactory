"""JWT 与密码单元测试。"""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.auth.errors import TOKEN_EXPIRED, AuthError  # noqa: E402
from service.auth.jwt_codec import JwtCodec, build_access_claims  # noqa: E402
from service.auth.ldap.ldap3_adapter import Ldap3Adapter  # noqa: E402
from service.auth.password import hash_password, verify_password  # noqa: E402
from service.auth.schemas import LdapConnectionConfig  # noqa: E402
from service.auth.tokens import hash_refresh_token, sanitize_client_ip  # noqa: E402


def test_password_hash_roundtrip() -> None:
    digest = hash_password("secret-1")
    assert digest != "secret-1"
    assert verify_password("secret-1", digest) is True
    assert verify_password("wrong", digest) is False


def test_jwt_encode_decode() -> None:
    claims = build_access_claims(user_id=uuid4(), org_id=uuid4(), roles=["ops"], ttl_seconds=60)
    raw = JwtCodec().encode(claims)
    decoded = JwtCodec().decode(raw)
    assert decoded.sub == claims.sub
    assert decoded.jti == claims.jti
    assert decoded.roles == ["ops"]
    assert decoded.token_type == "access"


def test_jwt_expired() -> None:
    claims = build_access_claims(user_id=uuid4(), org_id=uuid4(), roles=[], ttl_seconds=-1)
    raw = JwtCodec().encode(claims)
    with pytest.raises(AuthError) as exc:
        JwtCodec().decode(raw)
    assert exc.value.code == TOKEN_EXPIRED


def test_refresh_hash_and_ip() -> None:
    assert len(hash_refresh_token("abc")) == 64
    assert sanitize_client_ip("127.0.0.1") == "127.0.0.1"
    assert sanitize_client_ip("not-an-ip") is None


def test_ldap3_adapter_constructs_without_connecting() -> None:
    adapter = Ldap3Adapter(
        LdapConnectionConfig(host="", port=389, user_search_base="dc=example,dc=com")
    )
    with pytest.raises(AuthError):
        adapter.connect()
