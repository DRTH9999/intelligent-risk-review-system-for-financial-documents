"""审批流程：流程匹配、实例创建、节点流转与审批任务处理。"""
from __future__ import annotations

from fastapi import HTTPException, status as http_status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflow,
    ApprovalWorkflowNode,
    FinancialDocument,
    ReviewReport,
    User,
    UserRole,
    Role,
    AnalysisTask, ManualReview, RiskFinding,
)
from app.services.audit import log_action
from app.services.documents import log_status
from app.utils import iso, load_json, now


def assign_user_for_role(db: Session, role_code: str, applicant_id: int | None = None) -> int | None:
    user_id = db.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.role_code == role_code, User.status == "active", User.id != applicant_id if applicant_id is not None else True)
        .order_by(User.id)
    ).scalars().first()
    return user_id


def workflow_nodes(db: Session, workflow_id: int) -> list[ApprovalWorkflowNode]:
    return db.execute(
        select(ApprovalWorkflowNode)
        .where(ApprovalWorkflowNode.workflow_id == workflow_id)
        .order_by(ApprovalWorkflowNode.node_order)
    ).scalars().all()


def match_workflow(db: Session, doc: FinancialDocument) -> tuple[ApprovalWorkflow, list[ApprovalWorkflowNode]]:
    workflows = db.execute(
        select(ApprovalWorkflow).where(
            ApprovalWorkflow.document_type == doc.document_type,
            ApprovalWorkflow.status == "active",
        )
    ).scalars().all()

    amount = float(doc.total_amount or 0)
    candidates: list[tuple[int, float, ApprovalWorkflow]] = []
    for workflow in workflows:
        conditions = load_json(workflow.match_conditions_json, {}) or {}
        amount_min = float(conditions.get("amount_min", 0) or 0)
        amount_max = conditions.get("amount_max")
        if amount < amount_min:
            continue
        if amount_max is not None and amount > float(amount_max):
            continue
        departments = conditions.get("departments") or []
        if departments and doc.budget_department not in departments:
            continue
        specificity = len([key for key in ("amount_min", "amount_max", "departments") if key in conditions])
        span = float(amount_max) - amount_min if amount_max is not None else 10**12
        candidates.append((specificity, -span, workflow))

    if not candidates:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"未找到适用于「{doc.document_type}」且金额为 {amount:,.2f} 的审批流程，请先在流程配置中维护",
        )
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    workflow = candidates[0][2]
    nodes = workflow_nodes(db, workflow.id)
    if not nodes:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="审批流程未配置审批节点")
    return workflow, nodes


def start_approval(db: Session, doc: FinancialDocument, user_id: int) -> tuple[ApprovalInstance, ApprovalTask]:
    workflow, nodes = match_workflow(db, doc)
    first_node = nodes[0]
    instance = ApprovalInstance(
        workflow_id=workflow.id,
        document_id=doc.id,
        document_version=doc.current_version,
        instance_status="running",
        current_node_id=first_node.id,
    )
    db.add(instance)
    db.flush()

    approver_id = assign_user_for_role(db, first_node.approver_role, doc.applicant_id)
    if approver_id is None:
        raise HTTPException(409, '当前节点没有可用审批人员（申请人不能审批本人单据），请联系管理员')
    task = ApprovalTask(
        instance_id=instance.id,
        node_id=first_node.id,
        approver_id=approver_id,
        task_status="pending",
    )
    db.add(task)
    db.flush()
    log_action(
        db,
        user_id,
        "approval.start",
        "approval_instance",
        instance.id,
        {"document_id": doc.id, "workflow": workflow.workflow_name, "first_node": first_node.node_name},
    )
    return instance, task


def _next_node(db: Session, instance: ApprovalInstance, current_node: ApprovalWorkflowNode) -> ApprovalWorkflowNode | None:
    return db.execute(
        select(ApprovalWorkflowNode)
        .where(
            ApprovalWorkflowNode.workflow_id == instance.workflow_id,
            ApprovalWorkflowNode.node_order > current_node.node_order,
        )
        .order_by(ApprovalWorkflowNode.node_order)
    ).scalars().first()


