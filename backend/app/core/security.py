"""
认证与权限控制模块

本模块实现 JWT 认证和基于角色的访问控制（RBAC）。

认证流程：
1. 用户登录 -> 验证用户名密码
2. 生成 JWT Token -> 返回给客户端
3. 后续请求携带 Token -> 验证并提取用户信息
4. 根据角色权限决定是否放行

角色权限：
- admin: 完全访问权限
- analyst: 读写权限
- viewer: 只读权限

核心组件：
- User: 用户模型
- authenticate_user: 用户认证
- create_access_token: 创建访问令牌
- decode_token: 解码令牌
- AuthRBACMiddleware: 认证授权中间件

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
    """
    用户模型

    表示已认证的用户信息。

    属性：
    - username: 用户名
    - role: 角色（admin/analyst/viewer）
    """
    username: str
    role: str


# 默认用户列表（生产环境应使用数据库）
DEFAULT_USERS: Dict[str, Dict[str, str]] = {
    "admin": {"password": "admin123", "role": "admin"},
    "analyst": {"password": "analyst123", "role": "analyst"},
    "viewer": {"password": "viewer123", "role": "viewer"},
}

# 尝试导入 JWT 库，失败则使用回退实现
try:
    from jose import JWTError, jwt  # type: ignore
except Exception:  # pragma: no cover
    JWTError = Exception
    jwt = None


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    用户认证

    验证用户名和密码，成功返回用户对象。

    Args:
        username: 用户名
        password: 密码

    Returns:
        Optional[User]: 认证成功返回用户对象，失败返回 None
    """
    found = DEFAULT_USERS.get(username)
    if not found or found["password"] != password:
        return None
    return User(username=username, role=found["role"])


def create_access_token(user: User) -> str:
    """
    创建访问令牌

    为已认证用户生成 JWT Token。

    Token 载荷：
    - sub: 用户名
    - role: 角色
    - exp: 过期时间戳

    Args:
        user: 已认证的用户对象

    Returns:
        str: JWT Token 字符串
    """
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": int(expire.timestamp()),
    }

    # 优先使用 jose 库，失败则使用回退实现
    if jwt is not None:
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return _encode_fallback_token(payload)


def decode_token(token: str) -> User:
    """
    解码令牌

    解析 JWT Token 并验证有效性。

    验证项：
    - 签名有效性
    - Token 过期时间

    Args:
        token: JWT Token 字符串

    Returns:
        User: 解析出的用户对象

    Raises:
        HTTPException: Token 无效或已过期
    """
    if jwt is not None:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return _build_user_from_payload(payload)
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token decode failed: {e}",
            ) from e

    # 使用回退实现
    try:
        payload = _decode_fallback_token(token)
        return _build_user_from_payload(payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token decode failed: {e}",
        ) from e


def _build_user_from_payload(payload: Dict[str, Any]) -> User:
    """
    从载荷构建用户对象

    解析 Token 载荷并验证必要字段。

    Args:
        payload: Token 载荷字典

    Returns:
        User: 用户对象

    Raises:
        HTTPException: 载荷无效或 Token 已过期
    """
    username = payload.get("sub")
    role = payload.get("role")
    exp = int(payload.get("exp", 0))

    # 验证必要字段
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # 验证过期时间
    if exp and datetime.utcnow().timestamp() > exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return User(username=username, role=role)


def _encode_fallback_token(payload: Dict[str, Any]) -> str:
    """
    回退 Token 编码

    当 jose 库不可用时，使用 HMAC-SHA256 签名。
    格式：{base64(payload)}.{signature}

    Args:
        payload: Token 载荷

    Returns:
        str: 编码后的 Token
    """
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    token = f"{base64.urlsafe_b64encode(raw).decode('utf-8')}.{signature}"
    return token


def _decode_fallback_token(token: str) -> Dict[str, Any]:
    """
    回退 Token 解码

    解析 HMAC-SHA256 签名的 Token。

    Args:
        token: Token 字符串

    Returns:
        Dict[str, Any]: Token 载荷

    Raises:
        ValueError: 签名无效
    """
    encoded, signature = token.split(".", 1)
    raw = base64.urlsafe_b64decode(encoded.encode("utf-8"))
    expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid token signature")

    return json.loads(raw.decode("utf-8"))


class AuthRBACMiddleware(BaseHTTPMiddleware):
    """
    认证授权中间件

    实现 JWT 认证和基于角色的访问控制。

    工作流程：
    1. 检查是否启用认证
    2. 检查是否为开放路径
    3. 提取并验证 Token
    4. 检查角色权限

    权限规则：
    - GET 请求：viewer/analyst/admin
    - 其他请求：analyst/admin

    开放路径：
    - /: 首页
    - /health: 健康检查
    - /docs: API 文档
    - /redoc: ReDoc 文档
    - /openapi.json: OpenAPI 规范
    - /api/v1/auth/*: 认证相关接口
    """

    # 开放路径，不需要认证
    OPEN_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        提取 Token

        从 Authorization 头提取 Bearer Token。

        Args:
            request: 请求对象

        Returns:
            Optional[str]: Token 字符串，不存在则返回 None
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        return auth_header.replace("Bearer ", "", 1).strip()

    def _check_role(self, role: str, method: str) -> bool:
        """
        检查角色权限

        根据请求方法和角色判断是否有权限。

        Args:
            role: 用户角色
            method: HTTP 方法

        Returns:
            bool: True 表示有权限
        """
        if method == "GET":
            # 读权限：viewer/analyst/admin
            return role in {"viewer", "analyst", "admin"}
        # 写权限：analyst/admin
        return role in {"analyst", "admin"}

    async def dispatch(self, request: Request, call_next):
        """
        请求分发处理

        执行认证和授权检查。

        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理函数

        Returns:
            Response: 认证失败返回 401/403，否则返回正常响应
        """
        # 检查是否启用认证
        if not settings.AUTH_ENABLED:
            return await call_next(request)

        # 检查是否为开放路径
        path = request.url.path
        if path in self.OPEN_PATHS or path.startswith("/api/v1/auth/"):
            return await call_next(request)

        # 提取 Token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing Bearer token"},
            )

        # 验证 Token
        try:
            user = decode_token(token)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
            )

        # 检查角色权限
        if not self._check_role(user.role, request.method):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Insufficient role permissions"},
            )

        # 将用户信息附加到请求状态
        request.state.user = user.model_dump(mode="json")
        return await call_next(request)