"""所有测试强制使用临时数据库和附件目录，不连接业务数据。"""
import atexit
import os
from pathlib import Path
import tempfile

import pytest

_temporary = tempfile.TemporaryDirectory(prefix='financial-review-tests-')
_root = Path(_temporary.name)
os.environ['RISK_REVIEW_DATA_DIR'] = str(_root / 'data')
os.environ['RISK_REVIEW_STORAGE_DIR'] = str(_root / 'storage')
os.environ['RISK_REVIEW_DATABASE_URL'] = 'sqlite:///' + (_root / 'tests.db').as_posix()
os.environ['RISK_REVIEW_WORKER_ENABLED'] = 'false'

from app.database import Base, engine, SessionLocal
from app.main import app
from app.seed import ensure_base_data


def _cleanup():
    engine.dispose()
    _temporary.cleanup()


atexit.register(_cleanup)


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    ensure_base_data(session)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture
def headers(client):
    def login(username='zhangwei'):
        response = client.post('/api/v1/auth/login', json={'username': username,
            'password': 'Admin@123' if username == 'admin' else 'User@123'})
        assert response.status_code == 200, response.text
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    return login


@pytest.fixture
def document_factory(db):
    from datetime import date
    from sqlalchemy import select
    from app.models import User, DocumentAttachment
    from app.schemas import DocumentCreate
    from app.services.documents import create_document
    from app.services.parsing import parse_attachment_sync
    from app.config import ATTACHMENT_DIR
    import hashlib
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    def create(username='zhangwei', total='100.00', invoice='100.00', with_attachment=True, **changes):
        owner = db.scalars(select(User).where(User.username == username)).one()
        values = dict(document_type='费用报销单', applicant_department='市场部', budget_department='市场部',
            payee_name='测试供应商', expense_category='办公用品', total_amount=total, reason_text='项目资料采购',
            apply_date=date(2026, 10, 21), line_items=[dict(item_type='expense',item_name='办公用品',quantity=1,unit_price=total,amount=total)])
        values.update(changes)
        doc = create_document(db, owner, DocumentCreate(**values))
        if with_attachment:
            path = ATTACHMENT_DIR / f'test-{doc.id}.pdf'
            pdf = canvas.Canvas(str(path));pdf.setFont('STSong-Light',12)
            for index, text in enumerate(['增值税发票',f'发票号码：{doc.id:08d}', '销售方名称：测试供应商',
                '购买方名称：云启科技（上海）有限公司','开票日期：2026年10月21日',f'价税合计：{invoice}']):
                pdf.drawString(50, 750-index*30, text)
            pdf.save()
            attachment = DocumentAttachment(document_id=doc.id, document_version=1, file_name=path.name,
                file_type='pdf', file_size=path.stat().st_size, file_path=str(path),
                file_hash=hashlib.sha256(path.read_bytes()).hexdigest(), storage_status='stored',parse_status='pending',uploaded_by=owner.id)
            db.add(attachment);db.commit()
            parse_attachment_sync(db, attachment)
        return doc, owner
    return create


@pytest.fixture
def attachment_factory(db):
    from reportlab.pdfgen import canvas
    from app.config import ATTACHMENT_DIR
    from app.models import DocumentAttachment
    from app.services.parsing import parse_attachment_sync
    import hashlib
    import secrets
    def create(doc, owner, lines):
        path=ATTACHMENT_DIR / (secrets.token_hex(8)+'.pdf')
        pdf=canvas.Canvas(str(path));pdf.setFont('STSong-Light',12)
        for index,text in enumerate(lines): pdf.drawString(50,750-index*30,text)
        pdf.save()
        attachment=DocumentAttachment(document_id=doc.id,document_version=doc.current_version,file_name=path.name,
            file_type='pdf',file_size=path.stat().st_size,file_path=str(path),file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
            uploaded_by=owner.id,storage_status='stored',parse_status='pending')
        db.add(attachment);db.commit();parse_attachment_sync(db,attachment)
        return attachment
    return create
