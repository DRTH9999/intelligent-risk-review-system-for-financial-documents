import { api, downloadFile, session } from '../api.js';
import {
  RISK,
  TASK_STATUS,
  confidenceBar,
  docTypeBadge,
  emptyState,
  esc,
  fmtDate,
  fmtDateTime,
  icon,
  loadingBlock,
  money,
  percent,
  pretty,
  recommendationBadge,
  riskBadge,
  statusBadge,
  toast,
} from '../ui.js';

const STEPS = ['querying_document', 'loading_attachments', 'parsing_attachments', 'analyzing', 'generating_report', 'succeeded'];
const REVIEW_STATUS = {
  pending: ['待复核', 'warning'],
  confirmed: ['已确认', 'low'],
  dismissed: ['已忽略', 'neutral'],
};
const FIELD_LABELS = {
  invoice_code: '发票代码',
  invoice_no: '发票号码',
  invoice_date: '开票日期',
  buyer_name: '购买方',
  seller_name: '销售方',
  invoice_total: '价税合计',
  contract_no: '合同编号',
  contract_amount: '合同金额',
  party_b: '乙方',
  payment_ratio: '付款比例',
  payee_name: '收款单位',
  payee_account: '收款账号',
  payment_amount: '付款金额',
};

export async function render(root, ctx) {
  const taskId = Number(ctx.params.taskId);
  const roles = (session.user?.roles || []);
  let canReview = false;
  let timer = null;
  ctx.onCleanup(() => timer && clearInterval(timer));

  root.innerHTML = loadingBlock('正在加载分析结果…');
  let task;
  try {
    task = await api(`/api/v1/analysis-tasks/${taskId}`);
  } catch (error) {
    root.innerHTML = emptyState('分析任务加载失败', error.message, 'alert');
    return;
  }

  ctx.setTitle(`风险分析 · ${task.document?.document_no || ''}`, `${task.document?.document_type || ''} · 任务 #${taskId}`);
  ctx.setActions(`
    <a class="btn btn-ghost" href="#/documents/${task.document?.id}">单据详情</a>
    <button class="btn btn-ghost" data-act="reanalyze">${icon('refresh', 15)} 重新分析</button>
  `);
  const actionBar = document.getElementById('page-actions');
  actionBar.querySelector('[data-act="reanalyze"]').addEventListener('click', () => reanalyze(task.document.id));

  if (task.task_status !== 'succeeded') {
    renderProgress(task);
    if (['queued', 'querying_document', 'loading_attachments', 'parsing_attachments', 'analyzing', 'generating_report'].includes(task.task_status)) {
      timer = setInterval(async () => {
        try {
          const latest = await api(`/api/v1/analysis-tasks/${taskId}`);
          renderProgress(latest);
          if (latest.task_status === 'succeeded') {
            clearInterval(timer);
            timer = null;
            window.dispatchEvent(new HashChangeEvent('hashchange'));
          }
          if (latest.task_status === 'failed') {
            clearInterval(timer);
            timer = null;
          }
        } catch {
          /* ignore */
        }
      }, 1500);
    }
    return;
  }

  let report;
  try {
    report = await api(`/api/v1/analysis-tasks/${taskId}/report`);
  } catch (error) {
    root.innerHTML = emptyState('报告加载失败', error.message, 'alert');
    return;
  }

  canReview = report.can_review === true;
  const summary = report.summary || {};
  const counts = summary.level_counts || {};
  const findings = report.findings || [];
  const amount = report.amount_comparison || {};
  const doc = report.document || {};
  const overall = report.overall_risk_level || 'low';

  ctx.setActions(`
    <a class="btn btn-ghost" href="#/documents/${doc.id}">单据详情</a>
    <button class="btn btn-ghost" data-export="md">${icon('download', 15)} 导出 Markdown</button>
    <button class="btn btn-ghost" data-export="html">${icon('printer', 15)} 导出 HTML</button>
    <button class="btn btn-primary" data-act="reanalyze">${icon('refresh', 15)} 重新分析</button>
  `);
  actionBar.querySelectorAll('[data-export]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await downloadFile(`/api/v1/review-reports/${report.id}/export?format=${button.dataset.export}`, `风险审核报告_${doc.document_no}.${button.dataset.export}`);
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  });
  actionBar.querySelector('[data-act="reanalyze"]').addEventListener('click', () => reanalyze(doc.id));

  const categoryCounts = {};
  findings.forEach((finding) => {
    categoryCounts[finding.risk_category] = (categoryCounts[finding.risk_category] || 0) + 1;
  });
  const maxCategory = Math.max(1, ...Object.values(categoryCounts));

  root.innerHTML = `
    <div class="risk-hero ${overall}" style="margin-bottom:16px">
      <div class="risk-level-badge">
        <b>${RISK[overall]?.short || '低'}</b>
        <span>整体风险</span>
      </div>
      <div class="risk-hero-main">
        <h3>${esc(doc.document_no)} · ${esc(doc.document_type)}</h3>
        <p>申请人 ${esc(doc.applicant_name || '-')} · 预算部门 ${esc(doc.budget_department || '-')} · 金额 ${money(doc.total_amount)} · 附件 ${doc.attachment_count || 0} 个</p>
        <div class="risk-pill-row">
          <span class="risk-pill">高风险 ${counts.high || 0} 项</span>
          <span class="risk-pill">中风险 ${counts.medium || 0} 项</span>
          <span class="risk-pill">低风险 ${counts.low || 0} 项</span>
          <span class="risk-pill">风险评分 ${summary.risk_score || 0}</span>
          <span class="risk-pill">分析时间 ${esc(fmtDateTime(report.created_at))}</span>
        </div>
      </div>
      <div class="risk-hero-actions">
        <div style="text-align:right">
          <div style="font-size:11px;opacity:.75">处理建议</div>
          <div style="font-size:20px;font-weight:800;margin-top:2px">${esc(report.recommendation)}</div>
        </div>
      </div>
    </div>

    <div class="grid" style="grid-template-columns:1.55fr 1fr">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">金额核对面板</div>
            <div class="card-sub">单据金额、明细、发票、合同与付款金额交叉核对</div>
          </div>
          <div class="card-actions">${amountStatusBadge(amount.invoice_status, '发票')}</div>
        </div>
        <div class="card-body">
          <div class="amount-grid" style="grid-template-columns:repeat(5,minmax(0,1fr))">
            <div class="amount-cell">
              <div class="a-label">单据总金额</div>
              <div class="a-value">${money(amount.document_total)}</div>
              <div class="a-diff muted">基准金额</div>
            </div>
            ${(amount.rows || [])
              .map(
                (row) => `<div class="amount-cell ${row.status}">
                  <div class="a-label">${esc(row.label)}</div>
                  <div class="a-value">${row.amount === null || row.amount === undefined ? '—' : money(row.amount)}</div>
                  <div class="a-diff">${diffHTML(row)}</div>
                  ${row.expected_payment ? `<div class="cell-sub">应付 ${money(row.expected_payment)}</div>` : ''}
                  <div class="cell-sub">${esc(row.note || '')}</div>
                </div>`
              )
              .join('')}
          </div>
          <div class="divider"></div>
          <table class="criteria-table">
            <tbody>
              <tr><td>核对结论</td><td>${esc(amountConclusion(amount))}</td></tr>
              <tr><td>发票信息</td><td>${(amount.invoice_numbers || []).length ? esc((amount.invoice_numbers || []).join('、')) : '未识别发票号码'}</td></tr>
              <tr><td>合同信息</td><td>${amount.contract_amount ? `合同金额 ${money(amount.contract_amount)}，按比例应付 ${money(amount.contract_expected_payment)}` : '未识别合同金额'}</td></tr>
              <tr><td>付款信息</td><td>${amount.payment_amount !== null && amount.payment_amount !== undefined ? `本单付款 ${money(amount.payment_amount)}` : '非付款类单据'}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div class="card-title">风险分类统计</div></div>
        <div class="card-body">
          <div class="dist-list">
            ${
              Object.keys(categoryCounts).length
                ? Object.entries(categoryCounts)
                    .map(
                      ([category, count]) => `<div class="dist-row">
                        <span>${esc(category)}</span>
                        <span class="dist-bar"><span style="width:${(count / maxCategory) * 100}%"></span></span>
                        <b style="text-align:right">${count}</b>
                      </div>`
                    )
                    .join('')
                : '<div class="muted small">未发现风险项</div>'
            }
          </div>
          <div class="divider"></div>
          <div class="grid grid-3" style="gap:8px">
            <div class="amount-cell" style="padding:10px"><div class="a-label">高风险</div><div class="a-value" style="color:var(--high);font-size:20px">${counts.high || 0}</div></div>
            <div class="amount-cell" style="padding:10px"><div class="a-label">中风险</div><div class="a-value" style="color:var(--medium);font-size:20px">${counts.medium || 0}</div></div>
            <div class="amount-cell" style="padding:10px"><div class="a-label">低风险</div><div class="a-value" style="color:var(--low);font-size:20px">${counts.low || 0}</div></div>
          </div>
          <div class="divider"></div>
          <div class="supplier-card">
            <div class="supplier-avatar">${esc((report.supplier?.supplier_name || '供').slice(0, 1))}</div>
            <div style="flex:1;min-width:0">
              <div class="cell-main">${esc(report.supplier?.supplier_name || '未关联供应商')}</div>
              <div class="cell-sub">${esc(report.supplier?.supplier_code || '无供应商档案')}</div>
              <div class="tag-row">
                ${report.supplier?.blacklist_status && report.supplier.blacklist_status !== 'normal' ? '<span class="badge badge-high">黑名单</span>' : ''}
                ${(report.supplier?.risk_tags || []).map((tag) => `<span class="tag">${esc(tag)}</span>`).join('')}
                ${report.supplier ? `<span class="tag">历史付款 ${report.supplier.payment_count} 笔</span>` : ''}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head">
        <div>
          <div class="card-title">风险项明细（${findings.length}）</div>
          <div class="card-sub">每项风险均展示实际值、参考值、规则阈值与证据来源</div>
        </div>
      </div>
      <div class="card-body">
        ${
          findings.length
            ? findings
                .map((finding, index) => findingHTML(finding, index, canReview, doc.id, report.snapshot_status === 'complete' ? taskId : null))
                .join('')
            : emptyState('未发现风险项', '该单据通过全部规则校验', 'checkSquare')
        }
      </div>
    </div>

    <div class="grid grid-2" style="margin-top:16px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">人工复核记录</div>
            <div class="card-sub">复核结果将记录复核人、意见与时间</div>
          </div>
        </div>
        <div class="card-body">
          ${
            canReview
              ? `<div class="manual-review-form">
                  <div class="field" style="margin-bottom:10px">
                    <label>复核结论</label>
                    <select id="review-result">
                      ${['建议通过', '补充材料', '人工复核', '建议驳回'].map((item) => `<option value="${item}">${item}</option>`).join('')}
                    </select>
                  </div>
                  <div class="field">
                    <label>复核意见</label>
                    <textarea id="review-comment" placeholder="填写复核依据、补充材料要求或驳回原因"></textarea>
                  </div>
                  <div style="margin-top:10px;display:flex;justify-content:flex-end">
                    <button class="btn btn-primary btn-sm" id="btn-submit-review">提交复核意见</button>
                  </div>
                </div>`
              : '<p class="muted small">此报告当前不可复核，请在审批中的最新版本处理。</p>'
          }
          <div class="review-history" style="margin-top:14px" id="review-history">
            ${
              (report.manual_reviews || []).length
                ? report.manual_reviews
                    .map(
                      (review) => `<div class="review-entry">
                        <div><b>${esc(review.reviewer_name || '-')}</b> ${recommendationBadge(review.review_result)}</div>
                        <div style="margin-top:4px">${esc(review.review_comment || '无复核意见')}</div>
                        <div class="re-meta">${esc(fmtDateTime(review.reviewed_at))}</div>
                      </div>`
                    )
                    .join('')
                : '<p class="muted small">暂无人工复核记录。</p>'
            }
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">报告与审计</div>
            <div class="card-sub">报告编号 RPT-${String(report.id).padStart(6, '0')}</div>
          </div>
        </div>
        <div class="card-body">
          <div class="kv-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
            <div class="kv"><div class="k">分析任务</div><div class="v">#${report.task_id}</div></div>
            <div class="kv"><div class="k">报告状态</div><div class="v">已生成</div></div>
            <div class="kv"><div class="k">风险评分</div><div class="v">${summary.risk_score || 0}</div></div>
            <div class="kv"><div class="k">处理建议</div><div class="v">${esc(report.recommendation)}</div></div>
            <div class="kv full"><div class="k">报告摘要</div><div class="v" style="font-weight:400">${esc((summary.top_risks || []).map((item) => item.risk_title).join('；') || '未发现风险项')}</div></div>
          </div>
          <div style="display:flex;gap:9px;margin-top:14px;flex-wrap:wrap">
            <a class="btn btn-ghost btn-sm" href="#/documents/${doc.id}">查看单据</a>
            <a class="btn btn-ghost btn-sm" href="#/records">审核记录</a>
            ${canReview ? `<a class="btn btn-ghost btn-sm" href="#/approvals">审批任务</a>` : ''}
          </div>
          <p class="small muted" style="margin-top:14px;line-height:1.8">智能分析结果仅作为审批辅助依据，最终审批结果需由有权限的审批人员人工确认。所有金额对比、规则判断与风险结论均保留数据来源与审计记录。</p>
        </div>
      </div>
    </div>`;

  root.querySelectorAll('.finding-head').forEach((head) => {
    head.addEventListener('click', () => {
      head.closest('.finding').classList.toggle('open');
    });
  });

  if (doc.snapshot_warning || summary.coverage_warning) {
    root.insertAdjacentHTML('afterbegin', `<div class="card" style="padding:16px;margin-bottom:16px;color:#9a6518">${esc(doc.snapshot_warning || summary.coverage_warning)}</div>`);
  }
  const reanalyzeButton = document.getElementById('page-actions')?.querySelector('[data-act="reanalyze"]');
  if (reanalyzeButton && !report.can_analyze) reanalyzeButton.hidden = true;

  if (canReview) {
    root.querySelectorAll('[data-review-status]').forEach((button) => {
      button.addEventListener('click', async () => {
        const findingId = button.dataset.finding;
        const target = button.dataset.reviewStatus;
        const comment = window.prompt('请填写本次风险处理的依据（至少2个字）');
        if (!comment || comment.trim().length < 2) return;
        button.disabled = true;
        try {
          await api(`/api/v1/risk-findings/${findingId}/review-status`, {
            method: 'PATCH',
            body: { review_status: target, comment },
          });
          toast('风险项复核状态已更新', 'success');
          window.dispatchEvent(new HashChangeEvent('hashchange'));
        } catch (error) {
          toast(error.message, 'error');
          button.disabled = false;
        }
      });
    });

    const submitReview = root.querySelector('#btn-submit-review');
    submitReview.addEventListener('click', async () => {
      const result = root.querySelector('#review-result').value;
      const comment = root.querySelector('#review-comment').value.trim();
      if (comment.length < 2) {
        toast('请填写复核意见', 'warning');
        return;
      }
      submitReview.disabled = true;
      try {
        await api(`/api/v1/review-reports/${report.id}/manual-reviews`, {
          method: 'POST',
          body: { review_result: result, review_comment: comment || null },
        });
        toast('人工复核意见已提交', 'success');
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      } catch (error) {
        toast(error.message, 'error');
        submitReview.disabled = false;
      }
    });
  }

  function reanalyze(docId) {
    showConfirmReanalyze(docId);
  }

  async function showConfirmReanalyze(docId) {
    const button = document.getElementById('page-actions')?.querySelector('[data-act="reanalyze"]');
    if (button) button.disabled = true;
    try {
      const created = await api(`/api/v1/documents/${docId}/analysis`, { method: 'POST', body: {} });
      toast('已创建新的分析任务', 'success');
      window.location.hash = `#/analysis/${created.id}`;
    } catch (error) {
      toast(error.message, 'error');
      if (button) button.disabled = false;
    }
  }
}

