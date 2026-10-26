"""风险规则引擎：十类风险校验，输出可追溯的风险项。"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttachmentParseResult,
    DocumentAttachment,
    DocumentLineItem,
    FinancialDocument,
    InvoiceRecord,
    MarketPriceReference,
    ReviewRule,
    SupplierProfile,
)
from app.services.parsing import parsed_fields
from app.utils import load_json, money, pct, to_float

COMPANY_NAME = "云启科技（上海）有限公司"

DEFAULT_RULE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "rule_code": "amount_tolerance",
        "rule_name": "单据与发票金额容差",
        "rule_type": "amount",
        "config": {"abs_tolerance": 1.0, "pct_tolerance": 0.5, "medium_pct": 2.0, "high_pct": 5.0},
        "severity": "high",
    },
    {
        "rule_code": "line_item_tolerance",
        "rule_name": "明细合计容差",
        "rule_type": "amount",
        "config": {"abs_tolerance": 0.01, "pct_tolerance": 0.1, "medium_pct": 1.0, "high_pct": 5.0},
        "severity": "high",
    },
    {
        "rule_code": "contract_tolerance",
        "rule_name": "合同付款一致性",
        "rule_type": "contract",
        "config": {"pct_tolerance": 1.0, "high_pct": 5.0},
        "severity": "high",
    },
    {
        "rule_code": "batch_tolerance",
        "rule_name": "批量付款一致性",
        "rule_type": "batch",
        "config": {"amount_tolerance": 0.01, "count_tolerance": 0},
        "severity": "high",
    },
    {
        "rule_code": "expense_standards",
        "rule_name": "费用标准",
        "rule_type": "compliance",
        "config": {
            "standards": {
                "餐费": {"per_day": 150, "level": "medium"},
                "住宿费": {"per_night": 600, "level": "medium"},
                "交通费": {"per_trip": 2000, "level": "low"},
                "补贴": {"per_day": 120, "level": "low"},
                "会务费": {"per_item": 20000, "level": "medium"},
                "办公用品": {"per_item": 2000, "level": "low"},
            }
        },
        "severity": "medium",
    },
    {
        "rule_code": "market_price",
        "rule_name": "市场价格合理性",
        "rule_type": "price",
        "config": {"deviation_pct": 30, "high_pct": 100},
        "severity": "medium",
    },
    {
        "rule_code": "behavior",
        "rule_name": "消费行为异常",
        "rule_type": "behavior",
        "config": {
            "history_growth_ratio": 3.0,
            "split_window_days": 7,
            "split_min_count": 3,
            "split_amount_threshold": 5000,
            "short_term_count": 3,
            "short_term_days": 7,
            "same_day_tolerance_pct": 1.0,
        },
        "severity": "medium",
    },
    {
        "rule_code": "supplier",
        "rule_name": "供应商风险",
        "rule_type": "supplier",
        "config": {"concentration_window_days": 90, "concentration_count": 5, "account_mismatch_level": "high"},
        "severity": "high",
    },
    {
        "rule_code": "attachment",
        "rule_name": "附件完整性",
        "rule_type": "attachment",
        "config": {"min_confidence": 0.55, "company_name": COMPANY_NAME},
        "severity": "high",
    },
    {
        "rule_code": "duplicate_invoice",
        "rule_name": "重复票据风险",
        "rule_type": "duplicate",
        "config": {},
        "severity": "high",
    },
]


def default_config(rule_code: str) -> dict:
    for definition in DEFAULT_RULE_DEFINITIONS:
        if definition["rule_code"] == rule_code:
            return definition["config"]
    return {}


def load_rule_configs(db: Session, document_type: str | None = None) -> dict[str, dict]:
    configs = {}
    for rule in db.execute(select(ReviewRule).where(ReviewRule.status == "active")).scalars().all():
        if rule.document_type and rule.document_type != document_type:
            continue
        config = load_json(rule.config_json, {})
        if isinstance(config, dict):
            merged = deepcopy(default_config(rule.rule_code))
            merged.update(config)
            configs[rule.rule_code] = merged
    return configs


REQUIRED_ATTACHMENTS = {
    "对公付款单": ["invoice", "contract"],
    "预付款单": ["contract"],
    "批量付款单": ["payment_proof"],
    "费用报销单": ["invoice"],
    "差旅报销单": ["invoice", "itinerary"],
}

CATEGORY_NAMES = {
    "invoice": "发票",
    "contract": "合同",
    "itinerary": "行程单",
    "payment_proof": "付款依据",
    "other": "其他材料",
}


def _level_by_ratio(ratio_pct: float, medium_pct: float, high_pct: float) -> str:
    if ratio_pct > high_pct:
        return "high"
    if ratio_pct > medium_pct:
        return "medium"
    return "low"


def _suggestion(level: str) -> str:
    if level == "high":
        return "建议驳回或要求申请人补充说明及有效凭证后重新提交"
    if level == "medium":
        return "建议人工复核，必要时要求申请人补充材料"
    return "风险可控，建议按常规流程处理并关注"


def _evidence_from_parse(parse: AttachmentParseResult | None, attachment: DocumentAttachment | None, field: str | None = None) -> dict:
    if parse is None:
        return {
            "source_type": "attachment",
            "attachment_id": attachment.id if attachment else None,
            "attachment_name": attachment.file_name if attachment else None,
            "page": None,
            "snippet": None,
            "field": field,
            "confidence": 0,
        }
    items = load_json(parse.evidence_positions_json, []) or []
    matched = None
    if field:
        matched = next((item for item in items if item.get("field") == field), None)
    if matched is None and items:
        matched = items[0]
    return {
        "source_type": "attachment",
        "attachment_id": parse.attachment_id,
        "attachment_name": attachment.file_name if attachment else None,
        "page": matched.get("page") if matched else None,
        "snippet": matched.get("snippet") if matched else (parse.full_text[:160] if parse.full_text else None),
        "bbox": matched.get("bbox") if matched else None,
        "field": field,
        "confidence": matched.get("confidence") if matched else round(float(parse.confidence or 0), 3),
    }


def evaluate_document(db: Session, doc: FinancialDocument, *, inputs=None, context=None, configs=None) -> list[dict]:
    from app.services.snapshots import capture_input, capture_context, frozen_row
    inputs = inputs if inputs is not None else capture_input(db, doc)
    context = context if context is not None else capture_context(db, doc, inputs)
    configs = configs if configs is not None else load_rule_configs(db, doc.document_type)
    attachments = [frozen_row(DocumentAttachment, row) for row in inputs['attachments']]
    latest_states = {row['attachment_id']: row for row in context['parses']}
    for attachment in attachments:
        parsed = latest_states.get(attachment.id)
        if parsed:
            attachment.parse_status = 'failed' if parsed.get('error_message') else 'succeeded' if parsed['confidence'] >= .55 else 'manual_review'
    attachment_map = {a.id: a for a in attachments}
    parses: dict[int, AttachmentParseResult] = {}
    parses = {row['attachment_id']: frozen_row(AttachmentParseResult, row) for row in context['parses']}
    items = [frozen_row(DocumentLineItem, row) for row in inputs['items']]
    invoices = [frozen_row(InvoiceRecord, row) for row in context['invoices']]

    findings: list[dict] = []

    def add(
        risk_type: str,
        category: str,
        level: str,
        title: str,
        description: str,
        actual: dict,
        reference: dict,
        threshold: dict,
        evidence: list[dict],
        suggestion: str | None = None,
    ) -> None:
        code = next((code for prefix, code in (
            ('LINE_ITEM_', 'line_item_tolerance'), ('AMOUNT_', 'amount_tolerance'),
            ('INVOICE_AMOUNT_', 'amount_tolerance'), ('CONTRACT_', 'contract_tolerance'),
            ('BATCH_', 'batch_tolerance'), ('EXPENSE_', 'expense_standards'),
            ('MARKET_', 'market_price'), ('BEHAVIOR_', 'behavior'), ('SUPPLIER_', 'supplier'),
            ('ATTACHMENT_', 'attachment'), ('INVOICE_SUBJECT_', 'attachment'),
            ('DUPLICATE_', 'duplicate_invoice')) if risk_type.startswith(prefix)), None)
        if code not in configs:
            return
        findings.append(
            {
                "risk_type": risk_type,
                "risk_category": category,
                "risk_level": level,
                "risk_title": title,
                "description": description,
                "actual_value": actual,
                "reference_value": reference,
                "threshold": threshold,
                "evidence": evidence,
                "suggestion_text": suggestion or _suggestion(level),
            }
        )

    total = float(doc.total_amount or 0)
    items_total = float(sum((money(item.amount) for item in items), Decimal('0')))
    invoice_total = float(sum((money(inv.amount_including_tax) for inv in invoices), Decimal('0')))

    # ---------------------------------------------------------- 1. 明细与总金额
    line_cfg = configs.get("line_item_tolerance", {})
    line_pct = pct(items_total, total)
    line_diff = float(money(items_total) - money(total))
    if items:
        if abs(line_diff) > max(float(line_cfg.get("abs_tolerance", 0.01)), total * float(line_cfg.get("pct_tolerance", 0.1)) / 100):
            level = _level_by_ratio(line_pct, float(line_cfg.get("medium_pct", 1)), float(line_cfg.get("high_pct", 5)))
            add(
                "LINE_ITEM_MISMATCH",
                "金额一致性",
                level,
                "明细合计与单据总金额不一致",
                f"单据总金额 {total:,.2f} 元，{len(items)} 条明细合计 {items_total:,.2f} 元，差异 {line_diff:,.2f} 元（{line_pct:.2f}%）。",
                {"document_total": total, "line_items_total": items_total, "difference": line_diff, "difference_pct": line_pct, "item_count": len(items)},
                {"expected_total": total},
                {"abs_tolerance": line_cfg.get("abs_tolerance"), "pct_tolerance": line_cfg.get("pct_tolerance")},
                [
                    {
                        "source_type": "line_item",
                        "item_id": item.id,
                        "item_name": item.item_name,
                        "amount": float(item.amount or 0),
                        "expense_date": item.expense_date.isoformat() if item.expense_date else None,
                    }
                    for item in items
                ],
                "建议核对费用明细，确认是否存在漏项、重复项或总金额填写错误",
            )
        duplicates = {}
        for item in items:
            key = (item.item_name, float(item.amount or 0), item.expense_date)
            duplicates.setdefault(key, []).append(item)
        dup_groups = {key: values for key, values in duplicates.items() if len(values) > 1}
        if dup_groups:
            add(
                "LINE_ITEM_DUPLICATE",
                "金额一致性",
                "medium",
                "存在重复费用明细",
                "检测到 " + "；".join(f"「{key[0]}」{float(key[1]):,.2f} 元重复 {len(values)} 次" for key, values in dup_groups.items()) + "。",
                {"duplicate_groups": [{"item_name": k[0], "amount": float(k[1]), "count": len(v)} for k, v in dup_groups.items()]},
                {"expected": "同一明细仅出现一次"},
                {"duplicate_count": sum(len(v) for v in dup_groups.values())},
                [{"source_type": "line_item", "item_id": v[0].id, "item_name": v[0].item_name, "count": len(v)} for v in dup_groups.values()],
                "建议删除重复明细或说明重复原因",
            )
    elif doc.document_type == "批量付款单" and doc.batch_total_amount:
        add(
            "LINE_ITEM_MISSING",
            "金额一致性",
            "medium",
            "批量付款单未维护付款明细",
            "单据填写了批次总金额但未维护付款明细，无法核对逐笔金额与收款账号。",
            {"line_items_total": 0, "batch_total_amount": float(doc.batch_total_amount or 0)},
            {"expected": "逐笔付款明细"},
            {"min_items": 1},
            [{"source_type": "document", "document_id": doc.id, "field": "line_items"}],
            "建议补充付款明细后重新提交",
        )

    # ---------------------------------------------------------- 2. 单据与发票金额
    amount_cfg = configs.get("amount_tolerance", {})
    invoice_evidence = [_evidence_from_parse(parses.get(inv.attachment_id), attachment_map.get(inv.attachment_id), "invoice_total") for inv in invoices]
    if invoices:
        diff = round(invoice_total - total, 2)
        diff_pct = pct(invoice_total, total)
        tolerance = max(float(amount_cfg.get("abs_tolerance", 1)), total * float(amount_cfg.get("pct_tolerance", 0.5)) / 100)
        if abs(diff) > tolerance:
            level = _level_by_ratio(diff_pct, float(amount_cfg.get("medium_pct", 2)), float(amount_cfg.get("high_pct", 5)))
            add(
                "AMOUNT_MISMATCH",
                "金额一致性",
                level,
                "单据金额与发票金额不一致",
                f"单据申请金额 {total:,.2f} 元，{len(invoices)} 张发票价税合计 {invoice_total:,.2f} 元，差异 {diff:,.2f} 元（{diff_pct:.2f}%）。",
                {"document_amount": total, "invoice_total": invoice_total, "difference": diff, "difference_pct": diff_pct, "invoice_count": len(invoices)},
                {"invoice_numbers": [inv.invoice_no for inv in invoices], "invoice_total": invoice_total},
                {"abs_tolerance": amount_cfg.get("abs_tolerance"), "pct_tolerance": amount_cfg.get("pct_tolerance")},
                invoice_evidence,
                "建议核对发票金额与报销/付款金额，补充差额说明",
            )
        zero_invoices = [inv for inv in invoices if float(inv.amount_including_tax or 0) <= 0]
        if zero_invoices:
            add(
                "INVOICE_AMOUNT_MISSING",
                "附件完整性",
                "medium",
                "发票金额未识别",
                f"{len(zero_invoices)} 张发票未识别到价税合计金额，可能影响金额核对。",
                {"invoice_numbers": [inv.invoice_no for inv in zero_invoices]},
                {"expected": "发票价税合计 > 0"},
                {"min_amount": 0.01},
                [_evidence_from_parse(parses.get(inv.attachment_id), attachment_map.get(inv.attachment_id), "invoice_total") for inv in zero_invoices],
                "建议人工核对发票原件金额",
            )

    # ---------------------------------------------------------- 3. 合同一致性
    contract_parse = next((p for p in parses.values() if p.document_category == "contract"), None)
    contract_fields = parsed_fields(contract_parse)
    contract_cfg = configs.get("contract_tolerance", {})
    if doc.document_type in {"对公付款单", "预付款单"} and contract_fields:
        contract_attachment = attachment_map.get(contract_parse.attachment_id)
        if doc.contract_no and contract_fields.get("contract_no") and doc.contract_no != contract_fields["contract_no"]:
            add(
                "CONTRACT_NO_MISMATCH",
                "合规性",
                "medium",
                "合同编号与附件不一致",
                f"单据合同编号为 {doc.contract_no}，合同附件识别编号为 {contract_fields['contract_no']}。",
                {"document_contract_no": doc.contract_no},
                {"attachment_contract_no": contract_fields["contract_no"]},
                {"expected": "编号一致"},
                [_evidence_from_parse(contract_parse, contract_attachment, "contract_no")],
                "建议核对合同原件并修正合同编号",
            )
        supplier_name = doc.supplier_name or doc.payee_name
        party_b = contract_fields.get("party_b")
        if supplier_name and party_b and supplier_name.strip() != party_b.strip() and supplier_name.strip() not in party_b:
            add(
                "CONTRACT_PARTY_MISMATCH",
                "供应商风险",
                "medium",
                "收款主体与合同乙方不一致",
                f"单据收款单位为「{supplier_name}」，合同乙方为「{party_b}」。",
                {"payee_name": supplier_name},
                {"contract_party_b": party_b},
                {"expected": "收款主体与合同主体一致"},
                [_evidence_from_parse(contract_parse, contract_attachment, "party_b")],
                "建议核实收款主体与合同主体关系，防范资金支付风险",
            )
        contract_amount = to_float(contract_fields.get("contract_amount"))
        ratio = doc.payment_ratio if doc.payment_ratio is not None else contract_fields.get("payment_ratio")
        if contract_amount > 0 and ratio:
            expected_payment = round(contract_amount * float(ratio) / 100, 2)
            diff = round(total - expected_payment, 2)
            diff_pct = pct(total, expected_payment)
            if abs(diff) > max(1.0, expected_payment * float(contract_cfg.get("pct_tolerance", 1)) / 100):
                level = "high" if diff_pct > float(contract_cfg.get("high_pct", 5)) else "medium"
                add(
                    "CONTRACT_PAYMENT_MISMATCH",
                    "金额一致性",
                    level,
                    "付款金额与合同约定比例不一致",
                    f"合同金额 {contract_amount:,.2f} 元 × 付款比例 {float(ratio):.0f}% = {expected_payment:,.2f} 元，本次付款 {total:,.2f} 元，差异 {diff:,.2f} 元（{diff_pct:.2f}%）。",
                    {"payment_amount": total, "expected_payment": expected_payment, "difference": diff, "difference_pct": diff_pct},
                    {"contract_amount": contract_amount, "payment_ratio": float(ratio)},
                    {"pct_tolerance": contract_cfg.get("pct_tolerance")},
                    [_evidence_from_parse(contract_parse, contract_attachment, "contract_amount"), _evidence_from_parse(contract_parse, contract_attachment, "payment_ratio")],
                    "建议核对合同付款条款与本次付款比例",
                )

    # ---------------------------------------------------------- 4. 批量付款
    if doc.document_type == "批量付款单":
        batch_cfg = configs.get("batch_tolerance", {})
        batch_total = float(doc.batch_total_amount or total)
        payouts = [item for item in items if item.item_type in {"payout", "payment"} or item.payee_account]
        payout_total = round(sum(float(item.amount or 0) for item in payouts), 2)
        if payouts:
            if abs(payout_total - batch_total) > float(batch_cfg.get("amount_tolerance", 0.01)):
                add(
                    "BATCH_AMOUNT_MISMATCH",
                    "金额一致性",
                    "high",
                    "批量付款明细合计与批次总金额不一致",
                    f"批次总金额 {batch_total:,.2f} 元，{len(payouts)} 笔付款明细合计 {payout_total:,.2f} 元，差异 {payout_total - batch_total:,.2f} 元。",
                    {"batch_total_amount": batch_total, "payout_total": payout_total, "difference": round(payout_total - batch_total, 2), "payout_count": len(payouts)},
                    {"batch_payment_count": doc.batch_payment_count},
                    {"amount_tolerance": batch_cfg.get("amount_tolerance")},
                    [{"source_type": "line_item", "item_id": item.id, "payee_name": item.payee_name, "amount": float(item.amount or 0)} for item in payouts],
                    "建议重新核对每笔付款金额与批次总金额",
                )
            if doc.batch_payment_count and len(payouts) != int(doc.batch_payment_count):
                add(
                    "BATCH_COUNT_MISMATCH",
                    "金额一致性",
                    "medium",
                    "付款笔数与批次笔数不一致",
                    f"单据填写付款笔数 {int(doc.batch_payment_count)} 笔，实际付款明细 {len(payouts)} 笔。",
                    {"declared_count": int(doc.batch_payment_count), "actual_count": len(payouts)},
                    {"expected_count": int(doc.batch_payment_count)},
                    {"count_tolerance": batch_cfg.get("count_tolerance", 0)},
                    [{"source_type": "document", "document_id": doc.id, "field": "batch_payment_count"}],
                    "建议核对付款清单笔数",
                )
            accounts: dict[str, list] = {}
            for item in payouts:
                account = (item.payee_account or "").replace(" ", "")
                if account:
                    accounts.setdefault(account, []).append(item)
            duplicate_accounts = {key: value for key, value in accounts.items() if len(value) > 1}
            if duplicate_accounts:
                add(
                    "BATCH_DUPLICATE_ACCOUNT",
                    "供应商风险",
                    "high",
                    "批量付款存在重复收款账号",
                    "检测到 " + "；".join(
                        f"账号 {key}（尾号 {key[-4:]}）对应 {len(value)} 笔付款，合计 {sum(float(i.amount or 0) for i in value):,.2f} 元"
                        for key, value in duplicate_accounts.items()
                    ) + "。",
                    {"duplicate_accounts": [{"account_tail": key[-4:], "count": len(value), "amount": round(sum(float(i.amount or 0) for i in value), 2)} for key, value in duplicate_accounts.items()]},
                    {"expected": "同一批次内收款账号唯一"},
                    {"max_occurrences": 1},
                    [{"source_type": "line_item", "item_id": value[0].id, "payee_name": value[0].payee_name, "account": value[0].payee_account} for value in duplicate_accounts.values()],
                    "建议核实重复收款账号，防止重复付款",
                )

    # ---------------------------------------------------------- 5. 费用标准
    standards = configs.get("expense_standards", {}).get("standards", {})
    violations = []
    for item in [row for row in items if not row.payee_account]:
        category = item.expense_category or item.item_type or ""
        standard = None
        standard_key = None
        for key in standards:
            if key in str(category) or key in str(item.item_name):
                standard, standard_key = standards[key], key
                break
        if not standard:
            continue
        unit_amount = float(item.unit_price or item.amount or 0)
        limit = None
        if "per_night" in standard:
            limit = float(standard["per_night"])
        elif "per_day" in standard:
            limit = float(standard["per_day"])
        elif "per_trip" in standard:
            limit = float(standard["per_trip"])
        elif "per_item" in standard:
            limit = float(standard["per_item"])
        if limit and unit_amount > limit:
            over_pct = round((unit_amount - limit) / limit * 100, 2)
            level = "high" if over_pct > 100 else str(standard.get("level", "medium"))
            violations.append(
                {
                    "item": item,
                    "category": standard_key,
                    "actual": unit_amount,
                    "limit": limit,
                    "over_pct": over_pct,
                    "level": level,
                }
            )
    if violations:
        highest = max(violations, key=lambda v: {"low": 1, "medium": 2, "high": 3}[v["level"]])
        add(
            "EXPENSE_STANDARD_EXCEEDED",
            "合规性",
            highest["level"],
            "费用支出超出企业标准",
            "；".join(
                f"「{v['item'].item_name}」{v['actual']:,.2f} 元，超出{v['category']}标准 {v['limit']:,.2f} 元（{v['over_pct']:.1f}%）"
                for v in violations
            )
            + "。",
            {"violations": [{"item_name": v["item"].item_name, "actual": v["actual"], "limit": v["limit"], "over_pct": v["over_pct"]} for v in violations]},
            {"standards": standards},
            {"over_pct": 0},
            [
                {
                    "source_type": "line_item",
                    "item_id": v["item"].id,
                    "item_name": v["item"].item_name,
                    "amount": float(v["item"].amount or 0),
                    "expense_category": v["category"],
                }
                for v in violations
            ],
            "建议按企业费用标准核减超标金额，或补充审批说明",
        )

    # ---------------------------------------------------------- 6. 市场价
    market_cfg = configs.get("market_price", {})
    all_price_references = [frozen_row(MarketPriceReference, row) for row in context['prices']]
    price_findings = []
    for item in [row for row in items if not row.payee_account]:
        matched = None
        for ref in all_price_references:
            if not ref.item_name:
                continue
            if ref.region and ref.region != '全国' and ref.region != item.expense_location:
                continue
            if ref.item_name in item.item_name or item.item_name in ref.item_name:
                if ref.specification and item.item_spec and ref.specification not in (item.item_spec or "") and item.item_spec not in ref.specification:
                    continue
                if matched is None:
                    matched = ref
                elif item.expense_location and ref.region == item.expense_location and matched.region != item.expense_location:
                    matched = ref
        if matched is None:
            continue
        price = float(item.unit_price or item.amount or 0)
        if price <= 0:
            continue
        deviation = 0.0
        reference_text = f"{float(matched.price_min):,.2f} ~ {float(matched.price_max):,.2f} 元"
        if price > float(matched.price_max):
            deviation = round((price - float(matched.price_max)) / float(matched.price_max) * 100, 2)
        elif price < float(matched.price_min):
            deviation = round((float(matched.price_min) - price) / float(matched.price_min) * 100, 2)
        if deviation > float(market_cfg.get("deviation_pct", 30)):
            level = "high" if deviation > float(market_cfg.get("high_pct", 100)) else "medium"
            price_findings.append(
                {
                    "item": item,
                    "price": price,
                    "reference": matched,
                    "deviation": deviation,
                    "level": level,
                }
            )
    if price_findings:
        highest = max(price_findings, key=lambda v: v["deviation"])
        add(
            "MARKET_PRICE_DEVIATION",
            "价格合理性",
            highest["level"],
            "采购价格偏离市场参考区间",
            "；".join(
                f"「{v['item'].item_name}」单价 {v['price']:,.2f} 元，市场参考区间 {float(v['reference'].price_min):,.2f}~{float(v['reference'].price_max):,.2f} 元，偏离 {v['deviation']:.1f}%"
                for v in price_findings
            )
            + "。",
            {
                "items": [
                    {
                        "item_name": v["item"].item_name,
                        "unit_price": v["price"],
                        "market_min": float(v["reference"].price_min),
                        "market_max": float(v["reference"].price_max),
                        "deviation_pct": v["deviation"],
                    }
                    for v in price_findings
                ]
            },
            {
                "source": [
                    {
                        "item_name": v["reference"].item_name,
                        "region": v["reference"].region,
                        "source_name": v["reference"].source_name,
                        "effective_date": v["reference"].effective_date.isoformat() if v["reference"].effective_date else None,
                    }
                    for v in price_findings
                ]
            },
            {"deviation_pct": market_cfg.get("deviation_pct"), "high_pct": market_cfg.get("high_pct")},
            [
                {
                    "source_type": "market_price",
                    "item_id": v["item"].id,
                    "item_name": v["item"].item_name,
                    "unit_price": v["price"],
                    "reference_range": [float(v["reference"].price_min), float(v["reference"].price_max)],
                    "source_name": v["reference"].source_name,
                    "effective_date": v["reference"].effective_date.isoformat() if v["reference"].effective_date else None,
                }
                for v in price_findings
            ],
            "建议要求申请人提供询价记录或说明价格偏高原因",
        )

    # ---------------------------------------------------------- 7. 消费行为
    behavior_cfg = configs.get("behavior", {})
    historical_documents = [frozen_row(FinancialDocument, row) for row in context['documents']]
    history = [row for row in historical_documents if row.applicant_id == doc.applicant_id]
    apply_day = doc.apply_date or date.today()

    same_day = [
        other
        for other in history
        if other.apply_date == apply_day
        and pct(float(other.total_amount or 0), total) <= float(behavior_cfg.get("same_day_tolerance_pct", 1))
        and total > 0
    ]
    if same_day:
        add(
            "BEHAVIOR_SAME_DAY_REPEAT",
            "行为异常",
            "medium",
            "存在同日重复报销/付款",
            f"申请人 {apply_day.isoformat()} 当日还有 {len(same_day)} 张金额相近的单据："
            + "、".join(f"{d.document_no}（{float(d.total_amount or 0):,.2f} 元）" for d in same_day)
            + "。",
            {"same_day_documents": [{"document_no": d.document_no, "total_amount": float(d.total_amount or 0)} for d in same_day]},
            {"expected": "同日同金额单据需说明原因"},
            {"same_day_tolerance_pct": behavior_cfg.get("same_day_tolerance_pct")},
            [{"source_type": "database", "document_id": d.id, "document_no": d.document_no, "total_amount": float(d.total_amount or 0)} for d in same_day],
            "建议核对是否为重复提交或拆单报销",
        )

    prior = [other for other in history if other.apply_date and other.apply_date < apply_day]
    prior.sort(key=lambda d: d.apply_date)
    recent = prior[-5:]
    if recent and total > 0:
        average = sum(float(d.total_amount or 0) for d in recent) / len(recent)
        growth = total / average if average else 0
        if growth >= float(behavior_cfg.get("history_growth_ratio", 3)):
            add(
                "BEHAVIOR_AMOUNT_JUMP",
                "行为异常",
                "medium",
                "单据金额较历史水平异常增长",
                f"本次金额 {total:,.2f} 元，为近 {len(recent)} 笔历史单据平均值 {average:,.2f} 元的 {growth:.1f} 倍。",
                {"current_amount": total, "history_average": round(average, 2), "growth_ratio": round(growth, 2)},
                {"history_documents": [d.document_no for d in recent]},
                {"growth_ratio": behavior_cfg.get("history_growth_ratio")},
                [{"source_type": "database", "document_id": d.id, "document_no": d.document_no, "total_amount": float(d.total_amount or 0)} for d in recent],
                "建议要求申请人说明金额增长的业务背景",
            )

    window = int(behavior_cfg.get("short_term_days", 7))
    window_start = apply_day - timedelta(days=window)
    recent_docs = [d for d in history if d.apply_date and window_start <= d.apply_date <= apply_day]
    if len(recent_docs) + 1 >= int(behavior_cfg.get("short_term_count", 3)):
        add(
            "BEHAVIOR_HIGH_FREQUENCY",
            "行为异常",
            "low",
            "短期内单据提交频次较高",
            f"近 {window} 天申请人共提交 {len(recent_docs) + 1} 张单据（含本单）。",
            {"document_count": len(recent_docs) + 1, "window_days": window},
            {"threshold": behavior_cfg.get("short_term_count")},
            {"short_term_count": behavior_cfg.get("short_term_count"), "short_term_days": window},
            [{"source_type": "database", "document_id": d.id, "document_no": d.document_no, "apply_date": d.apply_date.isoformat()} for d in recent_docs],
            "建议关注短期集中报销行为",
        )

    split_docs = [
        d
        for d in history
        if d.apply_date
        and window_start <= d.apply_date <= apply_day
        and float(d.total_amount or 0) < float(behavior_cfg.get("split_amount_threshold", 5000))
    ]
    if len(split_docs) + 1 >= int(behavior_cfg.get("split_min_count", 3)) and total < float(behavior_cfg.get("split_amount_threshold", 5000)):
        add(
            "BEHAVIOR_SPLIT_SUBMISSION",
            "行为异常",
            "medium",
            "疑似拆单报销",
            f"近 {window} 天存在 {len(split_docs) + 1} 张单笔低于 {float(behavior_cfg.get('split_amount_threshold', 5000)):,.2f} 元的单据，疑似拆分大额支出。",
            {"document_count": len(split_docs) + 1, "window_days": window},
            {"threshold_count": behavior_cfg.get("split_min_count"), "amount_threshold": behavior_cfg.get("split_amount_threshold")},
            {"split_window_days": window},
            [{"source_type": "database", "document_id": d.id, "document_no": d.document_no, "total_amount": float(d.total_amount or 0)} for d in split_docs],
            "建议核实拆单原因并合并审核",
        )

    weekend_items = [item for item in items if item.expense_date and item.expense_date.weekday() >= 5]
    if weekend_items:
        add(
            "BEHAVIOR_WEEKEND_EXPENSE",
            "行为异常",
            "low",
            "存在周末/节假日消费",
            "、".join(f"「{item.item_name}」{item.expense_date.isoformat()}" for item in weekend_items) + " 发生在周末，需关注业务真实性。",
            {"weekend_items": [{"item_name": item.item_name, "expense_date": item.expense_date.isoformat(), "amount": float(item.amount or 0)} for item in weekend_items]},
            {"allowed": "工作日或已审批的加班/出差消费"},
            {"weekend_days": ["Saturday", "Sunday"]},
            [{"source_type": "line_item", "item_id": item.id, "item_name": item.item_name, "expense_date": item.expense_date.isoformat()} for item in weekend_items],
            "建议关注周末消费的业务背景",
        )

    if doc.document_type == "差旅报销单" and doc.travel_location:
        mismatch = [
            item
            for item in items
            if item.expense_location and doc.travel_location not in item.expense_location and item.expense_location not in doc.travel_location
        ]
        if mismatch:
            add(
                "BEHAVIOR_OUT_OF_REGION",
                "行为异常",
                "medium",
                "消费地点与出差地点不一致",
                f"出差地点为「{doc.travel_location}」，但存在 {len(mismatch)} 条消费记录地点不在出差地："
                + "、".join(f"{item.expense_location}（{item.item_name}）" for item in mismatch)
                + "。",
                {"travel_location": doc.travel_location, "mismatch_items": [{"item_name": item.item_name, "expense_location": item.expense_location, "amount": float(item.amount or 0)} for item in mismatch]},
                {"expected_location": doc.travel_location},
                {"max_mismatch": 0},
                [{"source_type": "line_item", "item_id": item.id, "item_name": item.item_name, "expense_location": item.expense_location} for item in mismatch],
                "建议核对出差行程与消费凭证的关联性",
            )

    # ---------------------------------------------------------- 8. 供应商风险
    supplier_cfg = configs.get("supplier", {})
    supplier = None
    profiles = [frozen_row(SupplierProfile, row) for row in context['suppliers']]
    supplier = next((row for row in profiles if row.supplier_code == doc.supplier_code), None)
    if supplier is None:
        supplier = next((row for row in profiles if row.supplier_name == (doc.supplier_name or doc.payee_name)), None)

    if supplier:
        risk_tags = load_json(supplier.risk_tags_json, []) or []
        bank_accounts = [str(a).replace(" ", "") for a in (load_json(supplier.bank_accounts_json, []) or [])]
        profile_evidence = [
            {
                "source_type": "supplier",
                "supplier_code": supplier.supplier_code,
                "supplier_name": supplier.supplier_name,
                "credit_status": supplier.credit_status,
                "blacklist_status": supplier.blacklist_status,
                "risk_tags": risk_tags,
            }
        ]
        if supplier.blacklist_status != "normal":
            add(
                "SUPPLIER_BLACKLIST",
                "供应商风险",
                "high",
                "供应商处于黑名单",
                f"收款单位「{supplier.supplier_name}」（{supplier.supplier_code}）黑名单状态为「{supplier.blacklist_status}」，历史风险标签：{'、'.join(risk_tags) or '无'}。",
                {"supplier_code": supplier.supplier_code, "blacklist_status": supplier.blacklist_status},
                {"expected": "normal"},
                {"blacklist_status": "normal"},
                profile_evidence,
                "建议停止付款并转交合规/风控部门处理",
            )
        if supplier.credit_status not in {"normal", "good"}:
            add(
                "SUPPLIER_CREDIT_ABNORMAL",
                "供应商风险",
                "medium",
                "供应商信用状态异常",
                f"供应商「{supplier.supplier_name}」信用状态为「{supplier.credit_status}」。",
                {"supplier_code": supplier.supplier_code, "credit_status": supplier.credit_status},
                {"expected": "normal"},
                {"credit_status": "normal"},
                profile_evidence,
                "建议核实供应商资质与履约能力",
            )
        if risk_tags:
            level = "high" if any(tag in {"关联交易", "账号变更", "履约异常", "涉诉"} for tag in risk_tags) else "medium"
            add(
                "SUPPLIER_RISK_TAG",
                "供应商风险",
                level,
                "供应商存在风险标签",
                f"供应商「{supplier.supplier_name}」风险标签：{'、'.join(risk_tags)}。",
                {"supplier_code": supplier.supplier_code, "risk_tags": risk_tags},
                {"expected": "无风险标签"},
                {"max_tags": 0},
                profile_evidence,
                "建议人工复核供应商历史履约、关联关系及收款信息",
            )
        account = (doc.payee_account or "").replace(" ", "")
        if bank_accounts and account and account not in bank_accounts:
            add(
                "SUPPLIER_ACCOUNT_MISMATCH",
                "供应商风险",
                "high",
                "收款账号与供应商备案账号不一致",
                f"单据收款账号尾号 {account[-4:]}，与供应商「{supplier.supplier_name}」备案账号（尾号 "
                + "、".join(a[-4:] for a in bank_accounts)
                + "）不一致，存在收款账号变更风险。",
                {"payee_account_tail": account[-4:], "payee_name": doc.payee_name},
                {"registered_accounts_tail": [a[-4:] for a in bank_accounts]},
                {"expected": "收款账号必须与备案账号一致"},
                profile_evidence,
                "建议与供应商电话核实收款账号，防范资金诈骗",
            )
        window_days = int(supplier_cfg.get("concentration_window_days", 90))
        window_start = doc.apply_date - timedelta(days=window_days)
        supplier_docs = [row for row in historical_documents if row.supplier_code == supplier.supplier_code
                         and row.apply_date >= window_start and row.document_status != 'returned']
        if len(supplier_docs) + 1 >= int(supplier_cfg.get("concentration_count", 5)):
            add(
                "SUPPLIER_CONCENTRATION",
                "供应商风险",
                "low",
                "对同一供应商付款较集中",
                f"近 {window_days} 天向供应商「{supplier.supplier_name}」付款 {len(supplier_docs) + 1} 笔（含本单），需关注集中付款风险。",
                {"payment_count": len(supplier_docs) + 1, "window_days": window_days},
                {"threshold": supplier_cfg.get("concentration_count")},
                {"concentration_count": supplier_cfg.get("concentration_count"), "concentration_window_days": window_days},
                [{"source_type": "database", "document_id": d.id, "document_no": d.document_no, "total_amount": float(d.total_amount or 0)} for d in supplier_docs],
                "建议定期复核供应商集中度与授信额度",
            )
    elif doc.document_type in {"对公付款单", "预付款单", "批量付款单"} and (doc.payee_name or doc.supplier_name):
        add(
            "SUPPLIER_NOT_REGISTERED",
            "供应商风险",
            "low",
            "供应商未建立档案",
            f"收款单位「{doc.supplier_name or doc.payee_name}」未在供应商库中建档，无法校验黑名单、资质及备案账号。",
            {"supplier_name": doc.supplier_name or doc.payee_name},
            {"expected": "供应商已建档"},
            {"profile_required": True},
            [{"source_type": "document", "document_id": doc.id, "field": "payee_name", "value": doc.payee_name}],
            "建议补充维护供应商档案",
        )

    # ---------------------------------------------------------- 9. 附件完整性
    attachment_cfg = configs.get("attachment", {})
    required = REQUIRED_ATTACHMENTS.get(doc.document_type, [])
    categories = {parse.document_category for parse in parses.values()}
    missing = [category for category in required if category not in categories]
    failed_atts = [att for att in attachments if att.parse_status == "failed"]
    manual_atts = [att for att in attachments if att.parse_status == "manual_review"]
    low_confidence = [
        (att, parses[att.id])
        for att in attachments
        if att.id in parses and float(parses[att.id].confidence or 0) < float(attachment_cfg.get("min_confidence", 0.55))
    ]
    if not attachments:
        add(
            "ATTACHMENT_MISSING",
            "附件完整性",
            "high",
            "单据未上传任何附件",
            f"「{doc.document_type}」要求上传 {'、'.join(CATEGORY_NAMES.get(c, c) for c in required)}，当前未检测到任何附件。",
            {"attachment_count": 0},
            {"required_categories": required},
            {"min_attachments": 1},
            [{"source_type": "document", "document_id": doc.id, "field": "attachments"}],
            "建议补齐必需附件后重新提交",
        )
    elif missing:
        level = "high" if "invoice" in missing and doc.document_type == "费用报销单" else "medium"
        add(
            "ATTACHMENT_INCOMPLETE",
            "附件完整性",
            level,
            "缺少必需附件",
            f"「{doc.document_type}」要求上传 {'、'.join(CATEGORY_NAMES.get(c, c) for c in required)}，当前缺少：{'、'.join(CATEGORY_NAMES.get(c, c) for c in missing)}。",
            {"missing_categories": missing, "detected_categories": sorted(categories)},
            {"required_categories": required},
            {"required": required},
            [
                {
                    "source_type": "attachment",
                    "attachment_id": att.id,
                    "attachment_name": att.file_name,
                    "document_category": parses.get(att.id).document_category if parses.get(att.id) else None,
                }
                for att in attachments
            ],
            "建议补齐缺失附件，避免影响审批判断",
        )
    if failed_atts:
        add(
            "ATTACHMENT_PARSE_FAILED",
            "附件完整性",
            "medium",
            "附件解析失败",
            "、".join(att.file_name for att in failed_atts) + f" 共 {len(failed_atts)} 个附件解析失败，无法提取关键字段。",
            {"failed_attachments": [{"id": att.id, "file_name": att.file_name} for att in failed_atts]},
            {"expected": "附件解析成功"},
            {"parse_status": "succeeded"},
            [{"source_type": "attachment", "attachment_id": att.id, "attachment_name": att.file_name} for att in failed_atts],
            "建议重新上传清晰附件或转人工复核",
        )
    if manual_atts:
        add(
            "ATTACHMENT_MANUAL_REVIEW",
            "附件完整性",
            "low",
            "附件识别置信度偏低",
            "、".join(att.file_name for att in manual_atts) + " 识别置信度低于阈值，关键字段需人工核对。",
            {"attachments": [{"id": att.id, "file_name": att.file_name} for att in manual_atts]},
            {"min_confidence": attachment_cfg.get("min_confidence")},
            {"min_confidence": attachment_cfg.get("min_confidence")},
            [{"source_type": "attachment", "attachment_id": att.id, "attachment_name": att.file_name, "confidence": round(float(parses[att.id].confidence or 0), 3) if att.id in parses else 0} for att in manual_atts],
            "建议人工核对附件关键字段",
        )
    if low_confidence:
        add(
            "ATTACHMENT_LOW_CONFIDENCE",
            "附件完整性",
            "low",
            "附件字段识别置信度不足",
            "、".join(f"{att.file_name}（{float(parse.confidence):.0%}）" for att, parse in low_confidence) + " 的关键字段识别置信度低于阈值。",
            {"attachments": [{"id": att.id, "file_name": att.file_name, "confidence": round(float(parse.confidence or 0), 3)} for att, parse in low_confidence]},
            {"min_confidence": attachment_cfg.get("min_confidence")},
            {"min_confidence": attachment_cfg.get("min_confidence")},
            [_evidence_from_parse(parse, att) for att, parse in low_confidence],
            "建议人工核对原文及识别字段",
        )

    company_name = attachment_cfg.get("company_name") or COMPANY_NAME
    buyer_mismatch = []
    for parse in parses.values():
        fields = parsed_fields(parse)
        buyer = fields.get("buyer_name")
        if buyer and company_name not in buyer and buyer not in company_name:
            buyer_mismatch.append((parse, buyer))
    if buyer_mismatch:
        add(
            "INVOICE_SUBJECT_MISMATCH",
            "附件完整性",
            "high",
            "发票购买方与报销主体不一致",
            "；".join(f"发票购买方「{buyer}」与公司主体「{company_name}」不一致" for _, buyer in buyer_mismatch) + "。",
            {"buyers": [buyer for _, buyer in buyer_mismatch], "company_name": company_name},
            {"expected": company_name},
            {"subject_must_match": True},
            [_evidence_from_parse(parse, attachment_map.get(parse.attachment_id), "buyer_name") for parse, _ in buyer_mismatch],
            "建议退回并要求提供公司主体的合规发票",
        )

    # ---------------------------------------------------------- 10. 重复票据
    other_invoices = [frozen_row(InvoiceRecord, row) for row in context['other_invoices']]
    duplicates = []
    for inv in invoices:
        for other in other_invoices:
            same_no = inv.invoice_no and inv.invoice_no == other.invoice_no
            same_combo = (
                inv.seller_name
                and inv.seller_name == other.seller_name
                and inv.amount_including_tax is not None
                and other.amount_including_tax is not None
                and float(inv.amount_including_tax) == float(other.amount_including_tax)
                and inv.invoice_date == other.invoice_date
            )
            if same_no or same_combo:
                duplicates.append((inv, other))
        for other in invoices:
            if other.id <= inv.id:
                continue
            if inv.invoice_no and inv.invoice_no == other.invoice_no:
                duplicates.append((inv, other))
    if duplicates:
        other_ids = sorted({other.document_id for _, other in duplicates})
        other_docs = [row for row in historical_documents if row.id in other_ids]
        doc_no_map = {d.id: d.document_no for d in other_docs}
        add(
            "DUPLICATE_INVOICE",
            "票据风险",
            "high",
            "检测到重复发票",
            f"本单发票与 {len(other_docs)} 张历史单据中的发票重复："
            + "、".join(
                f"{inv.invoice_no or '无号码'}（{float(inv.amount_including_tax or 0):,.2f} 元，重复单号 {doc_no_map.get(other.document_id, '-')}）"
                for inv, other in duplicates
            )
            + "。",
            {
                "duplicates": [
                    {
                        "invoice_no": inv.invoice_no,
                        "amount": float(inv.amount_including_tax or 0),
                        "duplicated_document_no": doc_no_map.get(other.document_id),
                    }
                    for inv, other in duplicates
                ]
            },
            {"matched_documents": [d.document_no for d in other_docs]},
            {"duplicate_count": 0},
            [
                {
                    "source_type": "database",
                    "document_id": other.document_id,
                    "document_no": doc_no_map.get(other.document_id),
                    "invoice_no": other.invoice_no,
                    "amount": float(other.amount_including_tax or 0),
                }
                for _, other in duplicates
            ],
            "建议立即核实重复票据，避免重复报销",
        )

    return findings
