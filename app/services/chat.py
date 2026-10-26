"""智能审核多轮对话：槽位澄清、单据解析与发起分析。"""
from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import can_view_document
from app.models import FinancialDocument, ReviewReport, ReviewSession, SessionMessage, User
from app.services.analysis import create_analysis_task, latest_any_task, report_for_task
from app.services.audit import log_action
from app.utils import dump_json, iso, load_json

DOCUMENT_TYPES = ["对公付款单", "预付款单", "批量付款单", "费用报销单", "差旅报销单"]

STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审批",
    "reviewing": "审批中",
    "returned": "已退回",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已撤回",
    "voided": "已作废",
}

TYPE_KEYWORDS = [
    ("批量付款", "批量付款单"),
    ("对公付款", "对公付款单"),
    ("预付款", "预付款单"),
    ("差旅", "差旅报销单"),
    ("费用报销", "费用报销单"),
    ("报销", "费用报销单"),
]

NO_PATTERN = re.compile(r"([A-Za-z]{2,4})\s*[-－—]\s*(\d{4,6})\s*[-－—]\s*(\d{3,6})")


def create_session(db: Session, user: User, document_type: str | None, document_no: str | None) -> ReviewSession:
    session = ReviewSession(
        user_id=user.id,
        document_type=document_type if document_type in DOCUMENT_TYPES else None,
        document_no=document_no,
        session_status="active",
        slots_json=dump_json({"document_type": document_type, "document_no": document_no}),
    )
    db.add(session)
    db.flush()
    greeting = (
        "您好，我是财务单据智能审核助手。请告诉我需要审核的单据类型和单据编号，"
        "例如「审核对公付款单 GF-202610-0001」。我会查询系统内的单据与附件并生成风险分析。"
    )
    db.add(
        SessionMessage(
            session_id=session.id,
            role="assistant",
            content=greeting,
            message_type="text",
        )
    )
    log_action(db, user.id, "session.create", "review_session", session.id)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: int, user: User) -> ReviewSession:
    session = db.get(ReviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核会话不存在")
    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该会话")
    return session


def session_messages(db: Session, session_id: int) -> list[dict]:
    rows = db.execute(
        select(SessionMessage).where(SessionMessage.session_id == session_id).order_by(SessionMessage.id)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "message_type": row.message_type,
            "payload": load_json(row.payload_json, {}),
            "created_at": iso(row.created_at),
        }
        for row in rows
    ]


def _detect_type(content: str, hint: str | None = None) -> str | None:
    if hint in DOCUMENT_TYPES and hint in content:
        return hint
    for keyword, doc_type in TYPE_KEYWORDS:
        if keyword in content:
            return doc_type
    return None


def _accessible_documents(db: Session, user: User, limit: int = 200) -> list[FinancialDocument]:
    docs = db.execute(
        select(FinancialDocument).order_by(FinancialDocument.id.desc()).limit(limit)
    ).scalars().all()
    return [doc for doc in docs if can_view_document(db, user, doc)]


def _find_document(db: Session, user: User, document_no: str, document_type: str | None) -> tuple[list[FinancialDocument], str | None]:
    normalized = re.sub(r"\s+", "", document_no).upper()
    docs = _accessible_documents(db, user)
    matches = [doc for doc in docs if re.sub(r"\s+", "", doc.document_no).upper() == normalized]
    if not matches:
        suffix_match = [
            doc
            for doc in docs
            if normalized and re.sub(r"\s+", "", doc.document_no).upper().endswith(normalized)
        ]
        if len(suffix_match) == 1:
            matches = suffix_match
        elif len(suffix_match) > 1:
            matches = suffix_match
    if document_type:
        typed = [doc for doc in matches if doc.document_type == document_type]
        if typed:
            matches = typed
    if not matches:
        return [], None
    if len(matches) == 1:
        return matches, None
    return matches, "multiple"


def _doc_brief(db: Session, doc: FinancialDocument) -> dict:
    applicant = db.get(User, doc.applicant_id)
    return {
        "document_id": doc.id,
        "document_no": doc.document_no,
        "document_type": doc.document_type,
        "total_amount": float(doc.total_amount or 0),
        "document_status": doc.document_status,
        "status_label": STATUS_LABELS.get(doc.document_status, doc.document_status),
        "applicant_name": applicant.display_name if applicant else None,
        "apply_date": iso(doc.apply_date),
    }


def _extract_document_no(content: str) -> str | None:
    match = NO_PATTERN.search(content)
    if match:
        return f"{match.group(1).upper()}-{match.group(2)}-{match.group(3)}"
    return None


def _assistant_reply(
    db: Session,
    session: ReviewSession,
    content: str,
    message_type: str = "text",
    payload: dict | None = None,
) -> dict:
    message = SessionMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        message_type=message_type,
        payload_json=dump_json(payload) if payload else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "message_type": message.message_type,
        "payload": payload or {},
        "created_at": iso(message.created_at),
    }


