# 财务单据智能风险审核系统

一套可独立运行的财务单据风险审核系统，覆盖 **单据创建 → 附件上传 → 智能解析 → 风险分析 → 审批流转 → 人工复核 → 报告导出 → 操作审计** 完整链路。

当前版本 **v1.1** 补充了提交校验、禁止自审、报告与证据快照、规则停用、并发保护及持久后台任务。详细行为、旧数据升级与验收范围见 [完善记录](docs/完善记录.md)。

系统内置五类业务单据、十类风险规则、三级风险等级、多节点审批流程和可追溯的证据定位，前后端均随项目提供，无需额外构建步骤。

---

## 一、功能概览

- **单据管理**：对公付款单、预付款单、批量付款单、费用报销单、差旅报销单；支持创建、编辑、复制、提交、撤回、作废、版本快照与状态日志。
- **附件管理**：PDF / PNG / JPG 上传、预览、下载、删除、格式与大小校验、访问权限校验。
- **文档解析**：PDF 文本层提取；扫描件与图片使用 RapidOCR 识别；自动分类发票、合同、行程单、付款依据；提取关键字段并保存页码、原文片段、字符位置/坐标与置信度。
- **风险分析**：金额一致性、明细合计、合同付款、批量付款、费用标准、市场价、消费行为、供应商、附件完整性、重复票据十类规则；输出实际值、参考值、规则阈值与证据。
- **多轮对话**：自动澄清单据类型与单据编号，支持候选确认、冲突纠正、权限内单据查询与一键发起分析。
- **审批流转**：按单据类型、金额区间、部门匹配流程；多节点审批、退回修改、驳回、重新提交；完整审批进度与意见记录。
- **配置管理**：审批流程、金额容差、费用标准、市场价区间、供应商档案与黑名单。
- **报告与审计**：可视化风险报告、Markdown / HTML 导出、人工复核、风险项确认/忽略、全量操作日志。

---

## 二、技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、SQLite（WAL）、PyJWT |
| 文档解析 | pypdf、pypdfium2、RapidOCR（ONNX Runtime）、Pillow |
| 示例附件生成 | ReportLab（中文 CID 字体）、Pillow |
| 前端 | 原生 ES Modules SPA + 自研 CSS 设计系统，无 npm 构建依赖 |
| 存储 | 本地文件系统（`storage/attachments`）+ SQLite（`data/risk_review.db`） |
| 环境管理 | uv（`uv sync` 生成 `uv.lock` 并同步项目 `.venv`） |

---

## 三、目录结构

```text
.
├─ app/
│  ├─ main.py                 # FastAPI 入口与静态资源托管
│  ├─ config.py               # 路径、令牌、上传限制等配置
│  ├─ database.py             # 引擎与会话
│  ├─ models.py               # 全部数据表（单据、附件、解析、审批、分析、规则、审计等）
│  ├─ schemas.py              # 请求模型
│  ├─ security.py             # PBKDF2 密码哈希、JWT
│  ├─ deps.py                 # 登录态、角色与数据权限
│  ├─ seed.py                 # 基础数据、示例单据与示例附件生成
│  ├─ routers/                # 认证、单据、会话、分析、审批、规则、供应商、工作台等接口
│  ├─ services/               # 解析、规则引擎、分析任务、审批、对话、报告、序列化
│  └─ static/                 # 前端 SPA（index.html / css / js/pages）
├─ scripts/
│  ├─ init_db.py              # 建表 + 基础数据
│  └─ seed_demo.py            # 初始化 + 示例数据（含附件）
├─ storage/attachments/       # 附件文件
├─ data/risk_review.db        # SQLite 数据库
├─ docs/接口说明.md            # 接口文档
├─ pyproject.toml             # 依赖声明（uv 依据此文件解析）
├─ uv.lock                    # uv 锁文件
├─ requirements.txt           # 非 uv 环境下的等价依赖清单
└─ run.py
```

---

## 四、快速开始

1. 创建并同步环境（按 `pyproject.toml` 生成 `uv.lock` 并安装到 `.venv`）：

```bash
uv sync
```

运行回归验证：`uv sync --group dev` 后执行 `uv run pytest -q`。测试使用独立临时数据库。

> 也可直接用 `uv run` 执行后续命令，uv 会自动校验并补齐环境。

2. 初始化数据库与基础数据：

```bash
uv run python scripts/init_db.py
```

3. 导入示例数据（五类单据、PDF/JPG 附件、审批状态、风险报告、人工复核记录）：

```bash
uv run python scripts/seed_demo.py
```

> 重新导入：`uv run python scripts/seed_demo.py --reset`（会清空数据表与附件文件后重建）。

4. 启动服务：

```bash
uv run python run.py
# 端口被占用时可指定端口（Windows PowerShell）：$env:PORT=9000; uv run python run.py
```

