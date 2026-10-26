"""智能分析任务：附件解析、规则评估、风险汇总与报告落库。"""
from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AnalysisTask,
    ApprovalInstance,
    ApprovalTask,
    AttachmentParseResult,
    DocumentAttachment,
    DocumentLineItem,
    FinancialDocument,
    InvoiceRecord,
    ReviewReport,
    RiskFinding,
    SupplierProfile,
    User,
)
from app.services.audit import log_action
from app.services.parsing import ensure_parsed, parsed_fields
from app.services.reports import build_markdown
from app.services.rules import evaluate_document, load_rule_configs
from app.services.snapshots import capture_input, capture_context, frozen_row
from app.services.serializers import document_to_dict, parse_result_to_dict
from app.utils import dump_json, iso, load_json, now, pct, money

ACTIVE_STATUSES = ['queued', 'querying_document', 'loading_attachments', 'parsing_attachments', 'analyzing', 'generating_report']


class TaskCancelled(Exception):
    pass


def cancel_tasks(db, document_id, reason):
    db.execute(update(AnalysisTask).where(AnalysisTask.document_id == document_id,
        AnalysisTask.task_status.in_(ACTIVE_STATUSES)).values(task_status='cancelled', current_step='cancelled',
        error_message=reason, finished_at=now()))

STEP_LABELS = {
    "queued": "等待分析",
    "querying_document": "查询单据与明细",
    "loading_attachments": "加载附件",
    "parsing_attachments": "解析附件",
    "analyzing": "执行风险规则",
    "generating_report": "生成审核报告",
    "succeeded": "分析完成",
    "failed": "分析失败",
    "cancelled": "已取消",
}

LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3}


def create_analysis_task(
    db: Session,
    doc: FinancialDocument,
    user_id: int,
    session_id: int | None = None,
    run_async: bool = True,
    commit: bool = True,
) -> AnalysisTask:
    if doc.document_status not in {'pending_review', 'reviewing'}:
        raise HTTPException(409, '请先提交单据，只有审批中的当前版本可以分析')
    if session_id is not None:
        from app.models import ReviewSession
        session = db.get(ReviewSession, session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(403, '无权关联此审核会话')
    existing = db.scalars(select(AnalysisTask).where(AnalysisTask.document_id == doc.id,
        AnalysisTask.document_version == doc.current_version, AnalysisTask.task_status.in_(ACTIVE_STATUSES))).first()
    if existing:
        return existing
    db.flush()
    inputs = capture_input(db, doc)
    inputs['rules'] = load_rule_configs(db, doc.document_type)
    from app.models import ReviewRule
    inputs['rule_revisions'] = [{'id':rule.id,'rule_code':rule.rule_code,'updated_at':iso(rule.updated_at)}
        for rule in db.scalars(select(ReviewRule).where(ReviewRule.status=='active')).all()
        if rule.rule_code in inputs['rules']]
    task = AnalysisTask(
        session_id=session_id,
        document_id=doc.id,
        document_version=doc.current_version,
        document_revision=doc.revision,
        input_snapshot_json=dump_json(inputs),
        task_status="queued",
        current_step="queued",
        progress=0,
        triggered_by=user_id,
    )
    db.add(task)
    db.flush()

    instance = db.execute(
        select(ApprovalInstance).where(ApprovalInstance.document_id == doc.id).order_by(ApprovalInstance.id.desc())
    ).scalars().first()
    if instance is not None:
        pending = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.task_status == "pending",
            )
        ).scalars().all()
        for item in pending:
            item.analysis_task_id = task.id

    log_action(db, user_id, "analysis.create", "analysis_task", task.id, {"document_id": doc.id})
    if commit:
        db.commit()
    # 任务持久化后由固定工作进程读取；请求不再创建临时线程。
    return task


def _set_step(db: Session, task: AnalysisTask, status: str, step: str, progress: int) -> None:
    result = db.execute(update(AnalysisTask).where(AnalysisTask.id == task.id,
        AnalysisTask.task_status.in_(ACTIVE_STATUSES)).values(task_status=status, current_step=step,
        progress=progress, heartbeat_at=now()))
    if not result.rowcount:
        db.rollback()
        raise TaskCancelled()
    db.commit()
    db.refresh(task)


