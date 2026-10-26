"""分析任务与风险结果接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_can_view, get_current_user
from app.models import (
    AnalysisTask,
    DocumentAttachment,
    FinancialDocument,
    ManualReview,
    RiskFinding,
    SupplierProfile,
    User,
)
from app.services.analysis import compute_amount_comparison, findings_for_task, report_for_task
from app.services.serializers import (
    analysis_task_to_dict,
    document_to_dict,
    finding_to_dict,
    report_to_dict,
    supplier_to_dict,
)
from app.utils import load_json
from app.services.snapshots import report_document

router = APIRouter(prefix="/api/v1/analysis-tasks", tags=["风险分析"])


def _get_task(db: Session, task_id: int) -> tuple[AnalysisTask, FinancialDocument]:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    document = db.get(FinancialDocument, task.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务对应单据不存在")
    return task, document


@router.get("/{task_id}")
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    task, document = _get_task(db, task_id)
    assert_can_view(db, user, document)
    report = report_for_task(db, task.id)
    findings = findings_for_task(db, task.id)
    applicant = db.get(User, document.applicant_id)
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        counts[finding.risk_level] = counts.get(finding.risk_level, 0) + 1
    return {
        **analysis_task_to_dict(task),
        "document": {
            "id": document.id,
            "document_no": document.document_no,
            "document_type": document.document_type,
            "total_amount": float(document.total_amount or 0),
            "document_status": document.document_status,
            "applicant_name": applicant.display_name if applicant else None,
        },
        "risk_counts": counts,
        "report_id": report.id if report else None,
        "overall_risk_level": report.overall_risk_level if report else None,
        "recommendation": report.recommendation if report else None,
    }


@router.get("/{task_id}/findings")
def get_findings(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    task, document = _get_task(db, task_id)
    assert_can_view(db, user, document)
    findings = findings_for_task(db, task.id)
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        counts[finding.risk_level] = counts.get(finding.risk_level, 0) + 1
    return {
        "task_id": task.id,
        "document_id": document.id,
        "level_counts": counts,
        "items": [finding_to_dict(finding) for finding in findings],
    }


@router.get("/{task_id}/report")
def get_report(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    task, document = _get_task(db, task_id)
    assert_can_view(db, user, document)
    if task.task_status != "succeeded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"分析任务尚未完成，当前状态：{task.task_status}")
    report = report_for_task(db, task.id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险报告不存在")

    findings = findings_for_task(db, task.id)
    applicant = db.get(User, document.applicant_id)
    attachments = db.execute(
        select(DocumentAttachment).where(DocumentAttachment.document_id == document.id)
    ).scalars().all()

    supplier = None
    if document.supplier_code:
        supplier = db.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_code == document.supplier_code)
        ).scalars().first()
    if supplier is None and (document.supplier_name or document.payee_name):
        supplier = db.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_name == (document.supplier_name or document.payee_name))
        ).scalars().first()

    data = report_to_dict(db, report, with_markdown=True)
    data["document"] = report_document(report, task)
    data["document"]["attachment_count"] = data['document'].get('attachment_count', len(data['document'].get('attachments', [])))
    data["findings"] = [finding_to_dict(finding) for finding in findings]
    data["amount_comparison"] = load_json(report.amount_comparison_json, {})
    data["supplier"] = load_json(report.supplier_snapshot_json, None)
    data["task"] = analysis_task_to_dict(task)
    data["summary"] = load_json(report.risk_summary_json, {})
    from app.routers.reviews import assert_current_review
    from app.security import user_role_codes
    data['can_review'] = False
    if set(user_role_codes(db, user.id)) & {'approver', 'finance', 'admin'}:
        try:
            assert_current_review(db, user, report, document, task)
            data['can_review'] = True
        except HTTPException:
            pass
    data['can_analyze'] = document.document_status in {'pending_review', 'reviewing'}
    return data


@router.get("/{task_id}/evidence")
def get_evidence(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    task, document = _get_task(db, task_id)
    assert_can_view(db, user, document)
    findings = findings_for_task(db, task.id)
    evidence = []
    for finding in findings:
        for item in load_json(finding.evidence_json, []) or []:
            evidence.append({**item, "finding_id": finding.id, "risk_title": finding.risk_title, "risk_level": finding.risk_level})
    return evidence
