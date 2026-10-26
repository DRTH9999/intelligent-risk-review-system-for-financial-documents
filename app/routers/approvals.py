"""审批任务与流程配置接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_can_view, get_current_user, require_roles
from app.models import (
    AnalysisTask,
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflow,
    ApprovalWorkflowNode,
    FinancialDocument,
    User,
)
from app.schemas import ApprovalAction, WorkflowIn, WorkflowUpdate
from app.services.approval import my_tasks, process_task
from app.services.audit import log_action
from app.services.serializers import (
    analysis_task_to_dict,
    document_to_dict,
    finding_to_dict,
    report_to_dict,
)
from app.services.analysis import compute_amount_comparison, findings_for_task, report_for_task
from app.utils import dump_json, iso, load_json

router = APIRouter(prefix="/api/v1", tags=["审批"])

VALID_ROLES = {"applicant", "approver", "finance", "admin"}


def workflow_to_dict(db: Session, workflow: ApprovalWorkflow) -> dict:
    nodes = db.execute(
        select(ApprovalWorkflowNode)
        .where(ApprovalWorkflowNode.workflow_id == workflow.id)
        .order_by(ApprovalWorkflowNode.node_order)
    ).scalars().all()
    return {
        "id": workflow.id,
        "workflow_name": workflow.workflow_name,
        "document_type": workflow.document_type,
        "match_conditions": load_json(workflow.match_conditions_json, {}),
        "status": workflow.status,
        "created_at": iso(workflow.created_at),
        "updated_at": iso(workflow.updated_at),
        "nodes": [
            {
                "id": node.id,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "approver_role": node.approver_role,
                "approval_mode": node.approval_mode,
            }
            for node in nodes
        ],
    }


def _validate_nodes(nodes: list) -> None:
    if not nodes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="审批流程至少需要一个审批节点")
    orders = [node.node_order for node in nodes]
    if len(set(orders)) != len(orders):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="审批节点顺序不能重复")
    for node in nodes:
        if node.approver_role not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"审批角色 {node.approver_role} 不受支持")


@router.get("/approval-tasks")
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    items = my_tasks(db, user, status_filter)
    counts: dict[str, int] = {}
    for item in my_tasks(db, user):
        counts[item["task_status"]] = counts.get(item["task_status"], 0) + 1
    return {"items": items, "counts": counts}


@router.get("/approval-tasks/{task_id}")
def task_detail(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    task = db.get(ApprovalTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批任务不存在")
    instance = db.get(ApprovalInstance, task.instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批实例不存在")
    document = db.get(FinancialDocument, instance.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="单据不存在")
    assert_can_view(db, user, document)

    data = {
        "task_id": task.id,
        "task_status": task.task_status,
        "node_id": task.node_id,
        "instance_id": instance.id,
        "instance_status": instance.instance_status,
        "analysis_task_id": task.analysis_task_id,
        "review_comment": task.review_comment,
        "created_at": iso(task.created_at),
        "processed_at": iso(task.processed_at),
        "document": document_to_dict(db, document, with_items=True, with_attachments=True, with_approval=True),
    }

    analysis_task_id = task.analysis_task_id
    if analysis_task_id is None:
        latest = db.execute(
            select(AnalysisTask)
            .where(AnalysisTask.document_id == document.id, AnalysisTask.task_status == "succeeded")
            .order_by(AnalysisTask.id.desc())
        ).scalars().first()
        analysis_task_id = latest.id if latest else None
    if analysis_task_id:
        analysis_task = db.get(AnalysisTask, analysis_task_id)
        report = report_for_task(db, analysis_task_id)
        data["analysis_task"] = analysis_task_to_dict(analysis_task) if analysis_task else None
        data["report"] = report_to_dict(db, report) if report else None
        if report:
            data["report"]["risk_summary"] = load_json(report.risk_summary_json, {})
            data["report"]["amount_comparison"] = load_json(report.amount_comparison_json, {})
        data["findings"] = [finding_to_dict(item) for item in findings_for_task(db, analysis_task_id)]
    else:
        data["analysis_task"] = None
        data["report"] = None
        data["findings"] = []
    return data


def _handle_action(task_id: int, action: str, payload: ApprovalAction, user: User, db: Session) -> dict:
    task = db.get(ApprovalTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批任务不存在")
    return process_task(db, task, action, user, payload.comment)


@router.post("/approval-tasks/{task_id}/approve")
def approve(task_id: int, payload: ApprovalAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _handle_action(task_id, "approve", payload, user, db)


@router.post("/approval-tasks/{task_id}/return")
def return_task(task_id: int, payload: ApprovalAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not payload.comment:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="退回单据必须填写审批意见")
    return _handle_action(task_id, "return", payload, user, db)


@router.post("/approval-tasks/{task_id}/reject")
def reject(task_id: int, payload: ApprovalAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not payload.comment:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="驳回单据必须填写审批意见")
    return _handle_action(task_id, "reject", payload, user, db)


@router.get("/approval-workflows")
def list_workflows(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    workflows = db.execute(select(ApprovalWorkflow).order_by(ApprovalWorkflow.id)).scalars().all()
    return [workflow_to_dict(db, workflow) for workflow in workflows]


@router.post("/approval-workflows")
def create_workflow(
    payload: WorkflowIn,
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    _validate_nodes(payload.nodes)
    workflow = ApprovalWorkflow(
        workflow_name=payload.workflow_name,
        document_type=payload.document_type,
        match_conditions_json=dump_json(payload.match_conditions),
        status=payload.status,
    )
    db.add(workflow)
    db.flush()
    for node in payload.nodes:
        db.add(
            ApprovalWorkflowNode(
                workflow_id=workflow.id,
                node_name=node.node_name,
                node_order=node.node_order,
                approver_role=node.approver_role,
                approval_mode=node.approval_mode,
            )
        )
    log_action(db, user.id, "workflow.create", "approval_workflow", workflow.id, {"name": payload.workflow_name})
    db.commit()
    db.refresh(workflow)
    return workflow_to_dict(db, workflow)


@router.patch("/approval-workflows/{workflow_id}")
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    workflow = db.get(ApprovalWorkflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批流程不存在")
    data = payload.model_dump(exclude_unset=True)
    nodes = data.pop("nodes", None)
    if "match_conditions" in data and data["match_conditions"] is not None:
        workflow.match_conditions_json = dump_json(data.pop("match_conditions"))
    for key, value in data.items():
        if value is not None:
            setattr(workflow, key, value)
    if nodes is not None:
        _validate_nodes(payload.nodes or [])
        used = db.execute(
            select(ApprovalInstance.id).where(ApprovalInstance.workflow_id == workflow.id)
        ).first()
        if used:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该流程已被审批实例引用，无法重建审批节点，请新建流程")
        for node in db.execute(
            select(ApprovalWorkflowNode).where(ApprovalWorkflowNode.workflow_id == workflow.id)
        ).scalars().all():
            db.delete(node)
        db.flush()
        for node in payload.nodes or []:
            db.add(
                ApprovalWorkflowNode(
                    workflow_id=workflow.id,
                    node_name=node.node_name,
                    node_order=node.node_order,
                    approver_role=node.approver_role,
                    approval_mode=node.approval_mode,
                )
            )
    log_action(db, user.id, "workflow.update", "approval_workflow", workflow.id, {"name": workflow.workflow_name})
    db.commit()
    db.refresh(workflow)
    return workflow_to_dict(db, workflow)
