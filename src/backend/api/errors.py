"""统一错误体与 AuthError 映射。"""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.sse.machine import StreamProtocolError
from service.auth.errors import (
    INVALID_CREDENTIALS,
    LDAP_PROVISION_FAILED,
    LDAP_UNAVAILABLE,
    REFRESH_REUSE,
    TOKEN_EXPIRED,
    TOKEN_INVALID,
    TOKEN_REVOKED,
    USER_DISABLED,
    USER_NOT_FOUND,
    USERNAME_CONFLICT,
    AuthError,
)

_AUTH_401 = {
    INVALID_CREDENTIALS,
    USER_DISABLED,
    TOKEN_EXPIRED,
    TOKEN_INVALID,
    TOKEN_REVOKED,
    REFRESH_REUSE,
}
_AUTH_503 = {LDAP_UNAVAILABLE, LDAP_PROVISION_FAILED}
_AUTH_404 = {USER_NOT_FOUND}
_AUTH_409 = {USERNAME_CONFLICT}


class ErrorBody(BaseModel):
    code: str
    message: str


def error_body(code: str, message: str) -> dict[str, str]:
    return ErrorBody(code=code, message=message).model_dump()


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error_body(code, message))


def auth_error_to_http(exc: AuthError) -> HTTPException:
    if exc.code in _AUTH_401:
        return http_error(status.HTTP_401_UNAUTHORIZED, exc.code, exc.message)
    if exc.code in _AUTH_404:
        return http_error(status.HTTP_404_NOT_FOUND, exc.code, exc.message)
    if exc.code in _AUTH_503:
        return http_error(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, exc.message)
    if exc.code in _AUTH_409:
        return http_error(status.HTTP_409_CONFLICT, exc.code, exc.message)
    return http_error(status.HTTP_400_BAD_REQUEST, exc.code, exc.message)


async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    mapped = auth_error_to_http(exc)
    detail = mapped.detail
    payload = detail if isinstance(detail, dict) else error_body("error", str(detail))
    return JSONResponse(status_code=mapped.status_code, content=payload)


async def stream_protocol_handler(_request: Request, exc: StreamProtocolError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=error_body("stream_protocol_error", str(exc)),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        payload = {"code": str(detail["code"]), "message": str(detail["message"])}
    else:
        payload = error_body("http_error", str(detail))
    return JSONResponse(status_code=exc.status_code, content=payload)
