import { api } from '../api.js';
import {
  RISK,
  emptyState,
  esc,
  fmtDate,
  fmtDateTime,
  icon,
  loadingBlock,
  money,
  percent,
  recommendationBadge,
  riskBadge,
  statusBadge,
  taskStatusBadge,
  toast,
} from '../ui.js';

export async function render(root, ctx) {
  const taskId = Number(ctx.params.taskId);
  root.innerHTML = loadingBlock('正在加载审批任务…');
  let data;
  try {
    data = await api(`/api/v1/approval-tasks/${taskId}`);
  } catch (error) {
    root.innerHTML = emptyState('审批任务加载失败', error.message, 'alert');
    return;
  }

  const document = data.document || {};
  const report = data.report;
  const findings = data.findings || [];
  const summary = report?.risk_summary || {};
  const counts = summary.level_counts || {};
  const amount = report?.amount_comparison || {};
  const approval = document.approval;
  const node = (approval?.nodes || []).find((item) => item.node_id === data.node_id);
  const pending = data.task_status === 'pending';

  ctx.setTitle(`审批处理 · ${document.document_no}`, `${document.document_type} · ${node?.node_name || '审批节点'} · ${fmtDateTime(data.created_at)}`);
  ctx.setActions(`
    <a class="btn btn-ghost" href="#/approvals">返回任务列表</a>
    <a class="btn btn-ghost" href="#/documents/${document.id}">查看单据</a>
    ${data.analysis_task_id ? `<a class="btn btn-primary" href="#/analysis/${data.analysis_task_id}">完整风险分析</a>` : ''}
  `);

  root.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <div class="card-body" style="padding-top:18px">
        <div class="doc-hero">
          <div>
            <div class="doc-id">审批节点 · ${esc(node?.node_name || '-')}</div>
            <div class="doc-no">${esc(document.document_no)}</div>
            <div class="doc-tags">
              ${statusBadge(document.document_status)}
              ${taskStatusBadge(data.task_status)}
              ${report ? riskBadge(report.overall_risk_level) : '<span class="badge badge-neutral">待分析</span>'}
              ${report ? recommendationBadge(report.recommendation) : ''}
              <span class="tag">申请人 ${esc(document.applicant_name || '-')}</span>
              <span class="tag">${esc(document.document_type)}</span>
            </div>
          </div>
          <div class="amount-hero">
            <div class="label">单据金额</div>
            <div class="value">${money(document.total_amount)}</div>
            <div class="small muted">${esc(document.budget_department || '')} · ${fmtDate(document.apply_date)}</div>
          </div>
        </div>
      </div>
    </div>

    ${
      report
        ? `<div class="risk-hero ${report.overall_risk_level}" style="margin-bottom:16px">
            <div class="risk-level-badge"><b>${RISK[report.overall_risk_level]?.short || '低'}</b><span>整体风险</span></div>
            <div class="risk-hero-main">
              <h3>智能审核结论：${esc(report.recommendation)}</h3>
              <p>高风险 ${counts.high || 0} 项 · 中风险 ${counts.medium || 0} 项 · 低风险 ${counts.low || 0} 项 · 风险评分 ${summary.risk_score || 0}</p>
              <div class="risk-pill-row">
                ${(summary.top_risks || []).map((item) => `<span class="risk-pill">${esc(item.risk_title)}</span>`).join('')}
              </div>
            </div>
            <div class="risk-hero-actions">
              <a class="btn" href="#/analysis/${data.analysis_task_id}">查看证据与报告</a>
            </div>
          </div>`
        : `<div class="card" style="margin-bottom:16px"><div class="card-body">${emptyState('该单据尚未完成风险分析', '建议先等待分析完成或重新发起分析后再处理审批', 'clock')}</div></div>`
    }

    <div class="grid" style="grid-template-columns:1.4fr 1fr">
      <div class="card">
        <div class="card-head">
          <div class="card-title">风险项摘要</div>
          <div class="card-actions"><span class="badge badge-neutral">${findings.length} 项</span></div>
        </div>
        <div class="card-body">
          ${
            findings.length
              ? `<div style="display:flex;flex-direction:column;gap:8px">
                  ${findings
                    .slice(0, 8)
                    .map(
                      (finding) => `<div style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--${finding.risk_level === 'high' ? 'high' : finding.risk_level === 'medium' ? 'medium' : 'low'});border-radius:8px">
                        <div style="flex:1;min-width:0">
                          <div style="font-size:13px;font-weight:600">${esc(finding.risk_title)}</div>
                          <div class="small muted" style="margin-top:2px">${esc(finding.description)}</div>
                        </div>
                        ${riskBadge(finding.risk_level)}
                      </div>`
                    )
                    .join('')}
                </div>
                ${findings.length > 8 ? `<p class="small muted" style="margin-top:10px">仅展示前 8 项，完整风险项请查看风险分析报告。</p>` : ''}`
              : emptyState('未发现风险项', '该单据通过全部规则校验', 'checkSquare')
          }
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div class="card-title">金额核对</div></div>
        <div class="card-body">
          <table class="criteria-table">
            <tbody>
              <tr><td>单据金额</td><td><b>${money(amount.document_total)}</b></td></tr>
              ${(amount.rows || [])
                .map(
                  (row) => `<tr><td>${esc(row.label)}</td><td>${row.amount === null || row.amount === undefined ? '—' : money(row.amount)}
                    ${row.difference ? `<span class="${row.status === 'error' ? 'diff-neg' : 'diff-pos'}" style="margin-left:8px">${row.difference > 0 ? '+' : ''}${money(row.difference)}</span>` : ''}</td></tr>`
                )
                .join('')}
            </tbody>
          </table>
          <div class="divider"></div>
          <div class="kv-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
            <div class="kv"><div class="k">收款单位</div><div class="v">${esc(document.payee_name || '-')}</div></div>
            <div class="kv"><div class="k">费用类别</div><div class="v">${esc(document.expense_category || '-')}</div></div>
            <div class="kv"><div class="k">预算部门</div><div class="v">${esc(document.budget_department || '-')}</div></div>
            <div class="kv"><div class="k">附件数量</div><div class="v">${(document.attachments || []).length} 个</div></div>
            <div class="kv full"><div class="k">申请事由</div><div class="v" style="font-weight:400">${esc(document.reason_text || '-')}</div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid" style="grid-template-columns:1fr 1.25fr;margin-top:16px">
      <div class="card">
        <div class="card-head"><div class="card-title">审批进度</div></div>
        <div class="card-body">
          ${
            approval
              ? `<div class="timeline">
                  ${(approval.nodes || [])
                    .map((item) => {
                      const cls = item.task_status === 'approved' ? 'done' : ['returned', 'rejected'].includes(item.task_status) ? 'fail' : approval.current_node_id === item.node_id ? 'current' : '';
                      return `<div class="timeline-item ${cls}">
                        <div class="tl-title">${esc(item.node_name)} ${taskStatusBadge(item.task_status)}</div>
                        <div class="tl-meta">审批人 ${esc(item.approver_name || '待分配')} · ${esc(item.approver_role)}</div>
                        ${item.review_comment ? `<div class="tl-body">${esc(item.review_comment)}</div>` : ''}
                      </div>`;
                    })
                    .join('')}
                </div>`
              : emptyState('审批流程加载失败')
          }
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">${pending ? '提交审批结果' : '审批结果'}</div>
            <div class="card-sub">${pending ? '请在查阅风险分析后提交处理意见' : '该任务已处理，结果不可再次修改'}</div>
          </div>
        </div>
        <div class="card-body">
          ${
            pending
              ? `<div class="field">
                  <label>审批意见</label>
                  <textarea id="approval-comment" placeholder="请填写审批依据，至少2个字；高风险单据通过前需先完成人工复核">${esc(data.review_comment || '')}</textarea>
                </div>
                <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
                  <button class="btn btn-primary" data-action="approve">${icon('check', 15)} 通过</button>
                  <button class="btn btn-ghost" data-action="return">${icon('refresh', 15)} 退回修改</button>
                  <button class="btn btn-danger" data-action="reject">${icon('xCircle', 15)} 驳回单据</button>
                </div>
                <p class="small muted" style="margin-top:12px">审批结果会记录操作人、时间与意见，并写入操作审计日志。</p>`
              : `<div class="kv-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
                  <div class="kv"><div class="k">任务状态</div><div class="v">${taskStatusBadge(data.task_status)}</div></div>
                  <div class="kv"><div class="k">处理时间</div><div class="v">${esc(fmtDateTime(data.processed_at))}</div></div>
                  <div class="kv full"><div class="k">审批意见</div><div class="v" style="font-weight:400">${esc(data.review_comment || '无')}</div></div>
                </div>`
          }
        </div>
      </div>
    </div>`;

  if (pending) {
    root.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const action = button.dataset.action;
        const comment = root.querySelector('#approval-comment').value.trim();
        if (comment.length < 2) {
          toast('请填写至少2个字的审批意见', 'warning');
          return;
        }
        const label = { approve: '通过', return: '退回', reject: '驳回' }[action];
        if (action !== 'approve') {
          const ok = window.confirm(`确认${label}单据 ${document.document_no} 吗？`);
          if (!ok) return;
        }
        button.disabled = true;
        try {
          await api(`/api/v1/approval-tasks/${taskId}/${action}`, { method: 'POST', body: { comment: comment || null } });
          toast(`审批结果已提交：${label}`, 'success');
          window.location.hash = '#/approvals';
        } catch (error) {
          toast(error.message, 'error');
          button.disabled = false;
        }
      });
    });
  }
}
