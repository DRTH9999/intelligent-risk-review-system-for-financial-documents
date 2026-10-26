"""统一的对象序列化。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisTask,
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflow,
    ApprovalWorkflowNode,
    AttachmentParseResult,
    DocumentAttachment,
    DocumentLineItem,
    DocumentStatusLog,
    DocumentVersion,
    FinancialDocument,
    ManualReview,
    ReviewReport,
    RiskFinding,
    SupplierProfile,
    User,
)
from app.utils import iso, load_json


def user_to_dict(db: Session, user: User) -> dict:
    from app.security import user_permissions, user_role_codes

    roles = user_role_codes(db, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "department": user.department,
        "job_level": user.job_level,
        "status": user.status,
        "roles": roles,
        "permissions": user_permissions(db, user.id),
        "created_at": iso(user.created_at),
    }



def line_item_to_dict(item: DocumentLineItem) -> dict:
    return {
        "id": item.id,
        "document_id": item.document_id,
        "item_type": item.item_type,
        "item_name": item.item_name,
        "item_spec": item.item_spec,
        "expense_category": item.expense_category,
        "expense_date": iso(item.expense_date),
        "expense_location": item.expense_location,
        "quantity": float(item.quantity or 0),
        "unit_price": float(item.unit_price or 0),
        "amount": float(item.amount or 0),
        "payee_name": item.payee_name,
        "payee_account": item.payee_account,
        "remark": item.remark,
    }


def attachment_to_dict(db: Session, att: DocumentAttachment, with_parse: bool = False) -> dict:
    data = {
        "id": att.id,
        "attachment_id": att.id,
        "document_id": att.document_id,
        "document_version": att.document_version,
        "file_name": att.file_name,
        "file_type": att.file_type,
        "file_size": att.file_size,
        "file_hash": att.file_hash,
        "storage_status": att.storage_status,
        "parse_status": att.parse_status,
        "created_at": iso(att.created_at),
        "preview_url": f"/api/v1/documents/{att.document_id}/attachments/{att.id}?disposition=inline",
        "download_url": f"/api/v1/documents/{att.document_id}/attachments/{att.id}?disposition=attachment",
    }
    if with_parse:
        parse = db.execute(
            select(AttachmentParseResult)
            .where(AttachmentParseResult.attachment_id == att.id)
            .order_by(AttachmentParseResult.id.desc())
        ).scalars().first()
        data["parse_result"] = parse_result_to_dict(parse) if parse else None
    return data


def parse_result_to_dict(parse: AttachmentParseResult | None) -> dict | None:
    if parse is None:
        return None
    return {
        "id": parse.id,
        "attachment_id": parse.attachment_id,
        "document_category": parse.document_category,
        "full_text": parse.full_text,
        "page_texts": load_json(parse.page_text_json, []),
        "fields": load_json(parse.fields_json, {}),
        "evidence": load_json(parse.evidence_positions_json, []),
        "confidence": round(float(parse.confidence or 0), 3),
        "parser_source": parse.parser_source,
        "error_message": parse.error_message,
        "created_at": iso(parse.created_at),
    }


def document_to_dict(
    db: Session,
    doc: FinancialDocument,
    *,
    with_items: bool = True,
    with_attachments: bool = True,
    with_versions: bool = False,
    with_logs: bool = False,
    with_approval: bool = False,
) -> dict:
    applicant = db.get(User, doc.applicant_id)
    data = {
        "id": doc.id,
        "document_id": doc.id,
        "document_type": doc.document_type,
        "document_no": doc.document_no,
        "applicant_id": doc.applicant_id,
        "applicant_name": applicant.display_name if applicant else None,
        "applicant_department": doc.applicant_department,
        "budget_department": doc.budget_department,
        "payee_name": doc.payee_name,
        "payee_account": doc.payee_account,
        "expense_category": doc.expense_category,
        "total_amount": float(doc.total_amount or 0),
        "currency": doc.currency,
        "apply_date": iso(doc.apply_date),
        "reason_text": doc.reason_text,
        "document_status": doc.document_status,
        "current_version": doc.current_version,
        "revision": doc.revision,
        "contract_no": doc.contract_no,
        "supplier_name": doc.supplier_name,
        "supplier_code": doc.supplier_code,
        "payment_ratio": doc.payment_ratio,
        "payment_terms": doc.payment_terms,
        "planned_payment_date": iso(doc.planned_payment_date),
        "batch_total_amount": float(doc.batch_total_amount) if doc.batch_total_amount is not None else None,
        "batch_payment_count": doc.batch_payment_count,
        "travel_location": doc.travel_location,
        "travel_start_date": iso(doc.travel_start_date),
        "travel_end_date": iso(doc.travel_end_date),
        "ext": load_json(doc.ext_json, {}),
        "created_at": iso(doc.created_at),
        "updated_at": iso(doc.updated_at),
    }
    if with_items:
        items = db.execute(
            select(DocumentLineItem).where(DocumentLineItem.document_id == doc.id).order_by(DocumentLineItem.id)
        ).scalars().all()
        data["line_items"] = [line_item_to_dict(i) for i in items]
        data["line_items_total"] = round(sum(float(i.amount or 0) for i in items), 2)
    if with_attachments:
        atts = db.execute(
            select(DocumentAttachment).where(DocumentAttachment.document_id == doc.id, DocumentAttachment.storage_status == 'stored').order_by(DocumentAttachment.id)
        ).scalars().all()
        data["attachments"] = [attachment_to_dict(db, a) for a in atts]
    if with_versions:
        versions = db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.version_no.desc())
        ).scalars().all()
        data["versions"] = [
            {
                "id": v.id,
                "version_no": v.version_no,
                "created_by": v.created_by,
                "created_by_name": (db.get(User, v.created_by).display_name if db.get(User, v.created_by) else None),
                "created_at": iso(v.created_at),
            }
            for v in versions
        ]
    if with_logs:
        logs = db.execute(
            select(DocumentStatusLog).where(DocumentStatusLog.document_id == doc.id).order_by(DocumentStatusLog.id)
        ).scalars().all()
        users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
        data["status_logs"] = [
            {
                "id": log.id,
                "from_status": log.from_status,
                "to_status": log.to_status,
                "operator_id": log.operator_id,
                "operator_name": users.get(log.operator_id),
                "remark": log.remark,
                "created_at": iso(log.created_at),
            }
            for log in logs
        ]
    if with_approval:
        data["approval"] = approval_progress(db, doc.id)
    return data


def approval_progress(db: Session, document_id: int) -> dict | None:
    instance = db.execute(
        select(ApprovalInstance)
        .where(ApprovalInstance.document_id == document_id)
        .order_by(ApprovalInstance.id.desc())
    ).scalars().first()
    if instance is None:
        return None
    workflow = db.get(ApprovalWorkflow, instance.workflow_id)
    nodes = db.execute(
        select(ApprovalWorkflowNode)
        .where(ApprovalWorkflowNode.workflow_id == instance.workflow_id)
        .order_by(ApprovalWorkflowNode.node_order)
    ).scalars().all()
    tasks = db.execute(
        select(ApprovalTask).where(ApprovalTask.instance_id == instance.id).order_by(ApprovalTask.id)
    ).scalars().all()
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    task_by_node: dict[int, ApprovalTask] = {}
    for task in tasks:
        task_by_node.setdefault(task.node_id, task)
    return {
        "instance_id": instance.id,
        "document_id": document_id,
        "instance_status": instance.instance_status,
        "current_node_id": instance.current_node_id,
        "document_version": instance.document_version,
        "started_at": iso(instance.started_at),
        "finished_at": iso(instance.finished_at),
        "workflow_name": workflow.workflow_name if workflow else None,
        "nodes": [
            {
                "node_id": node.id,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "approver_role": node.approver_role,
                "approval_mode": node.approval_mode,
                "task_id": task_by_node.get(node.id).id if task_by_node.get(node.id) else None,
                "task_status": task_by_node.get(node.id).task_status if task_by_node.get(node.id) else "waiting",
                "approver_id": task_by_node.get(node.id).approver_id if task_by_node.get(node.id) else None,
                "approver_name": users.get(task_by_node.get(node.id).approver_id) if task_by_node.get(node.id) else None,
                "review_comment": task_by_node.get(node.id).review_comment if task_by_node.get(node.id) else None,
                "processed_at": iso(task_by_node.get(node.id).processed_at) if task_by_node.get(node.id) else None,
            }
            for node in nodes
        ],
    }


def analysis_task_to_dict(task: AnalysisTask) -> dict:
    return {
        "id": task.id,
        "task_id": task.id,
        "session_id": task.session_id,
        "document_id": task.document_id,
        "document_version": task.document_version,
        "task_status": task.task_status,
        "current_step": task.current_step,
        "progress": task.progress,
        "triggered_by": task.triggered_by,
        "started_at": iso(task.started_at),
        "finished_at": iso(task.finished_at),
        "error_message": task.error_message,
    }


def finding_to_dict(finding: RiskFinding) -> dict:
    return {
        "id": finding.id,
        "finding_id": finding.id,
        "task_id": finding.task_id,
        "document_id": finding.document_id,
        "risk_type": finding.risk_type,
        "risk_category": finding.risk_category,
        "risk_level": finding.risk_level,
        "risk_title": finding.risk_title,
        "description": finding.description,
        "actual_value": load_json(finding.actual_value_json, {}),
        "reference_value": load_json(finding.reference_value_json, {}),
        "threshold": load_json(finding.threshold_json, {}),
        "evidence": load_json(finding.evidence_json, []),
        "suggestion_text": finding.suggestion_text,
        "review_status": finding.review_status,
        "created_at": iso(finding.created_at),
    }


def report_to_dict(db: Session, report: ReviewReport, with_markdown: bool = False) -> dict:
    reviews = db.execute(
        select(ManualReview).where(ManualReview.report_id == report.id).order_by(ManualReview.id)
    ).scalars().all()
    reviewers = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    data = {
        "id": report.id,
        "report_id": report.id,
        "task_id": report.task_id,
        "document_id": report.document_id,
        "overall_risk_level": report.overall_risk_level,
        "risk_summary": load_json(report.risk_summary_json, {}),
        "amount_comparison": load_json(report.amount_comparison_json, {}),
        "recommendation": report.recommendation,
        "created_at": iso(report.created_at),
        "snapshot_status": report.snapshot_status,
        "manual_reviews": [
            {
                "id": r.id,
                "reviewer_id": r.reviewer_id,
                "reviewer_name": reviewers.get(r.reviewer_id),
                "review_result": r.review_result,
                "review_comment": r.review_comment,
                "reviewed_at": iso(r.reviewed_at),
            }
            for r in reviews
        ],
    }
    if with_markdown:
        data["report_markdown"] = report.report_markdown
    return data


def supplier_to_dict(db: Session, supplier: SupplierProfile, user=None) -> dict:
    from app.models import FinancialDocument

    from sqlalchemy import or_
    docs = db.execute(
        select(FinancialDocument).where(or_(FinancialDocument.supplier_code == supplier.supplier_code,
            FinancialDocument.supplier_name == supplier.supplier_name, FinancialDocument.payee_name == supplier.supplier_name))
    ).scalars().all()
    if user is not None:
        from app.deps import can_view_document
        docs = [document for document in docs if can_view_document(db,user,document)]
    return {
        "id": supplier.id,
        "supplier_code": supplier.supplier_code,
        "supplier_name": supplier.supplier_name,
        "credit_status": supplier.credit_status,
        "blacklist_status": supplier.blacklist_status,
        "risk_tags": load_json(supplier.risk_tags_json, []),
        "bank_accounts": load_json(supplier.bank_accounts_json, []),
        "contact_info": supplier.contact_info,
        "updated_at": iso(supplier.updated_at),
        "history": [
            {
                "document_id": d.id,
                "document_no": d.document_no,
                "document_type": d.document_type,
                "total_amount": float(d.total_amount or 0),
                "document_status": d.document_status,
                "apply_date": iso(d.apply_date),
            }
            for d in docs
        ],
        "payment_count": len(docs),
        "payment_total": round(sum(float(d.total_amount or 0) for d in docs), 2),
    }
