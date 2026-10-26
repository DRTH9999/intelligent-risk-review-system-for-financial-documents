"""认证接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bearer, get_current_user
from app.models import AuthToken, User
from app.schemas import LoginRequest
from app.security import create_access_token, decode_token, user_role_codes, verify_password
from app.services.audit import log_action
from app.services.serializers import user_to_dict
from app.utils import iso

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = db.execute(select(User).where(User.username == payload.username.strip())).scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用，请联系系统管理员")

    token, jti, expires_at = create_access_token(user)
    db.add(AuthToken(user_id=user.id, jti=jti, expires_at=expires_at))
    log_action(db, user.id, "auth.login", "user", user.id, {"username": user.username}, request.client.host if request.client else None)
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": iso(expires_at),
        "user": user_to_dict(db, user),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return user_to_dict(db, user)


@router.post("/logout")
def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = decode_token(credentials.credentials) if credentials else None
    if payload:
        token = db.execute(select(AuthToken).where(AuthToken.jti == payload.get("jti"))).scalars().first()
        if token:
            token.revoked = True
    log_action(db, user.id, "auth.logout", "user", user.id, None, request.client.host if request.client else None)
    db.commit()
    return {"message": "已退出登录"}


@router.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    from app.services.serializers import user_to_dict as serialize_user

    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [
        {
            "id": item.id,
            "username": item.username,
            "display_name": item.display_name,
            "department": item.department,
            "job_level": item.job_level,
            "status": item.status,
            "roles": user_role_codes(db, item.id),
        }
        for item in users
    ]