def _user_roles(db: Session, user_id: int) -> set[str]:
    rows = db.execute(
        select(Role.role_code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).scalars().all()
    return set(rows)


def process_task(db: Session, task: ApprovalTask, action: str, user: User, comment: str | None = None) -> dict:
    if action not in {'approve', 'return', 'reject'}:
        raise HTTPException(400, '不支持的审批动作')
    if not comment or len(comment.strip()) < 2:
        raise HTTPException(422, '请填写至少2个字的审批意见')
    if task.task_status != "pending":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="该审批任务已处理")

    instance = db.get(ApprovalInstance, task.instance_id)
    if instance is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="审批实例不存在")
    if instance.instance_status != 'running' or instance.current_node_id != task.node_id:
        raise HTTPException(409, '审批实例已结束或该任务不是当前节点')
    node = db.get(ApprovalWorkflowNode, task.node_id)
    if node is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="审批节点不存在")

    roles = _user_roles(db, user.id)
    if task.approver_id is not None and task.approver_id != user.id and "admin" not in roles:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="该审批任务不属于当前用户")
    if task.approver_id is None and node.approver_role not in roles and "admin" not in roles:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="当前角色无权处理该审批节点")

    document = db.get(FinancialDocument, instance.document_id)
    if document is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="单据不存在")
    if user.id == document.applicant_id:
        raise HTTPException(403, '不能审批本人申请的单据')
    if document.document_status not in {'pending_review', 'reviewing'} or document.current_version != instance.document_version:
        raise HTTPException(409, '审批任务与当前单据状态或版本不一致')
    if node.approver_role not in roles and 'admin' not in roles:
        raise HTTPException(403, '当前用户已不具备此节点要求的审批角色')
    latest = db.scalars(select(AnalysisTask).where(AnalysisTask.document_id == document.id,
        AnalysisTask.document_version == instance.document_version).order_by(AnalysisTask.id.desc())).first()
    if action == 'approve':
        if latest is None or latest.task_status != 'succeeded':
            raise HTTPException(409, '请先完成当前版本的风险分析，再通过审批')
        report = db.scalars(select(ReviewReport).where(ReviewReport.task_id == latest.id)).first()
        if report is None or report.snapshot_status != 'complete':
            raise HTTPException(409, '当前分析报告缺少完整版本依据，请重新分析')
        if not load_json(report.risk_summary_json, {}).get('enabled_rules'):
            raise HTTPException(409, '当前分析没有启用审核规则，请配置规则后重新分析')
        if report.overall_risk_level == 'high':
            unresolved = db.scalar(select(RiskFinding.id).where(RiskFinding.task_id == latest.id,
                RiskFinding.risk_level == 'high', RiskFinding.review_status == 'pending'))
            review = db.scalars(select(ManualReview).where(ManualReview.report_id == report.id).order_by(ManualReview.id.desc())).first()
            if unresolved or review is None or review.review_result not in {'建议通过', '通过'}:
                raise HTTPException(409, '高风险单据需先处理所有高风险项，并填写建议通过的人工复核意见')
    claimed = db.execute(update(ApprovalTask).where(ApprovalTask.id == task.id,
        ApprovalTask.task_status == 'pending').values(task_status={'approve':'approved','return':'returned','reject':'rejected'}[action]))
    if not claimed.rowcount:
        raise HTTPException(409, '该审批任务已被其他操作处理，请刷新')

    task.review_comment = comment
    task.processed_at = now()
    task.approver_id = user.id

    if action == "approve":
        task.task_status = "approved"
        nxt = _next_node(db, instance, node)
        if nxt is not None:
            instance.current_node_id = nxt.id
            instance.instance_status = "running"
            next_task = ApprovalTask(
                instance_id=instance.id,
                node_id=nxt.id,
                approver_id=assign_user_for_role(db, nxt.approver_role, document.applicant_id),
                analysis_task_id=latest.id,
                task_status="pending",
            )
            if next_task.approver_id is None:
                raise HTTPException(409, '下一节点没有可用审批人员，请联系管理员配置')
            db.add(next_task)
            log_status(db, document, document.document_status, "reviewing", user.id, f"节点「{node.node_name}」审批通过，流转至「{nxt.node_name}」")
            document.document_status = "reviewing"
            result_status = "pending"
        else:
            instance.instance_status = "approved"
            instance.finished_at = now()
            log_status(db, document, document.document_status, "approved", user.id, "全部审批节点通过")
            document.document_status = "approved"
            result_status = "approved"
    elif action == "return":
        task.task_status = "returned"
        instance.instance_status = "returned"
        instance.finished_at = now()
        log_status(db, document, document.document_status, "returned", user.id, comment or "审批退回修改")
        document.document_status = "returned"
        result_status = "returned"
    elif action == "reject":
        task.task_status = "rejected"
        instance.instance_status = "rejected"
        instance.finished_at = now()
        log_status(db, document, document.document_status, "rejected", user.id, comment or "审批驳回")
        document.document_status = "rejected"
        result_status = "rejected"
    else:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="不支持的审批动作")

    if action != 'approve':
        from app.services.analysis import cancel_tasks
        cancel_tasks(db, document.id, '审批已退回或驳回')
    if action != "approve" or instance.instance_status in {"returned", "rejected", "approved"}:
        pending_tasks = db.execute(
            select(ApprovalTask).where(ApprovalTask.instance_id == instance.id, ApprovalTask.task_status == "pending")
        ).scalars().all()
        for pending in pending_tasks:
            pending.task_status = "cancelled"

    log_action(
        db,
        user.id,
        f"approval.{action}",
        "approval_task",
        task.id,
        {"document_id": document.id, "node": node.node_name, "comment": comment, "result": result_status},
    )
    db.commit()
    return {
        "task_id": task.id,
        "task_status": task.task_status,
        "instance_status": instance.instance_status,
        "document_status": document.document_status,
        "node_name": node.node_name,
        "processed_at": iso(task.processed_at),
    }


