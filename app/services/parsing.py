"""附件解析：PDF 文本提取、图片 OCR、文档分类、字段抽取与证据定位。"""
from __future__ import annotations

import re
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AttachmentParseResult, DocumentAttachment, InvoiceRecord
from app.services.audit import log_action
from app.utils import dump_json, load_json, parse_date, to_float


def validate_attachment_bytes(content: bytes, suffix: str):
    """校验实际文件内容，拒绝伪装扩展名、加密 PDF 和过大的图像。"""
    try:
        if suffix == '.pdf':
            from pypdf import PdfReader
            if not content.startswith(b'%PDF-'):
                raise ValueError('文件内容不是有效 PDF')
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
                raise ValueError('仅支持未加密的1到30页PDF')
        else:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as image:
                expected = 'PNG' if suffix == '.png' else 'JPEG'
                if image.format != expected:
                    raise ValueError('文件扩展名与实际图像格式不一致')
                if image.width * image.height > 25000000:
                    raise ValueError('图片不能超过2500万像素')
                image.verify()
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(422, f'附件格式校验失败：{exc}') from exc

# ------------------------------------------------------------------ 字段规则
FIELD_PATTERNS: list[tuple[str, str, str]] = [
    ("invoice_code", r"发票代码[:：]?\s*([0-9]{10,12})", "text"),
    ("invoice_no", r"发票号码[:：]?\s*([0-9]{8,20})", "text"),
    ("invoice_date", r"开票日期[:：]?\s*(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?)", "date"),
    ("buyer_name", r"购买方(?:名称)?[:：]?\s*([^\n，,]{2,60})", "text"),
    ("seller_name", r"(?:销售方|销方)(?:名称)?[:：]?\s*([^\n，,]{2,60})", "text"),
    ("invoice_total", r"价税合计[^\n]{0,24}?[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("amount_excluding_tax", r"(?:不含税金额|金额)[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("tax_amount", r"税额[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("contract_no", r"合同编号[:：]?\s*([A-Za-z0-9\-_/]{4,40})", "text"),
    ("contract_amount", r"合同金额[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("party_a", r"甲\s*方[:：]?\s*([^\n，,]{2,60})", "text"),
    ("party_b", r"乙\s*方[:：]?\s*([^\n，,]{2,60})", "text"),
    ("payment_ratio", r"付款比例[:：]?\s*([\d.]+)\s*%", "percent"),
    ("payee_name", r"收款(?:单位|方)[:：]?\s*([^\n，,]{2,60})", "text"),
    ("payee_account", r"收款账号[:：]?\s*([0-9\s\-]{8,40})", "text"),
    ("payment_amount", r"付款金额[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("payment_date", r"(?:付款|交易)日期[:：]?\s*(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?)", "date"),
    ("travel_location", r"(?:出差地点|目的地)[:：]?\s*([^\n，,]{2,40})", "text"),
    ("travel_start_date", r"出差起止[:：]?\s*(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2})", "date"),
    ("travel_end_date", r"出差起止[:：]?[^\n]{0,20}?至\s*(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2})", "date"),
    ("transport_fee", r"交通费[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("hotel_fee", r"住宿费[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("meal_fee", r"餐费[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
    ("allowance", r"补贴[:：]?\s*[¥￥]?\s*([\d,]+\.\d{2})", "money"),
]

CATEGORY_KEYWORDS = {
    "invoice": ["发票", "价税合计", "发票代码", "发票号码", "销售方"],
    "contract": ["合同", "甲方", "乙方", "合同金额", "付款条件"],
    "itinerary": ["出差", "行程", "航班", "车次", "酒店"],
    "payment_proof": ["付款", "回单", "收款账号", "转账", "付款金额"],
}

_ocr_engine = None


@dataclass
class LineSpan:
    page: int
    start: int
    end: int
    text: str
    confidence: float
    bbox: list | None = None


# ------------------------------------------------------------------ OCR
def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_image(image) -> tuple[str, list[dict]]:
    """对 PIL.Image 做 OCR，返回文本与行级位置。"""
    import numpy as np

    engine = _get_ocr_engine()
    result, _elapse = engine(np.array(image.convert("RGB")))
    lines: list[dict] = []
    if not result:
        return "", lines
    for item in result:
        box, text, score = item[0], item[1], float(item[2])
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(
            {
                "text": str(text),
                "score": score,
                "bbox": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
            }
        )
    return "\n".join(line["text"] for line in lines), lines


def _render_pdf_pages(path: Path) -> list:
    import pypdfium2 as pdfium

    images = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=2.2)
            images.append(bitmap.to_pil())
    finally:
        pdf.close()
    return images


def _extract_pdf(path: Path) -> tuple[list[dict], str]:
    from pypdf import PdfReader

    pages: list[dict] = []
    reader = PdfReader(str(path))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
        raise ValueError('仅支持未加密的1到30页PDF')
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append({"text": text, "ocr": False, "lines": []})
    missing = [index for index, page in enumerate(pages) if len(page['text'].strip()) < 30]
    if not missing:
        return pages, "pypdf"

    # 扫描件：整页渲染后 OCR
    images = _render_pdf_pages(path)
    for index in missing:
        image = images[index]
        text, lines = _ocr_image(image)
        pages[index] = {"text": text, "ocr": True, "lines": lines}
    return pages, "pypdfium2+rapidocr"


def _extract_image(path: Path) -> tuple[list[dict], str]:
    from PIL import Image

    with Image.open(path) as image:
        text, lines = _ocr_image(image)
    return [{"text": text, "ocr": True, "lines": lines}], "rapidocr"


# ------------------------------------------------------------------ 主流程
def _build_text_and_spans(pages: list[dict]) -> tuple[str, list[LineSpan]]:
    full_parts: list[str] = []
    spans: list[LineSpan] = []
    offset = 0
    for page_index, page in enumerate(pages, start=1):
        text = page["text"] or ""
        page_start = offset
        if page_index > 1:
            full_parts.append("\n")
            page_start += 1
        full_parts.append(text)
        # 建立行级位置
        cursor = page_start
        for line in text.split("\n"):
            if line.strip():
                spans.append(
                    LineSpan(
                        page=page_index,
                        start=cursor,
                        end=cursor + len(line),
                        text=line.strip(),
                        confidence=0.96 if not page.get("ocr") else _match_ocr_line_confidence(line, page.get("lines", [])),
                        bbox=_find_bbox(line, page.get("lines", [])),
                    )
                )
            cursor += len(line) + 1
        offset = page_start + len(text)
    full_text = "".join(full_parts)
    return full_text, spans


def _match_ocr_line_confidence(line: str, lines: list[dict]) -> float:
    stripped = line.strip()
    for item in lines:
        if item["text"].strip() == stripped:
            return round(item["score"], 3)
    return 0.85


def _find_bbox(line: str, lines: list[dict]) -> list | None:
    stripped = line.strip()
    for item in lines:
        if item["text"].strip() == stripped:
            return item["bbox"]
    return None


def _locate(spans: list[LineSpan], match_start: int, match_end: int, fallback_text: str) -> dict:
    for span in spans:
        if span.start <= match_start <= span.end or span.start <= match_end <= span.end:
            return {
                "page": span.page,
                "char_start": match_start,
                "char_end": match_end,
                "snippet": span.text[:180],
                "bbox": span.bbox,
                "confidence": span.confidence,
            }
    return {"page": 1, "char_start": match_start, "char_end": match_end, "snippet": fallback_text[:180], "bbox": None, "confidence": 0.6}


def classify_document(text: str, file_name: str) -> str:
    haystack = f"{file_name}\n{text}"
    scores = {category: sum(1 for kw in keywords if kw in haystack) for category, keywords in CATEGORY_KEYWORDS.items()}
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else "other"


def extract_fields(full_text: str, spans: list[LineSpan]) -> tuple[dict, list[dict]]:
    fields: dict[str, Any] = {}
    evidence: list[dict] = []
    for name, pattern, value_type in FIELD_PATTERNS:
        if name in fields:
            continue
        match = re.search(pattern, full_text)
        if not match:
            continue
        raw = match.group(1).strip()
        if value_type == "money":
            value = round(to_float(raw), 2)
        elif value_type == "date":
            value = parse_date(raw) or raw
        elif value_type == "percent":
            value = to_float(raw)
        else:
            value = re.sub(r"\s+", " ", raw).strip()
        if value in (None, "", 0) and value_type == "money":
            continue
        fields[name] = value
        location = _locate(spans, match.start(1), match.end(1), match.group(0))
        location["field"] = name
        location["value"] = value
        evidence.append(location)

    if "invoice_total" in fields:
        fields["amount_including_tax"] = fields["invoice_total"]
        evidence.append({**next(e for e in evidence if e["field"] == "invoice_total"), "field": "amount_including_tax"})
    if "payee_account" in fields:
        fields["payee_account"] = re.sub(r"\s+", "", str(fields["payee_account"]))
    return fields, evidence


def _confidence_of(evidence: list[dict], fields: dict) -> float:
    if not evidence:
        return 0.35
    base = sum(float(item.get("confidence") or 0.7) for item in evidence) / len(evidence)
    coverage = min(len(fields) / 8, 1.0)
    return round(min(0.99, base * 0.75 + coverage * 0.25), 3)


def parse_file(path: Path, file_name: str) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages, source = _extract_pdf(path)
    elif suffix in {".png", ".jpg", ".jpeg"}:
        pages, source = _extract_image(path)
    else:
        raise ValueError(f"不支持的文件类型：{suffix}")

    full_text, spans = _build_text_and_spans(pages)
    if not full_text.strip():
        raise ValueError("附件未识别到任何文本，请确认文件清晰度或改用手工复核")
    category = classify_document(full_text, file_name)
    fields, evidence = extract_fields(full_text, spans)
    confidence = _confidence_of(evidence, fields)
    return {
        "document_category": category,
        "full_text": full_text,
        "page_texts": [{"page": i + 1, "text": p["text"], "ocr": p["ocr"]} for i, p in enumerate(pages)],
        "fields": fields,
        "evidence": evidence,
        "confidence": confidence,
        "parser_source": source,
    }


def parse_attachment_sync(db: Session, attachment: DocumentAttachment) -> AttachmentParseResult:
    attachment.parse_status = "parsing"
    attachment_id = attachment.id
    db.commit()

    path = Path(attachment.file_path)
    try:
        if not path.exists():
            raise FileNotFoundError("附件文件不存在或已被移动")
        result = parse_file(path, attachment.file_name)

        db.query(InvoiceRecord).filter(InvoiceRecord.attachment_id == attachment.id).delete()
        # 旧解析结果保留，历史报告通过输入快照关联当时的解析版本。

        parse_row = AttachmentParseResult(
            attachment_id=attachment.id,
            document_category=result["document_category"],
            full_text=result["full_text"],
            page_text_json=dump_json(result["page_texts"]),
            fields_json=dump_json(result["fields"]),
            evidence_positions_json=dump_json(result["evidence"]),
            confidence=result["confidence"],
            parser_source=result["parser_source"],
        )
        db.add(parse_row)
        db.flush()

        if result["document_category"] == "invoice" and result["fields"].get("invoice_no"):
            fields = result["fields"]
            invoice_date = fields.get("invoice_date")
            db.add(
                InvoiceRecord(
                    attachment_id=attachment.id,
                    document_id=attachment.document_id,
                    invoice_code=fields.get("invoice_code"),
                    invoice_no=fields.get("invoice_no"),
                    seller_name=fields.get("seller_name"),
                    buyer_name=fields.get("buyer_name"),
                    invoice_date=datetime.strptime(invoice_date, "%Y-%m-%d").date() if invoice_date else None,
                    amount_excluding_tax=fields.get("amount_excluding_tax"),
                    tax_amount=fields.get("tax_amount"),
                    amount_including_tax=fields.get("invoice_total") or fields.get("amount_including_tax"),
                )
            )

        required = {'invoice': {'invoice_no', 'invoice_total'}, 'contract': {'contract_no', 'contract_amount'}}.get(result['document_category'], set())
        missing = required - result['fields'].keys()
        repeated_invoices = len(re.findall(r'发票号码[:：]?\s*[0-9]{8,20}', result['full_text'])) > 1
        if missing or repeated_invoices:
            parse_row.confidence = min(parse_row.confidence, .54)
        attachment.parse_status = "succeeded" if parse_row.confidence >= 0.55 else "manual_review"
        log_action(
            db,
            attachment.uploaded_by,
            "attachment.parse",
            "document_attachment",
            attachment.id,
            {"category": result["document_category"], "confidence": result["confidence"], "source": result["parser_source"]},
        )
        db.commit()
        return parse_row
    except Exception as exc:  # noqa: BLE001 - 解析失败需要落库并允许重试
        db.rollback()
        attachment = db.get(DocumentAttachment, attachment_id)
        if attachment is not None:
            attachment.parse_status = "failed"
            existing = db.execute(
                select(AttachmentParseResult)
                .where(AttachmentParseResult.attachment_id == attachment.id)
                .order_by(AttachmentParseResult.id.desc())
            ).scalars().first()
            if existing is None:
                db.add(
                    AttachmentParseResult(
                        attachment_id=attachment.id,
                        document_category="other",
                        full_text="",
                        fields_json=dump_json({}),
                        evidence_positions_json=dump_json([]),
                        confidence=0,
                        parser_source="error",
                        error_message=str(exc),
                    )
                )
            else:
                existing.error_message = str(exc)
        db.commit()
        raise


def parse_attachment_background(attachment_id: int) -> None:
    db = SessionLocal()
    try:
        attachment = db.get(DocumentAttachment, attachment_id)
        if attachment is None:
            return
        parse_attachment_sync(db, attachment)
    except Exception:  # noqa: BLE001 - 后台任务，异常已记录在附件状态
        pass
    finally:
        db.close()


def ensure_parsed(db: Session, attachment: DocumentAttachment) -> AttachmentParseResult | None:
    """分析阶段确保附件已解析；失败返回 None 并保留错误信息。"""
    result = db.execute(
        select(AttachmentParseResult)
        .where(AttachmentParseResult.attachment_id == attachment.id)
        .order_by(AttachmentParseResult.id.desc())
    ).scalars().first()
    if attachment.parse_status in {"succeeded", "manual_review"} and result is not None:
        return result
    try:
        return parse_attachment_sync(db, attachment)
    except Exception:  # noqa: BLE001 - 解析失败在分析中作为风险项处理
        return db.execute(
            select(AttachmentParseResult)
            .where(AttachmentParseResult.attachment_id == attachment.id)
            .order_by(AttachmentParseResult.id.desc())
        ).scalars().first()


def parsed_fields(parse: AttachmentParseResult | None) -> dict:
    if parse is None:
        return {}
    return load_json(parse.fields_json, {}) or {}
