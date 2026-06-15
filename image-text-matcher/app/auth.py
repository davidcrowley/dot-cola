from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Annotated

from fastapi import HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings


AUTH_COOKIE_NAME = "admin_session"
API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def is_authenticated(request: Request) -> bool:
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        return False
    username = _decode_cookie(cookie)
    return username == get_settings().admin_username


def is_valid_api_key(api_key: str | None) -> bool:
    configured_api_key = get_settings().api_key
    if not configured_api_key or not api_key:
        return False
    return hmac.compare_digest(api_key, configured_api_key)


def require_authenticated(
    request: Request,
    api_key: Annotated[str | None, Security(api_key_header)] = None,
) -> None:
    if not is_authenticated(request) and not is_valid_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def login(response: Response, username: str, password: str) -> bool:
    settings = get_settings()
    if username != settings.admin_username or password != settings.admin_password:
        return False
    response.set_cookie(
        AUTH_COOKIE_NAME,
        _encode_cookie(username),
        httponly=True,
        samesite="lax",
    )
    return True


def logout(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME)


def _encode_cookie(username: str) -> str:
    signature = hmac.new(
        get_settings().session_secret_key.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = f"{username}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cookie(cookie: str) -> str | None:
    try:
        payload = base64.urlsafe_b64decode(cookie.encode("ascii")).decode("utf-8")
        username, signature = payload.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    expected = hmac.new(
        get_settings().session_secret_key.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return username