def my_tasks(db: Session, user: User, status_filter: str | None = None) -> list[dict]:
    roles = _user_roles(db, user.id)
    query = (
        select(ApprovalTask, ApprovalInstance, FinancialDocument, ApprovalWorkflowNode)
        .join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id)
        .join(FinancialDocument, FinancialDocument.id == ApprovalInstance.document_id)
        .join(ApprovalWorkflowNode, ApprovalWorkflowNode.id == ApprovalTask.node_id)
        .order_by(ApprovalTask.id.desc())
    )
    rows = db.execute(query).all()
    result = []
    for task, instance, document, node in rows:
        if task.approver_id is not None:
            if task.approver_id != user.id:
                continue
        elif node.approver_role not in roles:
            continue
        if status_filter and task.task_status != status_filter:
            continue
        applicant = db.get(User, document.applicant_id)
        report = db.execute(
            select(ReviewReport)
            .where(ReviewReport.document_id == document.id)
            .order_by(ReviewReport.id.desc())
        ).scalars().first()
        result.append(
            {
                "task_id": task.id,
                "task_status": task.task_status,
                "node_name": node.node_name,
                "instance_id": instance.id,
                "document_id": document.id,
                "document_no": document.document_no,
                "document_type": document.document_type,
                "applicant_name": applicant.display_name if applicant else None,
                "budget_department": document.budget_department,
                "total_amount": float(document.total_amount or 0),
                "document_status": document.document_status,
                "analysis_task_id": task.analysis_task_id,
                "risk_level": report.overall_risk_level if report else None,
                "recommendation": report.recommendation if report else None,
                "review_comment": task.review_comment,
                "created_at": iso(task.created_at),
                "processed_at": iso(task.processed_at),
            }
        )
    return result
