"""将分析输入和报告冻结为独立快照，避免历史报告引用当前可变数据。"""
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import Date, DateTime, or_, select

from app.models import (AttachmentParseResult, DocumentAttachment, DocumentLineItem, FinancialDocument,
                        InvoiceRecord, MarketPriceReference, ReviewRule, SupplierProfile)
from app.utils import load_json


def row_data(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        result[column.name] = value.isoformat() if isinstance(value, (date, datetime)) else str(value) if isinstance(value, Decimal) else value
    return result


def frozen_row(model, data):
    values = dict(data)
    for column in model.__table__.columns:
        value = values.get(column.name)
        if value is not None and isinstance(value, str):
            if isinstance(column.type, DateTime): values[column.name] = datetime.fromisoformat(value)
            elif isinstance(column.type, Date): values[column.name] = date.fromisoformat(value)
    return SimpleNamespace(**values)


def capture_input(db, doc):
    from app.services.serializers import document_to_dict
    items = db.scalars(select(DocumentLineItem).where(DocumentLineItem.document_id == doc.id).order_by(DocumentLineItem.id)).all()
    attachments = db.scalars(select(DocumentAttachment).where(DocumentAttachment.document_id == doc.id, DocumentAttachment.storage_status == 'stored').order_by(DocumentAttachment.id)).all()
    return {'document': row_data(doc), 'display': document_to_dict(db, doc),
            'items': [row_data(item) for item in items], 'attachments': [row_data(att) for att in attachments]}


def capture_context(db, doc, inputs):
    attachment_ids = [att['id'] for att in inputs['attachments']]
    parses = []
    for aid in attachment_ids:
        parsed = db.scalars(select(AttachmentParseResult).where(AttachmentParseResult.attachment_id == aid).order_by(AttachmentParseResult.id.desc())).first()
        if parsed: parses.append(row_data(parsed))
    # 历史范围冻结到本单申请日期、币种，避免用未来交易或跨币种记录比较。
    documents = db.scalars(select(FinancialDocument).where(FinancialDocument.id != doc.id,
        FinancialDocument.currency == doc.currency, FinancialDocument.apply_date <= doc.apply_date,
        FinancialDocument.document_status.in_(['pending_review', 'reviewing', 'approved', 'returned']))).all()
    active_invoices = select(InvoiceRecord).join(DocumentAttachment, DocumentAttachment.id == InvoiceRecord.attachment_id).where(DocumentAttachment.storage_status == 'stored')
    invoices = db.scalars(active_invoices.where(InvoiceRecord.document_id == doc.id)).all()
    historical_ids = [d.id for d in documents]
    other_invoices = db.scalars(active_invoices.where(InvoiceRecord.document_id.in_(historical_ids))).all() if historical_ids else []
    prices = db.scalars(select(MarketPriceReference).where(MarketPriceReference.currency == doc.currency,
        MarketPriceReference.effective_date <= doc.apply_date).order_by(MarketPriceReference.effective_date.desc(), MarketPriceReference.id.desc())).all()
    profiles = db.scalars(select(SupplierProfile).where(or_(SupplierProfile.supplier_code == doc.supplier_code,
        SupplierProfile.supplier_name == (doc.supplier_name or doc.payee_name)))).all()
    return {'parses': parses, 'invoices': [row_data(x) for x in invoices],
            'documents': [row_data(x) for x in documents], 'other_invoices': [row_data(x) for x in other_invoices],
            'prices': [row_data(x) for x in prices], 'suppliers': [row_data(x) for x in profiles]}


def report_document(report, task):
    payload = load_json(report.document_snapshot_json, None)
    if payload:
        return payload
    # 老报告缺乏足够的原始快照时，明确标记资料不足，禁止以当前单据冒充。
    result = {'id': report.document_id, 'document_id': report.document_id,
            'document_no': f'历史单据 #{report.document_id}', 'document_type': '历史记录',
            'total_amount': load_json(report.amount_comparison_json, {}).get('document_total'),
            'current_version': task.document_version, 'attachments': [], 'line_items': [],
            'snapshot_warning': '此报告生成于版本升级前，缺少完整历史快照；金额取自报告原始存档，单据资料不回读当前版本。'}
    import re
    for label, key in [('单据编号', 'document_no'), ('单据类型', 'document_type'), ('申请人', 'applicant_name'),
                       ('申请部门', 'applicant_department'), ('预算部门', 'budget_department'), ('收款单位', 'payee_name'),
                       ('费用类别', 'expense_category'), ('申请日期', 'apply_date')]:
        match = re.search(r'^\| ' + label + r' \| (.*?) \|$', report.report_markdown or '', re.M)
        if match: result[key] = match.group(1)
    match = re.search(r'^\| 附件数量 \| (\d+) 个 \|$', report.report_markdown or '', re.M)
    if match: result['attachment_count'] = int(match.group(1))
    return result