def send_message(db: Session, session: ReviewSession, user: User, content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="消息内容不能为空")

    db.add(SessionMessage(session_id=session.id, role="user", content=content, message_type="text"))
    db.commit()

    slots = load_json(session.slots_json, {}) or {}
    slots.setdefault("document_type", session.document_type)
    slots.setdefault("document_no", session.document_no)

    # 候选确认
    candidates = slots.get("candidates") or []
    if candidates:
        choice = None
        if content in {"1", "第一个", "第1个", "选1"}:
            choice = candidates[0]
        elif content in {"2", "第二个", "第2个", "选2"} and len(candidates) > 1:
            choice = candidates[1]
        elif content in {"3", "第三个", "第3个", "选3"} and len(candidates) > 2:
            choice = candidates[2]
        elif content in {"取消", "重来"}:
            slots["candidates"] = []
            session.slots_json = dump_json(slots)
            db.commit()
            return {"messages": [_assistant_reply(db, session, "已清除候选单据，请重新提供单据类型和单据编号。")]}
        elif content in {"确认", "继续", "是", "开始分析"}:
            choice = candidates[0]
        if choice:
            slots["candidates"] = []
            slots["document_type"] = choice["document_type"]
            slots["document_no"] = choice["document_no"]
            session.document_type = choice["document_type"]
            session.document_no = choice["document_no"]
            session.slots_json = dump_json(slots)
            db.commit()
            doc = db.get(FinancialDocument, choice["document_id"])
            if doc is not None:
                return _start_analysis(db, session, user, doc, slots)

    detected_type = _detect_type(content, slots.get("document_type"))
    detected_no = _extract_document_no(content)

    # 已有会话槽位下，用户只回复编号
    if detected_no is None and slots.get("document_type") and not slots.get("document_no"):
        stripped = content.strip()
        if re.fullmatch(r"[A-Za-z0-9\-－—\s]{4,32}", stripped) and not any(kw in stripped for kw in ["分析", "报告", "结果", "查看"]):
            candidate_no = stripped.upper().replace(" ", "")
            if re.search(r"\d{3,}", candidate_no):
                detected_no = candidate_no

    # 用户直接输入编号，且与系统已有单据匹配
    if detected_no is None:
        docs = _accessible_documents(db, user)
        normalized_content = re.sub(r"\s+", "", content).upper()
        matched = [doc for doc in docs if re.sub(r"\s+", "", doc.document_no).upper() in normalized_content]
        if len(matched) == 1:
            detected_no = matched[0].document_no
            detected_type = detected_type or matched[0].document_type
        elif len(matched) > 1:
            detected_no = matched[0].document_no

    if detected_type:
        slots["document_type"] = detected_type
        session.document_type = detected_type
    if detected_no:
        slots["document_no"] = detected_no
        session.document_no = detected_no

    # 查看报告意图
    if any(keyword in content for keyword in ["报告", "结果", "结论"]) and slots.get("document_no"):
        doc = _resolve_single(db, user, slots)
        if doc is not None:
            task = latest_any_task(db, doc.id)
            report = report_for_task(db, task.id) if task else None
            if report is not None:
                summary = load_json(report.risk_summary_json, {})
                reply = (
                    f"单据 {doc.document_no} 的最新分析报告已生成：整体风险等级为"
                    f"「{ {'high': '高', 'medium': '中', 'low': '低'}.get(report.overall_risk_level, report.overall_risk_level) }」，"
                    f"共识别 {summary.get('total_count', 0)} 项风险，处理建议为「{report.recommendation}」。"
                )
                session.slots_json = dump_json(slots)
                db.commit()
                return {
                    "messages": [
                        _assistant_reply(
                            db,
                            session,
                            reply,
                            "report",
                            {"report_id": report.id, "analysis_task_id": task.id, "document_id": doc.id, "overall_risk_level": report.overall_risk_level},
                        )
                    ]
                }
            reply = f"单据 {doc.document_no} 尚未生成分析报告，正在为您发起分析。"
            return _start_analysis(db, session, user, doc, slots, prefix=reply)

    if not slots.get("document_type"):
        session.slots_json = dump_json(slots)
        db.commit()
        reply = (
            "请提供单据类型，可选：对公付款单、预付款单、批量付款单、费用报销单、差旅报销单。"
            "\n例如：「审核对公付款单 GF-202610-0001」。"
        )
        return {
            "messages": [
                _assistant_reply(
                    db,
                    session,
                    reply,
                    "slot_required",
                    {
                        "slot": "document_type",
                        "slot_name": "document_type",
                        "question_text": reply,
                        "candidates": DOCUMENT_TYPES,
                        "candidate_values": DOCUMENT_TYPES,
                    },
                )
            ]
        }

    if not slots.get("document_no"):
        docs = _accessible_documents(db, user)
        available = [doc for doc in docs if doc.document_type == slots["document_type"]][:5]
        session.slots_json = dump_json(slots)
        db.commit()
        reply = f"请提供「{slots['document_type']}」的单据编号，例如 {available[0].document_no if available else 'GF-202610-0001'}。"
        if available:
            reply += "\n当前可访问的单据：" + "、".join(
                f"{doc.document_no}（{STATUS_LABELS.get(doc.document_status, doc.document_status)}）" for doc in available
            )
        return {
            "messages": [
                _assistant_reply(
                    db,
                    session,
                    reply,
                    "slot_required",
                    {
                        "slot": "document_no",
                        "slot_name": "document_no",
                        "question_text": reply,
                        "candidates": [doc.document_no for doc in available],
                        "candidate_values": [doc.document_no for doc in available],
                    },
                )
            ]
        }

    matches, ambiguity = _find_document(db, user, slots["document_no"], slots.get("document_type"))
    if not matches:
        docs = _accessible_documents(db, user)
        available = docs[:5]
        slots["document_no"] = None
        session.document_no = None
        session.slots_json = dump_json(slots)
        db.commit()
        reply = f"未找到单据编号「{slots.get('document_no') or detected_no or content}」，或当前账号无权访问该单据。请重新提供单据编号。"
        if available:
            reply += "\n可访问单据示例：" + "、".join(doc.document_no for doc in available)
        return {
            "messages": [
                _assistant_reply(
                    db,
                    session,
                    reply,
                    "error",
                    {
                        "error_code": "DOCUMENT_NOT_FOUND",
                        "error_message": reply,
                        "candidates": [_doc_brief(db, doc) for doc in available],
                    },
                )
            ]
        }

    if ambiguity or len(matches) > 1:
        candidate_briefs = [_doc_brief(db, doc) for doc in matches[:5]]
        slots["candidates"] = candidate_briefs
        slots["document_no"] = None
        session.document_no = None
        session.slots_json = dump_json(slots)
        db.commit()
        lines = "\n".join(
            f"{index}. {item['document_no']}｜{item['document_type']}｜¥{item['total_amount']:,.2f}｜{item.get('status_label', item['document_status'])}"
            for index, item in enumerate(candidate_briefs, start=1)
        )
        reply = "匹配到多张单据，请确认需要分析的单据（回复序号或单据编号）：\n" + lines
        return {
            "messages": [
                _assistant_reply(
                    db,
                    session,
                    reply,
                    "slot_required",
                    {
                        "slot": "document_confirm",
                        "slot_name": "document_confirm",
                        "question_text": reply,
                        "candidates": candidate_briefs,
                        "candidate_values": [item["document_no"] for item in candidate_briefs],
                    },
                )
            ]
        }

    doc = matches[0]
    if slots.get("document_type") and doc.document_type != slots["document_type"]:
        slots["document_type"] = doc.document_type
        session.document_type = doc.document_type
        session.slots_json = dump_json(slots)
        db.commit()
        reply = f"单据 {doc.document_no} 的实际类型为「{doc.document_type}」，与您提供的信息不一致，已按系统单据类型继续。"
        return _start_analysis(db, session, user, doc, slots, prefix=reply)

    return _start_analysis(db, session, user, doc, slots)


