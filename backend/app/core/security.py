"""
认证与权限控制
Auth & RBAC
"""

from __future__ import annotations

from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class User(BaseModel):
    username: str
    role: str


DEFAULT_USERS: Dict[str, Dict[str, str]] = {
    "admin": {"password": "admin123", "role": "admin"},
    "analyst": {"password": "analyst123", "role": "analyst"},
    "viewer": {"password": "viewer123", "role": "viewer"},
}

try:
    from jose import JWTError, jwt  # type: ignore
except Exception:  # pragma: no cover
    JWTError = Exception
    jwt = None


def authenticate_user(username: str, password: str) -> Optional[User]:
    found = DEFAULT_USERS.get(username)
    if not found or found["password"] != password:
        return None
    return User(username=username, role=found["role"])


def create_access_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": int(expire.timestamp()),
    }
    if jwt is not None:
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return _encode_fallback_token(payload)


def decode_token(token: str) -> User:
    if jwt is not None:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return _build_user_from_payload(payload)
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token decode failed: {e}",
            ) from e
    try:
        payload = _decode_fallback_token(token)
        return _build_user_from_payload(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token decode failed: {e}",
        ) from e


def _build_user_from_payload(payload: Dict[str, Any]) -> User:
    username = payload.get("sub")
    role = payload.get("role")
    exp = int(payload.get("exp", 0))
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if exp and datetime.utcnow().timestamp() > exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return User(username=username, role=role)


def _encode_fallback_token(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    token = f"{base64.urlsafe_b64encode(raw).decode('utf-8')}.{signature}"
    return token


def _decode_fallback_token(token: str) -> Dict[str, Any]:
    encoded, signature = token.split(".", 1)
    raw = base64.urlsafe_b64decode(encoded.encode("utf-8"))
    expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid token signature")
    return json.loads(raw.decode("utf-8"))


class AuthRBACMiddleware(BaseHTTPMiddleware):
    """基于 JWT 的鉴权与 RBAC 中间件"""

    OPEN_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def _extract_token(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        return auth_header.replace("Bearer ", "", 1).strip()

    def _check_role(self, role: str, method: str) -> bool:
        if method == "GET":
            return role in {"viewer", "analyst", "admin"}
        return role in {"analyst", "admin"}

    async def dispatch(self, request: Request, call_next):
        if not settings.AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        if path in self.OPEN_PATHS or path.startswith("/api/v1/auth/"):
            return await call_next(request)

        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing Bearer token"},
            )

        try:
            user = decode_token(token)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
            )

        if not self._check_role(user.role, request.method):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Insufficient role permissions"},
            )

        request.state.user = user.model_dump(mode="json")
        return await call_next(request)
