"""单据、明细与附件接口。"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ALLOWED_EXTENSIONS, ATTACHMENT_DIR, MAX_ATTACHMENT_SIZE
from app.database import get_db
from app.deps import assert_can_edit, assert_can_view, can_view_document, get_current_user
from app.models import (
    AnalysisTask,
    ApprovalInstance,
    DocumentAttachment,
    DocumentLineItem,
    FinancialDocument,
    ReviewReport,
    RiskFinding,
    User,
)
from app.schemas import AnalysisCreate, DocumentCreate, DocumentUpdate, LineItemIn, LineItemUpdate
from app.services.analysis import compute_amount_comparison, create_analysis_task, latest_any_task, latest_task, report_for_task
from app.services.audit import log_action
from app.services.documents import (
    add_line_item,
    copy_document,
    create_document,
    get_document,
    submit_document,
    update_document,
    update_line_item,
    void_document,
    withdraw_document,
)
from app.services.parsing import validate_attachment_bytes
from app.services.serializers import (
    analysis_task_to_dict,
    attachment_to_dict,
    document_to_dict,
    finding_to_dict,
    parse_result_to_dict,
    report_to_dict,
)
from app.utils import load_json, now

router = APIRouter(prefix="/api/v1", tags=["单据"])

MEDIA_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _latest_attachment_parse(db: Session, doc_id: int) -> list[dict]:
    rows = db.execute(
        select(DocumentAttachment).where(DocumentAttachment.document_id == doc_id, DocumentAttachment.storage_status == 'stored').order_by(DocumentAttachment.id)
    ).scalars().all()
    return [attachment_to_dict(db, row, with_parse=True) for row in rows]


def _latest_findings(db: Session, task_id: int) -> list[dict]:
    rows = db.execute(select(RiskFinding).where(RiskFinding.task_id == task_id).order_by(RiskFinding.id)).scalars().all()
    return [finding_to_dict(row) for row in rows]


def _doc_allowed_actions(db: Session, user: User, doc: FinancialDocument, roles: set[str]) -> list[str]:
    actions = ["view"]
    is_owner = doc.applicant_id == user.id
    if is_owner or "admin" in roles:
        if doc.document_status in {"draft", "returned", "withdrawn"}:
            actions += ["edit", "upload", "delete_attachment"]
        if doc.document_status in {"draft", "returned", "withdrawn", "rejected"}:
            actions.append("void")
        actions.append("copy")
    if is_owner:
        if doc.document_status in {"draft", "returned", "withdrawn"}:
            actions.append("submit")
        if doc.document_status in {"pending_review", "reviewing"}:
            actions.append("withdraw")
    if "admin" in roles or "finance" in roles or "approver" in roles:
        actions.append("analyze")
    elif is_owner:
        actions.append("analyze")
    return sorted(set(actions))


@router.post("/documents")
def create(payload: DocumentCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = create_document(db, user, payload)
    log_action(db, user.id, "document.create", "financial_document", doc.id, {"document_no": doc.document_no}, request.client.host if request.client else None)
    db.commit()
    return document_to_dict(db, doc, with_items=True, with_attachments=True)


@router.get("/documents")
def list_documents(
    document_type: str | None = None,
    document_no: str | None = None,
    applicant_id: int | None = None,
    department: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = select(FinancialDocument).order_by(FinancialDocument.id.desc())
    if document_type:
        query = query.where(FinancialDocument.document_type == document_type)
    if document_no:
        query = query.where(FinancialDocument.document_no.like(f"%{document_no}%"))
    if applicant_id:
        query = query.where(FinancialDocument.applicant_id == applicant_id)
    if department:
        query = query.where(FinancialDocument.budget_department == department)
    if date_from:
        query = query.where(FinancialDocument.apply_date >= date_from)
    if date_to:
        query = query.where(FinancialDocument.apply_date <= date_to)

    docs = db.execute(query).scalars().all()
    visible_all = [doc for doc in docs if can_view_document(db, user, doc)]
    if keyword:
        needle = keyword.strip().lower()
        visible_all = [
            doc
            for doc in visible_all
            if needle in doc.document_no.lower()
            or needle in (doc.payee_name or "").lower()
            or needle in (doc.reason_text or "").lower()
        ]

    statuses: list[str] = []
    if status_filter:
        statuses = [item.strip() for item in status_filter.split(",") if item.strip()]
    visible = [doc for doc in visible_all if not statuses or doc.document_status in statuses]

    status_counts: dict[str, int] = {}
    for doc in visible_all:
        status_counts[doc.document_status] = status_counts.get(doc.document_status, 0) + 1

    total = len(visible)
    start = (page - 1) * page_size
    page_docs = visible[start : start + page_size]
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    items = []
    for doc in page_docs:
        att_count = len(
            db.execute(select(DocumentAttachment.id).where(DocumentAttachment.document_id == doc.id, DocumentAttachment.storage_status == 'stored')).all()
        )
        latest = latest_task(db, doc.id)
        report = report_for_task(db, latest.id) if latest else None
        items.append(
            {
                "id": doc.id,
                "document_no": doc.document_no,
                "document_type": doc.document_type,
                "applicant_id": doc.applicant_id,
                "applicant_name": users.get(doc.applicant_id),
                "budget_department": doc.budget_department,
                "payee_name": doc.payee_name,
                "total_amount": float(doc.total_amount or 0),
                "currency": doc.currency,
                "apply_date": doc.apply_date.isoformat() if doc.apply_date else None,
                "document_status": doc.document_status,
                "current_version": doc.current_version,
                "attachment_count": att_count,
                "risk_level": report.overall_risk_level if report else None,
                "recommendation": report.recommendation if report else None,
                "latest_analysis_task_id": latest.id if latest else None,
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "status_counts": status_counts,
    }


@router.get("/documents/{document_id}")
def detail(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    data = document_to_dict(db, doc, with_items=True, with_attachments=True, with_versions=True, with_logs=True, with_approval=True)
    latest = latest_any_task(db, doc.id)
    report = None
    if latest is not None:
        data["latest_task"] = analysis_task_to_dict(latest)
        report = report_for_task(db, latest.id) if latest.task_status == "succeeded" else None
        if report:
            data["latest_report"] = report_to_dict(db, report)
            data["latest_report"]["risk_summary"] = load_json(report.risk_summary_json, {})
            data["latest_report"]["amount_comparison"] = load_json(report.amount_comparison_json, {})
    else:
        data["latest_task"] = None
    from app.security import user_role_codes

    data["allowed_actions"] = _doc_allowed_actions(db, user, doc, set(user_role_codes(db, user.id)))
    return data


@router.patch("/documents/{document_id}")
def update(document_id: int, payload: DocumentUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.services.documents import get_document as _get

    doc = _get(db, document_id)
    assert_can_edit(db, user, doc)
    update_document(db, doc, payload, operator_id=user.id)
    return document_to_dict(db, doc)


@router.post("/documents/{document_id}/copy")
def copy(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    new_doc = copy_document(db, doc, user)
    return document_to_dict(db, new_doc)


@router.post("/documents/{document_id}/submit")
def submit(document_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    from app.security import user_role_codes

    if doc.applicant_id != user.id and "admin" not in user_role_codes(db, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能提交本人创建的单据")
    if doc.document_status not in {"draft", "returned", "withdrawn"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许提交")
    instance, task = submit_document(db, doc, user, request.client.host if request.client else None)
    db.refresh(doc)
    return {
        "document": document_to_dict(db, doc, with_items=False, with_attachments=False),
        "approval_instance_id": instance.id,
        "analysis_task": analysis_task_to_dict(task),
    }


@router.post("/documents/{document_id}/withdraw")
def withdraw(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    if doc.applicant_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能撤回本人创建的单据")
    withdraw_document(db, doc, user)
    db.refresh(doc)
    return document_to_dict(db, doc, with_items=False, with_attachments=False)


@router.post("/documents/{document_id}/void")
def void(document_id: int, payload: dict | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    from app.security import user_role_codes

    if doc.applicant_id != user.id and "admin" not in user_role_codes(db, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能作废本人创建的单据")
    void_document(db, doc, user, (payload or {}).get("remark"))
    db.refresh(doc)
    return document_to_dict(db, doc, with_items=False, with_attachments=False)


@router.post("/documents/{document_id}/line-items")
def create_line_item(document_id: int, payload: LineItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.services.serializers import line_item_to_dict

    doc = get_document(db, document_id)
    assert_can_edit(db, user, doc)
    line = add_line_item(db, doc, payload)
    log_action(db, user.id, "line_item.create", "document_line_item", line.id, {"document_id": doc.id})
    db.commit()
    return line_item_to_dict(line)


@router.patch("/documents/{document_id}/line-items/{line_item_id}")
def patch_line_item(document_id: int, line_item_id: int, payload: LineItemUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.services.serializers import line_item_to_dict

    doc = get_document(db, document_id)
    assert_can_edit(db, user, doc)
    line = db.get(DocumentLineItem, line_item_id)
    if line is None or line.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明细不存在")
    update_line_item(db, line, payload)
    log_action(db, user.id, "line_item.update", "document_line_item", line.id, {"document_id": doc.id})
    db.commit()
    return line_item_to_dict(line)


@router.delete("/documents/{document_id}/line-items/{line_item_id}")
def delete_line_item(document_id: int, line_item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_edit(db, user, doc)
    line = db.get(DocumentLineItem, line_item_id)
    if line is None or line.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明细不存在")
    db.delete(line)
    doc.revision += 1
    log_action(db, user.id, "line_item.delete", "document_line_item", line_item_id, {"document_id": doc.id})
    db.commit()
    return {"message": "明细已删除"}


@router.post("/documents/{document_id}/attachments")
def upload_attachment(
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    doc = get_document(db, document_id)
    assert_can_edit(db, user, doc)

    safe_name = Path(file.filename or "attachment").name
    safe_name = re.sub(r"[\\/:*?\"<>|]", "_", safe_name)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="仅支持 PDF、PNG、JPG 格式附件")
    content = file.file.read(MAX_ATTACHMENT_SIZE + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="附件内容为空")
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="附件大小不能超过 15MB")
    validate_attachment_bytes(content, suffix)

    file_hash = hashlib.sha256(content).hexdigest()
    target_dir = ATTACHMENT_DIR / str(doc.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{secrets.token_hex(16)}{suffix}"
    target.write_bytes(content)

    attachment = DocumentAttachment(
        document_id=doc.id,
        document_version=doc.current_version,
        file_name=safe_name,
        file_type=suffix.lstrip("."),
        file_size=len(content),
        file_path=str(target),
        file_hash=file_hash,
        storage_status="stored",
        parse_status="pending",
        uploaded_by=user.id,
    )
    db.add(attachment)
    doc.revision += 1
    db.flush()
    log_action(
        db,
        user.id,
        "attachment.upload",
        "document_attachment",
        attachment.id,
        {"document_id": doc.id, "file_name": safe_name, "size": len(content), "hash": file_hash},
        request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(attachment)
    return attachment_to_dict(db, attachment, with_parse=True)


@router.get("/documents/{document_id}/attachments/{attachment_id}")
def download_attachment(
    document_id: int,
    attachment_id: int,
    disposition: str = Query(default="attachment"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    attachment = db.get(DocumentAttachment, attachment_id)
    if attachment is None or attachment.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    path = Path(attachment.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件文件不存在")
    log_action(db, user.id, "attachment.download", "document_attachment", attachment.id, {"disposition": disposition})
    db.commit()
    return FileResponse(
        path=str(path),
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        filename=attachment.file_name,
        content_disposition_type="inline" if disposition == "inline" else "attachment",
    )


@router.delete("/documents/{document_id}/attachments/{attachment_id}")
def delete_attachment(document_id: int, attachment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_edit(db, user, doc)
    attachment = db.get(DocumentAttachment, attachment_id)
    if attachment is None or attachment.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    path = Path(attachment.file_path)
    attachment.storage_status = 'archived'
    doc.revision += 1
    log_action(db, user.id, "attachment.delete", "document_attachment", attachment_id, {"document_id": doc.id})
    db.commit()
    # 原始文件留存供历史报告取证，不从磁盘移除。
    return {"message": "附件已删除"}


@router.post("/documents/{document_id}/attachments/{attachment_id}/parse")
def parse_attachment(document_id: int, attachment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    attachment = db.get(DocumentAttachment, attachment_id)
    if attachment is None or attachment.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    if attachment.storage_status != 'stored' or doc.document_status not in {'draft','returned','withdrawn','pending_review','reviewing'}:
        raise HTTPException(409, '归档附件或已结束单据不能重写解析结果')
    from app.services.analysis import ACTIVE_STATUSES
    if db.scalar(select(AnalysisTask.id).where(AnalysisTask.document_id == doc.id, AnalysisTask.task_status.in_(ACTIVE_STATUSES))):
        raise HTTPException(409, '单据分析正在进行，请稍后重新解析')
    if attachment.parse_status == "parsing":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="附件正在解析中，请稍后刷新")
    attachment.parse_status = "pending"
    db.commit()
    return {"message": "已创建附件解析任务", "attachment": attachment_to_dict(db, attachment)}


@router.get("/documents/{document_id}/attachments/{attachment_id}/parse-result")
def attachment_parse_result(document_id: int, attachment_id: int, task_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    attachment = db.get(DocumentAttachment, attachment_id)
    if attachment is None or attachment.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    from app.models import AttachmentParseResult
    if task_id is not None:
        task = db.get(AnalysisTask, task_id)
        if task is None or task.document_id != doc.id or task.task_status != 'succeeded':
            raise HTTPException(404, '此分析版本不存在')
        saved = load_json(task.input_snapshot_json, {})
        context = load_json(task.context_snapshot_json, {})
        snapshot_attachment = next((row for row in saved.get('attachments', []) if row['id'] == attachment_id), None)
        snapshot_parse = next((row for row in context.get('parses', []) if row['attachment_id'] == attachment_id), None)
        if snapshot_attachment is None:
            raise HTTPException(404, '附件不属于此分析版本或旧报告缺少附件快照')
        from app.services.snapshots import frozen_row
        return {'attachment': attachment_to_dict(db, frozen_row(DocumentAttachment, snapshot_attachment)),
                'parse_result': parse_result_to_dict(frozen_row(AttachmentParseResult, snapshot_parse)) if snapshot_parse else None,
                'document_version': task.document_version}

    parse = db.execute(
        select(AttachmentParseResult)
        .where(AttachmentParseResult.attachment_id == attachment.id)
        .order_by(AttachmentParseResult.id.desc())
    ).scalars().first()
    return {
        "attachment": attachment_to_dict(db, attachment),
        "parse_result": parse_result_to_dict(parse),
    }


@router.post("/documents/{document_id}/analysis")
def trigger_analysis(document_id: int, payload: AnalysisCreate | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    task = create_analysis_task(db, doc, user.id, payload.session_id if payload else None)
    return analysis_task_to_dict(task)


@router.get("/documents/{document_id}/amount-comparison")
def amount_comparison(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    task = db.scalars(select(AnalysisTask).where(AnalysisTask.document_id == doc.id,
        AnalysisTask.document_version == doc.current_version, AnalysisTask.task_status == 'succeeded').order_by(AnalysisTask.id.desc())).first()
    report = report_for_task(db, task.id) if task else None
    return load_json(report.amount_comparison_json, {}) if report else compute_amount_comparison(db, doc)


@router.get("/documents/{document_id}/parsed-attachments")
def parsed_attachments(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    return _latest_attachment_parse(db, doc.id)


@router.get("/documents/{document_id}/analysis-history")
def analysis_history(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    doc = get_document(db, document_id)
    assert_can_view(db, user, doc)
    tasks = db.execute(
        select(AnalysisTask).where(AnalysisTask.document_id == doc.id).order_by(AnalysisTask.id.desc())
    ).scalars().all()
    users = {u.id: u.display_name for u in db.execute(select(User)).scalars().all()}
    result = []
    for task in tasks:
        report = report_for_task(db, task.id)
        result.append(
            {
                **analysis_task_to_dict(task),
                "triggered_by_name": users.get(task.triggered_by),
                "report": report_to_dict(db, report) if report else None,
            }
        )
    return result
