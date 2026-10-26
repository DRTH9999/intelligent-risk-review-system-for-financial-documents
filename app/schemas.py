"""请求参数模型。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Amount = Annotated[Decimal, Field(ge=0, le=Decimal('999999999999.99'), decimal_places=2, max_digits=14)]
Quantity = Annotated[Decimal, Field(gt=0, le=1000000, decimal_places=4)]
Ratio = Annotated[Decimal, Field(gt=0, le=100, decimal_places=2)]
DocumentType = Literal['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单']


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid', allow_inf_nan=False)


class DateRangeModel(InputModel):
    @model_validator(mode='after')
    def date_order(self):
        start = getattr(self, 'travel_start_date', None)
        end = getattr(self, 'travel_end_date', None)
        if start and end and end < start:
            raise ValueError('出差结束日期不能早于开始日期')
        return self


class LoginRequest(InputModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class LineItemIn(InputModel):
    item_type: Literal['expense', 'payment', 'payout', 'travel', 'transport', 'hotel', 'meal', 'allowance'] = "expense"
    item_name: str = Field(min_length=1, max_length=128)
    item_spec: str | None = None
    expense_category: str | None = None
    expense_date: date | None = None
    expense_location: str | None = None
    quantity: Quantity = Decimal('1')
    unit_price: Amount = Decimal('0')
    amount: Amount | None = None
    payee_name: str | None = None
    payee_account: str | None = None
    remark: str | None = None


class LineItemUpdate(InputModel):
    item_type: Literal['expense', 'payment', 'payout', 'travel', 'transport', 'hotel', 'meal', 'allowance'] | None = None
    item_name: str | None = Field(default=None, min_length=1, max_length=128)
    item_spec: str | None = None
    expense_category: str | None = None
    expense_date: date | None = None
    expense_location: str | None = None
    quantity: Quantity | None = None
    unit_price: Amount | None = None
    amount: Amount | None = None
    payee_name: str | None = None
    payee_account: str | None = None
    remark: str | None = None


class DocumentCreate(DateRangeModel):
    document_type: DocumentType
    applicant_department: str = Field(min_length=1, max_length=64)
    budget_department: str = Field(min_length=1, max_length=64)
    payee_name: str | None = None
    payee_account: str | None = None
    expense_category: str | None = None
    total_amount: Amount = Decimal('0')
    currency: Literal['CNY', 'USD', 'EUR'] = "CNY"
    apply_date: date | None = None
    reason_text: str | None = None
    contract_no: str | None = None
    supplier_name: str | None = None
    supplier_code: str | None = None
    payment_ratio: Ratio | None = None
    payment_terms: str | None = None
    planned_payment_date: date | None = None
    batch_total_amount: Amount | None = None
    batch_payment_count: int | None = Field(default=None, ge=1, le=500)
    travel_location: str | None = None
    travel_start_date: date | None = None
    travel_end_date: date | None = None
    ext: dict[str, Any] | None = None
    line_items: list[LineItemIn] = Field(default_factory=list, max_length=500)


class DocumentUpdate(DateRangeModel):
    revision: int | None = Field(default=None, ge=1)
    applicant_department: str | None = Field(default=None, min_length=1, max_length=64)
    budget_department: str | None = Field(default=None, min_length=1, max_length=64)
    payee_name: str | None = None
    payee_account: str | None = None
    expense_category: str | None = None
    total_amount: Amount | None = None
    currency: Literal['CNY', 'USD', 'EUR'] | None = None
    apply_date: date | None = None
    reason_text: str | None = None
    contract_no: str | None = None
    supplier_name: str | None = None
    supplier_code: str | None = None
    payment_ratio: Ratio | None = None
    payment_terms: str | None = None
    planned_payment_date: date | None = None
    batch_total_amount: Amount | None = None
    batch_payment_count: int | None = Field(default=None, ge=1, le=500)
    travel_location: str | None = None
    travel_start_date: date | None = None
    travel_end_date: date | None = None
    ext: dict[str, Any] | None = None
    line_items: list[LineItemIn] | None = Field(default=None, max_length=500)


class SessionCreate(BaseModel):
    document_type: str | None = None
    document_no: str | None = None


class MessageIn(BaseModel):
    content: str


class AnalysisCreate(BaseModel):
    session_id: int | None = None
    force: bool = False


class FindingReviewUpdate(InputModel):
    review_status: Literal["pending", "confirmed", "dismissed"]
    comment: str = Field(min_length=2, max_length=3000)


class ManualReviewIn(InputModel):
    review_result: Literal["建议通过", "补充材料", "人工复核", "建议驳回", "通过", "退回", "驳回"]
    review_comment: str = Field(min_length=2, max_length=3000)


class ApprovalAction(InputModel):
    comment: str = Field(min_length=2, max_length=3000)


class WorkflowNodeIn(BaseModel):
    node_name: str
    node_order: int
    approver_role: str
    approval_mode: str = "single"


class WorkflowIn(BaseModel):
    workflow_name: str
    document_type: str
    match_conditions: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    nodes: list[WorkflowNodeIn] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    workflow_name: str | None = None
    document_type: str | None = None
    match_conditions: dict[str, Any] | None = None
    status: str | None = None
    nodes: list[WorkflowNodeIn] | None = None


class RuleIn(InputModel):
    rule_code: str
    rule_name: str
    rule_type: str
    document_type: str | None = None
    config: dict[str, Any]
    severity: Literal['low','medium','high'] = "medium"
    status: Literal['active','inactive'] = "active"


class RuleUpdate(InputModel):
    rule_name: str | None = None
    rule_type: str | None = None
    document_type: str | None = None
    config: dict[str, Any] | None = None
    severity: Literal['low','medium','high'] | None = None
    status: Literal['active','inactive'] | None = None


class MarketPriceInput(InputModel):
    item_name: str = Field(min_length=1,max_length=128)
    specification: str | None = Field(default=None,max_length=128)
    region: str | None = Field(default=None,max_length=128)
    price_min: Amount = Field(gt=0)
    price_max: Amount = Field(gt=0)
    currency: Literal['CNY','USD','EUR'] = 'CNY'
    source_name: str = Field(min_length=1,max_length=255)
    effective_date: date = Field(default_factory=date.today)

    @model_validator(mode='after')
    def price_order(self):
        if self.price_max < self.price_min:
            raise ValueError('价格上限不能小于下限')
        return self


class SupplierUpdate(BaseModel):
    credit_status: str | None = None
    blacklist_status: str | None = None
    risk_tags: list[str] | None = None
    bank_accounts: list[str] | None = None
    contact_info: str | None = None


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    department: str | None = None
    job_level: str | None = None
    status: str = "active"
    roles: list[str] = Field(default_factory=lambda: ["applicant"])


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = None
    department: str | None = None
    job_level: str | None = None
    status: str | None = None
    roles: list[str] | None = None
