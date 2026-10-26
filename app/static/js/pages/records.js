import { api, downloadFile } from '../api.js';
import {
  emptyState,
  esc,
  fmtDateTime,
  icon,
  loadingBlock,
  money,
  recommendationBadge,
  riskBadge,
  toast,
} from '../ui.js';

const TABS = [
  ['reports', '风险报告'],
  ['reviews', '人工复核'],
  ['logs', '操作日志'],
];

const ACTION_LABELS = {
  'document.create': '创建单据',
  'document.update': '编辑单据',
  'document.submit': '提交审批',
  'document.withdraw': '撤回单据',
  'document.void': '作废单据',
  'document.copy': '复制单据',
  'attachment.upload': '上传附件',
  'attachment.delete': '删除附件',
  'attachment.parse': '解析附件',
  'attachment.download': '下载附件',
  'analysis.create': '发起分析',
  'analysis.complete': '分析完成',
  'analysis.failed': '分析失败',
  'approval.start': '发起审批',
  'approval.approve': '审批通过',
  'approval.return': '审批退回',
  'approval.reject': '审批驳回',
  'report.manual_review': '人工复核',
  'report.export': '导出报告',
  'risk_finding.review': '风险项复核',
  'rule.update': '更新规则',
  'rule.create': '创建规则',
  'workflow.create': '创建流程',
  'workflow.update': '更新流程',
  'supplier.update': '更新供应商',
  'user.create': '创建用户',
  'user.update': '更新用户',
  'auth.login': '用户登录',
  'auth.logout': '用户退出',
  'session.create': '创建会话',
};

