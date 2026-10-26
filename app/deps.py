"""FastAPI 依赖：登录态、角色权限、数据权限。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnalysisTask, ApprovalInstance, ApprovalTask, AuthToken, FinancialDocument, User
from app.security import decode_token, user_role_codes
from app.utils import now

bearer = HTTPBearer(auto_error=False)
ALL_SCOPE_ROLES = {"admin", "finance"}


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌无效或已过期")
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌格式错误")

    token_record = db.execute(select(AuthToken).where(AuthToken.jti == payload.get("jti"))).scalar_one_or_none()
    if token_record is None or token_record.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌已被撤销，请重新登录")
    if token_record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌已过期，请重新登录")

    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")
    request.state.user = user
    return user


def require_roles(*role_codes: str):
    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        codes = set(user_role_codes(db, user.id))
        if not codes.intersection(role_codes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权执行该操作")
        return user

    return checker


def can_view_document(db: Session, user: User, document: FinancialDocument) -> bool:
    roles = set(user_role_codes(db, user.id))
    if roles.intersection(ALL_SCOPE_ROLES):
        return True
    if document.applicant_id == user.id:
        return True
    if "approver" in roles:
        exists = db.execute(
            select(ApprovalTask.id)
            .join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id)
            .where(
                ApprovalInstance.document_id == document.id,
                ApprovalTask.approver_id == user.id,
            )
        ).first()
        if exists:
            return True
    return False


def assert_can_view(db: Session, user: User, document: FinancialDocument) -> None:
    if not can_view_document(db, user, document):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该单据")


def assert_can_edit(db: Session, user: User, document: FinancialDocument) -> None:
    roles = set(user_role_codes(db, user.id))
    if document.applicant_id != user.id and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能编辑本人创建的单据")
    if document.document_status not in {"draft", "returned", "withdrawn"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许编辑单据")
    active = db.execute(select(AnalysisTask.id).where(
        AnalysisTask.document_id == document.id,
        AnalysisTask.task_status.in_(
            ['queued', 'querying_document', 'loading_attachments', 'parsing_attachments', 'analyzing', 'generating_report']))).first()
    if active:
        raise HTTPException(status_code=409, detail='当前单据正在分析，请完成或取消后编辑')


def get_role_codes(db: Session, user: User) -> list[str]:
    return user_role_codes(db, user.id)