function amountStatusBadge(status, label) {
  const map = {
    ok: ['low', '一致'],
    warning: ['medium', '存在差异'],
    error: ['high', '严重差异'],
    missing: ['neutral', '缺少数据'],
  };
  const [cls, text] = map[status] || ['neutral', '未核对'];
  return `<span class="badge badge-${cls}">${label}${text}</span>`;
}

function diffHTML(row) {
  if (row.amount === null || row.amount === undefined) return '<span class="muted">—</span>';
  if (!row.difference) return '<span class="diff-zero">无差异</span>';
  const cls = row.status === 'ok' ? 'diff-zero' : row.status === 'warning' ? 'diff-pos' : 'diff-neg';
  const sign = row.difference > 0 ? '+' : '';
  return `<span class="${cls}">${sign}${money(row.difference)}（${percent(row.difference_pct)}）</span>`;
}

function amountConclusion(amount) {
  const rows = amount.rows || [];
  const issues = rows.filter((row) => ['warning', 'error'].includes(row.status));
  if (!issues.length) return '各金额来源核对一致，未发现金额差异。';
  return issues.map((row) => `${row.label}${row.status === 'error' ? '存在严重差异' : '存在差异'}（${percent(row.difference_pct)}）`).join('；') + '。';
}

function findingHTML(finding, index, canReview, documentId, taskId) {
  const level = finding.risk_level;
  const reviewMeta = REVIEW_STATUS[finding.review_status] || ['待复核', 'warning'];
  const evidence = finding.evidence || [];
  return `<div class="finding ${level} ${index === 0 && level === 'high' ? 'open' : ''}">
    <div class="finding-head">
      <div style="flex:1;min-width:0">
        <div class="f-title">${index + 1}. ${esc(finding.risk_title)}</div>
        <div class="f-desc">${esc(finding.description)}</div>
      </div>
      <div class="f-right">
        <span class="badge badge-neutral">${esc(finding.risk_category)}</span>
        ${riskBadge(level)}
        <span class="badge badge-${reviewMeta[1]}">${reviewMeta[0]}</span>
        ${icon('chevronDown', 16, 'style="color:#9aa6bd"')}
      </div>
    </div>
    <div class="finding-body">
      <div class="finding-block">
        <div class="fb-label">风险描述</div>
        ${esc(finding.description)}
      </div>
      <div class="grid grid-2" style="gap:10px;margin-top:10px">
        <div class="finding-block">
          <div class="fb-label">处理建议</div>
          ${esc(finding.suggestion_text || '-')}
        </div>
        <div class="finding-block">
          <div class="fb-label">风险类型</div>
          <span class="mono">${esc(finding.risk_type)}</span>
        </div>
      </div>
      <div class="grid grid-3" style="gap:10px;margin-top:10px">
        <div class="finding-block"><div class="fb-label">实际值</div><pre class="pre" style="margin:0;font-size:11.5px">${esc(pretty(finding.actual_value))}</pre></div>
        <div class="finding-block"><div class="fb-label">参考值</div><pre class="pre" style="margin:0;font-size:11.5px">${esc(pretty(finding.reference_value))}</pre></div>
        <div class="finding-block"><div class="fb-label">规则阈值</div><pre class="pre" style="margin:0;font-size:11.5px">${esc(pretty(finding.threshold))}</pre></div>
      </div>
      <div class="finding-evidence">
        <div class="fb-label" style="font-size:10.5px;font-weight:700;color:var(--text-3);letter-spacing:.5px">证据与原文定位</div>
        ${
          evidence.length
            ? evidence
                .slice(0, 8)
                .map((item) => {
                  const link =
                    taskId && item.attachment_id && item.source_type === 'attachment'
                      ? `<a class="btn btn-sm btn-ghost" href="#/attachments/${documentId}/${item.attachment_id}?task_id=${taskId}" style="margin-left:auto">查看原文</a>`
                      : '';
                  return `<div class="evidence-row" style="cursor:default">
                    <span class="ev-source">${esc(sourceLabel(item.source_type))}</span>
                    <div style="flex:1;min-width:0">
                      <div style="font-size:12px">${esc(item.attachment_name || item.document_no || item.item_name || item.supplier_name || item.field || '-')}</div>
                      <div class="cell-sub">${item.page ? `第 ${item.page} 页 · ` : ''}${esc(item.snippet || item.payee_name || item.expense_location || '')}</div>
                    </div>
                    ${item.confidence !== undefined ? confidenceBar(item.confidence) : ''}
                    ${link}
                  </div>`;
                })
                .join('')
            : '<span class="muted small">无结构化证据</span>'
        }
      </div>
      ${
        canReview
          ? `<div class="review-actions">
              <span class="small muted">人工复核：</span>
              <button class="btn btn-sm btn-ghost" data-finding="${finding.id}" data-review-status="confirmed">确认风险</button>
              <button class="btn btn-sm btn-ghost" data-finding="${finding.id}" data-review-status="dismissed">忽略风险</button>
              <button class="btn btn-sm btn-ghost" data-finding="${finding.id}" data-review-status="pending">重置</button>
            </div>`
          : ''
      }
    </div>
  </div>`;
}