5. 打开浏览器访问 <http://127.0.0.1:8000>，接口文档见 <http://127.0.0.1:8000/docs>。

---

## 五、演示账号

| 角色 | 用户名 | 密码 | 说明 |
| --- | --- | --- | --- |
| 单据申请人 | `zhangwei` | `User@123` | 张伟 · 市场部，拥有 5 张演示单据 |
| 单据申请人 | `chenchen` | `User@123` | 陈晨 · 研发部，拥有批量付款单等单据 |
| 审批人员 | `lina` | `User@123` | 李娜 · 财务部，拥有待处理审批任务 |
| 财务人员 | `wangfang` | `User@123` | 王芳 · 财务部，可维护规则、市场价、供应商 |
| 系统管理员 | `admin` | `Admin@123` | 可维护流程、用户、全部数据 |

> 登录页提供一键填充按钮，可直接选择角色体验。

---

## 六、演示链路

1. **申请人维护单据**：使用 `zhangwei` 登录 →「单据管理」→ 打开草稿 `BX-202610-0002` →「编辑」→ 修改金额/明细 → 上传发票 PDF →「保存草稿」。
2. **提交审批**：在编辑页点击「保存并提交审批」。系统生成单据版本、审批实例与首个审批任务，并自动创建分析任务。
3. **附件解析**：进入单据详情 →「附件」→「查看解析」，可查看原文预览、识别文本、提取字段、置信度与字段位置；解析失败可点击「重新解析」。
4. **风险分析**：进入「风险分析」页，查看整体风险、金额核对面板、风险分类、风险项（实际值/参考值/阈值/证据）、供应商信息与处理建议。
5. **审批处理**：切换 `lina` →「我的审批」→「处理审批」，查看风险摘要后提交通过、退回或驳回；财务节点可切换 `wangfang` 处理。
6. **人工复核与导出**：在风险分析页填写复核结论与意见；点击「导出 Markdown / HTML」下载报告。
7. **审核记录**：进入「风险报告与记录」，按风险等级查询报告、查看人工复核结果与操作日志。

示例数据中已预置多种风险场景：

| 单据 | 场景 | 预期结果 |
| --- | --- | --- |
| `GF-202610-0001` | 合同、发票、付款比例一致 | 低风险 / 建议通过（已通过） |
| `BX-202610-0001` | 发票金额少 1,000 元 + 重复发票 | 高风险 / 建议驳回（已退回） |
| `CL-202610-0001` | 住宿超标、市场价偏离、异地消费、发票差异 | 中风险 / 人工复核 |
| `PL-202610-0001` | 批量付款存在重复收款账号 | 高风险 / 建议驳回 |
| `YF-202610-0001` | 供应商信用异常、风险标签、收款账号变更 | 高风险 / 建议驳回 |
| `BX-202610-0003` | 与历史单据使用同一张发票 | 高风险 / 建议驳回 |

---

## 七、角色与权限

| 角色 | 权限范围 |
| --- | --- |
| 单据申请人 `applicant` | 创建/编辑本人单据、维护明细、上传附件、提交/撤回/作废、查看本人单据与风险报告 |
| 审批人员 `approver` | 查看审批任务关联单据、发起分析、查看风险面板与证据、提交通过/退回/驳回、人工复核 |
| 财务人员 `finance` | 查看全部单据与分析结果、维护审核规则/费用标准/市场价/供应商档案、查看审计日志 |
| 系统管理员 `admin` | 全部数据权限、审批流程配置、用户与角色管理、系统运维 |

所有单据、附件、分析与审批接口均校验登录态与数据权限；审批结果、风险项处理、规则/流程变更都会写入 `audit_logs`。

---

## 八、风险规则

| 规则编码 | 风险分类 | 说明 |
| --- | --- | --- |
| `AMOUNT_MISMATCH` | 金额一致性 | 单据金额与发票价税合计差异 |
| `LINE_ITEM_MISMATCH` / `LINE_ITEM_DUPLICATE` | 金额一致性 | 明细合计差异、重复明细 |
| `CONTRACT_*` | 金额一致性 / 供应商风险 | 合同编号、主体、金额与付款比例核对 |
| `BATCH_*` | 金额一致性 / 供应商风险 | 批次金额、笔数、重复收款账号 |
| `EXPENSE_STANDARD_EXCEEDED` | 合规性 | 按费用类别对比企业标准 |
| `MARKET_PRICE_DEVIATION` | 价格合理性 | 对比市场价区间并输出偏离比例 |
| `BEHAVIOR_*` | 行为异常 | 同日重复、金额突增、高频、拆单、周末消费、异地消费 |
| `SUPPLIER_*` | 供应商风险 | 黑名单、信用异常、风险标签、账号不一致、集中付款 |
| `ATTACHMENT_*` / `INVOICE_SUBJECT_MISMATCH` | 附件完整性 | 必需附件、解析失败、低置信度、发票主体 |
| `DUPLICATE_INVOICE` | 票据风险 | 发票号码或销售方+金额+日期跨单据重复 |

