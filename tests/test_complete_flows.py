from datetime import date

import pytest
from sqlalchemy import select

from app.models import AnalysisTask, ApprovalTask, FinancialDocument, ReviewReport, ReviewRule, RiskFinding, User
from app.schemas import DocumentUpdate
from app.services.analysis import create_analysis_task, run_analysis_task
from app.services.approval import process_task
from app.services.documents import submit_document, update_document
from app.utils import load_json


@pytest.mark.parametrize('document_type',['费用报销单','差旅报销单','对公付款单','预付款单','批量付款单'])
def test_five_types_create_analyze_approve_export(db,client,headers,document_factory,attachment_factory,document_type):
    extra={'document_type':document_type}
    if document_type in {'对公付款单','预付款单'}:
        extra.update(contract_no='HT-2026-001',supplier_name='测试供应商',payment_ratio=100,
            payment_terms='验收后付款',planned_payment_date=date(2026,10,21),payee_account='622202012345')
    if document_type=='差旅报销单':
        extra.update(travel_start_date=date(2026,10,20),travel_end_date=date(2026,10,21),travel_location='北京')
    if document_type=='批量付款单':
        extra.update(batch_total_amount='100.00',batch_payment_count=1,line_items=[dict(item_type='payout',
            item_name='项目付款',quantity=1,unit_price='100.00',amount='100.00',payee_name='测试供应商',payee_account='622202012345')])
    doc,owner=document_factory(**extra)
    if document_type in {'对公付款单','预付款单'}:
        attachment_factory(doc,owner,['采购合同','合同编号：HT-2026-001','合同金额：100.00','乙方：测试供应商','付款比例：100%'])
    if document_type=='差旅报销单':
        attachment_factory(doc,owner,['出差行程单','出差地点：北京','出差起止：2026年10月20日至2026年10月21日'])
    if document_type=='批量付款单':
        attachment_factory(doc,owner,['银行转账回单','收款单位：测试供应商','收款账号：622202012345','付款金额：100.00'])
    instance,analysis=submit_document(db,doc,owner)
    run_analysis_task(analysis.id);db.expire_all()
    analysis=db.get(AnalysisTask,analysis.id)
    assert analysis.task_status=='succeeded',analysis.error_message
    report=db.scalars(select(ReviewReport).where(ReviewReport.task_id==analysis.id)).one()
    assert report.snapshot_status=='complete'
    while True:
        task=db.scalars(select(ApprovalTask).where(ApprovalTask.instance_id==instance.id,ApprovalTask.task_status=='pending')).first()
        if task is None: break
        assert process_task(db,task,'approve',db.get(User,task.approver_id),'逐项核对原始材料')['task_status']=='approved'
    assert db.get(FinancialDocument,doc.id).document_status=='approved'
    response=client.get(f'/api/v1/review-reports/{report.id}/export?format=html',headers=headers())
    assert response.status_code==200 and doc.document_no in response.text


def test_rules_and_reference_inputs_remain_frozen(db,document_factory):
    doc,owner=document_factory(invoice='50.00')
    _,task=submit_document(db,doc,owner)
    rule=db.scalars(select(ReviewRule).where(ReviewRule.rule_code=='amount_tolerance')).one()
    rule.status='inactive';db.commit()
    run_analysis_task(task.id);db.expire_all()
    assert db.scalar(select(RiskFinding.id).where(RiskFinding.task_id==task.id,RiskFinding.risk_type=='AMOUNT_MISMATCH'))
    assert 'amount_tolerance' in load_json(db.get(AnalysisTask,task.id).input_snapshot_json)['rules']


def test_atomic_save_includes_details_and_rejects_stale_page(db,client,headers,document_factory):
    doc,_=document_factory()
    response=client.patch(f'/api/v1/documents/{doc.id}',headers=headers(),json={'revision':doc.revision,'total_amount':'250.00',
        'line_items':[{'item_name':'新明细','quantity':'2','unit_price':'125.00','amount':'250.00'}]})
    assert response.status_code==200,response.text
    detail=client.get(f'/api/v1/documents/{doc.id}',headers=headers()).json()
    assert detail['total_amount']==detail['line_items_total']==250
    assert len(detail['line_items'])==1 and detail['line_items'][0]['item_name']=='新明细'
    stale=client.patch(f'/api/v1/documents/{doc.id}',headers=headers(),json={'revision':doc.revision,'total_amount':'1.00'})
    assert stale.status_code==409


