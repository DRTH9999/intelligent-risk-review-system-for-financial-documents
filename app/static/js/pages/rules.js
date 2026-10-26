import { api, session } from '../api.js';
import {
  emptyState,
  esc,
  fmtDate,
  icon,
  loadingBlock,
  money,
  openModal,
  toast,
} from '../ui.js';

const CONFIG_LABELS = {
  abs_tolerance: '绝对容差（元）',
  pct_tolerance: '比例容差（%）',
  medium_pct: '中风险阈值（%）',
  high_pct: '高风险阈值（%）',
  amount_tolerance: '金额容差（元）',
  count_tolerance: '笔数容差',
  standards: '费用标准',
  per_day: '每日限额',
  per_night: '每晚限额',
  per_trip: '单次限额',
  per_item: '单项限额',
  level: '超标等级',
  deviation_pct: '偏离阈值（%）',
  history_growth_ratio: '历史增长倍数',
  split_window_days: '拆单观察窗口（天）',
  split_min_count: '拆单最少笔数',
  split_amount_threshold: '拆单金额阈值（元）',
  short_term_count: '短期频次阈值（笔）',
  short_term_days: '短期观察窗口（天）',
  same_day_tolerance_pct: '同日金额相似容差（%）',
  concentration_window_days: '集中付款窗口（天）',
  concentration_count: '集中付款笔数阈值',
  account_mismatch_level: '账号不一致等级',
  min_confidence: '最低置信度',
  company_name: '公司主体名称',
};

const SEVERITY_LABELS = { high: '高', medium: '中', low: '低' };

