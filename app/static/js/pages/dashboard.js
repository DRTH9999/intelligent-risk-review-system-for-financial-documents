import { api } from '../api.js';
import {
  RISK,
  TASK_STATUS,
  compactMoney,
  docTypeBadge,
  donutChart,
  emptyState,
  esc,
  fmtDate,
  fmtDateTime,
  icon,
  lineChart,
  loadingBlock,
  money,
  recommendationBadge,
  riskBadge,
  statusBadge,
} from '../ui.js';

function greeting() {
  const hour = new Date().getHours();
  if (hour < 6) return '夜深了';
  if (hour < 12) return '上午好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

export async function render(root, ctx) {
  root.innerHTML = loadingBlock('正在汇总风险数据…');
  const data = await api('/api/v1/dashboard/summary');
  const stats = data.stats || {};
  const user = data.user || {};

  ctx.setTitle(`${greeting()}，${user.display_name || ''}`, `${new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })} · ${user.department || ''}`);
  ctx.setActions(`
    <a class="btn btn-ghost" href="#/chat">${icon('message', 16)} 智能审核对话</a>
    <a class="btn btn-primary" href="#/documents/new">${icon('plus', 16)} 新建单据</a>
  `);

  const riskTotal = (data.risk_distribution || []).reduce((sum, item) => sum + item.count, 0);
  const donut = donutChart(
    [
      { label: '高风险', value: stats.high_risk || 0, color: '#e5484d' },
      { label: '中风险', value: stats.medium_risk || 0, color: '#e08a00' },
      { label: '低风险', value: stats.low_risk || 0, color: '#16a34a' },
    ],
    { centerValue: String(riskTotal), centerLabel: '已分析单据' }
  );

  const trendPoints = (data.trend || []).map((item) => ({ label: item.date, value: item.documents }));
  const maxType = Math.max(1, ...(data.type_distribution || []).map((item) => item.count));

  const statCards = [
    {
      label: '待我审批',
      value: stats.pending_approvals ?? 0,
      icon: 'checkSquare',
      tone: '#2f6fed',
      tint: '#eaf0ff',
      foot: '待处理审批任务',
      href: '#/approvals',
    },
    {
      label: '高风险单据',
      value: stats.high_risk ?? 0,
      icon: 'alert',
      tone: '#e5484d',
      tint: '#fdecec',
      foot: '需优先处理',
      href: '#/records?risk_level=high',
    },
    {
      label: '中风险单据',
      value: stats.medium_risk ?? 0,
      icon: 'shield',
      tone: '#e08a00',
      tint: '#fff4e0',
      foot: '建议人工复核',
      href: '#/records?risk_level=medium',
    },
    {
      label: '待人工复核',
      value: stats.pending_manual_reviews ?? 0,
      icon: 'clock',
      tone: '#7c5cf0',
      tint: '#f0ecfe',
      foot: `累计单据 ${stats.total_documents ?? 0} 张`,
      href: '#/records',
    },
  ];

  root.innerHTML = `
    <div class="grid grid-4">
      ${statCards
        .map(
          (card) => `<a class="card stat-card" href="${card.href}" style="--tone:${card.tone};--tint:${card.tint};text-decoration:none;color:inherit">
            <div class="stat-icon">${icon(card.icon, 21)}</div>
            <div>
              <div class="stat-value">${card.value}</div>
              <div class="stat-label">${esc(card.label)}</div>
              <div class="stat-foot">${esc(card.foot)}</div>
            </div>
          </a>`
        )
        .join('')}
    </div>

    <div class="grid" style="grid-template-columns:1.75fr 1fr;margin-top:16px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">近 7 天单据提交趋势</div>
            <div class="card-sub">按申请日期统计，单位：张</div>
          </div>
          <div class="card-actions">
            <span class="badge badge-primary">累计金额 ${compactMoney(stats.total_amount)}</span>
          </div>
        </div>
        <div class="card-body">${lineChart(trendPoints)}</div>
      </div>
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">风险等级分布</div>
            <div class="card-sub">基于每张单据最新分析报告</div>
          </div>
        </div>
        <div class="card-body">
          <div class="donut-wrap">
            ${donut}
            <div class="donut-legend">
              ${[
                ['高风险', stats.high_risk || 0, '#e5484d'],
                ['中风险', stats.medium_risk || 0, '#e08a00'],
                ['低风险', stats.low_risk || 0, '#16a34a'],
              ]
                .map(
                  ([label, value, color]) => `<div class="legend-row"><span class="legend-dot" style="background:${color}"></span>${label}<b>${value}</b></div>`
                )
                .join('')}
              <div class="legend-row" style="border-top:1px dashed var(--line);padding-top:8px;margin-top:2px">
                <span class="legend-dot" style="background:#c9d3e6"></span>未分析<b>${Math.max(0, (stats.total_documents || 0) - riskTotal)}</b>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-3" style="margin-top:16px">
      <div class="card">
        <div class="card-head"><div class="card-title">单据类型分布</div></div>
        <div class="card-body">
          <div class="dist-list">
            ${
              (data.type_distribution || [])
                .map(
                  (item) => `<div class="dist-row">
                    <span>${esc(item.type)}</span>
                    <span class="dist-bar"><span style="width:${(item.count / maxType) * 100}%"></span></span>
                    <b style="text-align:right">${item.count}</b>
                  </div>`
                )
                .join('') || '<div class="muted small">暂无单据</div>'
            }
          </div>
          <div class="divider"></div>
          <div class="mini-list">
            ${Object.entries(data.status_counts || {})
              .map(
                ([status, count]) => `<div class="mini-item"><span class="grow">${statusBadge(status)}</span><b>${count}</b></div>`
              )
              .join('')}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="card-title">待人工复核</div>
          <div class="card-actions"><a class="btn btn-sm btn-ghost" href="#/records">全部记录</a></div>
        </div>
        <div class="card-body">
          ${
            (data.pending_review_items || []).length
              ? `<div class="mini-list">${data.pending_review_items
                  .map(
                    (item) => `<a class="mini-item" href="#/records" style="text-decoration:none;color:inherit">
                      <div class="grow">
                        <div class="mini-title">${esc(item.document_no)}</div>
                        <div class="mini-sub">${esc(fmtDateTime(item.created_at))}</div>
                      </div>
                      ${recommendationBadge(item.recommendation)}
                    </a>`
                  )
                  .join('')}</div>`
              : emptyState('暂无待复核事项', '所有分析报告均已复核', 'checkSquare')
          }
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="card-title">供应商风险提示</div>
          <div class="card-actions"><a class="btn btn-sm btn-ghost" href="#/suppliers">供应商列表</a></div>
        </div>
        <div class="card-body">
          ${
            (data.supplier_alerts || []).length
              ? data.supplier_alerts
                  .map(
                    (supplier) => `<div class="alert-item">
                      <div class="alert-icon">${icon('building', 15)}</div>
                      <div style="flex:1;min-width:0">
                        <div class="mini-title">${esc(supplier.supplier_name)}</div>
                        <div class="mini-sub">${esc(supplier.supplier_code)} · ${esc(supplier.credit_status)}</div>
                        <div class="tag-row">
                          ${supplier.blacklist_status !== 'normal' ? '<span class="badge badge-high">黑名单</span>' : ''}
                          ${(supplier.risk_tags || []).map((tag) => `<span class="tag">${esc(tag)}</span>`).join('')}
                        </div>
                      </div>
                    </div>`
                  )
                  .join('')
              : emptyState('供应商状态正常', '暂无高风险供应商', 'building')
          }
        </div>
      </div>
    </div>

    <div class="grid" style="grid-template-columns:1.35fr 1fr;margin-top:16px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">最近分析任务</div>
            <div class="card-sub">附件解析与规则引擎执行记录</div>
          </div>
          <div class="card-actions"><a class="btn btn-sm btn-ghost" href="#/records">查看全部</a></div>
        </div>
        <div class="card-body flush">
          ${
            (data.recent_tasks || []).length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>单据</th><th>分析状态</th><th>风险</th><th>触发时间</th><th></th></tr></thead>
                  <tbody>
                    ${data.recent_tasks
                      .map(
                        (task) => `<tr>
                          <td>
                            <div class="cell-main">${esc(task.document_no || '-')}</div>
                            <div class="cell-sub">${esc(task.document_type || '')}</div>
                          </td>
                          <td>
                            <div class="cell-main" style="font-size:12.5px">${esc(TASK_STATUS[task.task_status] || task.task_status)}</div>
                            <div class="cell-sub">进度 ${task.progress}%</div>
                          </td>
                          <td>${riskBadge(task.overall_risk_level)}</td>
                          <td class="muted small">${esc(fmtDateTime(task.started_at))}</td>
                          <td class="row-actions">
                            ${
                              task.task_status === 'succeeded'
                                ? `<a class="btn btn-sm btn-ghost" href="#/analysis/${task.id}">报告</a>`
                                : `<a class="btn btn-sm btn-ghost" href="#/analysis/${task.id}">进度</a>`
                            }
                          </td>
                        </tr>`
                      )
                      .join('')}
                  </tbody>
                </table></div>`
              : emptyState('暂无分析任务', '提交单据后系统会自动创建分析任务')
          }
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="card-title">最新风险报告</div>
          <div class="card-actions"><a class="btn btn-sm btn-ghost" href="#/records">审核记录</a></div>
        </div>
        <div class="card-body flush">
          ${
            (data.recent_reports || []).length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>单据</th><th>金额</th><th>风险</th></tr></thead>
                  <tbody>
                    ${data.recent_reports
                      .map(
                        (report) => `<tr>
                          <td>
                            <a class="cell-main" href="#/analysis/${report.task_id}" style="text-decoration:none">${esc(report.document_no)}</a>
                            <div class="cell-sub">${esc(report.document_type)} · ${esc(report.applicant_name || '')}</div>
                          </td>
                          <td class="num">${money(report.total_amount)}</td>
                          <td>${riskBadge(report.overall_risk_level)}</td>
                        </tr>`
                      )
                      .join('')}
                  </tbody>
                </table></div>`
              : emptyState('暂无风险报告')
          }
        </div>
      </div>
    </div>
  `;
}