def _resolve_single(db: Session, user: User, slots: dict) -> FinancialDocument | None:
    matches, _ = _find_document(db, user, slots.get("document_no", ""), slots.get("document_type"))
    return matches[0] if len(matches) == 1 else None


def _start_analysis(
    db: Session,
    session: ReviewSession,
    user: User,
    doc: FinancialDocument,
    slots: dict,
    prefix: str | None = None,
) -> dict:
    slots["document_type"] = doc.document_type
    slots["document_no"] = doc.document_no
    slots["candidates"] = []
    session.document_type = doc.document_type
    session.document_no = doc.document_no
    session.slots_json = dump_json(slots)
    db.commit()

    task = create_analysis_task(db, doc, user.id, session_id=session.id)
    applicant = db.get(User, doc.applicant_id)
    reply = (
        (prefix + "\n" if prefix else "")
        + f"已定位单据 {doc.document_no}（{doc.document_type}，申请人 {applicant.display_name if applicant else '-'}，"
        f"金额 ¥{float(doc.total_amount or 0):,.2f}），正在执行附件解析与风险分析。"
        f"\n分析任务 #{task.id} 已启动，完成后可在「风险分析」页面查看风险项、证据与处理建议。"
    )
    return {
        "messages": [
            _assistant_reply(
                db,
                session,
                reply,
                "analysis_started",
                {
                    "analysis_task_id": task.id,
                    "task_id": task.id,
                    "document_id": doc.id,
                    "document_no": doc.document_no,
                    "document_type": doc.document_type,
                    "task_status": task.task_status,
                },
            )
        ],
        "analysis_task": {
            "id": task.id,
            "task_status": task.task_status,
            "current_step": task.current_step,
            "progress": task.progress,
            "document_id": doc.id,
        },
    }
