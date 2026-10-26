"""操作审计。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.utils import dump_json


def log_action(
    db: Session,
    user_id: int | None,
    action_type: str,
    resource_type: str,
    resource_id: Any = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        detail_json=dump_json(detail) if detail else None,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
