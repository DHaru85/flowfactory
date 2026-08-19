"""Access JWT 编解码。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from service.auth.errors import TOKEN_EXPIRED, TOKEN_INVALID, AuthError
from service.auth.schemas import TokenClaims
from settings.config import get_settings


class JwtCodec:
    """HS256 access token；算法与密钥来自配置。"""

    def encode(self, claims: TokenClaims) -> str:
        cfg = get_settings()
        payload = {
            "sub": str(claims.sub),
            "jti": str(claims.jti),
            "iat": claims.iat,
            "exp": claims.exp,
            "org_id": str(claims.org_id),
            "roles": claims.roles,
            "token_type": claims.token_type,
            "iss": cfg.jwt_issuer,
        }
        return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)

    def decode(self, raw_token: str) -> TokenClaims:
        cfg = get_settings()
        try:
            payload = jwt.decode(
                raw_token,
                cfg.jwt_secret,
                algorithms=[cfg.jwt_algorithm],
                issuer=cfg.jwt_issuer,
            )
        except ExpiredSignatureError as exc:
            raise AuthError(TOKEN_EXPIRED, "access token 已过期") from exc
        except InvalidTokenError as exc:
            raise AuthError(TOKEN_INVALID, "access token 无效") from exc
        token_type = payload.get("token_type", "access")
        if token_type != "access":
            raise AuthError(TOKEN_INVALID, "token_type 不是 access")
        try:
            return TokenClaims(
                sub=uuid.UUID(str(payload["sub"])),
                jti=uuid.UUID(str(payload["jti"])),
                iat=int(payload["iat"]),
                exp=int(payload["exp"]),
                org_id=uuid.UUID(str(payload["org_id"])),
                roles=list(payload.get("roles") or []),
                token_type="access",
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthError(TOKEN_INVALID, "access token claims 不完整") from exc


def build_access_claims(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    roles: list[str],
    ttl_seconds: int | None = None,
) -> TokenClaims:
    cfg = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else cfg.jwt_access_ttl_seconds
    now = datetime.now(UTC)
    iat = int(now.timestamp())
    exp = int((now + timedelta(seconds=ttl)).timestamp())
    return TokenClaims(
        sub=user_id,
        jti=uuid.uuid4(),
        iat=iat,
        exp=exp,
        org_id=org_id,
        roles=roles,
        token_type="access",
    )