风险等级：`low` / `medium` / `high`；整体风险取最高单项并结合风险数量评分生成。规则参数可在「审核规则」页面在线调整，保存后对后续分析生效。

---

## 九、接口说明

- Swagger UI：`/docs`
- ReDoc：`/redoc`
- 详细说明：[docs/接口说明.md](docs/接口说明.md)

所有业务接口统一前缀 `/api/v1`，除登录外均需请求头：

```http
Authorization: Bearer <access_token>
```

主要接口分组：

| 分组 | 示例 |
| --- | --- |
| 认证 | `POST /auth/login`、`GET /auth/me`、`POST /auth/logout` |
| 单据 | `POST /documents`、`GET /documents`、`GET /documents/{id}`、`POST /documents/{id}/submit`、`POST /documents/{id}/withdraw`、`POST /documents/{id}/void` |
| 明细 | `POST/PATCH/DELETE /documents/{id}/line-items/{item_id}` |
| 附件 | `POST /documents/{id}/attachments`、`GET /documents/{id}/attachments/{att_id}`、`POST .../parse` |
| 会话 | `POST /review-sessions`、`POST /review-sessions/{id}/messages` |
| 分析 | `POST /documents/{id}/analysis`、`GET /analysis-tasks/{id}`、`GET /analysis-tasks/{id}/findings`、`GET /analysis-tasks/{id}/report` |
| 复核/报告 | `PATCH /risk-findings/{id}/review-status`、`POST /review-reports/{id}/manual-reviews`、`GET /review-reports/{id}/export` |
| 审批 | `GET /approval-tasks`、`POST /approval-tasks/{id}/approve|return|reject` |
| 配置 | `GET/POST/PATCH /approval-workflows`、`GET/POST/PATCH /rules`、`GET /market-prices` |
| 供应商 | `GET /suppliers`、`GET /suppliers/{code}/risks`、`PATCH /suppliers/{code}` |
| 工作台 | `GET /dashboard/summary`、`GET /audit-logs` |

---

## 十、配置项

配置通过环境变量提供，也可复制 [.env.example](.env.example) 为项目根目录的 `.env` 后修改：

```powershell
Copy-Item .env.example .env     # Linux/macOS: cp .env.example .env
```

启动时自动读取 `.env`（`python-dotenv`），已存在的进程环境变量优先级更高。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | `run.py` 启动端口 |
| `RISK_REVIEW_DATABASE_URL` | `sqlite:///data/risk_review.db` | 数据库连接串 |
| `RISK_REVIEW_DATA_DIR` | `./data` | 数据目录 |
| `RISK_REVIEW_STORAGE_DIR` | `./storage` | 附件存储目录 |
| `RISK_REVIEW_SECRET_KEY` | 开发默认值 | JWT 签名密钥，生产必须修改 |
| `RISK_REVIEW_TOKEN_EXPIRE_MINUTES` | `480` | 访问令牌有效期（分钟） |

上传限制：单文件 ≤ 15MB，仅允许 `.pdf`、`.png`、`.jpg`、`.jpeg`。

---

## 十一、实现说明与边界

- 密码使用 PBKDF2-HMAC-SHA256（24 万次迭代 + 随机盐）保存；令牌携带 `jti` 并在数据库登记，支持过期与主动撤销。
- 附件以 SHA-256 命名落盘，下载/预览均校验单据数据权限；前端通过携带令牌的请求获取 Blob 预览，避免直接暴露文件路径。
- 分析任务在后台线程执行，状态依次经过 `queued → querying_document → loading_attachments → parsing_attachments → analyzing → generating_report → succeeded/failed`，前端轮询展示进度。
- 图片 OCR 依赖 `rapidocr-onnxruntime` 内置模型；首次识别会加载模型，耗时会略长。若 OCR 不可用，附件会标记为解析失败并允许人工复核/重试，不影响其他流程。
- 智能分析结论仅作为审批辅助依据，最终审批结果由有权限的人员人工确认。
- 当前为单机演示部署：SQLite + 本地文件 + 内置后台线程。生产环境建议替换为 PostgreSQL、对象存储、任务队列（如 Celery/RQ）与 HTTPS 网关，并修改默认密钥。

---

## 十二、常见问题

**端口被占用（Windows 10013/10048）**

```powershell
$env:PORT=9000
python run.py
```

**需要恢复初始演示数据**

```bash
python scripts/seed_demo.py --reset
```

**只重建表结构、不导入示例单据**

```bash
python scripts/init_db.py --reset
```
