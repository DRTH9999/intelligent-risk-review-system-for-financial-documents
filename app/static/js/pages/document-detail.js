import { api, downloadFile } from '../api.js';
import {
  RISK,
  TASK_STATUS,
  confirmDialog,
  docTypeBadge,
  emptyState,
  esc,
  fileSize,
  fmtDate,
  fmtDateTime,
  icon,
  loadingBlock,
  money,
  parseBadge,
  recommendationBadge,
  riskBadge,
  statusBadge,
  taskStatusBadge,
  toast,
} from '../ui.js';

export async function render(root, ctx) {
  const docId = Number(ctx.params.id);
  root.innerHTML = loadingBlock('正在加载单据详情…');
  let doc;
  try {
    doc = await api(`/api/v1/documents/${docId}`);
  } catch (error) {
    root.innerHTML = emptyState('单据加载失败', error.message, 'alert');
    return;
  }

  ctx.setTitle(doc.document_no, `${doc.document_type} · 申请人 ${doc.applicant_name || '-'} · ${doc.budget_department || ''}`);
  const latest = doc.latest_task;
  const report = doc.latest_report;
  const reportSummary = report?.risk_summary || {};
  const counts = reportSummary.level_counts || {};
  const actions = doc.allowed_actions || [];

  const actionButtons = [
    actions.includes('edit') ? `<a class="btn btn-ghost" href="#/documents/${doc.id}/edit">${icon('edit', 15)} 编辑</a>` : '',
    actions.includes('submit') ? `<button class="btn btn-primary" data-act="submit">${icon('send', 15)} 提交审批</button>` : '',
    actions.includes('withdraw') ? `<button class="btn btn-ghost" data-act="withdraw">${icon('refresh', 15)} 撤回</button>` : '',
    actions.includes('copy') ? `<button class="btn btn-ghost" data-act="copy">${icon('layers', 15)} 复制</button>` : '',
    actions.includes('void') ? `<button class="btn btn-ghost" data-act="void">${icon('xCircle', 15)} 作废</button>` : '',
    `<button class="btn btn-ghost" data-act="analyze">${icon('sparkles', 15)} 重新分析</button>`,
  ]
    .filter(Boolean)
    .join('');
  ctx.setActions(`<a class="btn btn-ghost" href="#/documents">返回列表</a>${actionButtons}`);

  const typeFields = [];
  if (doc.contract_no) typeFields.push(['合同编号', doc.contract_no]);
  if (doc.supplier_name) typeFields.push(['供应商名称', doc.supplier_name]);
  if (doc.supplier_code) typeFields.push(['供应商编码', doc.supplier_code]);
  if (doc.payment_ratio !== null && doc.payment_ratio !== undefined) typeFields.push(['付款比例', `${doc.payment_ratio}%`]);
  if (doc.planned_payment_date) typeFields.push(['计划付款日期', fmtDate(doc.planned_payment_date)]);
  if (doc.batch_total_amount !== null && doc.batch_total_amount !== undefined) typeFields.push(['批次总金额', money(doc.batch_total_amount)]);
  if (doc.batch_payment_count) typeFields.push(['付款笔数', `${doc.batch_payment_count} 笔`]);
  if (doc.travel_location) typeFields.push(['出差地点', doc.travel_location]);
  if (doc.travel_start_date) typeFields.push(['出差起止', `${fmtDate(doc.travel_start_date)} 至 ${fmtDate(doc.travel_end_date)}`]);
  if (doc.payment_terms) typeFields.push(['付款条件', doc.payment_terms]);

  const approval = doc.approval;
  const approvalNodes = approval?.nodes || [];

  const tabs = [
    ['basic', '基本信息', 'fileText'],
    ['items', `明细（${(doc.line_items || []).length}）`, 'list'],
    ['attachments', `附件（${(doc.attachments || []).length}）`, 'paperclip'],
    ['approval', '审批进度', 'branch'],
    ['logs', '状态记录', 'clock'],
    ['versions', `版本（${(doc.versions || []).length}）`, 'layers'],
  ];

  root.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <div class="card-body" style="padding-top:18px">
        <div class="doc-hero">
          <div>
            <div class="doc-id">${esc(doc.document_type)} · 版本 V${doc.current_version}</div>
            <div class="doc-no">${esc(doc.document_no)}</div>
            <div class="doc-tags">
              ${statusBadge(doc.document_status)}
              ${report ? riskBadge(report.overall_risk_level) : '<span class="badge badge-neutral">未分析</span>'}
              ${report ? recommendationBadge(report.recommendation) : ''}
              <span class="tag">申请人 ${esc(doc.applicant_name || '-')}</span>
              <span class="tag">${esc(doc.budget_department || '-')}</span>
            </div>
          </div>
          <div class="amount-hero">
            <div class="label">单据总金额</div>
            <div class="value">${money(doc.total_amount)}</div>
            <div class="small muted">${esc(doc.currency)} · 申请日期 ${fmtDate(doc.apply_date)}</div>
          </div>
        </div>
      </div>
    </div>

    ${
      latest
        ? `<div class="card" style="margin-bottom:16px">
            <div class="card-head">
              <div>
                <div class="card-title">最新智能分析</div>
                <div class="card-sub">任务 #${latest.id} · ${esc(TASK_STATUS[latest.task_status] || latest.task_status)} · ${esc(fmtDateTime(latest.started_at))}</div>
              </div>
              <div class="card-actions">
                ${latest.task_status === 'succeeded' ? `<a class="btn btn-sm btn-primary" href="#/analysis/${latest.id}">查看完整报告</a>` : `<a class="btn btn-sm btn-ghost" href="#/analysis/${latest.id}">查看进度</a>`}
              </div>
            </div>
            <div class="card-body">
              ${
                latest.task_status === 'succeeded' && report
                  ? `<div class="grid grid-4" style="gap:10px">
                      <div class="amount-cell"><div class="a-label">整体风险</div><div style="margin-top:6px">${riskBadge(report.overall_risk_level)}</div><div class="a-diff muted">${esc(report.recommendation)}</div></div>
                      <div class="amount-cell"><div class="a-label">高风险</div><div class="a-value" style="color:var(--high)">${counts.high || 0}</div><div class="a-diff muted">项</div></div>
                      <div class="amount-cell"><div class="a-label">中风险</div><div class="a-value" style="color:var(--medium)">${counts.medium || 0}</div><div class="a-diff muted">项</div></div>
                      <div class="amount-cell"><div class="a-label">低风险</div><div class="a-value" style="color:var(--low)">${counts.low || 0}</div><div class="a-diff muted">项</div></div>
                    </div>`
                  : `<div>
                      <div class="progress"><div class="progress-bar" style="width:${latest.progress || 0}%"></div></div>
                      <p class="small muted" style="margin-top:8px">当前步骤：${esc(TASK_STATUS[latest.current_step] || latest.current_step)}（${latest.progress || 0}%）${latest.error_message ? ` · ${esc(latest.error_message)}` : ''}</p>
                    </div>`
              }
            </div>
          </div>`
        : ''
    }

    <div class="card">
      <div class="card-head" style="padding-bottom:0">
        <div class="tabs" style="margin-bottom:0;border-bottom:none;flex:1">
          ${tabs.map(([key, label], index) => `<div class="tab ${index === 0 ? 'active' : ''}" data-tab="${key}">${esc(label)}</div>`).join('')}
        </div>
      </div>
      <div class="card-body" style="padding-top:16px">
        <div data-panel="basic">
          <div class="section-title">基础信息</div>
          <div class="kv-grid">
            <div class="kv"><div class="k">单据类型</div><div class="v">${esc(doc.document_type)}</div></div>
            <div class="kv"><div class="k">申请人</div><div class="v">${esc(doc.applicant_name || '-')}</div></div>
            <div class="kv"><div class="k">申请部门</div><div class="v">${esc(doc.applicant_department || '-')}</div></div>
            <div class="kv"><div class="k">预算部门</div><div class="v">${esc(doc.budget_department || '-')}</div></div>
            <div class="kv"><div class="k">收款单位</div><div class="v">${esc(doc.payee_name || '-')}</div></div>
            <div class="kv"><div class="k">收款账号</div><div class="v mono">${esc(doc.payee_account || '-')}</div></div>
            <div class="kv"><div class="k">费用类别</div><div class="v">${esc(doc.expense_category || '-')}</div></div>
            <div class="kv"><div class="k">币种</div><div class="v">${esc(doc.currency || 'CNY')}</div></div>
            ${typeFields.map(([key, value]) => `<div class="kv"><div class="k">${esc(key)}</div><div class="v">${esc(value)}</div></div>`).join('')}
            <div class="kv full"><div class="k">申请事由</div><div class="v" style="font-weight:400">${esc(doc.reason_text || '-')}</div></div>
          </div>
          <div class="section-title" style="margin-top:20px">金额信息</div>
          <div class="kv-grid">
            <div class="kv"><div class="k">单据总金额</div><div class="v">${money(doc.total_amount)}</div></div>
            <div class="kv"><div class="k">明细合计</div><div class="v">${money(doc.line_items_total)}</div></div>
            <div class="kv"><div class="k">明细数量</div><div class="v">${(doc.line_items || []).length} 条</div></div>
            <div class="kv"><div class="k">附件数量</div><div class="v">${(doc.attachments || []).length} 个</div></div>
          </div>
        </div>

        <div data-panel="items" hidden>
          ${
            (doc.line_items || []).length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>项目名称</th><th>规格 / 类别</th><th>发生日期</th><th>地点</th><th style="text-align:right">数量</th><th style="text-align:right">单价</th><th style="text-align:right">金额</th>${doc.document_type === '批量付款单' ? '<th>收款方</th><th>收款账号</th>' : ''}<th>备注</th></tr></thead>
                  <tbody>
                    ${doc.line_items
                      .map(
                        (item) => `<tr>
                          <td><div class="cell-main">${esc(item.item_name)}</div><div class="cell-sub">${esc(item.item_type)}</div></td>
                          <td>${esc(item.item_spec || '-')}<div class="cell-sub">${esc(item.expense_category || '')}</div></td>
                          <td class="muted small">${fmtDate(item.expense_date)}</td>
                          <td>${esc(item.expense_location || '-')}</td>
                          <td class="num">${item.quantity}</td>
                          <td class="num">${money(item.unit_price)}</td>
                          <td class="num"><b>${money(item.amount)}</b></td>
                          ${doc.document_type === '批量付款单' ? `<td>${esc(item.payee_name || '-')}</td><td class="mono small">${esc(item.payee_account || '-')}</td>` : ''}
                          <td class="muted small">${esc(item.remark || '-')}</td>
                        </tr>`
                      )
                      .join('')}
                  </tbody>
                </table></div>`
              : emptyState('暂无明细')
          }
        </div>

        <div data-panel="attachments" hidden>
          ${
            (doc.attachments || []).length
              ? `<div class="attach-list">${doc.attachments
                  .map(
                    (att) => `<div class="attach-item">
                      <div class="file-badge ${att.file_type === 'pdf' ? 'file-pdf' : 'file-img'}">${att.file_type === 'pdf' ? 'PDF' : 'IMG'}</div>
                      <div style="flex:1;min-width:0">
                        <div class="attach-name">${esc(att.file_name)}</div>
                        <div class="attach-meta">${fileSize(att.file_size)} · 上传于 ${esc(fmtDateTime(att.created_at))} · ${parseBadge(att.parse_status)}</div>
                      </div>
                      <a class="btn btn-sm btn-ghost" href="#/attachments/${doc.id}/${att.id}">${icon('scan', 13)} 查看解析</a>
                      <button class="btn btn-sm btn-ghost" data-download="${esc(att.download_url)}" data-name="${esc(att.file_name)}">${icon('download', 13)} 下载</button>
                    </div>`
                  )
                  .join('')}</div>`
              : emptyState('暂无附件', '编辑单据时可上传 PDF、PNG、JPG 材料', 'paperclip')
          }
        </div>

        <div data-panel="approval" hidden>
          ${
            approval
              ? `<div class="section-title">${esc(approval.workflow_name || '审批流程')} · ${taskStatusBadge(approval.instance_status)}</div>
                <div class="timeline">
                  ${approvalNodes
                    .map((node, index) => {
                      const status = node.task_status;
                      const cls = ['approved'].includes(status)
                        ? 'done'
                        : ['returned', 'rejected'].includes(status)
                          ? 'fail'
                          : status === 'pending' && approval.current_node_id === node.node_id
                            ? 'current'
                            : '';
                      return `<div class="timeline-item ${cls}">
                        <div class="tl-title">${esc(node.node_name)} ${taskStatusBadge(status)}</div>
                        <div class="tl-meta">第 ${node.node_order} 节点 · 审批角色 ${esc(node.approver_role)} · 审批人 ${esc(node.approver_name || '待分配')}</div>
                        ${node.review_comment ? `<div class="tl-body">${esc(node.review_comment)}</div>` : ''}
                        ${node.processed_at ? `<div class="tl-meta">处理时间 ${esc(fmtDateTime(node.processed_at))}</div>` : ''}
                      </div>`;
                    })
                    .join('')}
                </div>`
              : emptyState('尚未发起审批', '提交单据后系统将按流程生成审批任务', 'branch')
          }
        </div>

        <div data-panel="logs" hidden>
          ${
            (doc.status_logs || []).length
              ? `<div class="timeline">${doc.status_logs
                  .map(
                    (log) => `<div class="timeline-item done">
                      <div class="tl-title">${statusBadge(log.to_status)} <span class="small muted">${esc(log.operator_name || '')}</span></div>
                      <div class="tl-meta">${esc(fmtDateTime(log.created_at))}</div>
                      ${log.remark ? `<div class="tl-body">${esc(log.remark)}</div>` : ''}
                    </div>`
                  )
                  .join('')}</div>`
              : emptyState('暂无状态记录')
          }
        </div>

        <div data-panel="versions" hidden>
          ${
            (doc.versions || []).length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>版本</th><th>创建人</th><th>创建时间</th><th>说明</th></tr></thead>
                  <tbody>${doc.versions
                    .map(
                      (version) => `<tr>
                        <td><span class="badge badge-primary">V${version.version_no}</span></td>
                        <td>${esc(version.created_by_name || '-')}</td>
                        <td class="muted small">${esc(fmtDateTime(version.created_at))}</td>
                        <td class="muted small">提交审批时生成单据快照</td>
                      </tr>`
                    )
                    .join('')}</tbody>
                </table></div>`
              : emptyState('暂无版本记录')
          }
        </div>
      </div>
    </div>`;

  root.querySelectorAll('[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      root.querySelectorAll('[data-tab]').forEach((item) => item.classList.toggle('active', item === tab));
      root.querySelectorAll('[data-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.panel !== tab.dataset.tab;
      });
    });
  });

  root.querySelectorAll('[data-act]').forEach((button) => {
    button.addEventListener('click', () => handleAction(button.dataset.act, button));
  });

  const actionBar = document.getElementById('page-actions');
  actionBar.querySelectorAll('[data-act]').forEach((button) => {
    button.addEventListener('click', () => handleAction(button.dataset.act, button));
  });

  root.querySelectorAll('[data-download]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await downloadFile(button.dataset.download, button.dataset.name);
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  });

  async function handleAction(action, button) {
    try {
      if (action === 'submit') {
        const ok = await confirmDialog({
          title: '提交审批',
          message: '提交后单据将进入审批流程，系统会自动解析附件并生成风险分析报告。确认继续吗？',
          confirmText: '提交审批',
        });
        if (!ok) return;
        button.disabled = true;
        const result = await api(`/api/v1/documents/${doc.id}/submit`, { method: 'POST' });
        toast(`单据已提交，分析任务 #${result.analysis_task.id} 已启动`, 'success');
        window.location.hash = `#/analysis/${result.analysis_task.id}`;
        return;
      }
      if (action === 'withdraw') {
        const ok = await confirmDialog({ title: '撤回单据', message: '撤回后当前审批任务将被取消，确认继续吗？', confirmText: '确认撤回' });
        if (!ok) return;
        await api(`/api/v1/documents/${doc.id}/withdraw`, { method: 'POST' });
        toast('单据已撤回', 'success');
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        return;
      }
      if (action === 'void') {
        const ok = await confirmDialog({ title: '作废单据', message: '作废后不可恢复，确认继续吗？', confirmText: '确认作废', danger: true });
        if (!ok) return;
        await api(`/api/v1/documents/${doc.id}/void`, { method: 'POST', body: { remark: '申请人作废' } });
        toast('单据已作废', 'success');
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        return;
      }
      if (action === 'copy') {
        const copied = await api(`/api/v1/documents/${doc.id}/copy`, { method: 'POST' });
        toast(`已复制为 ${copied.document_no}`, 'success');
        window.location.hash = `#/documents/${copied.id}/edit`;
        return;
      }
      if (action === 'analyze') {
        button.disabled = true;
        const task = await api(`/api/v1/documents/${doc.id}/analysis`, { method: 'POST', body: {} });
        toast('分析任务已创建', 'success');
        window.location.hash = `#/analysis/${task.id}`;
      }
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
    }
  }
}
