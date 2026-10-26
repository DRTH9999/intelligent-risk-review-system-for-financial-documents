"""基础数据与演示数据初始化。"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ATTACHMENT_DIR
from app.models import (
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflow,
    ApprovalWorkflowNode,
    DocumentAttachment,
    FinancialDocument,
    ManualReview,
    MarketPriceReference,
    Permission,
    ReviewReport,
    ReviewRule,
    RiskFinding,
    Role,
    RolePermission,
    SupplierProfile,
    User,
    UserRole,
)
from app.schemas import DocumentCreate, LineItemIn
from app.security import hash_password
from app.services.analysis import create_analysis_task, run_analysis_task
from app.services.approval import process_task, start_approval
from app.services.documents import add_line_item, create_document, log_status, snapshot_document
from app.services.parsing import ensure_parsed
from app.services.rules import DEFAULT_RULE_DEFINITIONS

PASSWORD = "User@123"

ROLE_DEFINITIONS = [
    ("applicant", "单据申请人"),
    ("approver", "审批人员"),
    ("finance", "财务人员"),
    ("admin", "系统管理员"),
]

PERMISSION_DEFINITIONS = [
    ("document:create", "创建单据", "document", "create"),
    ("document:read", "查看单据", "document", "read"),
    ("document:update", "编辑单据", "document", "update"),
    ("document:submit", "提交单据", "document", "submit"),
    ("document:withdraw", "撤回单据", "document", "withdraw"),
    ("document:void", "作废单据", "document", "void"),
    ("attachment:upload", "上传附件", "attachment", "upload"),
    ("attachment:view", "查看附件", "attachment", "view"),
    ("attachment:delete", "删除附件", "attachment", "delete"),
    ("analysis:run", "发起风险分析", "analysis", "run"),
    ("analysis:view", "查看风险分析", "analysis", "view"),
    ("approval:process", "处理审批任务", "approval", "process"),
    ("rule:manage", "维护审核规则", "rule", "manage"),
    ("workflow:manage", "维护审批流程", "workflow", "manage"),
    ("supplier:manage", "维护供应商", "supplier", "manage"),
    ("report:export", "导出报告", "report", "export"),
    ("user:manage", "用户管理", "user", "manage"),
    ("audit:view", "查看审计日志", "audit", "view"),
]

ROLE_PERMISSIONS = {
    "applicant": [
        "document:create",
        "document:read",
        "document:update",
        "document:submit",
        "document:withdraw",
        "document:void",
        "attachment:upload",
        "attachment:view",
        "attachment:delete",
        "analysis:run",
        "analysis:view",
        "report:export",
    ],
    "approver": [
        "document:read",
        "attachment:view",
        "analysis:run",
        "analysis:view",
        "approval:process",
        "report:export",
    ],
    "finance": [
        "document:read",
        "attachment:view",
        "analysis:view",
        "rule:manage",
        "supplier:manage",
        "report:export",
        "audit:view",
    ],
    "admin": [code for code, *_ in PERMISSION_DEFINITIONS],
}

WORKFLOW_DEFINITIONS = [
    {
        "workflow_name": "费用报销标准流程（5000 元以下）",
        "document_type": "费用报销单",
        "match_conditions": {"amount_min": 0, "amount_max": 5000},
        "nodes": [("部门负责人审批", "approver")],
    },
    {
        "workflow_name": "费用报销标准流程（5000 元以上）",
        "document_type": "费用报销单",
        "match_conditions": {"amount_min": 5000.01},
        "nodes": [("部门负责人审批", "approver"), ("财务复核", "finance")],
    },
    {
        "workflow_name": "差旅报销标准流程（5000 元以下）",
        "document_type": "差旅报销单",
        "match_conditions": {"amount_min": 0, "amount_max": 5000},
        "nodes": [("部门负责人审批", "approver")],
    },
    {
        "workflow_name": "差旅报销标准流程（5000 元以上）",
        "document_type": "差旅报销单",
        "match_conditions": {"amount_min": 5000.01},
        "nodes": [("部门负责人审批", "approver"), ("财务复核", "finance")],
    },
    {
        "workflow_name": "对公付款标准流程",
        "document_type": "对公付款单",
        "match_conditions": {"amount_min": 0},
        "nodes": [("财务审核", "finance"), ("部门负责人审批", "approver")],
    },
    {
        "workflow_name": "预付款标准流程",
        "document_type": "预付款单",
        "match_conditions": {"amount_min": 0},
        "nodes": [("财务审核", "finance")],
    },
    {
        "workflow_name": "批量付款标准流程",
        "document_type": "批量付款单",
        "match_conditions": {"amount_min": 0},
        "nodes": [("财务审核", "finance"), ("部门负责人审批", "approver")],
    },
]

SUPPLIER_DEFINITIONS = [
    {
        "supplier_code": "SUP-001",
        "supplier_name": "上海锦程会务服务有限公司",
        "credit_status": "normal",
        "blacklist_status": "normal",
        "risk_tags": [],
        "bank_accounts": ["6222020111002233445"],
        "contact_info": "021-5888 1020",
    },
    {
        "supplier_code": "SUP-002",
        "supplier_name": "北京华信科技有限公司",
        "credit_status": "watch",
        "blacklist_status": "normal",
        "risk_tags": ["履约异常", "涉诉"],
        "bank_accounts": ["6228480012345678901"],
        "contact_info": "010-6677 8899",
    },
    {
        "supplier_code": "SUP-003",
        "supplier_name": "深圳市鑫源贸易有限公司",
        "credit_status": "abnormal",
        "blacklist_status": "blacklist",
        "risk_tags": ["关联交易", "涉诉"],
        "bank_accounts": ["6225880111223344"],
        "contact_info": "0755-8899 1122",
    },
    {
        "supplier_code": "SUP-004",
        "supplier_name": "杭州云采办公用品有限公司",
        "credit_status": "good",
        "blacklist_status": "normal",
        "risk_tags": [],
        "bank_accounts": ["6222020200011223344"],
        "contact_info": "0571-8899 6677",
    },
    {
        "supplier_code": "SUP-005",
        "supplier_name": "上海宏图印务有限公司",
        "credit_status": "normal",
        "blacklist_status": "normal",
        "risk_tags": ["账号变更"],
        "bank_accounts": ["6222020200011223344"],
        "contact_info": "021-6333 2211",
    },
]

MARKET_PRICES = [
    ("会议服务", "人/场", "上海", 200, 400, "上海市会展行业协会指导价"),
    ("会务服务", "场", "上海", 8000, 15000, "企业内部历史采购价"),
    ("酒店住宿", "间/晚", "北京", 400, 700, "差旅平台协议价"),
    ("宣传册印刷", "册", "上海", 150, 260, "印刷行业协会报价"),
    ("笔记本电脑", "台", "全国", 5000, 8000, "京东企业购参考价"),
    ("办公用品", "批", "全国", 500, 5000, "企业采购平台参考价"),
]


def ensure_base_data(db: Session) -> None:
    if db.execute(select(User.id)).first():
        return

    roles = {}
    for code, name in ROLE_DEFINITIONS:
        role = Role(role_code=code, role_name=name, status="active")
        db.add(role)
        db.flush()
        roles[code] = role

    permissions = {}
    for code, name, resource_type, action_type in PERMISSION_DEFINITIONS:
        permission = Permission(
            permission_code=code,
            permission_name=name,
            resource_type=resource_type,
            action_type=action_type,
        )
        db.add(permission)
        db.flush()
        permissions[code] = permission

    for role_code, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            db.add(RolePermission(role_id=roles[role_code].id, permission_id=permissions[code].id))

    users = [
        ("admin", "系统管理员", "Admin@123", "信息技术部", "M3", ["admin"]),
        ("zhangwei", "张伟", PASSWORD, "市场部", "P6", ["applicant"]),
        ("chenchen", "陈晨", PASSWORD, "研发部", "P7", ["applicant"]),
        ("lina", "李娜", PASSWORD, "财务部", "M2", ["approver"]),
        ("zhaolei", "赵磊", PASSWORD, "总经理办公室", "M4", ["approver"]),
        ("wangfang", "王芳", PASSWORD, "财务部", "P7", ["finance"]),
    ]
    created_users = {}
    for username, display_name, password, department, level, role_codes in users:
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            department=department,
            job_level=level,
            status="active",
        )
        db.add(user)
        db.flush()
        created_users[username] = user
        for code in role_codes:
            db.add(UserRole(user_id=user.id, role_id=roles[code].id))

    for definition in WORKFLOW_DEFINITIONS:
        workflow = ApprovalWorkflow(
            workflow_name=definition["workflow_name"],
            document_type=definition["document_type"],
            match_conditions_json=json.dumps(definition["match_conditions"], ensure_ascii=False),
            status="active",
        )
        db.add(workflow)
        db.flush()
        for order, (node_name, role_code) in enumerate(definition["nodes"], start=1):
            db.add(
                ApprovalWorkflowNode(
                    workflow_id=workflow.id,
                    node_name=node_name,
                    node_order=order,
                    approver_role=role_code,
                    approval_mode="single",
                )
            )

    for definition in DEFAULT_RULE_DEFINITIONS:
        db.add(
            ReviewRule(
                rule_code=definition["rule_code"],
                rule_name=definition["rule_name"],
                rule_type=definition["rule_type"],
                document_type=definition.get("document_type"),
                config_json=json.dumps(definition["config"], ensure_ascii=False),
                severity=definition["severity"],
                status="active",
                updated_by=created_users["admin"].id,
            )
        )

    for supplier in SUPPLIER_DEFINITIONS:
        db.add(
            SupplierProfile(
                supplier_code=supplier["supplier_code"],
                supplier_name=supplier["supplier_name"],
                credit_status=supplier["credit_status"],
                blacklist_status=supplier["blacklist_status"],
                risk_tags_json=json.dumps(supplier["risk_tags"], ensure_ascii=False),
                bank_accounts_json=json.dumps(supplier["bank_accounts"], ensure_ascii=False),
                contact_info=supplier["contact_info"],
            )
        )

    for item_name, spec, region, price_min, price_max, source in MARKET_PRICES:
        db.add(
            MarketPriceReference(
                item_name=item_name,
                specification=spec,
                region=region,
                price_min=price_min,
                price_max=price_max,
                currency="CNY",
                source_name=source,
                effective_date=date.today(),
            )
        )

    db.commit()


# ------------------------------------------------------------------ 附件生成
def _register_cjk_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _pdf(path: Path, title: str, lines: list[str], footer: str | None = None) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    font = _register_cjk_font()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFont(font, 18)
    c.drawString(70, height - 80, title)
    c.setLineWidth(1)
    c.line(70, height - 95, width - 70, height - 95)
    y = height - 135
    for line in lines:
        c.setFont(font, 11.5)
        c.drawString(70, y, line)
        y -= 26
    if footer:
        c.setFont(font, 9)
        c.setFillGray(0.4)
        c.drawString(70, 70, footer)
    c.setFillGray(0)
    c.showPage()
    c.save()


def _image(path: Path, title: str, lines: list[str]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1240, 1754
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = None
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"):
        if Path(candidate).exists():
            font_path = candidate
            break
    title_font = ImageFont.truetype(font_path, 52) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, 36) if font_path else ImageFont.load_default()
    draw.rectangle([40, 40, width - 40, height - 40], outline=(60, 70, 90), width=3)
    draw.text((width / 2, 110), title, font=title_font, fill=(20, 30, 50), anchor="mm")
    draw.line([(90, 190), (width - 90, 190)], fill=(60, 70, 90), width=2)
    y = 270
    for line in lines:
        draw.text((100, y), line, font=body_font, fill=(25, 30, 40))
        y += 92
    draw.text((width - 170, height - 240), "行程专用章", font=body_font, fill=(190, 40, 40))
    image.save(path, quality=92)


def _attach(
    db: Session,
    doc: FinancialDocument,
    user_id: int,
    file_name: str,
    builder,
    *,
    parse_now: bool = True,
) -> DocumentAttachment:
    target_dir = ATTACHMENT_DIR / str(doc.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / file_name
    builder(path)
    content = path.read_bytes()
    file_hash = hashlib.sha256(content).hexdigest()
    stored_path = target_dir / f"{file_hash[:12]}_{file_name}"
    if stored_path != path:
        path.replace(stored_path)
    attachment = DocumentAttachment(
        document_id=doc.id,
        document_version=doc.current_version,
        file_name=file_name,
        file_type=stored_path.suffix.lstrip(".").lower(),
        file_size=len(content),
        file_path=str(stored_path),
        file_hash=file_hash,
        storage_status="stored",
        parse_status="pending",
        uploaded_by=user_id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    if parse_now:
        ensure_parsed(db, attachment)
    return attachment


def _invoice_pdf(
    path: Path,
    *,
    code: str,
    no: str,
    invoice_date: str,
    seller: str,
    buyer: str,
    item_name: str,
    quantity: float,
    unit_price: float,
    amount_excl: float,
    tax: float,
    total: float,
) -> None:
    lines = [
        f"发票代码：{code}",
        f"发票号码：{no}",
        f"开票日期：{invoice_date}",
        f"购买方名称：{buyer}",
        f"销售方名称：{seller}",
        "",
        "项目名称        数量      单价          金额",
        f"{item_name}      {quantity:g}        {unit_price:,.2f}      {amount_excl:,.2f}",
        "",
        f"金额：¥{amount_excl:,.2f}",
        "税率：6%",
        f"税额：¥{tax:,.2f}",
        "价税合计（大写）：" + "人民币" + f"{total:,.2f}元",
        f"价税合计（小写）：¥{total:,.2f}",
        "",
        "收款人：财务部    复核：张敏    开票人：李静",
        "销售方（章）：" + seller,
    ]
    _pdf(path, "增值税电子普通发票", lines, "本发票为演示数据，仅用于系统功能验证")


def _contract_pdf(
    path: Path,
    *,
    contract_no: str,
    party_a: str,
    party_b: str,
    amount: float,
    ratio: float,
    terms: str,
) -> None:
    lines = [
        f"合同编号：{contract_no}",
        f"甲方：{party_a}",
        f"乙方：{party_b}",
        f"合同金额：¥{amount:,.2f}",
        f"付款比例：{ratio:g}%",
        f"付款条件：{terms}",
        "",
        "第一条 服务内容",
        "乙方向甲方提供会议策划、场地布置及会务执行服务。",
        "",
        "第二条 付款方式",
        f"合同签订后按 {ratio:g}% 支付首付款，尾款在服务验收后 30 日内支付。",
        "",
        "第三条 违约责任",
        "任何一方违约，应赔偿对方因此遭受的直接经济损失。",
        "",
        "甲方（盖章）：" + party_a,
        "乙方（盖章）：" + party_b,
        "签订日期：2026年09月10日",
    ]
    _pdf(path, "采购合同", lines, "合同正文共 3 页，本页为签署页（演示数据）")


def _payment_proof_pdf(path: Path, *, payee: str, account: str, amount: float, purpose: str, pay_date: str) -> None:
    lines = [
        "付款回单",
        f"付款日期：{pay_date}",
        "付款单位：云启科技（上海）有限公司",
        f"收款单位：{payee}",
        f"收款账号：{account}",
        f"付款金额：¥{amount:,.2f}",
        f"付款用途：{purpose}",
        "交易流水号：20260920000123456789",
        "状态：交易成功",
        "",
        "备注：本回单由企业网银生成，可作为付款依据。",
    ]
    _pdf(path, "银行付款回单", lines, "演示数据")


def _itinerary_image(path: Path, *, location: str, start: str, end: str, transport: float, hotel: float, meal: float, allowance: float) -> None:
    lines = [
        f"出差地点：{location}",
        f"出差起止：{start} 至 {end}",
        "出差人：张伟",
        "部门：市场部",
        "",
        f"交通费：¥{transport:,.2f}",
        f"住宿费：¥{hotel:,.2f}",
        f"餐费：¥{meal:,.2f}",
        f"补贴：¥{allowance:,.2f}",
        "",
        "审批单号：TRIP-2026-0922",
        "备注：参加行业峰会并进行客户拜访。",
    ]
    _image(path, "出差行程单", lines)


# ------------------------------------------------------------------ 演示数据
def seed_demo(db: Session) -> bool:
    if db.execute(select(FinancialDocument.id)).first():
        return False

    users = {user.username: user for user in db.execute(select(User)).scalars().all()}
    zhangwei = users["zhangwei"]
    chenchen = users["chenchen"]
    lina = users["lina"]
    wangfang = users["wangfang"]
    admin = users["admin"]

    today = date.today()
    company = "云启科技（上海）有限公司"

    def create_base(
        user: User,
        *,
        document_type: str,
        department: str,
        budget_department: str,
        payee_name: str,
        payee_account: str | None = None,
        expense_category: str,
        total: float,
        apply_date: date,
        reason: str,
        items: list[dict],
        **extra,
    ) -> FinancialDocument:
        payload = DocumentCreate(
            document_type=document_type,
            applicant_department=department,
            budget_department=budget_department,
            payee_name=payee_name,
            payee_account=payee_account,
            expense_category=expense_category,
            total_amount=total,
            apply_date=apply_date,
            reason_text=reason,
            **extra,
        )
        doc = create_document(db, user, payload)
        for item in items:
            add_line_item(db, doc, LineItemIn(**item))
        return doc

    docs: dict[str, FinancialDocument] = {}

    # 1. 对公付款单（已通过，低风险）
    doc1 = create_base(
        zhangwei,
        document_type="对公付款单",
        department="市场部",
        budget_department="市场部",
        payee_name="上海锦程会务服务有限公司",
        payee_account="6222020111002233445",
        expense_category="会务费",
        total=39000,
        apply_date=today - timedelta(days=6),
        reason="2026 秋季行业峰会会务服务首付款",
        items=[
            {
                "item_type": "expense",
                "item_name": "会议服务",
                "item_spec": "人/场",
                "expense_category": "会务费",
                "expense_date": today - timedelta(days=6),
                "expense_location": "上海",
                "quantity": 130,
                "unit_price": 300,
                "amount": 39000,
            }
        ],
        contract_no="HT-2026-0918",
        supplier_name="上海锦程会务服务有限公司",
        supplier_code="SUP-001",
        payment_ratio=30,
        payment_terms="合同签订后 10 个工作日内支付 30% 首付款",
        planned_payment_date=today - timedelta(days=2),
    )
    docs["gongfu"] = doc1
    _attach(
        db,
        doc1,
        zhangwei.id,
        "会务服务发票_39000.pdf",
        lambda path: _invoice_pdf(
            path,
            code="031002100111",
            no="24567891",
            invoice_date=(today - timedelta(days=8)).strftime("%Y年%m月%d日"),
            seller="上海锦程会务服务有限公司",
            buyer=company,
            item_name="会议服务费",
            quantity=130,
            unit_price=300,
            amount_excl=36792.45,
            tax=2207.55,
            total=39000,
        ),
    )
    _attach(
        db,
        doc1,
        zhangwei.id,
        "会务服务合同_HT-2026-0918.pdf",
        lambda path: _contract_pdf(
            path,
            contract_no="HT-2026-0918",
            party_a=company,
            party_b="上海锦程会务服务有限公司",
            amount=130000,
            ratio=30,
            terms="合同签订后 10 个工作日内支付 30% 首付款",
        ),
    )

    # 2. 费用报销单（已退回，中风险）
    doc2 = create_base(
        zhangwei,
        document_type="费用报销单",
        department="市场部",
        budget_department="市场部",
        payee_name="上海锦程会务服务有限公司",
        expense_category="会务费",
        total=13000,
        apply_date=today - timedelta(days=5),
        reason="客户答谢会会务执行费用报销",
        items=[
            {
                "item_type": "expense",
                "item_name": "会务服务",
                "expense_category": "会务费",
                "expense_date": today - timedelta(days=7),
                "expense_location": "上海",
                "quantity": 1,
                "unit_price": 13000,
                "amount": 13000,
            }
        ],
    )
    docs["baoxiao"] = doc2
    _attach(
        db,
        doc2,
        zhangwei.id,
        "会务服务发票_12000.pdf",
        lambda path: _invoice_pdf(
            path,
            code="031002100112",
            no="24567890",
            invoice_date=(today - timedelta(days=7)).strftime("%Y年%m月%d日"),
            seller="上海锦程会务服务有限公司",
            buyer=company,
            item_name="会务服务费",
            quantity=1,
            unit_price=12000,
            amount_excl=11320.75,
            tax=679.25,
            total=12000,
        ),
    )

    # 3. 差旅报销单（待审批，高风险，含 JPG 行程单 OCR）
    doc3 = create_base(
        zhangwei,
        document_type="差旅报销单",
        department="市场部",
        budget_department="市场部",
        payee_name="张伟",
        expense_category="差旅费",
        total=4740,
        apply_date=today - timedelta(days=3),
        reason="北京行业峰会出差及客户拜访",
        items=[
            {
                "item_type": "transport",
                "item_name": "交通费-高铁",
                "expense_category": "交通费",
                "expense_date": today - timedelta(days=9),
                "expense_location": "北京",
                "quantity": 1,
                "unit_price": 1860,
                "amount": 1860,
            },
            {
                "item_type": "hotel",
                "item_name": "酒店住宿-北京国贸酒店",
                "expense_category": "住宿费",
                "expense_date": today - timedelta(days=9),
                "expense_location": "北京",
                "quantity": 2,
                "unit_price": 980,
                "amount": 1960,
            },
            {
                "item_type": "meal",
                "item_name": "餐费-客户招待",
                "expense_category": "餐费",
                "expense_date": today - timedelta(days=8),
                "expense_location": "天津",
                "quantity": 3,
                "unit_price": 206.67,
                "amount": 620,
            },
            {
                "item_type": "allowance",
                "item_name": "出差补贴",
                "expense_category": "补贴",
                "expense_date": today - timedelta(days=8),
                "expense_location": "北京",
                "quantity": 3,
                "unit_price": 100,
                "amount": 300,
            },
        ],
        travel_location="北京",
        travel_start_date=today - timedelta(days=9),
        travel_end_date=today - timedelta(days=7),
    )
    docs["chailv"] = doc3
    _attach(
        db,
        doc3,
        zhangwei.id,
        "差旅行程单_北京.jpg",
        lambda path: _itinerary_image(
            path,
            location="北京",
            start=(today - timedelta(days=9)).strftime("%Y年%m月%d日"),
            end=(today - timedelta(days=7)).strftime("%Y年%m月%d日"),
            transport=1860,
            hotel=1960,
            meal=620,
            allowance=300,
        ),
    )
    _attach(
        db,
        doc3,
        zhangwei.id,
        "差旅服务费发票_4600.pdf",
        lambda path: _invoice_pdf(
            path,
            code="011002100233",
            no="33881245",
            invoice_date=(today - timedelta(days=7)).strftime("%Y年%m月%d日"),
            seller="北京中旅商务服务有限公司",
            buyer=company,
            item_name="差旅服务费",
            quantity=1,
            unit_price=4600,
            amount_excl=4339.62,
            tax=260.38,
            total=4600,
        ),
    )

    # 4. 批量付款单（待审批，高风险：重复收款账号）
    batch_items = [
        ("上海锦程会务服务有限公司", "6222020111002233445", 26000, "会务服务尾款"),
        ("北京华信科技有限公司", "6228480012345678901", 18000, "系统实施服务费"),
        ("杭州云采办公用品有限公司", "6222020200011223344", 12000, "办公用品采购"),
        ("上海宏图印务有限公司", "6222020200011223344", 22000, "宣传物料印刷"),
        ("上海锦程会务服务有限公司", "6222020111002233445", 18000, "活动执行费用"),
    ]
    doc4 = create_base(
        chenchen,
        document_type="批量付款单",
        department="研发部",
        budget_department="研发部",
        payee_name="批量付款（5 笔）",
        expense_category="批量付款",
        total=96000,
        apply_date=today - timedelta(days=2),
        reason="季度供应商款项批量支付",
        items=[
            {
                "item_type": "payout",
                "item_name": name,
                "expense_category": "批量付款",
                "expense_date": today - timedelta(days=2),
                "payee_name": name,
                "payee_account": account,
                "quantity": 1,
                "unit_price": amount,
                "amount": amount,
                "remark": purpose,
            }
            for name, account, amount, purpose in batch_items
        ],
        batch_total_amount=96000,
        batch_payment_count=5,
        planned_payment_date=today,
    )
    docs["piliang"] = doc4
    _attach(
        db,
        doc4,
        chenchen.id,
        "批量付款清单_202609.pdf",
        lambda path: _payment_proof_pdf(
            path,
            payee="批量付款（5 笔）",
            account="6222020111002233445",
            amount=96000,
            purpose="季度供应商款项批量支付",
            pay_date=(today - timedelta(days=2)).strftime("%Y年%m月%d日"),
        ),
    )

    # 5. 预付款单（待审批，高风险：供应商资质与账号）
    doc5 = create_base(
        zhangwei,
        document_type="预付款单",
        department="市场部",
        budget_department="市场部",
        payee_name="北京华信科技有限公司",
        payee_account="6217000010001234567",
        expense_category="技术服务费",
        total=50000,
        apply_date=today - timedelta(days=1),
        reason="数字营销平台建设项目预付款",
        items=[
            {
                "item_type": "expense",
                "item_name": "平台建设预付款",
                "expense_category": "技术服务费",
                "expense_date": today - timedelta(days=1),
                "quantity": 1,
                "unit_price": 50000,
                "amount": 50000,
            }
        ],
        contract_no="HT-2026-1002",
        supplier_name="北京华信科技有限公司",
        supplier_code="SUP-002",
        payment_ratio=50,
        payment_terms="合同签订后支付 50% 预付款",
        planned_payment_date=today,
    )
    docs["yufu"] = doc5
    _attach(
        db,
        doc5,
        zhangwei.id,
        "技术服务合同_HT-2026-1002.pdf",
        lambda path: _contract_pdf(
            path,
            contract_no="HT-2026-1002",
            party_a=company,
            party_b="北京华信科技有限公司",
            amount=100000,
            ratio=50,
            terms="合同签订后支付 50% 预付款，验收后支付尾款",
        ),
    )

    # 6. 费用报销单（草稿，供编辑与提交演示）
    doc6 = create_base(
        zhangwei,
        document_type="费用报销单",
        department="市场部",
        budget_department="市场部",
        payee_name="张伟",
        expense_category="办公用品",
        total=12999,
        apply_date=today,
        reason="部门笔记本电脑采购报销（草稿）",
        items=[
            {
                "item_type": "expense",
                "item_name": "笔记本电脑",
                "item_spec": "ThinkPad X1 Carbon",
                "expense_category": "办公用品",
                "expense_date": today - timedelta(days=2),
                "expense_location": "上海",
                "quantity": 1,
                "unit_price": 12999,
                "amount": 12999,
            }
        ],
    )
    docs["draft"] = doc6

    # 7. 费用报销单（待审批，重复票据 / 收款账号不一致）
    doc7 = create_base(
        chenchen,
        document_type="费用报销单",
        department="研发部",
        budget_department="研发部",
        payee_name="上海锦程会务服务有限公司",
        payee_account="6222020200099887766",
        expense_category="会务费",
        total=12000,
        apply_date=today - timedelta(days=4),
        reason="客户交流活动会务服务费报销",
        items=[
            {
                "item_type": "expense",
                "item_name": "会务服务",
                "item_spec": "场",
                "expense_category": "会务费",
                "expense_date": today - timedelta(days=7),
                "expense_location": "上海",
                "quantity": 1,
                "unit_price": 12000,
                "amount": 12000,
            }
        ],
        supplier_name="上海锦程会务服务有限公司",
        supplier_code="SUP-001",
    )
    docs["duplicate"] = doc7
    _attach(
        db,
        doc7,
        chenchen.id,
        "会务服务发票_重复_12000.pdf",
        lambda path: _invoice_pdf(
            path,
            code="031002100112",
            no="24567890",
            invoice_date=(today - timedelta(days=7)).strftime("%Y年%m月%d日"),
            seller="上海锦程会务服务有限公司",
            buyer=company,
            item_name="会务服务费",
            quantity=1,
            unit_price=12000,
            amount_excl=11320.75,
            tax=679.25,
            total=12000,
        ),
    )

    # 提交审批状态
    submitted = ["gongfu", "baoxiao", "chailv", "piliang", "yufu", "duplicate"]
    instances: dict[str, ApprovalInstance] = {}
    for key in submitted:
        doc = docs[key]
        snapshot_document(db, doc, doc.applicant_id, doc.current_version)
        log_status(db, doc, "draft", "pending_review", doc.applicant_id, "提交审批（演示数据）")
        doc.document_status = "pending_review"
        db.commit()
        instance, _task = start_approval(db, doc, doc.applicant_id)
        db.commit()
        instances[key] = instance

    # 智能分析
    for key in ["gongfu", "baoxiao", "chailv", "piliang", "yufu", "duplicate"]:
        doc = docs[key]
        task = create_analysis_task(db, doc, doc.applicant_id, session_id=None, run_async=False)
        db.commit()
        run_analysis_task(task.id)
        db.refresh(doc)

    # 已通过单据：完成两级审批
    instance1 = instances["gongfu"]
    task_rows = db.execute(
        select(ApprovalTask).where(ApprovalTask.instance_id == instance1.id).order_by(ApprovalTask.id)
    ).scalars().all()
    if task_rows:
        process_task(db, task_rows[0], "approve", wangfang, "合同、发票与付款比例核验一致，同意付款")
        next_task = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance1.id,
                ApprovalTask.task_status == "pending",
            )
        ).scalars().first()
        if next_task:
            process_task(db, next_task, "approve", lina, "业务真实，同意支付首付款")

    # 已退回单据
    instance2 = instances["baoxiao"]
    task2 = db.execute(
        select(ApprovalTask).where(ApprovalTask.instance_id == instance2.id, ApprovalTask.task_status == "pending")
    ).scalars().first()
    if task2:
        process_task(db, task2, "return", lina, "发票金额 12,000 元与报销金额 13,000 元不一致，请补充差额说明后重新提交")

    # 人工复核记录（已通过的低风险单据）
    report1 = db.execute(
        select(ReviewReport)
        .where(ReviewReport.document_id == doc1.id)
        .order_by(ReviewReport.id.desc())
    ).scalars().first()
    if report1:
        db.add(
            ManualReview(
                report_id=report1.id,
                reviewer_id=wangfang.id,
                review_result="通过",
                review_comment="金额、发票、合同及供应商信息核对一致，同意通过。",
            )
        )
    report2 = db.execute(
        select(ReviewReport)
        .where(ReviewReport.document_id == doc2.id)
        .order_by(ReviewReport.id.desc())
    ).scalars().first()
    if report2:
        finding = db.execute(
            select(RiskFinding)
            .where(RiskFinding.task_id == report2.task_id)
            .order_by(RiskFinding.id)
        ).scalars().first()
        if finding:
            finding.review_status = "confirmed"
        db.add(
            ManualReview(
                report_id=report2.id,
                reviewer_id=lina.id,
                review_result="退回",
                review_comment="金额存在差异，要求申请人补充发票差额说明。",
            )
        )
    db.commit()
    return True


def reset_database() -> None:
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def clear_attachments() -> None:
    import shutil

    if not ATTACHMENT_DIR.exists():
        return
    for child in ATTACHMENT_DIR.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def seed_all() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        ensure_base_data(db)
        seed_demo(db)
    finally:
        db.close()
