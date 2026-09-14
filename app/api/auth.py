"""Small dependency-free authentication layer for local and self-hosted deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import get_settings
from app.data.store import create_user, get_user_by_email, get_user_by_id, mark_login, public_user

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "exp": int(time.time()) + settings.auth_token_hours * 3600,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(get_settings().auth_secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64decode(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效或已过期") from exc


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if not user or not user.get("active") or not verify_password(password, user["password_hash"]):
        return None
    mark_login(user["id"])
    return get_user_by_id(user["id"])


def ensure_admin_user() -> None:
    settings = get_settings()
    if get_user_by_email(settings.admin_email):
        return
    create_user(settings.admin_email, settings.admin_name, hash_password(settings.admin_password), role="admin")


def register_user(email: str, display_name: str, password: str) -> dict[str, Any]:
    if not get_settings().allow_registration:
        raise HTTPException(status_code=403, detail="当前未开放用户注册")
    return create_user(email, display_name, hash_password(password), role="member")


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user = get_user_by_id(str(payload.get("sub", "")))
    if not user or not user.get("active"):
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


async def admin_user(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def websocket_user(websocket: WebSocket) -> dict[str, Any]:
    token = websocket.query_params.get("token", "")
    payload = decode_access_token(token)
    user = get_user_by_id(str(payload.get("sub", "")))
    if not user or not user.get("active"):
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}