def compute_amount_comparison(db: Session, doc: FinancialDocument, *, inputs=None, context=None) -> dict:
    inputs = inputs if inputs is not None else capture_input(db, doc)
    context = context if context is not None else capture_context(db, doc, inputs)
    items = [frozen_row(DocumentLineItem, row) for row in inputs['items']]
    invoices = [frozen_row(InvoiceRecord, row) for row in context['invoices']]
    attachments = [frozen_row(DocumentAttachment, row) for row in inputs['attachments']]
    parse_map = {row['attachment_id']: frozen_row(AttachmentParseResult, row) for row in context['parses']}

    contract_amount = None
    for att in attachments:
        parse = parse_map.get(att.id)
        if parse and parse.document_category == "contract":
            fields = parsed_fields(parse)
            if fields.get("contract_amount"):
                contract_amount = float(fields["contract_amount"])
                break

    total = float(doc.total_amount or 0)
    items_total = float(sum((money(item.amount) for item in items), Decimal('0')))
    invoice_total = float(sum((money(inv.amount_including_tax) for inv in invoices), Decimal('0')))
    payment_amount = total if doc.document_type in {"对公付款单", "预付款单", "批量付款单"} else None

    line_diff = float(money(items_total) - money(total))
    line_status = "ok" if abs(line_diff) <= max(0.01, total * 0.001) else ("warning" if abs(line_diff) <= max(50, total * 0.05) else "error")

    invoice_diff = float(money(invoice_total) - money(total)) if invoices else 0.0
    if not invoices:
        invoice_status = "missing"
    elif abs(invoice_diff) <= max(1.0, total * 0.005):
        invoice_status = "ok"
    elif abs(invoice_diff) <= total * 0.05:
        invoice_status = "warning"
    else:
        invoice_status = "error"

    contract_expected = None
    contract_diff = None
    contract_status = "missing"
    if contract_amount:
        ratio = doc.payment_ratio if doc.payment_ratio is not None else 100
        contract_expected = round(contract_amount * float(ratio) / 100, 2)
        contract_diff = round(total - contract_expected, 2)
        if abs(contract_diff) <= max(1.0, contract_expected * 0.01):
            contract_status = "ok"
        elif abs(contract_diff) <= contract_expected * 0.05:
            contract_status = "warning"
        else:
            contract_status = "error"

    payment_diff = round(payment_amount - total, 2) if payment_amount is not None else None
    payment_status = "ok" if payment_amount is not None else "missing"

    rows = [
        {
            "key": "line_items",
            "label": "明细合计",
            "amount": items_total,
            "difference": line_diff,
            "difference_pct": pct(items_total, total),
            "status": line_status,
            "note": f"{len(items)} 条明细",
        },
        {
            "key": "invoice",
            "label": "发票合计",
            "amount": invoice_total,
            "difference": invoice_diff,
            "difference_pct": pct(invoice_total, total) if invoices else 0,
            "status": invoice_status,
            "note": f"{len(invoices)} 张发票",
        },
        {
            "key": "contract",
            "label": "合同金额",
            "amount": contract_amount,
            "expected_payment": contract_expected,
            "difference": contract_diff,
            "difference_pct": pct(total, contract_expected) if contract_expected else 0,
            "status": contract_status,
            "note": f"按付款比例 {doc.payment_ratio if doc.payment_ratio is not None else 100}% 计算应付 {contract_expected:,.2f} 元" if contract_expected else "未识别合同金额",
        },
        {
            "key": "payment",
            "label": "付款金额",
            "amount": payment_amount,
            "difference": payment_diff,
            "difference_pct": 0,
            "status": payment_status,
            "note": "本单付款总额" if payment_amount is not None else "非付款类单据",
        },
    ]
    return {
        "document_total": total,
        "line_items_total": items_total,
        "line_items_difference": line_diff,
        "line_items_difference_pct": pct(items_total, total),
        "line_items_status": line_status,
        "invoice_total": invoice_total,
        "invoice_difference": invoice_diff,
        "invoice_difference_pct": pct(invoice_total, total) if invoices else 0,
        "invoice_status": invoice_status,
        "contract_amount": contract_amount,
        "contract_expected_payment": contract_expected,
        "contract_difference": contract_diff,
        "contract_difference_pct": pct(total, contract_expected) if contract_expected else 0,
        "contract_status": contract_status,
        "payment_amount": payment_amount,
        "payment_difference": payment_diff,
        "payment_difference_pct": 0,
        "payment_status": payment_status,
        "rows": rows,
        "invoice_count": len(invoices),
        "invoice_numbers": [inv.invoice_no for inv in invoices if inv.invoice_no],
    }