function sourceLabel(type) {
  return (
    {
      attachment: '附件',
      line_item: '明细',
      database: '历史单据',
      supplier: '供应商',
      market_price: '市场价',
      document: '单据',
    }[type] || type || '证据'
  );
}

function renderProgress(task) {
  const root = document.getElementById('page-content');
  if (!root) return;
  const steps = STEPS.map((step) => {
    const index = STEPS.indexOf(step);
    const currentIndex = STEPS.indexOf(task.current_step);
    const cls = task.task_status === 'succeeded' ? 'done' : index < currentIndex ? 'done' : step === task.current_step ? 'active' : '';
    return `<span class="step-chip ${cls}">${esc(TASK_STATUS[step] || step)}</span>`;
  }).join('');
  root.innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">${task.task_status === 'failed' ? '分析失败' : '智能分析进行中'}</div>
          <div class="card-sub">任务 #${task.id} · 单据 ${esc(task.document?.document_no || '')} · ${esc(task.document?.document_type || '')}</div>
        </div>
        <div class="card-actions"><span class="badge badge-${task.task_status === 'failed' ? 'high' : 'info'}">${esc(TASK_STATUS[task.task_status] || task.task_status)}</span></div>
      </div>
      <div class="card-body">
        <div class="progress" style="height:9px"><div class="progress-bar" style="width:${task.progress || 0}%"></div></div>
        <div style="display:flex;justify-content:space-between;margin-top:8px" class="small muted">
          <span>当前步骤：${esc(TASK_STATUS[task.current_step] || task.current_step)}</span>
          <span>${task.progress || 0}%</span>
        </div>
        <div class="steps" style="margin-top:16px">${steps}</div>
        <div class="divider"></div>
        <div class="grid grid-3">
          <div class="amount-cell"><div class="a-label">单据金额</div><div class="a-value" style="font-size:16px">${money(task.document?.total_amount)}</div></div>
          <div class="amount-cell"><div class="a-label">分析任务</div><div class="a-value" style="font-size:16px">#${task.id}</div></div>
          <div class="amount-cell"><div class="a-label">触发时间</div><div class="a-value" style="font-size:14px">${esc(fmtDateTime(task.started_at))}</div></div>
        </div>
        ${
          task.error_message
            ? `<div class="finding-block" style="margin-top:14px;border-color:#f3c6c8;background:#fffafa"><div class="fb-label">失败原因</div>${esc(task.error_message)}</div>`
            : ''
        }
        <div style="margin-top:16px;display:flex;gap:10px">
          <a class="btn btn-ghost btn-sm" href="#/documents/${task.document?.id}">查看单据</a>
          ${task.task_status === 'failed' ? `<button class="btn btn-primary btn-sm" data-retry>重新分析</button>` : '<span class="small muted">页面每 1.5 秒自动刷新进度</span>'}
        </div>
      </div>
    </div>`;
  const retry = root.querySelector('[data-retry]');
  if (retry) {
    retry.addEventListener('click', async () => {
      retry.disabled = true;
      try {
        const created = await api(`/api/v1/documents/${task.document.id}/analysis`, { method: 'POST', body: {} });
        window.location.hash = `#/analysis/${created.id}`;
      } catch (error) {
        toast(error.message, 'error');
        retry.disabled = false;
      }
    });
  }
}

function fieldLabel(key) {
  return FIELD_LABELS[key] || key;
}
