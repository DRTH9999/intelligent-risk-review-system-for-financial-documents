"""风险报告、人工复核与导出接口。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_can_view, get_current_user, require_roles
from app.models import (
    AnalysisTask,
    DocumentAttachment,
    FinancialDocument,
    ManualReview,
    ReviewReport,
    RiskFinding,
    SupplierProfile,
    User,
)
from app.schemas import FindingReviewUpdate, ManualReviewIn
from app.services.analysis import compute_amount_comparison, findings_for_task
from app.services.audit import log_action
from app.services.reports import build_markdown, markdown_to_html
from app.services.serializers import document_to_dict, finding_to_dict, report_to_dict, supplier_to_dict
from app.utils import iso, load_json, now
from app.services.snapshots import report_document

router = APIRouter(prefix="/api/v1", tags=["风险报告"])


def _report_with_document(db: Session, report_id: int, user: User) -> tuple[ReviewReport, FinancialDocument, AnalysisTask]:
    report = db.get(ReviewReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险报告不存在")
    document = db.get(FinancialDocument, report.document_id)
    task = db.get(AnalysisTask, report.task_id)
    if document is None or task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告关联的数据不存在")
    assert_can_view(db, user, document)
    return report, document, task


def _supplier_of(db: Session, document: FinancialDocument) -> SupplierProfile | None:
    if document.supplier_code:
        supplier = db.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_code == document.supplier_code)
        ).scalars().first()
        if supplier:
            return supplier
    if document.supplier_name or document.payee_name:
        return db.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_name == (document.supplier_name or document.payee_name))
        ).scalars().first()
    return None


@router.get("/review-reports")
def list_reports(
    document_id: int | None = None,
    risk_level: str | None = None,
    recommendation: str | None = None,
    has_review: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.deps import can_view_document

    query = select(ReviewReport).order_by(ReviewReport.id.desc())
    if document_id:
        query = query.where(ReviewReport.document_id == document_id)
    if risk_level:
        query = query.where(ReviewReport.overall_risk_level == risk_level)
    if recommendation:
        query = query.where(ReviewReport.recommendation == recommendation)
    reports = db.execute(query).scalars().all()

    docs = {doc.id: doc for doc in db.execute(select(FinancialDocument)).scalars().all()}
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    entries = []
    for report in reports:
        doc = docs.get(report.document_id)
        if doc is None or not can_view_document(db, user, doc):
            continue
        saved_document = report_document(report, db.get(AnalysisTask,report.task_id))
        summary = load_json(report.risk_summary_json, {})
        latest_review = db.execute(
            select(ManualReview).where(ManualReview.report_id == report.id).order_by(ManualReview.id.desc())
        ).scalars().first()
        if has_review is True and latest_review is None:
            continue
        if has_review is False and latest_review is not None:
            continue
        entries.append(
            {
                "id": report.id,
                "task_id": report.task_id,
                "document_id": doc.id,
                "document_no": doc.document_no,
                "document_type": doc.document_type,
                "applicant_name": users.get(doc.applicant_id),
                "total_amount": saved_document.get('total_amount'),
                "document_version": saved_document.get('current_version'),
                "overall_risk_level": report.overall_risk_level,
                "recommendation": report.recommendation,
                "risk_counts": summary.get("level_counts", {}),
                "created_at": iso(report.created_at),
                "last_review": (
                    {
                        "reviewer_name": users.get(latest_review.reviewer_id),
                        "review_result": latest_review.review_result,
                        "review_comment": latest_review.review_comment,
                        "reviewed_at": iso(latest_review.reviewed_at),
                    }
                    if latest_review
                    else None
                ),
            }
        )

    total = len(entries)
    start = (page - 1) * page_size
    return {"items": entries[start : start + page_size], "total": total, "page": page, "page_size": page_size}


@router.get("/review-reports/{report_id}")
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    report, document, task = _report_with_document(db, report_id, user)
    data = report_to_dict(db, report, with_markdown=True)
    findings = findings_for_task(db, task.id)
    data["findings"] = [finding_to_dict(item) for item in findings]
    data["amount_comparison"] = load_json(report.amount_comparison_json, {})
    data["document"] = report_document(report, task)
    return data


def assert_current_review(db, user, report, document, task):
    if document.applicant_id == user.id:
        raise HTTPException(403, '不能复核本人申请的单据')
    latest = db.scalars(select(AnalysisTask).where(AnalysisTask.document_id == document.id,
        AnalysisTask.document_version == document.current_version).order_by(AnalysisTask.id.desc())).first()
    if document.document_status not in {'pending_review', 'reviewing'} or task.document_version != document.current_version or not latest or latest.id != task.id or latest.task_status != 'succeeded':
        raise HTTPException(409, '仅可复核当前审批版本的最新已完成报告')


@router.patch("/risk-findings/{finding_id}/review-status")
def update_finding(
    finding_id: int,
    payload: FindingReviewUpdate,
    user: User = Depends(require_roles("approver", "finance", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    finding = db.get(RiskFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险项不存在")
    document = db.get(FinancialDocument, finding.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险项对应单据不存在")
    assert_can_view(db, user, document)
    report = db.scalars(select(ReviewReport).where(ReviewReport.task_id == finding.task_id)).first()
    if not report:
        raise HTTPException(409, '此风险项没有完整报告')
    assert_current_review(db, user, report, document, db.get(AnalysisTask, finding.task_id))
    previous = finding.review_status
    finding.review_status = payload.review_status
    log_action(
        db,
        user.id,
        "risk_finding.review",
        "risk_finding",
        finding.id,
        {"from": previous, "to": payload.review_status, "comment": payload.comment, "document_id": document.id},
    )
    db.commit()
    return finding_to_dict(finding)


@router.post("/review-reports/{report_id}/manual-reviews")
def create_manual_review(
    report_id: int,
    payload: ManualReviewIn,
    user: User = Depends(require_roles("approver", "finance", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    report, document, _task = _report_with_document(db, report_id, user)
    assert_current_review(db, user, report, document, _task)
    if not (payload.review_comment or '').strip() or len(payload.review_comment.strip()) < 2:
        raise HTTPException(422, '请填写至少2个字的复核意见')
    review = ManualReview(
        report_id=report.id,
        reviewer_id=user.id,
        review_result=payload.review_result,
        review_comment=payload.review_comment,
    )
    db.add(review)
    log_action(
        db,
        user.id,
        "report.manual_review",
        "review_report",
        report.id,
        {"document_id": document.id, "result": payload.review_result, "comment": payload.review_comment},
    )
    db.commit()
    db.refresh(review)
    return {
        "id": review.id,
        "report_id": review.report_id,
        "reviewer_id": review.reviewer_id,
        "reviewer_name": user.display_name,
        "review_result": review.review_result,
        "review_comment": review.review_comment,
        "reviewed_at": iso(review.reviewed_at),
    }


@router.get("/review-reports/{report_id}/export")
def export_report(
    report_id: int,
    format: str = Query(default="md", pattern="^(md|html)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report, document, task = _report_with_document(db, report_id, user)
    findings = findings_for_task(db, task.id)
    summary = load_json(report.risk_summary_json, {})
    amount = load_json(report.amount_comparison_json, {})
    supplier = load_json(report.supplier_snapshot_json, None)
    applicant = db.get(User, document.applicant_id)
    doc_payload = report_document(report, task)

    reviews = db.execute(
        select(ManualReview).where(ManualReview.report_id == report.id).order_by(ManualReview.id)
    ).scalars().all()
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    review_payload = [
        {
            "reviewer_name": users.get(item.reviewer_id),
            "review_result": item.review_result,
            "review_comment": item.review_comment,
            "reviewed_at": iso(item.reviewed_at),
        }
        for item in reviews
    ]

    markdown = build_markdown(
        report_id=report.id,
        document=doc_payload,
        findings=[finding_to_dict(item) for item in findings],
        summary=summary,
        amount=amount,
        recommendation=report.recommendation,
        supplier=supplier,
        manual_reviews=review_payload,
        generated_at=iso(report.created_at) or "",
    )
    if report.snapshot_status != 'complete':
        markdown = (report.report_markdown or markdown) + '\n\n> 旧报告缺少完整历史快照，以上内容保留原始存档。\n'
        markdown += '\n## 升级后追加的人工复核记录\n' + '\n'.join(
            f"- {r['reviewed_at']} {r['reviewer_name']}：{r['review_result']}；{r['review_comment']}" for r in review_payload)

    log_action(db, user.id, "report.export", "review_report", report.id, {"format": format, "document_id": document.id})
    db.commit()

    base_name = f"风险审核报告_{document.document_no}_RPT{report.id:06d}"
    if format == "html":
        content = markdown_to_html(markdown, title=base_name)
        media_type = "text/html; charset=utf-8"
        filename = f"{base_name}.html"
    else:
        content = markdown
        media_type = "text/markdown; charset=utf-8"
        filename = f"{base_name}.md"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return Response(content=content.encode("utf-8"), media_type=media_type, headers=headers)
