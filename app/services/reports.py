"""风险报告渲染：Markdown 与 HTML 导出。"""
from __future__ import annotations

import html
import json
import re
from typing import Any

from app.utils import money_text

LEVEL_NAMES = {"high": "高", "medium": "中", "low": "低"}


def _md_cell(value: Any) -> str:
    text = str(value if value is not None else "-")
    return text.replace("|", "\\|").replace("\n", " ")


def build_markdown(
    *,
    report_id: int,
    document: dict,
    findings: list[dict],
    summary: dict,
    amount: dict,
    recommendation: str,
    supplier: dict | None,
    manual_reviews: list[dict],
    generated_at: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# 财务单据风险审核报告")
    lines.append("")
    lines.append(f"> 报告编号：RPT-{report_id:06d}　生成时间：{generated_at}")
    lines.append("")

    lines.append("## 一、单据摘要")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    summary_rows = [
        ("单据类型", document.get("document_type")),
        ("单据编号", document.get("document_no")),
        ("申请人", document.get("applicant_name")),
        ("申请部门", document.get("applicant_department")),
        ("预算部门", document.get("budget_department")),
        ("收款单位", document.get("payee_name")),
        ("费用类别", document.get("expense_category")),
        ("总金额", money_text(document.get("total_amount"))),
        ("申请日期", document.get("apply_date")),
        ("附件数量", f"{len(document.get('attachments') or [])} 个"),
    ]
    for key, value in summary_rows:
        lines.append(f"| {_md_cell(key)} | {_md_cell(value)} |")
    lines.append("")

    lines.append("## 二、整体风险")
    lines.append("")
    counts = summary.get("level_counts", {})
    lines.append(f"- **整体风险等级**：{LEVEL_NAMES.get(summary.get('overall_risk_level'), summary.get('overall_risk_level'))}")
    lines.append(f"- **风险数量**：高 {counts.get('high', 0)} 项 / 中 {counts.get('medium', 0)} 项 / 低 {counts.get('low', 0)} 项")
    lines.append(f"- **审核建议**：{recommendation}")
    lines.append(f"- **风险评分**：{summary.get('risk_score', 0)}")
    lines.append("")

    lines.append("## 三、金额核对")
    lines.append("")
    lines.append("| 核对项 | 金额 | 差异 | 差异比例 | 结论 |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    lines.append(f"| 单据总金额 | {money_text(amount.get('document_total'))} | - | - | 基准 |")
    lines.append(
        f"| 明细合计 | {_money_dash(amount.get('line_items_total'), amount.get('line_items_status'))} | "
        f"{_diff_dash(amount.get('line_items_difference'), amount.get('line_items_status'))} | "
        f"{amount.get('line_items_difference_pct', 0)}% | {_status_text(amount.get('line_items_status'))} |"
    )
    lines.append(
        f"| 发票合计 | {_money_dash(amount.get('invoice_total'), amount.get('invoice_status'))} | "
        f"{_diff_dash(amount.get('invoice_difference'), amount.get('invoice_status'))} | "
        f"{amount.get('invoice_difference_pct', 0)}% | {_status_text(amount.get('invoice_status'))} |"
    )
    lines.append(
        f"| 合同金额 | {_money_dash(amount.get('contract_amount'), amount.get('contract_status'))} | "
        f"{_diff_dash(amount.get('contract_difference'), amount.get('contract_status'))} | "
        f"{amount.get('contract_difference_pct', 0)}% | {_status_text(amount.get('contract_status'))} |"
    )
    lines.append(
        f"| 付款金额 | {_money_dash(amount.get('payment_amount'), amount.get('payment_status'))} | "
        f"{_diff_dash(amount.get('payment_difference'), amount.get('payment_status'))} | "
        f"{amount.get('payment_difference_pct', 0)}% | {_status_text(amount.get('payment_status'))} |"
    )
    lines.append("")

    lines.append("## 四、风险项列表")
    lines.append("")
    if not findings:
        lines.append("未发现风险项。")
        lines.append("")
    for index, finding in enumerate(findings, start=1):
        level = LEVEL_NAMES.get(finding["risk_level"], finding["risk_level"])
        lines.append(f"### {index}. [{level}] {finding['risk_title']}")
        lines.append("")
        lines.append(f"- **风险类型**：{finding['risk_type']}（{finding['risk_category']}）")
        lines.append(f"- **风险描述**：{finding['description']}")
        lines.append(f"- **实际值**：`{_compact(finding.get('actual_value'))}`")
        lines.append(f"- **参考值**：`{_compact(finding.get('reference_value'))}`")
        lines.append(f"- **规则阈值**：`{_compact(finding.get('threshold'))}`")
        lines.append(f"- **处理建议**：{finding.get('suggestion_text') or '-'}")
        lines.append("")

    lines.append("## 五、证据列表")
    lines.append("")
    evidence_rows: list[list[str]] = []
    for finding in findings:
        for ev in finding.get("evidence") or []:
            evidence_rows.append(
                [
                    ev.get("source_type") or "-",
                    ev.get("attachment_name") or ev.get("document_no") or ev.get("supplier_name") or "-",
                    str(ev.get("page") or "-"),
                    (ev.get("snippet") or ev.get("item_name") or ev.get("field") or "-")[:80],
                    ev.get("field") or "-",
                    f"{float(ev.get('confidence') or 0):.0%}" if ev.get("confidence") is not None else "-",
                ]
            )
    if evidence_rows:
        lines.append("| 来源类型 | 来源 | 页码 | 原文/字段片段 | 字段 | 置信度 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in evidence_rows[:80]:
            lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    else:
        lines.append("暂无证据数据。")
    lines.append("")

    lines.append("## 六、供应商风险")
    lines.append("")
    if supplier:
        lines.append(f"- **供应商**：{supplier.get('supplier_name')}（{supplier.get('supplier_code')}）")
        lines.append(f"- **信用状态**：{supplier.get('credit_status')}")
        lines.append(f"- **黑名单状态**：{supplier.get('blacklist_status')}")
        lines.append(f"- **风险标签**：{'、'.join(supplier.get('risk_tags') or []) or '无'}")
        lines.append(f"- **备案账号**：{'、'.join(supplier.get('bank_accounts') or []) or '未备案'}")
        lines.append(f"- **历史付款**：{supplier.get('payment_count', 0)} 笔，合计 {money_text(supplier.get('payment_total'))}")
    else:
        lines.append("本单未关联供应商档案。")
    lines.append("")

    lines.append("## 七、处理建议")
    lines.append("")
    lines.append(f"**{recommendation}**。智能分析结果仅作为审批辅助依据，最终审批结果需由有权限的审批人员人工确认。")
    lines.append("")

    lines.append("## 八、人工复核")
    lines.append("")
    if manual_reviews:
        for review in manual_reviews:
            lines.append(
                f"- {review.get('reviewed_at')}　{review.get('reviewer_name')}　**{review.get('review_result')}**　{review.get('review_comment') or ''}"
            )
    else:
        lines.append("暂无人工复核记录。")
    lines.append("")
    return "\n".join(lines)


def _status_text(status: str | None) -> str:
    return {"ok": "一致", "warning": "存在差异", "error": "严重差异", "missing": "缺少数据"}.get(status or "", "未核对")


def _money_dash(value: Any, status: str | None = None) -> str:
    if value is None or status == "missing":
        return "—"
    return money_text(value)


def _diff_dash(value: Any, status: str | None = None) -> str:
    if value is None or status == "missing":
        return "—"
    if abs(float(value)) < 0.005:
        return "¥0.00"
    return money_text(value)


def _compact(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)[:400]
    return str(value)[:400]


def markdown_to_html(markdown: str, title: str = "财务单据风险审核报告") -> str:
    body = _render_markdown(markdown)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 48px 24px; background: #f3f5f9; color: #1d2433;
         font-family: "Microsoft YaHei", "PingFang SC", -apple-system, sans-serif; line-height: 1.8; }}
  article {{ max-width: 980px; margin: 0 auto; background: #fff; padding: 48px 56px;
             border-radius: 16px; box-shadow: 0 18px 48px rgba(24, 40, 72, .12); }}
  h1 {{ font-size: 28px; margin: 0 0 12px; }}
  h2 {{ font-size: 20px; margin: 36px 0 12px; padding-bottom: 8px; border-bottom: 1px solid #e6eaf2; }}
  h3 {{ font-size: 16px; margin: 24px 0 8px; }}
  blockquote {{ margin: 0 0 24px; padding: 10px 16px; background: #f5f8ff; border-left: 3px solid #3b6ef6;
                color: #506080; border-radius: 6px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 14px 0 22px; font-size: 13px; }}
  th, td {{ border: 1px solid #e6eaf2; padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f7f9fd; font-weight: 600; }}
  code {{ background: #f1f4fa; padding: 1px 6px; border-radius: 4px; font-size: 12px;
          font-family: Consolas, monospace; word-break: break-all; }}
  ul {{ padding-left: 22px; }}
  li {{ margin: 4px 0; }}
  strong {{ color: #0f1b33; }}
  @media print {{ body {{ background: #fff; padding: 0; }} article {{ box-shadow: none; padding: 0; }} }}
</style>
</head>
<body>
<article>
{body}
</article>
</body>
</html>"""


def _render_markdown(markdown: str) -> str:
    lines = markdown.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("| "):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            output.append(_render_table(table_lines))
            continue
        if stripped.startswith("### "):
            output.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            output.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            output.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("> "):
            output.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
        elif stripped.startswith("- "):
            items = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(f"<li>{_inline(lines[index].strip()[2:])}</li>")
                index += 1
            output.append("<ul>" + "".join(items) + "</ul>")
            continue
        else:
            output.append(f"<p>{_inline(stripped)}</p>")
        index += 1
    return "\n".join(output)


def _render_table(table_lines: list[str]) -> str:
    rows = []
    for line in table_lines:
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        rows.append(cells)
    if not rows:
        return ""
    head, *body = rows
    html_rows = ["<thead><tr>" + "".join(f"<th>{_inline(cell)}</th>" for cell in head) + "</tr></thead>"]
    html_rows.append(
        "<tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in body) + "</tbody>"
    )
    return "<table>" + "".join(html_rows) + "</table>"


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped
