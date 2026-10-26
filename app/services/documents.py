"""单据领域服务：创建、编辑、提交、撤回、作废、复制与版本。"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import ATTACHMENT_DIR
from app.models import (
    AnalysisTask,
    ApprovalInstance,
    ApprovalTask,
    DocumentAttachment,
    DocumentLineItem,
    DocumentStatusLog,
    DocumentVersion,
    FinancialDocument,
    User,
)
from app.services.audit import log_action
from app.services.serializers import document_to_dict
from app.utils import dump_json, load_json, money, now

DOCUMENT_TYPE_PREFIX = {
    "对公付款单": "GF",
    "预付款单": "YF",
    "批量付款单": "PL",
    "费用报销单": "BX",
    "差旅报销单": "CL",
}

PAYMENT_TYPES = {"对公付款单", "预付款单", "批量付款单"}

REQUIRED_ATTACHMENT_CATEGORIES = {
    "对公付款单": ["invoice", "contract"],
    "预付款单": ["contract"],
    "批量付款单": ["payment_proof"],
    "费用报销单": ["invoice"],
    "差旅报销单": ["invoice", "itinerary"],
}

EDITABLE_STATUSES = {"draft", "returned", "withdrawn"}


def generate_document_no(db: Session, document_type: str) -> str:
    prefix = DOCUMENT_TYPE_PREFIX.get(document_type, "DOC")
    month = date.today().strftime("%Y%m")
    like = f"{prefix}-{month}-%"
    count = db.execute(
        select(func.count(FinancialDocument.id)).where(FinancialDocument.document_no.like(like))
    ).scalar_one()
    seq = int(count) + 1
    while True:
        candidate = f"{prefix}-{month}-{seq:04d}"
        exists = db.execute(
            select(FinancialDocument.id).where(FinancialDocument.document_no == candidate)
        ).first()
        if not exists:
            return candidate
        seq += 1


def log_status(db: Session, doc: FinancialDocument, from_status: str | None, to_status: str, operator_id: int, remark: str | None = None) -> None:
    db.add(
        DocumentStatusLog(
            document_id=doc.id,
            from_status=from_status,
            to_status=to_status,
            operator_id=operator_id,
            remark=remark,
        )
    )


def snapshot_document(db: Session, doc: FinancialDocument, user_id: int, version_no: int) -> DocumentVersion:
    snapshot = document_to_dict(db, doc, with_items=True, with_attachments=True)
    version = DocumentVersion(
        document_id=doc.id,
        version_no=version_no,
        document_snapshot_json=dump_json(snapshot),
        created_by=user_id,
    )
    db.add(version)
    return version


def get_document(db: Session, document_id: int) -> FinancialDocument:
    doc = db.get(FinancialDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="单据不存在")
    return doc


def _apply_line_items(db: Session, doc: FinancialDocument, items: list) -> None:
    for item in items:
        payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        amount = payload.get("amount")
        quantity = Decimal(str(payload.get("quantity") or 1))
        unit_price = money(payload.get("unit_price"))
        if amount is None:
            amount = money(quantity * unit_price)
        db.add(
            DocumentLineItem(
                document_id=doc.id,
                item_type=payload.get("item_type") or "expense",
                item_name=payload["item_name"],
                item_spec=payload.get("item_spec"),
                expense_category=payload.get("expense_category"),
                expense_date=payload.get("expense_date"),
                expense_location=payload.get("expense_location"),
                quantity=float(quantity),
                unit_price=unit_price,
                amount=money(amount),
                payee_name=payload.get("payee_name"),
                payee_account=payload.get("payee_account"),
                remark=payload.get("remark"),
            )
        )


def create_document(db: Session, user: User, payload: Any) -> FinancialDocument:
    data = payload.model_dump()
    items = data.pop("line_items", [])
    ext = data.pop("ext", None)
    doc = FinancialDocument(
        document_type=data["document_type"],
        document_no=generate_document_no(db, data["document_type"]),
        applicant_id=user.id,
        applicant_department=data["applicant_department"],
        budget_department=data["budget_department"],
        payee_name=data.get("payee_name"),
        payee_account=data.get("payee_account"),
        expense_category=data.get("expense_category"),
        total_amount=money(data.get("total_amount") or 0),
        currency=data.get("currency") or "CNY",
        apply_date=data.get("apply_date") or date.today(),
        reason_text=data.get("reason_text"),
        document_status="draft",
        current_version=1,
        contract_no=data.get("contract_no"),
        supplier_name=data.get("supplier_name"),
        supplier_code=data.get("supplier_code"),
        payment_ratio=float(data["payment_ratio"]) if data.get("payment_ratio") is not None else None,
        payment_terms=data.get("payment_terms"),
        planned_payment_date=data.get("planned_payment_date"),
        batch_total_amount=money(data["batch_total_amount"]) if data.get("batch_total_amount") is not None else None,
        batch_payment_count=data.get("batch_payment_count"),
        travel_location=data.get("travel_location"),
        travel_start_date=data.get("travel_start_date"),
        travel_end_date=data.get("travel_end_date"),
        ext_json=dump_json(ext) if ext else None,
    )
    db.add(doc)
    db.flush()
    _apply_line_items(db, doc, items)
    log_status(db, doc, None, "draft", user.id, "创建单据草稿")
    log_action(db, user.id, "document.create", "financial_document", doc.id, {"document_no": doc.document_no})
    db.commit()
    db.refresh(doc)
    return doc


def update_document(db: Session, doc: FinancialDocument, payload: Any, operator_id: int | None = None) -> FinancialDocument:
    from app.schemas import DocumentCreate, LineItemIn
    data = payload.model_dump(exclude_unset=True)
    revision = data.pop('revision', None)
    if revision is not None and revision != doc.revision:
        raise HTTPException(409, '单据已被其他操作修改，请刷新后重试')
    items = data.pop('line_items', None)
    # 对部分更新合并后校验，避免只改一个日期就绕过日期范围约束。
    merged = {key: getattr(doc, key) for key in DocumentCreate.model_fields if hasattr(doc, key)}
    merged.update(data)
    merged['ext'] = load_json(doc.ext_json, {}) if 'ext' not in data else data['ext']
    DocumentCreate.model_validate(merged)
    ext = data.pop("ext", "__absent__")
    if "total_amount" in data and data["total_amount"] is not None:
        data["total_amount"] = money(data["total_amount"])
    if "batch_total_amount" in data and data["batch_total_amount"] is not None:
        data["batch_total_amount"] = money(data["batch_total_amount"])
    for key, value in data.items():
        if key == "ext":
            continue
        if key == 'payment_ratio' and value is not None: value = float(value)
        setattr(doc, key, value)
    if ext != "__absent__":
        doc.ext_json = dump_json(ext) if ext is not None else None
    if items is not None:
        db.query(DocumentLineItem).filter(DocumentLineItem.document_id == doc.id).delete(synchronize_session=False)
        _apply_line_items(db, doc, [LineItemIn.model_validate(item) for item in items])
    doc.revision += 1
    log_action(db, operator_id if operator_id is not None else doc.applicant_id, "document.update", "financial_document", doc.id,
               {"fields": list(data.keys()), "line_items_replaced": items is not None})
    db.commit()
    db.refresh(doc)
    return doc


def add_line_item(db: Session, doc: FinancialDocument, item: Any) -> DocumentLineItem:
    payload = item.model_dump()
    amount = payload.get("amount")
    quantity = Decimal(str(payload.get("quantity") or 1))
    unit_price = money(payload.get("unit_price"))
    if amount is None:
        amount = money(quantity * unit_price)
    line = DocumentLineItem(
        document_id=doc.id,
        item_type=payload.get("item_type") or "expense",
        item_name=payload["item_name"],
        item_spec=payload.get("item_spec"),
        expense_category=payload.get("expense_category"),
        expense_date=payload.get("expense_date"),
        expense_location=payload.get("expense_location"),
        quantity=float(quantity),
        unit_price=unit_price,
        amount=money(amount),
        payee_name=payload.get("payee_name"),
        payee_account=payload.get("payee_account"),
        remark=payload.get("remark"),
    )
    db.add(line)
    doc.revision += 1
    db.commit()
    db.refresh(line)
    return line


def update_line_item(db: Session, line: DocumentLineItem, payload: Any) -> DocumentLineItem:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(line, key, float(value) if key == 'quantity' else value)
    if "amount" not in data and ("quantity" in data or "unit_price" in data):
        line.amount = money(Decimal(str(line.quantity or 0)) * money(line.unit_price))
    db.get(FinancialDocument, line.document_id).revision += 1
    db.commit()
    db.refresh(line)
    return line


def copy_document(db: Session, doc: FinancialDocument, user: User) -> FinancialDocument:
    new_doc = FinancialDocument(
        document_type=doc.document_type,
        document_no=generate_document_no(db, doc.document_type),
        applicant_id=user.id,
        applicant_department=doc.applicant_department,
        budget_department=doc.budget_department,
        payee_name=doc.payee_name,
        payee_account=doc.payee_account,
        expense_category=doc.expense_category,
        total_amount=doc.total_amount,
        currency=doc.currency,
        apply_date=date.today(),
        reason_text=doc.reason_text,
        document_status="draft",
        current_version=1,
        contract_no=doc.contract_no,
        supplier_name=doc.supplier_name,
        supplier_code=doc.supplier_code,
        payment_ratio=doc.payment_ratio,
        payment_terms=doc.payment_terms,
        planned_payment_date=doc.planned_payment_date,
        batch_total_amount=doc.batch_total_amount,
        batch_payment_count=doc.batch_payment_count,
        travel_location=doc.travel_location,
        travel_start_date=doc.travel_start_date,
        travel_end_date=doc.travel_end_date,
        ext_json=doc.ext_json,
    )
    db.add(new_doc)
    db.flush()

    items = db.execute(select(DocumentLineItem).where(DocumentLineItem.document_id == doc.id)).scalars().all()
    for item in items:
        db.add(
            DocumentLineItem(
                document_id=new_doc.id,
                item_type=item.item_type,
                item_name=item.item_name,
                item_spec=item.item_spec,
                expense_category=item.expense_category,
                expense_date=item.expense_date,
                expense_location=item.expense_location,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                payee_name=item.payee_name,
                payee_account=item.payee_account,
                remark=item.remark,
            )
        )

    attachments = db.execute(
        select(DocumentAttachment).where(DocumentAttachment.document_id == doc.id, DocumentAttachment.storage_status == 'stored')
    ).scalars().all()
    for att in attachments:
        source = Path(att.file_path)
        if source.exists():
            target_dir = ATTACHMENT_DIR / str(new_doc.id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{att.file_hash[:12]}_{att.file_name}"
            shutil.copy2(source, target)
            db.add(
                DocumentAttachment(
                    document_id=new_doc.id,
                    document_version=1,
                    file_name=att.file_name,
                    file_type=att.file_type,
                    file_size=att.file_size,
                    file_path=str(target),
                    file_hash=att.file_hash,
                    storage_status="stored",
                    parse_status="pending",
                    uploaded_by=user.id,
                )
            )

    log_status(db, new_doc, None, "draft", user.id, f"复制自单据 {doc.document_no}")
    log_action(db, user.id, "document.copy", "financial_document", new_doc.id, {"source": doc.id})
    db.commit()
    db.refresh(new_doc)
    return new_doc


def validate_submit(db: Session, doc: FinancialDocument) -> list[str]:
    issues: list[str] = []
    if not doc.budget_department:
        issues.append("预算部门不能为空")
    if not doc.applicant_department or not (doc.reason_text or '').strip():
        issues.append('请填写申请部门和申请事由')
    if float(doc.total_amount or 0) <= 0:
        issues.append("单据总金额必须大于 0")
    if doc.document_type in PAYMENT_TYPES and not doc.payee_name:
        issues.append("付款类单据必须填写收款单位")
    if doc.document_type in {"对公付款单", "预付款单"}:
        if not doc.contract_no:
            issues.append("对公付款单必须填写合同编号")
        if doc.payment_ratio is None:
            issues.append("对公付款单必须填写付款比例")
        elif not 0 < Decimal(str(doc.payment_ratio)) <= 100:
            issues.append('付款比例必须大于0且不超过100')
        if not doc.supplier_name or not doc.payment_terms or not doc.planned_payment_date:
            issues.append('付款类单据请填写供应商名称、付款条件和计划付款日期')
    if doc.document_type == "批量付款单" and not doc.batch_payment_count:
        issues.append("批量付款单必须填写付款笔数")
    if doc.document_type == "差旅报销单" and (not doc.travel_start_date or not doc.travel_end_date):
        issues.append("差旅报销单必须填写出差起止日期")
    if doc.travel_start_date and doc.travel_end_date and doc.travel_end_date < doc.travel_start_date:
        issues.append('出差结束日期不能早于开始日期')
    if doc.document_type == '差旅报销单' and not doc.travel_location:
        issues.append('请填写出差地点')
    items = db.scalars(select(DocumentLineItem).where(DocumentLineItem.document_id == doc.id)).all()
    if not items:
        issues.append('请至少填写一条明细')
    if sum((money(item.amount) for item in items), Decimal('0')) != money(doc.total_amount):
        issues.append('明细合计必须与单据总金额一致')
    for item in items:
        if Decimal(str(item.quantity)) <= 0 or money(item.unit_price) < 0 or money(item.amount) < 0:
            issues.append('明细数量必须大于零，单价与金额不能为负数')
        elif money(Decimal(str(item.quantity)) * money(item.unit_price)) != money(item.amount):
            issues.append(f'明细「{item.item_name}」金额必须等于数量乘单价')
    if doc.document_type == '批量付款单':
        if doc.batch_payment_count != len(items): issues.append('付款笔数必须与明细条数一致')
        if doc.batch_total_amount is None or money(doc.batch_total_amount) != money(doc.total_amount): issues.append('批次总金额必须与单据金额一致')
        if any(not item.payee_name or not item.payee_account for item in items): issues.append('每条付款明细必须填写收款人和账号')

    attachments = db.execute(
        select(DocumentAttachment).where(DocumentAttachment.document_id == doc.id, DocumentAttachment.storage_status == 'stored')
    ).scalars().all()
    if not attachments:
        issues.append("提交前必须至少上传一个附件")
    from app.models import AttachmentParseResult
    categories = set()
    for attachment in attachments:
        parsed = db.scalars(select(AttachmentParseResult).where(AttachmentParseResult.attachment_id == attachment.id)
            .order_by(AttachmentParseResult.id.desc())).first()
        if parsed and not parsed.error_message:
            categories.add(parsed.document_category)
        if attachment.parse_status in {'pending', 'parsing', 'failed'}:
            issues.append(f'附件「{attachment.file_name}」尚未成功解析，请重试或更换材料')
    missing = set(REQUIRED_ATTACHMENT_CATEGORIES[doc.document_type]) - categories
    if missing:
        names = {'invoice':'发票','contract':'合同','payment_proof':'付款依据','itinerary':'行程单'}
        issues.append('缺少必需附件：' + '、'.join(names[key] for key in sorted(missing)))
    return list(dict.fromkeys(issues))


def submit_document(db: Session, doc: FinancialDocument, user: User, ip: str | None = None) -> tuple[ApprovalInstance, AnalysisTask]:
    from app.services.analysis import create_analysis_task
    from app.services.approval import start_approval

    issues = validate_submit(db, doc)
    if issues:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"message": "单据校验未通过", "issues": issues})

    from_status = doc.document_status
    if from_status not in EDITABLE_STATUSES:
        raise HTTPException(409, '当前状态不允许提交')
    last_version = db.scalar(select(func.max(DocumentVersion.version_no)).where(DocumentVersion.document_id == doc.id)) or 0
    doc.current_version = last_version + 1
    doc.document_status = "pending_review"
    db.flush()
    snapshot_document(db, doc, user.id, doc.current_version)
    log_status(db, doc, from_status, "pending_review", user.id, "提交审批")
    instance, _task = start_approval(db, doc, user.id)
    analysis_task = create_analysis_task(db, doc, user.id, session_id=None, commit=False)
    log_action(
        db,
        user.id,
        "document.submit",
        "financial_document",
        doc.id,
        {"document_no": doc.document_no, "version": doc.current_version, "analysis_task_id": analysis_task.id},
        ip,
    )
    db.commit()
    return instance, analysis_task


def withdraw_document(db: Session, doc: FinancialDocument, user: User) -> None:
    if doc.document_status not in {"pending_review", "reviewing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许撤回")

    instance = db.execute(
        select(ApprovalInstance)
        .where(ApprovalInstance.document_id == doc.id)
        .order_by(ApprovalInstance.id.desc())
    ).scalars().first()
    if instance:
        processed = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.task_status.in_(["approved", "returned", "rejected"]),
            )
        ).first()
        if processed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有审批处理结果，无法撤回")
        for task in db.execute(select(ApprovalTask).where(ApprovalTask.instance_id == instance.id)).scalars().all():
            task.task_status = "cancelled"
        instance.instance_status = "cancelled"
        instance.finished_at = now()
    from app.services.analysis import cancel_tasks
    cancel_tasks(db, doc.id, '单据已撤回')

    from_status = doc.document_status
    doc.document_status = "withdrawn"
    log_status(db, doc, from_status, "withdrawn", user.id, "申请人撤回单据")
    log_action(db, user.id, "document.withdraw", "financial_document", doc.id)
    db.commit()


def void_document(db: Session, doc: FinancialDocument, user: User, remark: str | None = None) -> None:
    if doc.document_status not in {"draft", "returned", "withdrawn", "rejected"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许作废")
    from_status = doc.document_status
    doc.document_status = "voided"
    log_status(db, doc, from_status, "voided", user.id, remark or "作废单据")
    log_action(db, user.id, "document.void", "financial_document", doc.id, {"remark": remark})
    db.commit()


def get_document_ext(doc: FinancialDocument) -> dict:
    return load_json(doc.ext_json, {}) or {}
