"""工作台统计与审计日志接口。"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import can_view_document, get_current_user
from app.models import (
    AnalysisTask,
    AuditLog,
    FinancialDocument,
    ManualReview,
    ReviewReport,
    SupplierProfile,
    User,
)
from app.services.approval import my_tasks
from app.services.serializers import analysis_task_to_dict
from app.utils import iso, load_json

router = APIRouter(prefix="/api/v1", tags=["工作台"])


@router.get("/dashboard/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    documents = db.execute(select(FinancialDocument).order_by(FinancialDocument.id.desc())).scalars().all()
    visible_docs = [doc for doc in documents if can_view_document(db, user, doc)]
    visible_ids = {doc.id for doc in visible_docs}

    reports = db.execute(select(ReviewReport).order_by(ReviewReport.id.desc())).scalars().all()
    latest_by_doc: dict[int, ReviewReport] = {}
    for report in reports:
        if report.document_id in visible_ids and report.document_id not in latest_by_doc:
            latest_by_doc[report.document_id] = report

    risk_counts = {"high": 0, "medium": 0, "low": 0}
    for report in latest_by_doc.values():
        risk_counts[report.overall_risk_level] = risk_counts.get(report.overall_risk_level, 0) + 1

    type_distribution: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for doc in visible_docs:
        type_distribution[doc.document_type] = type_distribution.get(doc.document_type, 0) + 1
        status_counts[doc.document_status] = status_counts.get(doc.document_status, 0) + 1

    reviews = db.execute(select(ManualReview)).scalars().all()
    reviewed_report_ids = {review.report_id for review in reviews}
    pending_reviews = [
        report
        for report in latest_by_doc.values()
        if report.recommendation in {"人工复核", "补充材料", "建议驳回"} and report.id not in reviewed_report_ids
    ]

    tasks = db.execute(select(AnalysisTask).order_by(AnalysisTask.id.desc())).scalars().all()
    recent_tasks = []
    for task in tasks:
        if task.document_id not in visible_ids:
            continue
        document = next((doc for doc in visible_docs if doc.id == task.document_id), None)
        report = latest_by_doc.get(task.document_id)
        report_for_task = db.execute(
            select(ReviewReport).where(ReviewReport.task_id == task.id).order_by(ReviewReport.id.desc())
        ).scalars().first()
        recent_tasks.append(
            {
                **analysis_task_to_dict(task),
                "document_no": document.document_no if document else None,
                "document_type": document.document_type if document else None,
                "overall_risk_level": report_for_task.overall_risk_level if report_for_task else None,
            }
        )
        if len(recent_tasks) >= 8:
            break

    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    recent_reports = []
    for report in latest_by_doc.values():
        if len(recent_reports) >= 6:
            break
        document = next((doc for doc in visible_docs if doc.id == report.document_id), None)
        if document is None:
            continue
        recent_reports.append(
            {
                "report_id": report.id,
                "task_id": report.task_id,
                "document_id": document.id,
                "document_no": document.document_no,
                "document_type": document.document_type,
                "applicant_name": users.get(document.applicant_id),
                "total_amount": load_json(report.amount_comparison_json, {}).get('document_total'),
                "overall_risk_level": report.overall_risk_level,
                "recommendation": report.recommendation,
                "created_at": iso(report.created_at),
            }
        )

    pending_review_items = [
        {
            "report_id": report.id,
            "document_id": report.document_id,
            "document_no": next((doc.document_no for doc in visible_docs if doc.id == report.document_id), None),
            "overall_risk_level": report.overall_risk_level,
            "recommendation": report.recommendation,
            "created_at": iso(report.created_at),
        }
        for report in pending_reviews[:6]
    ]

    today = date.today()
    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_docs = [doc for doc in visible_docs if doc.apply_date == day]
        day_reports = [report for report in latest_by_doc.values() if report.created_at.date() == day]
        trend.append(
            {
                "date": day.isoformat(),
                "documents": len(day_docs),
                "high_risk": len([report for report in day_reports if report.overall_risk_level == "high"]),
                "risk_reports": len(day_reports),
            }
        )

    suppliers = db.execute(select(SupplierProfile)).scalars().all()
    from app.security import user_role_codes
    if not set(user_role_codes(db,user.id)) & {'admin','finance'}:
        suppliers = [supplier for supplier in suppliers if any(
            document.supplier_code == supplier.supplier_code or (document.supplier_name or document.payee_name) == supplier.supplier_name
            for document in visible_docs)]
    supplier_alerts = [
        {
            "supplier_code": supplier.supplier_code,
            "supplier_name": supplier.supplier_name,
            "blacklist_status": supplier.blacklist_status,
            "credit_status": supplier.credit_status,
            "risk_tags": load_json(supplier.risk_tags_json, []),
        }
        for supplier in suppliers
        if supplier.blacklist_status != "normal" or supplier.credit_status not in {"normal", "good"}
    ][:6]

    return {
        "user": {"id": user.id, "display_name": user.display_name, "department": user.department},
        "stats": {
            "total_documents": len(visible_docs),
            "pending_approvals": len(my_tasks(db, user, "pending")),
            "high_risk": risk_counts["high"],
            "medium_risk": risk_counts["medium"],
            "low_risk": risk_counts["low"],
            "pending_manual_reviews": len(pending_reviews),
            "total_amount": round(sum(float(doc.total_amount or 0) for doc in visible_docs), 2),
            "analyzed_documents": len(latest_by_doc),
        },
        "status_counts": status_counts,
        "type_distribution": [{"type": key, "count": value} for key, value in type_distribution.items()],
        "risk_distribution": [{"level": key, "count": value} for key, value in risk_counts.items()],
        "recent_tasks": recent_tasks,
        "recent_reports": recent_reports,
        "pending_review_items": pending_review_items,
        "trend": trend,
        "supplier_alerts": supplier_alerts,
    }


@router.get("/audit-logs")
def audit_logs(
    action_type: str | None = None,
    resource_type: str | None = None,
    user_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.security import user_role_codes

    query = select(AuditLog).order_by(AuditLog.id.desc())
    if action_type:
        query = query.where(AuditLog.action_type.like(f"%{action_type}%"))
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    roles = set(user_role_codes(db, user.id))
    if not roles.intersection({"admin", "finance"}):
        query = query.where(AuditLog.user_id == user.id)
    rows = db.execute(query).scalars().all()
    total = len(rows)
    start = (page - 1) * page_size
    users = {item.id: item.display_name for item in db.execute(select(User)).scalars().all()}
    return {
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "user_name": users.get(row.user_id),
                "action_type": row.action_type,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "detail": load_json(row.detail_json, {}),
                "ip_address": row.ip_address,
                "created_at": iso(row.created_at),
            }
            for row in rows[start : start + page_size]
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
