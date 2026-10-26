import { api, session } from '../api.js';
import {
  emptyState,
  esc,
  fmtDate,
  icon,
  loadingBlock,
  money,
  openModal,
  riskBadge,
  toast,
} from '../ui.js';

const CREDIT_LABELS = {
  normal: '正常',
  good: '良好',
  watch: '关注',
  abnormal: '异常',
};

export async function render(root, ctx) {
  const roles = session.user?.roles || [];
  const canManage = roles.some((role) => ['finance', 'admin'].includes(role));
  let suppliers = [];
  let selected = null;
  let detail = null;
  let keyword = '';

  ctx.setActions(`<button class="btn btn-ghost" id="btn-refresh">${icon('refresh', 15)} 刷新</button>`);

  root.innerHTML = `
    <div class="grid" style="grid-template-columns:0.95fr 1.4fr;align-items:start">
      <div class="card">
        <div class="card-head">
          <div class="card-title">供应商档案</div>
          <div class="card-actions"><span class="badge badge-neutral" id="supplier-count">0</span></div>
        </div>
        <div class="card-body">
          <div class="field" style="margin-bottom:12px">
            <input id="supplier-search" placeholder="搜索供应商名称" />
          </div>
          <div id="supplier-list">${loadingBlock('正在加载供应商…')}</div>
        </div>
      </div>
      <div id="supplier-detail">${emptyState('请选择供应商', '查看供应商风险标签、备案账号与历史付款', 'building')}</div>
    </div>`;

  const listEl = root.querySelector('#supplier-list');
  const detailEl = root.querySelector('#supplier-detail');

  function renderList() {
    root.querySelector('#supplier-count').textContent = `${suppliers.length} 家`;
    if (!suppliers.length) {
      listEl.innerHTML = emptyState('未找到供应商', '调整搜索关键词后重试', 'building');
      return;
    }
    listEl.innerHTML = suppliers
      .map(
        (supplier) => `<div class="mini-item" data-code="${esc(supplier.supplier_code)}" style="cursor:pointer;padding:11px 8px;border-radius:8px;${selected === supplier.supplier_code ? 'background:var(--primary-soft)' : ''}">
          <div class="supplier-avatar" style="width:34px;height:34px;border-radius:9px;font-size:12px">${esc(supplier.supplier_name.slice(0, 1))}</div>
          <div class="grow">
            <div class="mini-title">${esc(supplier.supplier_name)}</div>
            <div class="mini-sub">${esc(supplier.supplier_code)} · ${supplier.payment_count} 笔 · ${money(supplier.payment_total)}</div>
            <div class="tag-row" style="margin-top:4px">
              ${supplier.blacklist_status !== 'normal' ? '<span class="badge badge-high">黑名单</span>' : ''}
              ${supplier.credit_status !== 'normal' && supplier.credit_status !== 'good' ? `<span class="badge badge-medium">${esc(CREDIT_LABELS[supplier.credit_status] || supplier.credit_status)}</span>` : ''}
              ${(supplier.risk_tags || []).slice(0, 2).map((tag) => `<span class="tag">${esc(tag)}</span>`).join('')}
            </div>
          </div>
        </div>`
      )
      .join('');
    listEl.querySelectorAll('[data-code]').forEach((item) => {
      item.addEventListener('click', () => selectSupplier(item.dataset.code));
    });
  }

  async function loadSuppliers() {
    try {
      suppliers = await api(`/api/v1/suppliers${keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''}`);
    } catch (error) {
      listEl.innerHTML = emptyState('供应商加载失败', error.message, 'alert');
      return;
    }
    if (!suppliers.length) {
      renderList();
      return;
    }
    if (!selected || !suppliers.some((item) => item.supplier_code === selected)) {
      selected = suppliers[0].supplier_code;
    }
    renderList();
    await loadDetail(selected);
  }

  async function selectSupplier(code) {
    selected = code;
    renderList();
    await loadDetail(code);
  }

  async function loadDetail(code) {
    detailEl.innerHTML = loadingBlock('正在加载供应商风险信息…');
    try {
      detail = await api(`/api/v1/suppliers/${encodeURIComponent(code)}/risks`);
    } catch (error) {
      detailEl.innerHTML = emptyState('供应商详情加载失败', error.message, 'alert');
      return;
    }
    renderDetail();
  }

  function renderDetail() {
    const supplier = detail;
    if (!supplier) {
      detailEl.innerHTML = emptyState('请选择供应商', '', 'building');
      return;
    }
    detailEl.innerHTML = `
      <div class="card">
        <div class="card-body" style="padding-top:18px">
          <div class="supplier-card">
            <div class="supplier-avatar" style="width:56px;height:56px;font-size:20px">${esc(supplier.supplier_name.slice(0, 1))}</div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <h3 style="font-size:17px">${esc(supplier.supplier_name)}</h3>
                <span class="mono muted small">${esc(supplier.supplier_code)}</span>
                ${supplier.blacklist_status !== 'normal' ? '<span class="badge badge-high">黑名单</span>' : '<span class="badge badge-low">非黑名单</span>'}
                <span class="badge badge-${['normal', 'good'].includes(supplier.credit_status) ? 'low' : supplier.credit_status === 'watch' ? 'medium' : 'high'}">信用 ${esc(CREDIT_LABELS[supplier.credit_status] || supplier.credit_status)}</span>
              </div>
              <div class="tag-row">
                ${(supplier.risk_tags || []).map((tag) => `<span class="tag">${esc(tag)}</span>`).join('') || '<span class="muted small">暂无风险标签</span>'}
              </div>
              <div class="cell-sub" style="margin-top:6px">联系方式：${esc(supplier.contact_info || '-')} · 最近更新 ${esc(fmtDate(supplier.updated_at))}</div>
            </div>
            ${canManage ? `<button class="btn btn-sm btn-ghost" id="btn-edit-supplier">${icon('edit', 14)} 维护档案</button>` : ''}
          </div>

          <div class="divider"></div>
          <div class="grid grid-4" style="gap:10px">
            <div class="amount-cell"><div class="a-label">历史付款</div><div class="a-value" style="font-size:18px">${supplier.payment_count} 笔</div></div>
            <div class="amount-cell"><div class="a-label">累计金额</div><div class="a-value" style="font-size:18px">${money(supplier.payment_total)}</div></div>
            <div class="amount-cell"><div class="a-label">风险标签</div><div class="a-value" style="font-size:18px">${(supplier.risk_tags || []).length} 个</div></div>
            <div class="amount-cell"><div class="a-label">风险事件</div><div class="a-value" style="font-size:18px;color:${(supplier.risk_events || []).length ? 'var(--high)' : 'var(--low)'}">${(supplier.risk_events || []).length} 条</div></div>
          </div>

          <div class="section-title" style="margin-top:18px">备案收款账号</div>
          <div class="tag-row">
            ${(supplier.bank_accounts || []).map((account) => `<span class="mono tag" style="font-size:12px">${esc(account)}</span>`).join('') || '<span class="muted small">未备案收款账号</span>'}
          </div>

          <div class="section-title" style="margin-top:18px">历史付款记录</div>
          ${
            (supplier.history || []).length
              ? `<div class="table-wrap"><table class="table">
                  <thead><tr><th>单据编号</th><th>类型</th><th style="text-align:right">金额</th><th>状态</th><th>申请日期</th></tr></thead>
                  <tbody>${supplier.history
                    .map(
                      (item) => `<tr>
                        <td><a class="cell-main" href="#/documents/${item.document_id}" style="text-decoration:none">${esc(item.document_no)}</a></td>
                        <td class="muted small">${esc(item.document_type)}</td>
                        <td class="num">${money(item.total_amount)}</td>
                        <td class="muted small">${esc(item.document_status)}</td>
                        <td class="muted small">${fmtDate(item.apply_date)}</td>
                      </tr>`
                    )
                    .join('')}</tbody>
                </table></div>`
              : '<p class="muted small">该供应商暂无付款记录。</p>'
          }

          <div class="section-title" style="margin-top:18px">供应商风险事件</div>
          ${
            (supplier.risk_events || []).length
              ? supplier.risk_events
                  .map(
                    (event) => `<div class="alert-item">
                      <div class="alert-icon" style="background:${event.risk_level === 'high' ? 'var(--high-soft)' : 'var(--medium-soft)'};color:${event.risk_level === 'high' ? 'var(--high)' : 'var(--medium)'}">${icon('alert', 15)}</div>
                      <div style="flex:1;min-width:0">
                        <div class="mini-title">${esc(event.risk_title)}</div>
                        <div class="mini-sub">${esc(event.description)}</div>
                        <div class="cell-sub">关联单据 <a href="#/documents/${event.document_id}">#${event.document_id}</a> · ${esc(fmtDate(event.created_at))}</div>
                      </div>
                      ${riskBadge(event.risk_level)}
                    </div>`
                  )
                  .join('')
              : '<p class="muted small">暂无高风险或中风险事件。</p>'
          }
        </div>
      </div>`;

    if (canManage) {
      detailEl.querySelector('#btn-edit-supplier')?.addEventListener('click', openEditModal);
    }
  }

  function openEditModal() {
    const supplier = detail;
    const { root: modal, close } = openModal({
      title: '维护供应商档案',
      size: 'lg',
      body: `
        <div class="form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="field"><label>信用状态</label>
            <select id="s-credit">
              ${Object.entries(CREDIT_LABELS).map(([value, label]) => `<option value="${value}" ${supplier.credit_status === value ? 'selected' : ''}>${label}</option>`).join('')}
            </select>
          </div>
          <div class="field"><label>黑名单状态</label>
            <select id="s-blacklist">
              <option value="normal" ${supplier.blacklist_status === 'normal' ? 'selected' : ''}>正常</option>
              <option value="watch" ${supplier.blacklist_status === 'watch' ? 'selected' : ''}>关注</option>
              <option value="blacklist" ${supplier.blacklist_status === 'blacklist' ? 'selected' : ''}>黑名单</option>
            </select>
          </div>
          <div class="field full"><label>风险标签（逗号分隔）</label><input id="s-tags" value="${esc((supplier.risk_tags || []).join('，'))}" /></div>
          <div class="field full"><label>备案收款账号（逗号分隔）</label><input id="s-accounts" value="${esc((supplier.bank_accounts || []).join('，'))}" /></div>
          <div class="field full"><label>联系方式</label><input id="s-contact" value="${esc(supplier.contact_info || '')}" /></div>
        </div>`,
      footer: `<button class="btn btn-ghost" data-cancel>取消</button><button class="btn btn-primary" data-save>保存档案</button>`,
    });
    modal.querySelector('[data-cancel]').addEventListener('click', close);
    modal.querySelector('[data-save]').addEventListener('click', async () => {
      const tags = modal
        .querySelector('#s-tags')
        .value.split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean);
      const accounts = modal
        .querySelector('#s-accounts')
        .value.split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean);
      try {
        await api(`/api/v1/suppliers/${encodeURIComponent(supplier.supplier_code)}`, {
          method: 'PATCH',
          body: {
            credit_status: modal.querySelector('#s-credit').value,
            blacklist_status: modal.querySelector('#s-blacklist').value,
            risk_tags: tags,
            bank_accounts: accounts,
            contact_info: modal.querySelector('#s-contact').value.trim() || null,
          },
        });
        close();
        toast('供应商档案已更新', 'success');
        await loadSuppliers();
        await loadDetail(supplier.supplier_code);
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  }

  document.getElementById('page-actions')?.querySelector('#btn-refresh')?.addEventListener('click', loadSuppliers);
  const search = root.querySelector('#supplier-search');
  let debounceTimer;
  search.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      keyword = search.value.trim();
      loadSuppliers();
    }, 320);
  });

  await loadSuppliers();
}
