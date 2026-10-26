"""审核会话与多轮对话接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ReviewSession, User
from app.schemas import MessageIn, SessionCreate
from app.services.chat import create_session, get_session, send_message, session_messages
from app.utils import iso

router = APIRouter(prefix="/api/v1/review-sessions", tags=["智能审核会话"])


@router.post("")
def create(payload: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    session = create_session(db, user, payload.document_type, payload.document_no)
    return {
        "id": session.id,
        "document_type": session.document_type,
        "document_no": session.document_no,
        "session_status": session.session_status,
        "created_at": iso(session.created_at),
        "messages": session_messages(db, session.id),
    }


@router.get("")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(ReviewSession).where(ReviewSession.user_id == user.id).order_by(ReviewSession.id.desc())
    ).scalars().all()
    result = []
    for session in rows:
        last = session_messages(db, session.id)
        result.append(
            {
                "id": session.id,
                "document_type": session.document_type,
                "document_no": session.document_no,
                "session_status": session.session_status,
                "updated_at": iso(session.updated_at),
                "last_message": last[-1]["content"] if last else None,
                "message_count": len(last),
            }
        )
    return result


@router.get("/{session_id}")
def get_one(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    session = get_session(db, session_id, user)
    return {
        "id": session.id,
        "document_type": session.document_type,
        "document_no": session.document_no,
        "session_status": session.session_status,
        "created_at": iso(session.created_at),
        "messages": session_messages(db, session.id),
    }


@router.post("/{session_id}/messages")
def post_message(session_id: int, payload: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    session = get_session(db, session_id, user)
    result = send_message(db, session, user, payload.content)
    return {
        "session_id": session.id,
        "messages": result.get("messages", []),
        "analysis_task": result.get("analysis_task"),
        "slots": {
            "document_type": session.document_type,
            "document_no": session.document_no,
        },
    }


@router.get("/{session_id}/messages")
def get_messages(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    session = get_session(db, session_id, user)
    return session_messages(db, session.id)