def test_reports_and_attachments_enforce_document_scope(db,client,headers,document_factory):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner);run_analysis_task(task.id)
    report=db.scalars(select(ReviewReport).where(ReviewReport.task_id==task.id)).one()
    from app.models import DocumentAttachment
    attachment=db.scalars(select(DocumentAttachment).where(DocumentAttachment.document_id==doc.id)).one()
    stranger=headers('chenchen')
    assert client.get(f'/api/v1/review-reports/{report.id}',headers=stranger).status_code==403
    assert client.get(f'/api/v1/review-reports/{report.id}/export',headers=stranger).status_code==403
    assert client.get(f'/api/v1/documents/{doc.id}/attachments/{attachment.id}',headers=stranger).status_code==403


def test_historical_evidence_survives_reparse_and_removal(db,client,headers,document_factory):
    from app.models import DocumentAttachment,AttachmentParseResult
    from app.utils import dump_json
    doc,owner=document_factory()
    instance,task=submit_document(db,doc,owner);run_analysis_task(task.id);db.expire_all()
    approval=db.scalars(select(ApprovalTask).where(ApprovalTask.instance_id==instance.id)).one()
    process_task(db,approval,'return',db.get(User,approval.approver_id),'请补充资料')
    attachment=db.scalars(select(DocumentAttachment).where(DocumentAttachment.document_id==doc.id)).one()
    original=db.scalars(select(AttachmentParseResult).where(AttachmentParseResult.attachment_id==attachment.id)).first()
    original_fields=load_json(original.fields_json)
    db.add(AttachmentParseResult(attachment_id=attachment.id,document_category='invoice',full_text='新的识别结果',
        fields_json=dump_json({'invoice_total':999}),confidence=.99));db.commit()
    response=client.get(f'/api/v1/documents/{doc.id}/attachments/{attachment.id}/parse-result?task_id={task.id}',headers=headers())
    assert response.status_code==200,response.text
    assert response.json()['parse_result']['fields']==original_fields
    assert client.delete(f'/api/v1/documents/{doc.id}/attachments/{attachment.id}',headers=headers()).status_code==200
    assert attachment.file_path
    assert client.get(f'/api/v1/documents/{doc.id}/attachments/{attachment.id}',headers=headers()).status_code==200
    assert client.get(f'/api/v1/documents/{doc.id}',headers=headers()).json()['attachments']==[]


def test_invalid_file_and_reference_price_are_rejected(client,headers,document_factory):
    doc,_=document_factory(with_attachment=False)
    fake=client.post(f'/api/v1/documents/{doc.id}/attachments',headers=headers(),
        files={'file':('disguised.pdf',b'not a PDF','application/pdf')})
    assert fake.status_code==422
    price=client.post('/api/v1/market-prices',headers=headers('wangfang'),json={
        'item_name':'测试报价','price_min':0,'price_max':0,'source_name':'测试来源'})
    assert price.status_code==422


def test_partial_date_update_is_validated_after_merge(db,client,headers,document_factory):
    doc,_=document_factory(document_type='差旅报销单',travel_start_date=date(2026,10,20),travel_end_date=date(2026,10,21))
    result=client.patch(f'/api/v1/documents/{doc.id}',headers=headers(),json={'travel_start_date':'2026-10-22'})
    assert result.status_code==422
    db.refresh(doc)
    assert doc.travel_start_date==date(2026,10,20)


def test_invalid_rule_config_does_not_replace_existing_rule(db,client,headers):
    rule=db.scalars(select(ReviewRule).where(ReviewRule.rule_code=='amount_tolerance')).one()
    before=rule.config_json
    response=client.patch(f'/api/v1/rules/{rule.id}',headers=headers('wangfang'),json={'config':{'abs_tolerance':-1}})
    assert response.status_code==422
    db.refresh(rule)
    assert rule.config_json==before


def test_suppliers_do_not_expose_other_applicants_payments(db,client,headers,document_factory):
    from app.models import SupplierProfile
    supplier=db.scalars(select(SupplierProfile).where(SupplierProfile.supplier_code=='SUP-001')).one()
    doc,_=document_factory(supplier_code=supplier.supplier_code,payee_name=supplier.supplier_name)
    outsider=client.get(f'/api/v1/suppliers/{supplier.supplier_code}/risks',headers=headers('chenchen'))
    assert outsider.status_code==404
    own=client.get(f'/api/v1/suppliers/{supplier.supplier_code}/risks',headers=headers())
    assert own.status_code==200 and own.json()['payment_count']==1


def test_admin_edits_record_actual_operator(db,client,headers,document_factory):
    from app.models import AuditLog
    doc,_=document_factory()
    response=client.patch(f'/api/v1/documents/{doc.id}',headers=headers('admin'),json={'revision':doc.revision,'reason_text':'管理员核对并补充说明'})
    assert response.status_code==200,response.text
    action=db.scalars(select(AuditLog).where(AuditLog.action_type=='document.update').order_by(AuditLog.id.desc())).first()
    assert db.get(User,action.user_id).username=='admin'
