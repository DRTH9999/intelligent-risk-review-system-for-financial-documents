import { api, session } from '../api.js';
import {
  emptyState,
  esc,
  fmtDate,
  icon,
  loadingBlock,
  money,
  riskBadge,
  statusBadge,
  toast,
  confirmDialog,
} from '../ui.js';

const STATUS_TABS = [
  ['', '全部'],
  ['draft', '草稿'],
  ['pending_review', '待审批'],
  ['reviewing', '审批中'],
  ['returned', '已退回'],
  ['approved', '已通过'],
  ['rejected', '已驳回'],
];

export async function render(root, ctx) {
  const user = session.user || {};
  const roles = user.roles || [];
  const state = {
    page: Number(ctx.query.page || 1),
    page_size: 10,
    keyword: ctx.query.keyword || '',
    document_type: ctx.query.document_type || '',
    status: ctx.query.status || '',
    date_from: ctx.query.date_from || '',
    date_to: ctx.query.date_to || '',
  };

  ctx.setActions(`<a class="btn btn-primary" href="#/documents/new">${icon('plus', 16)} 新建单据</a>`);

  root.innerHTML = `
    <div class="card">
      <div class="card-head" style="flex-wrap:wrap">
        <div class="tabs" id="status-tabs" style="margin:0;border:none;flex:1">
          ${STATUS_TABS.map(
            ([value, label]) => `<div class="tab ${state.status === value ? 'active' : ''}" data-status="${value}">${label} <span class="muted" data-count="${value}"></span></div>`
          ).join('')}
        </div>
        <div class="card-actions">
          <button class="btn btn-sm btn-ghost" id="btn-refresh">${icon('refresh', 14)} 刷新</button>
        </div>
      </div>
      <div class="card-body">
        <div class="filters">
          <div class="field" style="width:220px">
            <label>关键词</label>
            <input id="f-keyword" placeholder="单据编号 / 收款单位 / 事由" value="${esc(state.keyword)}" />
          </div>
          <div class="field" style="width:150px">
            <label>单据类型</label>
            <select id="f-type">
              <option value="">全部类型</option>
              ${['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单']
                .map((type) => `<option value="${type}" ${state.document_type === type ? 'selected' : ''}>${type}</option>`)
                .join('')}
            </select>
          </div>
          <div class="field" style="width:150px">
            <label>申请开始日期</label>
            <input type="date" id="f-from" value="${esc(state.date_from)}" />
          </div>
          <div class="field" style="width:150px">
            <label>申请结束日期</label>
            <input type="date" id="f-to" value="${esc(state.date_to)}" />
          </div>
          <button class="btn btn-primary" id="btn-search">${icon('search', 15)} 查询</button>
          <button class="btn btn-ghost" id="btn-reset">重置</button>
        </div>
        <div id="doc-table">${loadingBlock()}</div>
      </div>
    </div>`;

  const tableRoot = root.querySelector('#doc-table');

  function updateUrl() {
    const params = new URLSearchParams();
    Object.entries(state).forEach(([key, value]) => {
      if (value && key !== 'page_size') params.set(key, value);
    });
    const query = params.toString();
    history.replaceState(null, '', `#/documents${query ? `?${query}` : ''}`);
  }

  async function load() {
    tableRoot.innerHTML = loadingBlock('正在查询单据…');
    const params = new URLSearchParams();
    if (state.keyword) params.set('keyword', state.keyword);
    if (state.document_type) params.set('document_type', state.document_type);
    if (state.status) params.set('status', state.status);
    if (state.date_from) params.set('date_from', state.date_from);
    if (state.date_to) params.set('date_to', state.date_to);
    params.set('page', state.page);
    params.set('page_size', state.page_size);

    let data;
    try {
      data = await api(`/api/v1/documents?${params.toString()}`);
    } catch (error) {
      tableRoot.innerHTML = emptyState('查询失败', error.message, 'alert');
      return;
    }

    const counts = data.status_counts || {};
    root.querySelectorAll('[data-count]').forEach((el) => {
      const key = el.dataset.count;
      const value = key ? counts[key] || 0 : data.total || 0;
      el.textContent = value ? `(${value})` : '';
    });

    if (!data.items.length) {
      tableRoot.innerHTML = emptyState('没有符合条件的单据', '调整筛选条件或新建一张单据', 'fileText');
      return;
    }

    const canEdit = (doc) => (doc.applicant_id === user.id || roles.includes('admin')) && ['draft', 'returned'].includes(doc.document_status);
    const canWithdraw = (doc) => doc.applicant_id === user.id && ['pending_review', 'reviewing'].includes(doc.document_status);
    const canVoid = (doc) => (doc.applicant_id === user.id || roles.includes('admin')) && ['draft', 'returned', 'withdrawn', 'rejected'].includes(doc.document_status);

    tableRoot.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>单据编号 / 类型</th>
              <th>申请人 / 部门</th>
              <th>收款单位</th>
              <th style="text-align:right">金额</th>
              <th>状态</th>
              <th>风险</th>
              <th>申请日期</th>
              <th style="text-align:center">附件</th>
              <th style="text-align:right">操作</th>
            </tr>
          </thead>
          <tbody>
            ${data.items
              .map(
                (doc) => `<tr>
                  <td>
                    <a class="cell-main" href="#/documents/${doc.id}" style="text-decoration:none">${esc(doc.document_no)}</a>
                    <div class="cell-sub">${esc(doc.document_type)}</div>
                  </td>
                  <td>
                    <div class="cell-main" style="font-size:12.5px">${esc(doc.applicant_name || '-')}</div>
                    <div class="cell-sub">${esc(doc.budget_department || '-')}</div>
                  </td>
                  <td>${esc(doc.payee_name || '-')}</td>
                  <td class="num"><b>${money(doc.total_amount)}</b><div class="cell-sub">${esc(doc.currency || 'CNY')}</div></td>
                  <td>${statusBadge(doc.document_status)}</td>
                  <td>${doc.risk_level ? `<a href="#/analysis/${doc.latest_analysis_task_id}" style="text-decoration:none">${riskBadge(doc.risk_level)}</a>` : '<span class="muted small">未分析</span>'}</td>
                  <td class="muted small">${esc(fmtDate(doc.apply_date))}</td>
                  <td style="text-align:center" class="muted small">${doc.attachment_count || 0}</td>
                  <td>
                    <div class="row-actions">
                      <a class="btn btn-sm btn-ghost" href="#/documents/${doc.id}">详情</a>
                      ${canEdit(doc) ? `<a class="btn btn-sm btn-ghost" href="#/documents/${doc.id}/edit">编辑</a>` : ''}
                      ${canEdit(doc) ? `<button class="btn btn-sm btn-primary" data-action="submit" data-id="${doc.id}" data-no="${esc(doc.document_no)}">提交</button>` : ''}
                      ${canWithdraw(doc) ? `<button class="btn btn-sm btn-ghost" data-action="withdraw" data-id="${doc.id}" data-no="${esc(doc.document_no)}">撤回</button>` : ''}
                      ${canVoid(doc) ? `<button class="btn btn-sm btn-ghost" data-action="void" data-id="${doc.id}" data-no="${esc(doc.document_no)}">作废</button>` : ''}
                      <button class="btn btn-sm btn-ghost" data-action="copy" data-id="${doc.id}">复制</button>
                      ${doc.latest_analysis_task_id ? `<a class="btn btn-sm btn-ghost" href="#/analysis/${doc.latest_analysis_task_id}">分析</a>` : `<button class="btn btn-sm btn-ghost" data-action="analyze" data-id="${doc.id}">分析</button>`}
                    </div>
                  </td>
                </tr>`
              )
              .join('')}
          </tbody>
        </table>
      </div>
      ${pagination(data.total, data.page, data.page_size)}`;

    tableRoot.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', () => handleAction(button.dataset.action, Number(button.dataset.id), button));
    });
    tableRoot.querySelectorAll('[data-page]').forEach((button) => {
      button.addEventListener('click', () => {
        state.page = Number(button.dataset.page);
        updateUrl();
        load();
      });
    });
  }

  async function handleAction(action, id, button) {
    try {
      if (action === 'copy') {
        button.disabled = true;
        const doc = await api(`/api/v1/documents/${id}/copy`, { method: 'POST' });
        toast(`已复制为 ${doc.document_no}`, 'success');
        window.location.hash = `#/documents/${doc.id}/edit`;
        return;
      }
      if (action === 'analyze') {
        button.disabled = true;
        const task = await api(`/api/v1/documents/${id}/analysis`, { method: 'POST', body: {} });
        toast('分析任务已创建', 'success');
        window.location.hash = `#/analysis/${task.id}`;
        return;
      }
      if (action === 'submit') {
        const ok = await confirmDialog({
          title: '提交审批',
          message: `确认提交单据 ${button.dataset.no} 吗？提交后系统将生成审批实例并自动执行附件解析与风险分析。`,
          confirmText: '提交审批',
        });
        if (!ok) return;
        button.disabled = true;
        const result = await api(`/api/v1/documents/${id}/submit`, { method: 'POST' });
        toast(`单据已提交，分析任务 #${result.analysis_task.id} 已启动`, 'success');
        load();
        return;
      }
      if (action === 'withdraw') {
        const ok = await confirmDialog({
          title: '撤回单据',
          message: `确认撤回单据 ${button.dataset.no} 吗？撤回后审批任务将被取消。`,
          confirmText: '确认撤回',
        });
        if (!ok) return;
        await api(`/api/v1/documents/${id}/withdraw`, { method: 'POST' });
        toast('单据已撤回', 'success');
        load();
        return;
      }
      if (action === 'void') {
        const ok = await confirmDialog({
          title: '作废单据',
          message: `确认作废单据 ${button.dataset.no} 吗？作废后不可恢复。`,
          confirmText: '确认作废',
          danger: true,
        });
        if (!ok) return;
        await api(`/api/v1/documents/${id}/void`, { method: 'POST', body: { remark: '申请人作废' } });
        toast('单据已作废', 'success');
        load();
      }
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
    }
  }

  root.querySelectorAll('[data-status]').forEach((tab) => {
    tab.addEventListener('click', () => {
      state.status = tab.dataset.status;
      state.page = 1;
      root.querySelectorAll('[data-status]').forEach((item) => item.classList.toggle('active', item === tab));
      updateUrl();
      load();
    });
  });

  root.querySelector('#btn-search').addEventListener('click', () => {
    state.keyword = root.querySelector('#f-keyword').value.trim();
    state.document_type = root.querySelector('#f-type').value;
    state.date_from = root.querySelector('#f-from').value;
    state.date_to = root.querySelector('#f-to').value;
    state.page = 1;
    updateUrl();
    load();
  });
  root.querySelector('#f-keyword').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') root.querySelector('#btn-search').click();
  });
  root.querySelector('#btn-reset').addEventListener('click', () => {
    Object.assign(state, { page: 1, keyword: '', document_type: '', status: '', date_from: '', date_to: '' });
    root.querySelector('#f-keyword').value = '';
    root.querySelector('#f-type').value = '';
    root.querySelector('#f-from').value = '';
    root.querySelector('#f-to').value = '';
    root.querySelectorAll('[data-status]').forEach((item) => item.classList.toggle('active', item.dataset.status === ''));
    updateUrl();
    load();
  });
  root.querySelector('#btn-refresh').addEventListener('click', load);

  await load();
}

function pagination(total, page, pageSize) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) {
    return `<div class="pagination">共 ${total} 张单据</div>`;
  }
  const buttons = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  buttons.push(`<button data-page="${Math.max(1, page - 1)}" ${page <= 1 ? 'disabled' : ''}>上一页</button>`);
  for (let index = start; index <= end; index += 1) {
    buttons.push(`<button data-page="${index}" class="${index === page ? 'active' : ''}">${index}</button>`);
  }
  buttons.push(`<button data-page="${Math.min(pages, page + 1)}" ${page >= pages ? 'disabled' : ''}>下一页</button>`);
  return `<div class="pagination">共 ${total} 张单据 ${buttons.join('')}</div>`;
}
