from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models import (AnalysisTask, ApprovalTask, DocumentLineItem, DocumentVersion, ManualReview,
                        ReviewReport, ReviewRule, RiskFinding, User)
from app.schemas import DocumentCreate, DocumentUpdate, LineItemIn
from app.services.analysis import create_analysis_task, run_analysis_task
from app.services.approval import process_task
from app.services.documents import submit_document, update_document, validate_submit, withdraw_document
from app.services.rules import evaluate_document, load_rule_configs
from app.utils import load_json, now


def analyze(db, document, owner):
    _, task = submit_document(db, document, owner)
    run_analysis_task(task.id)
    db.expire_all()
    assert db.get(AnalysisTask, task.id).task_status == 'succeeded', db.get(AnalysisTask, task.id).error_message
    return db.scalars(select(ReviewReport).where(ReviewReport.task_id == task.id)).one()


@pytest.mark.parametrize('field,value', [('quantity',-1),('quantity',0),('unit_price',-1),('amount',-1),('amount','NaN'),('amount','Infinity')])
def test_invalid_line_values(field, value):
    values = dict(item_name='测试明细',quantity=1,unit_price='1.00',amount='1.00')
    values[field] = value
    with pytest.raises(ValidationError): LineItemIn(**values)


@pytest.mark.parametrize('ratio', [0,-10,101,500])
def test_invalid_payment_ratio(ratio):
    with pytest.raises(ValidationError):
        DocumentCreate(document_type='预付款单',applicant_department='市场部',budget_department='市场部',payment_ratio=ratio)


def test_disabled_rule_is_not_evaluated(db, document_factory):
    doc, _ = document_factory()
    doc.total_amount = Decimal('200');db.commit()
    rule = db.scalars(select(ReviewRule).where(ReviewRule.rule_code == 'line_item_tolerance')).one()
    assert 'LINE_ITEM_MISMATCH' in {finding['risk_type'] for finding in evaluate_document(db,doc)}
    rule.status='inactive';db.commit()
    assert 'line_item_tolerance' not in load_rule_configs(db, doc.document_type)
    assert 'LINE_ITEM_MISMATCH' not in {finding['risk_type'] for finding in evaluate_document(db,doc)}


def test_submission_requires_matching_lines_and_invoice(db, document_factory):
    doc, _ = document_factory(with_attachment=False)
    db.scalars(select(DocumentLineItem).where(DocumentLineItem.document_id==doc.id)).one().amount=Decimal('1')
    db.commit()
    errors=validate_submit(db,doc)
    assert any('明细合计' in error for error in errors)
    assert any('发票' in error for error in errors)


def test_old_report_and_export_are_frozen(db,client,headers,document_factory):
    doc,owner=document_factory()
    report=analyze(db,doc,owner)
    report_id=report.id
    reviewer=db.scalars(select(User).where(User.username=='lina')).one()
    task=db.scalars(select(ApprovalTask).where(ApprovalTask.task_status=='pending')).one()
    process_task(db,task,'return',reviewer,'补充采购说明')
    update_document(db,doc,DocumentUpdate(total_amount='200.00'))
    response=client.get(f'/api/v1/review-reports/{report_id}',headers=headers())
    assert response.status_code==200,response.text
    assert response.json()['document']['total_amount']==100
    assert response.json()['amount_comparison']['document_total']==100
    task_response=client.get(f'/api/v1/analysis-tasks/{report.task_id}/report',headers=headers())
    assert task_response.json()['document']['total_amount']==100
    exported=client.get(f'/api/v1/review-reports/{report_id}/export',headers=headers()).text
    assert '¥100.00' in exported and '¥200.00' not in exported


def test_owner_is_never_assigned_as_approver(db,document_factory):
    doc,owner=document_factory(username='lina')
    _,analysis=submit_document(db,doc,owner)
    task=db.scalars(select(ApprovalTask).where(ApprovalTask.task_status=='pending')).one()
    assert task.approver_id != owner.id
    task.approver_id=owner.id;db.commit()
    with pytest.raises(HTTPException) as error:
        process_task(db,task,'approve',owner,'我自己确认')
    assert error.value.status_code==403