def compute_summary(findings: list[dict]) -> dict:
    level_counts = {"high": 0, "medium": 0, "low": 0}
    category_counts: dict[str, int] = {}
    for finding in findings:
        level_counts[finding["risk_level"]] = level_counts.get(finding["risk_level"], 0) + 1
        category_counts[finding["risk_category"]] = category_counts.get(finding["risk_category"], 0) + 1
    score = level_counts["high"] * 40 + level_counts["medium"] * 15 + level_counts["low"] * 5
    if level_counts["high"] > 0 or score >= 80:
        overall = "high"
    elif level_counts["medium"] > 0 or score >= 20:
        overall = "medium"
    else:
        overall = "low"
    top = sorted(findings, key=lambda item: LEVEL_ORDER.get(item["risk_level"], 0), reverse=True)[:5]
    return {
        "overall_risk_level": overall,
        "level_counts": level_counts,
        "category_counts": category_counts,
        "risk_score": min(score, 100),
        "total_count": len(findings),
        "top_risks": [{"risk_title": item["risk_title"], "risk_level": item["risk_level"]} for item in top],
    }


def decide_recommendation(summary: dict, findings: list[dict]) -> str:
    if summary["level_counts"]["high"] > 0:
        return "建议驳回"
    if summary["level_counts"]["medium"] > 0:
        return "人工复核"
    attachment_issues = {
        "ATTACHMENT_MISSING",
        "ATTACHMENT_INCOMPLETE",
        "ATTACHMENT_PARSE_FAILED",
        "INVOICE_AMOUNT_MISSING",
        "ATTACHMENT_MANUAL_REVIEW",
        "ATTACHMENT_LOW_CONFIDENCE",
    }
    if any(finding["risk_type"] in attachment_issues for finding in findings):
        return "补充材料"
    return "建议通过"


