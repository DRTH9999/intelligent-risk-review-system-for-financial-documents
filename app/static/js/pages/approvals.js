import { api } from '../api.js';
import {
  emptyState,
  esc,
  fmtDateTime,
  icon,
  loadingBlock,
  money,
  recommendationBadge,
  riskBadge,
  taskStatusBadge,
} from '../ui.js';

const TABS = [
  ['pending', '待处理'],
  ['approved', '已通过'],
  ['returned', '已退回'],
  ['rejected', '已驳回'],
  ['', '全部'],
];

export async function render(root, ctx) {
  const state = { status: ctx.query.status || 'pending' };

  ctx.setActions(`<button class="btn btn-ghost" id="btn-refresh">${icon('refresh', 15)} 刷新任务</button>`);

  root.innerHTML = `
    <div class="card">
      <div class="card-head" style="flex-wrap:wrap">
        <div class="tabs" id="task-tabs" style="margin:0;border:none;flex:1">
          ${TABS.map(
            ([value, label]) => `<div class="tab ${state.status === value ? 'active' : ''}" data-status="${value}">${label} <span class="muted" data-count="${value}"></span></div>`
          ).join('')}
        </div>
      </div>
      <div class="card-body" id="task-list">${loadingBlock('正在加载审批任务…')}</div>
    </div>`;

  const listEl = root.querySelector('#task-list');

  function updateUrl() {
    history.replaceState(null, '', `#/approvals${state.status ? `?status=${state.status}` : ''}`);
  }

  async function load() {
    listEl.innerHTML = loadingBlock('正在加载审批任务…');
    let data;
    try {
      data = await api(`/api/v1/approval-tasks${state.status ? `?status=${state.status}` : ''}`);
    } catch (error) {
      listEl.innerHTML = emptyState('加载失败', error.message, 'alert');
      return;
    }
    const counts = data.counts || {};
    root.querySelectorAll('[data-count]').forEach((el) => {
      const key = el.dataset.count;
      const value = key ? counts[key] || 0 : Object.values(counts).reduce((sum, item) => sum + item, 0);
      el.textContent = value ? `(${value})` : '';
    });

    if (!data.items.length) {
      listEl.innerHTML = emptyState(
        state.status === 'pending' ? '暂无待处理审批任务' : '暂无审批任务',
        state.status === 'pending' ? '当申请人提交单据且流转到您时，任务会出现在这里' : '',
        'checkSquare'
      );
      return;
    }

    listEl.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr>
        <th>单据 / 类型</th><th>申请人</th><th style="text-align:right">金额</th><th>当前节点</th>
        <th>风险</th><th>任务状态</th><th>创建时间</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        ${data.items
          .map(
            (task) => `<tr>
              <td>
                <a class="cell-main" href="#/documents/${task.document_id}" style="text-decoration:none">${esc(task.document_no)}</a>
                <div class="cell-sub">${esc(task.document_type)}</div>
              </td>
              <td><div class="cell-main" style="font-size:12.5px">${esc(task.applicant_name || '-')}</div><div class="cell-sub">${esc(task.budget_department || '')}</div></td>
              <td class="num"><b>${money(task.total_amount)}</b></td>
              <td>${esc(task.node_name)}</td>
              <td>${task.risk_level ? `<a href="#/analysis/${task.analysis_task_id}" style="text-decoration:none">${riskBadge(task.risk_level)}</a>` : '<span class="muted small">未分析</span>'}
                ${task.recommendation ? `<div class="cell-sub">${recommendationBadge(task.recommendation)}</div>` : ''}</td>
              <td>${taskStatusBadge(task.task_status)}</td>
              <td class="muted small">${esc(fmtDateTime(task.created_at))}</td>
              <td>
                <div class="row-actions">
                  <a class="btn btn-sm btn-ghost" href="#/documents/${task.document_id}">单据</a>
                  ${task.analysis_task_id ? `<a class="btn btn-sm btn-ghost" href="#/analysis/${task.analysis_task_id}">风险分析</a>` : ''}
                  ${task.task_status === 'pending' ? `<a class="btn btn-sm btn-primary" href="#/approvals/${task.task_id}">处理审批</a>` : `<a class="btn btn-sm btn-ghost" href="#/approvals/${task.task_id}">查看</a>`}
                </div>
              </td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table></div>`;
  }

  root.querySelectorAll('[data-status]').forEach((tab) => {
    tab.addEventListener('click', () => {
      state.status = tab.dataset.status;
      root.querySelectorAll('[data-status]').forEach((item) => item.classList.toggle('active', item === tab));
      updateUrl();
      load();
    });
  });
  document.getElementById('page-actions')?.querySelector('#btn-refresh')?.addEventListener('click', load);

  await load();
}