export async function render(root, ctx) {
  const roles = session.user?.roles || [];
  if (!roles.some((role) => ['finance', 'admin'].includes(role))) {
    root.innerHTML = emptyState('无访问权限', '规则配置仅财务人员与系统管理员可访问', 'shield');
    return;
  }
  let rules = [];
  let prices = [];

  ctx.setActions(`<button class="btn btn-ghost" id="btn-refresh">${icon('refresh', 15)} 刷新配置</button>`);
  root.innerHTML = `<div id="rules-wrap">${loadingBlock('正在加载审核规则…')}</div>`;
  const wrap = root.querySelector('#rules-wrap');

  async function load() {
    wrap.innerHTML = loadingBlock('正在加载审核规则…');
    try {
      [rules, prices] = await Promise.all([api('/api/v1/rules'), api('/api/v1/market-prices')]);
    } catch (error) {
      wrap.innerHTML = emptyState('配置加载失败', error.message, 'alert');
      return;
    }
    wrap.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div class="card-head">
          <div>
            <div class="card-title">风险规则参数</div>
            <div class="card-sub">保存后对后续新建的分析任务生效，规则变更将写入审计日志</div>
          </div>
          <div class="card-actions"><span class="badge badge-primary">${rules.filter((rule) => rule.status === 'active').length} 条启用</span></div>
        </div>
        <div class="card-body">
          <div class="grid grid-2">
            ${rules
              .map(
                (rule) => `<div class="rule-card" data-rule="${rule.id}">
                  <div class="rule-head">
                    <div style="flex:1;min-width:0">
                      <div style="font-weight:700;font-size:13.5px">${esc(rule.rule_name)}</div>
                      <div class="rule-code">${esc(rule.rule_code)} · ${esc(rule.rule_type)}</div>
                    </div>
                    <span class="badge badge-${rule.status === 'active' ? 'low' : 'neutral'}">${rule.status === 'active' ? '启用' : '停用'}</span>
                    <span class="badge badge-${rule.severity === 'high' ? 'high' : rule.severity === 'medium' ? 'medium' : 'low'}">默认${SEVERITY_LABELS[rule.severity] || rule.severity}</span>
                  </div>
                  <div class="rule-config">
                    ${configFields(rule.config || {}, [])}
                  </div>
                  <div style="display:flex;gap:8px;align-items:center;margin-top:12px">
                    <select data-rule-status style="height:30px;border:1px solid var(--line);border-radius:7px;padding:0 7px;font-size:12px">
                      <option value="active" ${rule.status === 'active' ? 'selected' : ''}>启用</option>
                      <option value="inactive" ${rule.status !== 'active' ? 'selected' : ''}>停用</option>
                    </select>
                    <span class="small muted" style="flex:1">更新于 ${esc(fmtDate(rule.updated_at))}</span>
                    <button class="btn btn-sm btn-primary" data-save-rule>保存规则</button>
                  </div>
                </div>`
              )
              .join('')}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">市场价参考数据</div>
            <div class="card-sub">用于比对采购单价是否偏离市场区间</div>
          </div>
          <div class="card-actions"><button class="btn btn-sm btn-primary" id="btn-add-price">${icon('plus', 13)} 新增参考价</button></div>
        </div>
        <div class="card-body flush">
          ${
            prices.length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>商品 / 服务</th><th>规格</th><th>地区</th><th>参考区间</th><th>数据来源</th><th>生效日期</th><th></th></tr></thead>
                  <tbody>${prices
                    .map(
                      (price) => `<tr>
                        <td class="cell-main">${esc(price.item_name)}</td>
                        <td class="muted small">${esc(price.specification || '-')}</td>
                        <td>${esc(price.region || '全国')}</td>
                        <td>${money(price.price_min)} ~ ${money(price.price_max)}</td>
                        <td class="muted small">${esc(price.source_name || '-')}</td>
                        <td class="muted small">${fmtDate(price.effective_date)}</td>
                        <td style="text-align:right"><button class="btn btn-sm btn-ghost" data-edit-price="${price.id}">编辑</button></td>
                      </tr>`
                    )
                    .join('')}</tbody>
                </table></div>`
              : emptyState('暂无市场价参考数据', '点击右上角新增', 'cash')
          }
        </div>
      </div>`;

    bindRules();
    bindPrices();
  }

  function label(key) {
    return CONFIG_LABELS[key] || key;
  }

  function configFields(config, path) {
    return Object.entries(config)
      .map(([key, value]) => {
        if (value && typeof value === 'object' && !Array.isArray(value)) {
          return `<div class="config-nested">
            <div class="config-nested-title">${esc(label(key))}</div>
            <div class="rule-config">${configFields(value, [...path, key])}</div>
          </div>`;
        }
        const type = typeof value;
        const pathJson = esc(JSON.stringify([...path, key]));
        return `<div class="field">
          <label>${esc(label(key))}</label>
          <input data-config-path="${pathJson}" data-type="${type}" value="${esc(value)}" />
        </div>`;
      })
      .join('');
  }

  function bindRules() {
    wrap.querySelectorAll('[data-save-rule]').forEach((button) => {
      button.addEventListener('click', async () => {
        const card = button.closest('[data-rule]');
        const ruleId = Number(card.dataset.rule);
        const rule = rules.find((item) => item.id === ruleId);
        if (!rule) return;
        const config = JSON.parse(JSON.stringify(rule.config || {}));
        card.querySelectorAll('[data-config-path]').forEach((input) => {
          const path = JSON.parse(input.dataset.configPath);
          let value = input.value;
          if (input.dataset.type === 'number') value = Number(value || 0);
          if (input.dataset.type === 'boolean') value = value === 'true';
          let target = config;
          path.slice(0, -1).forEach((segment) => {
            target = target[segment];
          });
          target[path[path.length - 1]] = value;
        });
        button.disabled = true;
        try {
          await api(`/api/v1/rules/${ruleId}`, {
            method: 'PATCH',
            body: { config, status: card.querySelector('[data-rule-status]').value },
          });
          toast(`${rule.rule_name} 已更新`, 'success');
          await load();
        } catch (error) {
          toast(error.message, 'error');
          button.disabled = false;
        }
      });
    });
  }

  function bindPrices() {
    wrap.querySelector('#btn-add-price').addEventListener('click', () => openPriceModal(null));
    wrap.querySelectorAll('[data-edit-price]').forEach((button) => {
      button.addEventListener('click', () => {
        openPriceModal(prices.find((item) => item.id === Number(button.dataset.editPrice)));
      });
    });
  }

  function openPriceModal(price) {
    const isEdit = Boolean(price);
    const { root: modal, close } = openModal({
      title: isEdit ? '编辑市场价参考' : '新增市场价参考',
      body: `
        <div class="form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="field full"><label class="required">商品 / 服务名称</label><input id="p-name" value="${esc(price?.item_name || '')}" placeholder="如：会议服务" /></div>
          <div class="field"><label>规格</label><input id="p-spec" value="${esc(price?.specification || '')}" placeholder="如：人/场" /></div>
          <div class="field"><label>地区</label><input id="p-region" value="${esc(price?.region || '')}" placeholder="如：上海" /></div>
          <div class="field"><label>最低价</label><input id="p-min" type="number" step="0.01" value="${price?.price_min ?? ''}" /></div>
          <div class="field"><label>最高价</label><input id="p-max" type="number" step="0.01" value="${price?.price_max ?? ''}" /></div>
          <div class="field"><label>数据来源</label><input id="p-source" value="${esc(price?.source_name || '')}" /></div>
          <div class="field"><label>生效日期</label><input id="p-date" type="date" value="${esc(price?.effective_date || new Date().toISOString().slice(0, 10))}" /></div>
        </div>`,
      footer: `<button class="btn btn-ghost" data-cancel>取消</button><button class="btn btn-primary" data-save>保存</button>`,
    });
    modal.querySelector('[data-cancel]').addEventListener('click', close);
    modal.querySelector('[data-save]').addEventListener('click', async () => {
      const name = modal.querySelector('#p-name').value.trim();
      if (!name) {
        toast('请填写商品或服务名称', 'warning');
        return;
      }
      const payload = {
        item_name: name,
        specification: modal.querySelector('#p-spec').value.trim() || null,
        region: modal.querySelector('#p-region').value.trim() || null,
        price_min: Number(modal.querySelector('#p-min').value || 0),
        price_max: Number(modal.querySelector('#p-max').value || 0),
        source_name: modal.querySelector('#p-source').value.trim() || null,
        effective_date: modal.querySelector('#p-date').value || null,
      };
      try {
        if (isEdit) {
          await api(`/api/v1/market-prices/${price.id}`, { method: 'PATCH', body: payload });
        } else {
          await api('/api/v1/market-prices', { method: 'POST', body: payload });
        }
        close();
        toast('市场价参考数据已保存', 'success');
        await load();
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  }

  document.getElementById('page-actions')?.querySelector('#btn-refresh')?.addEventListener('click', load);
  await load();
}