def run_analysis_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        claimed = db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id,
            AnalysisTask.task_status == 'queued').values(task_status='querying_document',
            current_step='querying_document', heartbeat_at=now()))
        db.commit()
        if not claimed.rowcount:
            return
        task = db.get(AnalysisTask, task_id)
        inputs = load_json(task.input_snapshot_json, None)
        if not inputs:
            raise ValueError('旧任务缺少版本快照，请重新发起分析')
        current = db.get(FinancialDocument, task.document_id)
        if current is None or current.current_version != task.document_version or current.document_status not in {'pending_review', 'reviewing'}:
            raise ValueError('单据版本或状态已变化，请在当前提交版本重新分析')
        document = frozen_row(FinancialDocument, inputs['document'])
        _set_step(db, task, 'loading_attachments', 'loading_attachments', 25)
        for saved in inputs['attachments']:
            attachment = db.get(DocumentAttachment, saved['id'])
            if attachment is None or attachment.storage_status != 'stored':
                raise ValueError('提交版本的附件已变化，请重新提交')
            path = Path(saved['file_path'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != saved['file_hash']:
                raise ValueError('附件文件不存在或摘要与提交版本不一致')
        _set_step(db, task, 'parsing_attachments', 'parsing_attachments', 40)
        for index, saved in enumerate(inputs['attachments'], 1):
            attachment = db.get(DocumentAttachment, saved['id'])
            ensure_parsed(db, attachment)
            _set_step(db, task, 'parsing_attachments', 'parsing_attachments', 40 + int(20*index/max(len(inputs['attachments']), 1)))
        context = capture_context(db, document, inputs)
        task.context_snapshot_json = dump_json(context)
        db.commit()
        _set_step(db, task, 'analyzing', 'analyzing', 70)
        findings = evaluate_document(db, document, inputs=inputs, context=context, configs=inputs['rules'])
        summary = compute_summary(findings)
        summary['enabled_rules'] = list(inputs['rules'])
        summary['rule_revisions'] = inputs.get('rule_revisions', [])
        summary['document_version'] = task.document_version
        amount = compute_amount_comparison(db, document, inputs=inputs, context=context)
        recommendation = decide_recommendation(summary, findings)
        if not inputs['rules']:
            summary['coverage_warning'] = '没有启用审核规则，本次结果不能作为通过依据'
            summary['overall_risk_level'] = 'medium'
            recommendation = '人工复核'
        _set_step(db, task, 'generating_report', 'generating_report', 92)
        for finding in findings:
            db.add(RiskFinding(task_id=task.id, document_id=document.id,
                **{key: finding[key] for key in ('risk_type', 'risk_category', 'risk_level', 'risk_title', 'description', 'suggestion_text')},
                actual_value_json=dump_json(finding['actual_value']), reference_value_json=dump_json(finding['reference_value']),
                threshold_json=dump_json(finding['threshold']), evidence_json=dump_json(finding['evidence'])))
        supplier = next((row for row in context['suppliers'] if row['supplier_code'] == document.supplier_code), None)
        supplier = supplier or next(iter(context['suppliers']), None)
        supplier_dict = None
        if supplier:
            supplier_dict = dict(supplier, risk_tags=load_json(supplier['risk_tags_json'], []),
                bank_accounts=load_json(supplier['bank_accounts_json'], []))
            history = [row for row in context['documents'] if row['supplier_code'] == supplier['supplier_code']]
            supplier_dict['payment_count'] = len(history) + 1
            supplier_dict['payment_total'] = float(sum((money(row['total_amount']) for row in history), money(document.total_amount)))
        display = inputs['display']
        display['current_version'] = task.document_version
        display['attachment_count'] = len(inputs['attachments'])
        report = ReviewReport(task_id=task.id, document_id=document.id,
            document_snapshot_json=dump_json(display), supplier_snapshot_json=dump_json(supplier_dict), snapshot_status='complete',
            overall_risk_level=summary['overall_risk_level'], risk_summary_json=dump_json(summary),
            amount_comparison_json=dump_json(amount), recommendation=recommendation)
        db.add(report)
        db.flush()
        report.report_markdown = build_markdown(report_id=report.id, document=display, findings=findings,
            summary=summary, amount=amount, recommendation=recommendation, supplier=supplier_dict,
            manual_reviews=[], generated_at=iso(now()) or '')
        # 最后一次条件更新和报告落库同一事务，取消/超时任务不会再次变成成功。
        finished = db.execute(update(AnalysisTask).where(AnalysisTask.id == task.id,
            AnalysisTask.task_status.in_(ACTIVE_STATUSES)).values(task_status='succeeded', current_step='succeeded',
            progress=100, heartbeat_at=now(), finished_at=now()))
        if not finished.rowcount:
            raise TaskCancelled()
        log_action(db, task.triggered_by, 'analysis.complete', 'analysis_task', task.id,
            {'document_id': document.id, 'document_version': task.document_version,
             'overall_risk_level': summary['overall_risk_level'], 'findings': len(findings), 'report_id': report.id})
        db.commit()
    except TaskCancelled:
        db.rollback()
    except Exception as exc:
        db.rollback()
        task = db.get(AnalysisTask, task_id)
        if task is not None:
            changed = db.execute(update(AnalysisTask).where(AnalysisTask.id == task_id,
                AnalysisTask.task_status.in_(ACTIVE_STATUSES)).values(task_status='failed', current_step='failed',
                error_message=str(exc)[:1000], finished_at=now()))
            if changed.rowcount:
                log_action(db, task.triggered_by, 'analysis.failed', 'analysis_task', task.id, {'error': str(exc)[:1000]})
            db.commit()
    finally:
        db.close()


def latest_task(db: Session, document_id: int) -> AnalysisTask | None:
    return db.execute(
        select(AnalysisTask)
        .where(AnalysisTask.document_id == document_id, AnalysisTask.task_status == "succeeded")
        .order_by(AnalysisTask.id.desc())
    ).scalars().first()


def latest_any_task(db: Session, document_id: int) -> AnalysisTask | None:
    return db.execute(
        select(AnalysisTask).where(AnalysisTask.document_id == document_id).order_by(AnalysisTask.id.desc())
    ).scalars().first()


def report_for_task(db: Session, task_id: int) -> ReviewReport | None:
    return db.execute(
        select(ReviewReport).where(ReviewReport.task_id == task_id).order_by(ReviewReport.id.desc())
    ).scalars().first()


def findings_for_task(db: Session, task_id: int) -> list[RiskFinding]:
    return db.execute(
        select(RiskFinding).where(RiskFinding.task_id == task_id).order_by(RiskFinding.id)
    ).scalars().all()


def parsed_results_for_document(db: Session, document_id: int) -> list[dict]:
    attachments = db.execute(
        select(DocumentAttachment).where(DocumentAttachment.document_id == document_id, DocumentAttachment.storage_status == 'stored').order_by(DocumentAttachment.id)
    ).scalars().all()
    result = []
    for att in attachments:
        parse = db.execute(
            select(AttachmentParseResult)
            .where(AttachmentParseResult.attachment_id == att.id)
            .order_by(AttachmentParseResult.id.desc())
        ).scalars().first()
        result.append(
            {
                "attachment_id": att.id,
                "file_name": att.file_name,
                "file_type": att.file_type,
                "parse_status": att.parse_status,
                "parse_result": parse_result_to_dict(parse),
            }
        )
    return result
