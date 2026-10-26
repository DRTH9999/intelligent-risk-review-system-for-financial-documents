"""用户与角色管理接口（系统管理员）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import Role, User, UserRole
from app.schemas import UserCreate, UserUpdate
from app.security import hash_password, user_role_codes
from app.services.audit import log_action
from app.utils import iso

router = APIRouter(prefix="/api/v1", tags=["系统管理"])


def _user_row(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "department": user.department,
        "job_level": user.job_level,
        "status": user.status,
        "roles": user_role_codes(db, user.id),
        "created_at": iso(user.created_at),
    }


@router.get("/users")
def list_users(
    keyword: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(User).order_by(User.id)
    if keyword:
        query = query.where(User.display_name.like(f"%{keyword}%"))
    return [_user_row(db, item) for item in db.execute(query).scalars().all()]


@router.get("/roles")
def list_roles(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    roles = db.execute(select(Role).order_by(Role.id)).scalars().all()
    return [
        {
            "id": role.id,
            "role_code": role.role_code,
            "role_name": role.role_name,
            "status": role.status,
        }
        for role in roles
    ]


def _sync_roles(db: Session, user_id: int, role_codes: list[str]) -> None:
    roles = db.execute(select(Role).where(Role.role_code.in_(role_codes))).scalars().all()
    if len(roles) != len(set(role_codes)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="存在无效的角色编码")
    for assignment in db.execute(select(UserRole).where(UserRole.user_id == user_id)).scalars().all():
        db.delete(assignment)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user_id, role_id=role.id))


@router.post("/users")
def create_user(
    payload: UserCreate,
    current: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    exists = db.execute(select(User).where(User.username == payload.username)).scalars().first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        department=payload.department,
        job_level=payload.job_level,
        status=payload.status or "active",
    )
    db.add(user)
    db.flush()
    _sync_roles(db, user.id, payload.roles or ["applicant"])
    log_action(db, current.id, "user.create", "user", user.id, {"username": user.username, "roles": payload.roles})
    db.commit()
    return _user_row(db, user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    current: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    roles = data.pop("roles", None)
    password = data.pop("password", None)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    if password:
        user.password_hash = hash_password(password)
        user.token_version = (user.token_version or 0) + 1
    if roles is not None:
        _sync_roles(db, user.id, roles)
    log_action(db, current.id, "user.update", "user", user.id, {"fields": list(payload.model_dump(exclude_unset=True).keys())})
    db.commit()
    return _user_row(db, user)
