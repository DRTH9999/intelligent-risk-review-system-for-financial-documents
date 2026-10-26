"""密码哈希、访问令牌与权限辅助。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY
from app.models import Permission, Role, RolePermission, User, UserRole

ALGORITHM = "HS256"
PBKDF2_ITERATIONS = 240_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(user: User) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "jti": jti,
        "ver": user.token_version,
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), jti, expires_at.replace(tzinfo=None)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def user_role_codes(db: Session, user_id: int) -> list[str]:
    rows = db.execute(
        select(Role.role_code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).scalars().all()
    return list(rows)


def user_permissions(db: Session, user_id: int) -> list[str]:
    rows = db.execute(
        select(Permission.permission_code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    ).scalars().all()
    return sorted(set(rows))


def has_role(db: Session, user_id: int, *role_codes: str) -> bool:
    codes = set(user_role_codes(db, user_id))
    return bool(codes.intersection(role_codes))