def test_approval_waits_for_analysis_and_is_not_repeatable(db,document_factory):
    doc,owner=document_factory()
    _,analysis=submit_document(db,doc,owner)
    reviewer=db.scalars(select(User).where(User.username=='lina')).one()
    task=db.scalars(select(ApprovalTask).where(ApprovalTask.task_status=='pending')).one()
    with pytest.raises(HTTPException) as error:
        process_task(db,task,'approve',reviewer,'已核对材料')
    assert error.value.status_code==409
    run_analysis_task(analysis.id);db.expire_all()
    result=process_task(db,task,'approve',reviewer,'已核对材料')
    assert result['document_status']=='approved'
    with pytest.raises(HTTPException) as error: process_task(db,task,'approve',reviewer,'重复通过')
    assert error.value.status_code==409


def test_high_risk_requires_review_and_finding_disposition(db,document_factory):
    doc,owner=document_factory(invoice='50.00')
    report=analyze(db,doc,owner)
    assert report.overall_risk_level=='high'
    reviewer=db.scalars(select(User).where(User.username=='lina')).one()
    task=db.scalars(select(ApprovalTask).where(ApprovalTask.task_status=='pending')).one()
    with pytest.raises(HTTPException) as error: process_task(db,task,'approve',reviewer,'确认业务真实')
    assert error.value.status_code==409
    for finding in db.scalars(select(RiskFinding).where(RiskFinding.task_id==report.task_id)):
        finding.review_status='confirmed'
    db.add(ManualReview(report_id=report.id,reviewer_id=reviewer.id,review_result='建议通过',review_comment='已核实差异并附业务说明'));db.commit()
    assert process_task(db,task,'approve',reviewer,'依据复核意见通过')['document_status']=='approved'


def test_duplicate_queue_and_cancelled_worker(db,document_factory):
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    same=create_analysis_task(db,doc,owner.id)
    assert same.id==task.id
    withdraw_document(db,doc,owner)
    run_analysis_task(task.id);db.expire_all()
    assert db.get(AnalysisTask,task.id).task_status=='cancelled'
    assert db.scalar(select(ReviewReport.id).where(ReviewReport.task_id==task.id)) is None


def test_recovery_fails_stale_tasks_but_preserves_queue(db,document_factory):
    from app.services.jobs import recover_interrupted
    doc,owner=document_factory()
    _,task=submit_document(db,doc,owner)
    assert recover_interrupted(db,180)==0
    task.task_status='parsing_attachments';task.heartbeat_at=now()-timedelta(seconds=181);db.commit()
    assert recover_interrupted(db,180)==1
    db.refresh(task)
    assert task.task_status=='failed'


def test_resubmission_preserves_original_version(db,document_factory):
    doc,owner=document_factory()
    report=analyze(db,doc,owner)
    reviewer=db.scalars(select(User).where(User.username=='lina')).one()
    task=db.scalars(select(ApprovalTask).where(ApprovalTask.task_status=='pending')).one()
    process_task(db,task,'return',reviewer,'请补充业务说明')
    update_document(db,doc,DocumentUpdate(reason_text='补充后的业务事由'))
    _,new_task=submit_document(db,doc,owner)
    assert new_task.document_version==2
    versions=db.scalars(select(DocumentVersion).order_by(DocumentVersion.version_no)).all()
    assert len(versions)==2
    assert load_json(versions[0].document_snapshot_json)['reason_text']=='项目资料采购'


def test_stale_editor_is_rejected(db,document_factory):
    doc,_=document_factory()
    revision=doc.revision
    update_document(db,doc,DocumentUpdate(reason_text='第一次修改',revision=revision))
    with pytest.raises(HTTPException) as error:
        update_document(db,doc,DocumentUpdate(reason_text='旧页面的修改',revision=revision))
    assert error.value.status_code==409