export async function render(root, ctx) {
  const state = {
    tab: ['reports', 'reviews', 'logs'].includes(ctx.query.tab) ? ctx.query.tab : 'reports',
    page: 1,
    risk_level: ctx.query.risk_level || '',
    recommendation: '',
    action_type: '',
  };

  ctx.setActions(`<button class="btn btn-ghost" id="btn-refresh">${icon('refresh', 15)} 刷新</button>`);
  root.innerHTML = `
    <div class="card">
      <div class="card-head" style="flex-wrap:wrap">
        <div class="tabs" id="record-tabs" style="margin:0;border:none;flex:1">
          ${TABS.map(([value, label]) => `<div class="tab ${state.tab === value ? 'active' : ''}" data-tab="${value}">${label}</div>`).join('')}
        </div>
        <div class="card-actions" id="record-filters"></div>
      </div>
      <div class="card-body" id="record-body">${loadingBlock('正在加载审核记录…')}</div>
    </div>`;

  const body = root.querySelector('#record-body');
  const filters = root.querySelector('#record-filters');

  function renderFilters() {
    if (state.tab === 'logs') {
      filters.innerHTML = `<div class="field" style="width:190px"><label>动作类型</label>
        <select id="f-action">
          <option value="">全部动作</option>
          ${Object.entries(ACTION_LABELS).map(([value, label]) => `<option value="${value}" ${state.action_type === value ? 'selected' : ''}>${label}</option>`).join('')}
        </select></div>`;
      filters.querySelector('#f-action').addEventListener('change', (event) => {
        state.action_type = event.target.value;
        state.page = 1;
        load();
      });
    } else {
      filters.innerHTML = `<div class="field" style="width:150px"><label>风险等级</label>
        <select id="f-risk">
          <option value="">全部等级</option>
          <option value="high" ${state.risk_level === 'high' ? 'selected' : ''}>高风险</option>
          <option value="medium" ${state.risk_level === 'medium' ? 'selected' : ''}>中风险</option>
          <option value="low" ${state.risk_level === 'low' ? 'selected' : ''}>低风险</option>
        </select></div>`;
      filters.querySelector('#f-risk').addEventListener('change', (event) => {
        state.risk_level = event.target.value;
        state.page = 1;
        load();
      });
    }
  }

  async function load() {
    renderFilters();
    body.innerHTML = loadingBlock('正在加载审核记录…');
    if (state.tab === 'logs') {
      await loadLogs();
      return;
    }
    const params = new URLSearchParams({ page: state.page, page_size: 12 });
    if (state.risk_level) params.set('risk_level', state.risk_level);
    if (state.tab === 'reviews') params.set('has_review', 'true');
    let data;
    try {
      data = await api(`/api/v1/review-reports?${params.toString()}`);
    } catch (error) {
      body.innerHTML = emptyState('记录加载失败', error.message, 'alert');
      return;
    }
    if (!data.items.length) {
      body.innerHTML = emptyState(state.tab === 'reviews' ? '暂无人工复核记录' : '暂无风险报告', '提交单据并完成分析后会生成报告', 'archive');
      return;
    }

    body.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr>
        <th>单据</th><th>申请人</th><th style="text-align:right">金额</th><th>风险</th><th>处理建议</th>
        <th>${state.tab === 'reviews' ? '复核结果' : '风险项'}</th><th>生成时间</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        ${data.items
          .map(
            (report) => `<tr>
              <td>
                <a class="cell-main" href="#/analysis/${report.task_id}" style="text-decoration:none">${esc(report.document_no)}</a>
                <div class="cell-sub">${esc(report.document_type)}</div>
              </td>
              <td>${esc(report.applicant_name || '-')}</td>
              <td class="num">${money(report.total_amount)}</td>
              <td>${riskBadge(report.overall_risk_level)}</td>
              <td>${recommendationBadge(report.recommendation)}</td>
              <td>
                ${
                  state.tab === 'reviews' && report.last_review
                    ? `<div class="cell-main" style="font-size:12.5px">${esc(report.last_review.review_result)} · ${esc(report.last_review.reviewer_name || '')}</div>
                       <div class="cell-sub">${esc(report.last_review.review_comment || '')}</div>`
                    : `高 ${report.risk_counts?.high || 0} / 中 ${report.risk_counts?.medium || 0} / 低 ${report.risk_counts?.low || 0}`
                }
              </td>
              <td class="muted small">${esc(fmtDateTime(report.created_at))}</td>
              <td>
                <div class="row-actions">
                  <a class="btn btn-sm btn-ghost" href="#/analysis/${report.task_id}">查看报告</a>
                  <button class="btn btn-sm btn-ghost" data-export="md" data-report="${report.id}" data-no="${esc(report.document_no)}">MD</button>
                  <button class="btn btn-sm btn-ghost" data-export="html" data-report="${report.id}" data-no="${esc(report.document_no)}">HTML</button>
                </div>
              </td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table></div>
    ${pagination(data.total, data.page, data.page_size)}`;

    body.querySelectorAll('[data-export]').forEach((button) => {
      button.addEventListener('click', async () => {
        try {
          await downloadFile(
            `/api/v1/review-reports/${button.dataset.report}/export?format=${button.dataset.export}`,
            `风险审核报告_${button.dataset.no}.${button.dataset.export}`
          );
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    });
    bindPagination();
  }

  async function loadLogs() {
    const params = new URLSearchParams({ page: state.page, page_size: 18 });
    if (state.action_type) params.set('action_type', state.action_type);
    let data;
    try {
      data = await api(`/api/v1/audit-logs?${params.toString()}`);
    } catch (error) {
      body.innerHTML = emptyState('日志加载失败', error.message, 'alert');
      return;
    }
    if (!data.items.length) {
      body.innerHTML = emptyState('暂无操作日志');
      return;
    }
    body.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>资源</th><th>详情</th><th>IP</th></tr></thead>
      <tbody>
        ${data.items
          .map(
            (log) => `<tr>
              <td class="muted small" style="white-space:nowrap">${esc(fmtDateTime(log.created_at))}</td>
              <td>${esc(log.user_name || '-')}</td>
              <td><span class="badge badge-neutral">${esc(ACTION_LABELS[log.action_type] || log.action_type)}</span></td>
              <td class="muted small">${esc(log.resource_type)}${log.resource_id ? ` #${esc(log.resource_id)}` : ''}</td>
              <td class="muted small" style="max-width:360px;word-break:break-all">${esc(detailText(log.detail))}</td>
              <td class="muted small">${esc(log.ip_address || '-')}</td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table></div>
    ${pagination(data.total, data.page, data.page_size)}`;
    bindPagination();
  }

  function bindPagination() {
    body.querySelectorAll('[data-page]').forEach((button) => {
      button.addEventListener('click', () => {
        state.page = Number(button.dataset.page);
        load();
      });
    });
  }

  function detailText(detail) {
    if (!detail || typeof detail !== 'object') return detail || '-';
    const parts = [];
    Object.entries(detail).slice(0, 3).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') return;
      const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
      parts.push(`${key}: ${text.slice(0, 80)}`);
    });
    return parts.join('；') || '-';
  }

  root.querySelectorAll('[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      state.tab = tab.dataset.tab;
      state.page = 1;
      root.querySelectorAll('[data-tab]').forEach((item) => item.classList.toggle('active', item === tab));
      history.replaceState(null, '', `#/records?tab=${state.tab}`);
      load();
    });
  });
  document.getElementById('page-actions')?.querySelector('#btn-refresh')?.addEventListener('click', load);

  await load();
}

function pagination(total, page, pageSize) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return `<div class="pagination">共 ${total} 条记录</div>`;
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  const buttons = [`<button data-page="${Math.max(1, page - 1)}" ${page <= 1 ? 'disabled' : ''}>上一页</button>`];
  for (let index = start; index <= end; index += 1) {
    buttons.push(`<button data-page="${index}" class="${index === page ? 'active' : ''}">${index}</button>`);
  }
  buttons.push(`<button data-page="${Math.min(pages, page + 1)}" ${page >= pages ? 'disabled' : ''}>下一页</button>`);
  return `<div class="pagination">共 ${total} 条记录 ${buttons.join('')}</div>`;
}
