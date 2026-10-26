"""系统全部数据表定义。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


# ---------------------------------------------------------------- 认证与权限
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    department: Mapped[str | None] = mapped_column(String(64))
    job_level: Mapped[str | None] = mapped_column(String(32))
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permission_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    permission_name: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


# ---------------------------------------------------------------- 审核会话
class ReviewSession(Base, TimestampMixin):
    __tablename__ = "review_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    document_type: Mapped[str | None] = mapped_column(String(32))
    document_no: Mapped[str | None] = mapped_column(String(64))
    session_status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    slots_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class SessionMessage(Base):
    __tablename__ = "session_messages"
    __table_args__ = (Index("ix_session_messages_session", "session_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


# ---------------------------------------------------------------- 单据
class FinancialDocument(Base, TimestampMixin):
    __tablename__ = "financial_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    document_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    applicant_department: Mapped[str] = mapped_column(String(64), nullable=False)
    budget_department: Mapped[str] = mapped_column(String(64), nullable=False)
    payee_name: Mapped[str | None] = mapped_column(String(128))
    payee_account: Mapped[str | None] = mapped_column(String(64))
    expense_category: Mapped[str | None] = mapped_column(String(64))
    total_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    apply_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason_text: Mapped[str | None] = mapped_column(Text)
    document_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": revision}

    contract_no: Mapped[str | None] = mapped_column(String(64))
    supplier_name: Mapped[str | None] = mapped_column(String(128))
    supplier_code: Mapped[str | None] = mapped_column(String(32), index=True)
    payment_ratio: Mapped[float | None] = mapped_column(Float)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    planned_payment_date: Mapped[date | None] = mapped_column(Date)
    batch_total_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    batch_payment_count: Mapped[int | None] = mapped_column(Integer)
    travel_location: Mapped[str | None] = mapped_column(String(128))
    travel_start_date: Mapped[date | None] = mapped_column(Date)
    travel_end_date: Mapped[date | None] = mapped_column(Date)

    ext_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    document_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class DocumentLineItem(Base):
    __tablename__ = "document_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(32), default="expense", nullable=False)
    item_name: Mapped[str] = mapped_column(String(128), nullable=False)
    item_spec: Mapped[str | None] = mapped_column(String(128))
    expense_category: Mapped[str | None] = mapped_column(String(64))
    expense_date: Mapped[date | None] = mapped_column(Date)
    expense_location: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    payee_name: Mapped[str | None] = mapped_column(String(128))
    payee_account: Mapped[str | None] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class DocumentAttachment(Base):
    __tablename__ = "document_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_status: Mapped[str] = mapped_column(String(16), default="stored", nullable=False)
    parse_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AttachmentParseResult(Base):
    __tablename__ = "attachment_parse_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("document_attachments.id", ondelete="CASCADE"), nullable=False, index=True)
    document_category: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    full_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    page_text_json: Mapped[str | None] = mapped_column(Text)
    fields_json: Mapped[str | None] = mapped_column(Text)
    evidence_positions_json: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    parser_source: Mapped[str] = mapped_column(String(32), default="pypdf", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("document_attachments.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_code: Mapped[str | None] = mapped_column(String(32))
    invoice_no: Mapped[str | None] = mapped_column(String(32), index=True)
    seller_name: Mapped[str | None] = mapped_column(String(128))
    buyer_name: Mapped[str | None] = mapped_column(String(128))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    amount_excluding_tax: Mapped[float | None] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    amount_including_tax: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


# ---------------------------------------------------------------- 审批
class ApprovalWorkflow(Base, TimestampMixin):
    __tablename__ = "approval_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    match_conditions_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class ApprovalWorkflowNode(Base):
    __tablename__ = "approval_workflow_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    node_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_mode: Mapped[str] = mapped_column(String(16), default="single", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("approval_workflows.id"), nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    instance_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    current_node_id: Mapped[int | None] = mapped_column(ForeignKey("approval_workflow_nodes.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("approval_workflow_nodes.id"), nullable=False)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    task_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    review_comment: Mapped[str | None] = mapped_column(Text)
    analysis_task_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)


class DocumentStatusLog(Base):
    __tablename__ = "document_status_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


# ---------------------------------------------------------------- 分析
class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (Index('uq_analysis_active_version', 'document_id', 'document_version', unique=True,
        sqlite_where=text("task_status IN ('queued','querying_document','loading_attachments','parsing_attachments','analyzing','generating_report')"),
        postgresql_where=text("task_status IN ('queued','querying_document','loading_attachments','parsing_attachments','analyzing','generating_report')")),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("review_sessions.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_version: Mapped[int | None] = mapped_column(Integer)
    document_revision: Mapped[int | None] = mapped_column(Integer)
    input_snapshot_json: Mapped[str | None] = mapped_column(Text)
    context_snapshot_json: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    task_status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)


class RiskFinding(Base):
    __tablename__ = "risk_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    risk_title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actual_value_json: Mapped[str | None] = mapped_column(Text)
    reference_value_json: Mapped[str | None] = mapped_column(Text)
    threshold_json: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[str | None] = mapped_column(Text)
    suggestion_text: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ReviewReport(Base):
    __tablename__ = "review_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_snapshot_json: Mapped[str | None] = mapped_column(Text)
    supplier_snapshot_json: Mapped[str | None] = mapped_column(Text)
    snapshot_status: Mapped[str] = mapped_column(String(24), default="complete", nullable=False)
    overall_risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_summary_json: Mapped[str | None] = mapped_column(Text)
    amount_comparison_json: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    report_markdown: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class MarketPriceReference(Base):
    __tablename__ = "market_price_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    specification: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(64))
    price_min: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    price_max: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(128))
    effective_date: Mapped[date | None] = mapped_column(Date)


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    credit_status: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    blacklist_status: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    risk_tags_json: Mapped[str | None] = mapped_column(Text)
    bank_accounts_json: Mapped[str | None] = mapped_column(Text)
    contact_info: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, nullable=False)


class ManualReview(Base):
    __tablename__ = "manual_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("review_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    review_result: Mapped[str] = mapped_column(String(32), nullable=False)
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ReviewRule(Base, TimestampMixin):
    __tablename__ = "review_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(32))
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
