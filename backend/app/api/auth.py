"""
认证 API
Auth API
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.core.security import authenticate_user, create_access_token, decode_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime
    role: str
    username: str


class UserResponse(BaseModel):
    username: str
    role: str


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        role=user.role,
        username=user.username,
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户")
async def me(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    user = decode_token(authorization.replace("Bearer ", "", 1).strip())
    return UserResponse(username=user.username, role=user.role)
