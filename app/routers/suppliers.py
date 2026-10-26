"""供应商档案与风险信息接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models import FinancialDocument, ReviewReport, RiskFinding, SupplierProfile, User
from app.schemas import SupplierUpdate
from app.services.audit import log_action
from app.services.serializers import supplier_to_dict
from app.utils import dump_json, iso, load_json

router = APIRouter(prefix="/api/v1/suppliers", tags=["供应商"])


@router.get("")
def list_suppliers(
    keyword: str | None = None,
    blacklist: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(SupplierProfile).order_by(SupplierProfile.id)
    if keyword:
        query = query.where(SupplierProfile.supplier_name.like(f"%{keyword}%"))
    rows = db.execute(query).scalars().all()
    result = []
    for supplier in rows:
        if blacklist is not None and (supplier.blacklist_status != "normal") != blacklist:
            continue
        data = supplier_to_dict(db, supplier, user)
        from app.security import user_role_codes
        if data['history'] or set(user_role_codes(db,user.id)) & {'finance','admin'}:
            result.append(data)
    return result


@router.get("/{supplier_code}/risks")
def supplier_risks(supplier_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    supplier = db.execute(
        select(SupplierProfile).where(SupplierProfile.supplier_code == supplier_code)
    ).scalars().first()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    data = supplier_to_dict(db, supplier, user)
    from app.security import user_role_codes
    if not data['history'] and not set(user_role_codes(db,user.id)) & {'finance','admin'}:
        raise HTTPException(404, '供应商不存在或不在数据权限范围内')

    documents = db.execute(
        select(FinancialDocument).where(FinancialDocument.supplier_code == supplier.supplier_code)
    ).scalars().all()
    doc_ids = [document['document_id'] for document in data['history']]
    reports = []
    if doc_ids:
        reports = db.execute(
            select(ReviewReport).where(ReviewReport.document_id.in_(doc_ids)).order_by(ReviewReport.id.desc()).limit(20)
        ).scalars().all()
    findings = []
    for report in reports:
        rows = db.execute(
            select(RiskFinding).where(
                RiskFinding.task_id == report.task_id,
                RiskFinding.risk_level.in_(["high", "medium"]),
            )
        ).scalars().all()
        findings.extend(
            {
                "finding_id": row.id,
                "document_id": row.document_id,
                "risk_type": row.risk_type,
                "risk_level": row.risk_level,
                "risk_title": row.risk_title,
                "description": row.description,
                "created_at": iso(row.created_at),
            }
            for row in rows
        )
    data["risk_events"] = findings[:20]
    data["reports"] = [
        {
            "report_id": report.id,
            "document_id": report.document_id,
            "overall_risk_level": report.overall_risk_level,
            "recommendation": report.recommendation,
            "created_at": iso(report.created_at),
        }
        for report in reports
    ]
    return data


@router.patch("/{supplier_code}")
def update_supplier(
    supplier_code: str,
    payload: SupplierUpdate,
    user: User = Depends(require_roles("finance", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    supplier = db.execute(
        select(SupplierProfile).where(SupplierProfile.supplier_code == supplier_code)
    ).scalars().first()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    data = payload.model_dump(exclude_unset=True)
    risk_tags = data.pop("risk_tags", None)
    bank_accounts = data.pop("bank_accounts", None)
    for key, value in data.items():
        if value is not None:
            setattr(supplier, key, value)
    if risk_tags is not None:
        supplier.risk_tags_json = dump_json(risk_tags)
    if bank_accounts is not None:
        supplier.bank_accounts_json = dump_json(bank_accounts)
    log_action(
        db,
        user.id,
        "supplier.update",
        "supplier_profile",
        supplier.id,
        {"supplier_code": supplier.supplier_code, "changes": payload.model_dump(exclude_unset=True)},
    )
    db.commit()
    return supplier_to_dict(db, supplier)
