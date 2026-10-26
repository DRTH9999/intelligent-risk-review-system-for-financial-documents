import { api } from '../api.js';
import {
  confirmDialog,
  emptyState,
  esc,
  fileSize,
  fmtDate,
  icon,
  loadingBlock,
  money,
  parseBadge,
  setLoading,
  toast,
} from '../ui.js';

const TYPE_OPTIONS = ['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单'];
const PAYMENT_TYPES = ['对公付款单', '预付款单'];
const TYPE_HINTS = {
  对公付款单: '需上传发票与合同，系统将核验合同金额、付款比例与收款主体',
  预付款单: '需上传合同，系统将核验预付款比例与合同条款',
  批量付款单: '需上传付款依据，系统将校验批次金额、笔数与重复收款账号',
  费用报销单: '需上传发票，系统将校验发票金额、费用标准与重复票据',
  差旅报销单: '需上传发票与行程单，系统将校验行程、住宿与餐费标准',
};

export async function render(root, ctx) {
  const docId = ctx.params.id ? Number(ctx.params.id) : null;
  let doc = null;
  let state = { items: [], initialItems: [], attachments: [] };

  root.innerHTML = loadingBlock(docId ? '正在加载单据…' : '正在初始化表单…');

  if (docId) {
    try {
      doc = await api(`/api/v1/documents/${docId}`);
    } catch (error) {
      root.innerHTML = emptyState('单据加载失败', error.message, 'alert');
      return;
    }
    if (!['draft', 'returned', 'withdrawn'].includes(doc.document_status)) {
      root.innerHTML = `<div class="card"><div class="empty">${icon('alert', 38)}<h4>当前状态不可编辑</h4>
        <p class="small">单据状态为「${esc(doc.document_status)}」，仅草稿、退回或撤回状态允许编辑。</p>
        <div style="margin-top:16px"><a class="btn btn-primary" href="#/documents/${doc.id}">返回单据详情</a></div></div></div>`;
      return;
    }
    state.items = (doc.line_items || []).map((item) => ({ ...item }));
    state.initialItems = JSON.parse(JSON.stringify(state.items));
    state.attachments = doc.attachments || [];
    ctx.setTitle(`编辑单据 ${doc.document_no}`, `${doc.document_type} · 当前版本 V${doc.current_version} · 申请人 ${doc.applicant_name || ''}`);
  } else {
    ctx.setTitle('新建单据', '填写基础信息与明细，保存草稿后可上传附件并提交审批');
  }

  const currentType = doc?.document_type || '费用报销单';
  const user = JSON.parse(localStorage.getItem('risk_review_user') || '{}');

  root.innerHTML = `
    <div class="grid" style="grid-template-columns:1fr">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">单据基本信息</div>
            <div class="card-sub" id="type-hint">${esc(TYPE_HINTS[currentType])}</div>
          </div>
          ${doc ? `<div class="card-actions"><span class="badge badge-${doc.document_status === 'returned' ? 'medium' : 'neutral'}">${doc.document_status === 'returned' ? '退回修改' : '草稿'}</span></div>` : ''}
        </div>
        <div class="card-body">
          <form id="doc-form" class="form-grid" autocomplete="off">
            <div class="field">
              <label class="required">单据类型</label>
              <select id="f-document_type" ${doc ? 'disabled' : ''}>
                ${TYPE_OPTIONS.map((type) => `<option value="${type}" ${currentType === type ? 'selected' : ''}>${type}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label class="required">申请部门</label>
              <input id="f-applicant_department" value="${esc(doc?.applicant_department || user.department || '')}" placeholder="如：市场部" />
            </div>
            <div class="field">
              <label class="required">预算部门</label>
              <input id="f-budget_department" value="${esc(doc?.budget_department || user.department || '')}" placeholder="如：市场部" />
            </div>
            <div class="field">
              <label>收款单位</label>
              <input id="f-payee_name" value="${esc(doc?.payee_name || '')}" placeholder="收款主体名称" />
            </div>
            <div class="field">
              <label>收款账号</label>
              <input id="f-payee_account" value="${esc(doc?.payee_account || '')}" placeholder="用于核对供应商备案账号" />
            </div>
            <div class="field">
              <label>费用类别</label>
              <input id="f-expense_category" value="${esc(doc?.expense_category || '')}" placeholder="如：会务费 / 差旅费 / 办公用品" />
            </div>
            <div class="field">
              <label class="required">单据总金额</label>
              <input id="f-total_amount" type="number" step="0.01" min="0" value="${doc ? Number(doc.total_amount).toFixed(2) : ''}" placeholder="0.00" />
            </div>
            <div class="field">
              <label>币种</label>
              <select id="f-currency">
                ${['CNY', 'USD', 'HKD', 'EUR'].map((currency) => `<option value="${currency}" ${(doc?.currency || 'CNY') === currency ? 'selected' : ''}>${currency}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label class="required">申请日期</label>
              <input id="f-apply_date" type="date" value="${esc(doc?.apply_date || new Date().toISOString().slice(0, 10))}" />
            </div>
            <div class="field full">
              <label>申请事由</label>
              <textarea id="f-reason_text" placeholder="说明支出背景、业务用途与金额构成">${esc(doc?.reason_text || '')}</textarea>
            </div>
          </form>
          <div id="type-extra"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">费用 / 付款明细</div>
            <div class="card-sub" id="items-hint">明细合计需与单据总金额保持一致</div>
          </div>
          <div class="card-actions">
            <button class="btn btn-sm btn-ghost" id="btn-add-item">${icon('plus', 14)} 添加明细</button>
          </div>
        </div>
        <div class="card-body">
          <div id="items-editor">${loadingBlock()}</div>
          <div class="line-total">
            <span>明细合计</span><b id="items-total">¥0.00</b>
            <span>单据总金额</span><b id="doc-total">¥0.00</b>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">附件材料</div>
            <div class="card-sub">支持 PDF、PNG、JPG，单个文件不超过 15MB，上传后自动解析</div>
          </div>
        </div>
        <div class="card-body">
          <div id="attachments-area">${doc ? loadingBlock('正在加载附件…') : ''}</div>
        </div>
      </div>
    </div>`;

  const typeExtra = root.querySelector('#type-extra');
  const itemsRoot = root.querySelector('#items-editor');
  const attachmentsArea = root.querySelector('#attachments-area');

  function currentDocType() {
    return root.querySelector('#f-document_type').value;
  }

  function isBatch() {
    return currentDocType() === '批量付款单';
  }

  function renderTypeExtra() {
    const type = currentDocType();
    root.querySelector('#type-hint').textContent = TYPE_HINTS[type] || '';
    let html = '';
    if (PAYMENT_TYPES.includes(type)) {
      html = `<div class="form-grid" style="margin-top:14px">
        <div class="field"><label>合同编号</label><input id="f-contract_no" value="${esc(doc?.contract_no || '')}" placeholder="如：HT-2026-0918" /></div>
        <div class="field"><label>供应商名称</label><input id="f-supplier_name" value="${esc(doc?.supplier_name || '')}" placeholder="用于匹配供应商档案" /></div>
        <div class="field"><label>供应商编码</label><input id="f-supplier_code" value="${esc(doc?.supplier_code || '')}" placeholder="如：SUP-001" /></div>
        <div class="field"><label>付款比例（%）</label><input id="f-payment_ratio" type="number" step="0.01" min="0" max="100" value="${doc?.payment_ratio ?? ''}" /></div>
        <div class="field"><label>计划付款日期</label><input id="f-planned_payment_date" type="date" value="${esc(doc?.planned_payment_date || '')}" /></div>
        <div class="field"><label>付款条件</label><input id="f-payment_terms" value="${esc(doc?.payment_terms || '')}" /></div>
      </div>`;
    } else if (type === '批量付款单') {
      html = `<div class="form-grid" style="margin-top:14px">
        <div class="field"><label>批次总金额</label><input id="f-batch_total_amount" type="number" step="0.01" value="${doc?.batch_total_amount ?? ''}" /></div>
        <div class="field"><label>付款笔数</label><input id="f-batch_payment_count" type="number" min="1" value="${doc?.batch_payment_count ?? ''}" /></div>
        <div class="field"><label>计划付款日期</label><input id="f-planned_payment_date" type="date" value="${esc(doc?.planned_payment_date || '')}" /></div>
      </div>`;
    } else if (type === '差旅报销单') {
      html = `<div class="form-grid" style="margin-top:14px">
        <div class="field"><label>出差地点</label><input id="f-travel_location" value="${esc(doc?.travel_location || '')}" placeholder="如：北京" /></div>
        <div class="field"><label>出差开始日期</label><input id="f-travel_start_date" type="date" value="${esc(doc?.travel_start_date || '')}" /></div>
        <div class="field"><label>出差结束日期</label><input id="f-travel_end_date" type="date" value="${esc(doc?.travel_end_date || '')}" /></div>
      </div>`;
    }
    typeExtra.innerHTML = html;
    renderItems();
  }

  function newItem() {
    return {
      _key: `tmp-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      item_type: isBatch() ? 'payout' : 'expense',
      item_name: '',
      item_spec: '',
      expense_category: isBatch() ? '批量付款' : '',
      expense_date: root.querySelector('#f-apply_date').value || '',
      expense_location: '',
      quantity: 1,
      unit_price: 0,
      amount: 0,
      payee_name: '',
      payee_account: '',
      remark: '',
    };
  }

  function renderItems() {
    if (!state.items.length) {
      itemsRoot.innerHTML = `<div class="empty" style="padding:26px">${icon('list', 32)}<h4>尚未维护明细</h4><p class="small">点击右上角「添加明细」录入费用或付款信息</p></div>`;
      updateTotals();
      return;
    }
    const batch = isBatch();
    itemsRoot.innerHTML = `<div class="table-wrap"><table class="line-editor">
      <thead><tr>
        <th style="min-width:150px">项目名称</th>
        <th style="min-width:110px">规格/类别</th>
        <th style="min-width:120px">费用类别</th>
        <th style="min-width:130px">发生日期</th>
        <th style="min-width:110px">地点</th>
        <th style="width:70px">数量</th>
        <th style="width:100px">单价</th>
        <th style="width:110px;text-align:right">金额</th>
        ${batch ? '<th style="min-width:160px">收款方</th><th style="min-width:160px">收款账号</th>' : ''}
        <th style="min-width:120px">备注</th>
        <th style="width:44px"></th>
      </tr></thead>
      <tbody>
        ${state.items
          .map(
            (item, index) => `<tr data-row="${index}">
              <td><input data-index="${index}" data-field="item_name" value="${esc(item.item_name || '')}" placeholder="项目名称" /></td>
              <td><input data-index="${index}" data-field="item_spec" value="${esc(item.item_spec || '')}" placeholder="规格" /></td>
              <td><input data-index="${index}" data-field="expense_category" value="${esc(item.expense_category || '')}" placeholder="费用类别" /></td>
              <td><input type="date" data-index="${index}" data-field="expense_date" value="${esc((item.expense_date || '').slice(0, 10))}" /></td>
              <td><input data-index="${index}" data-field="expense_location" value="${esc(item.expense_location || '')}" placeholder="地点" /></td>
              <td><input type="number" step="0.01" data-index="${index}" data-field="quantity" value="${item.quantity ?? 1}" /></td>
              <td><input type="number" step="0.01" data-index="${index}" data-field="unit_price" value="${Number(item.unit_price || 0)}" /></td>
              <td style="text-align:right;font-weight:600" data-amount="${index}">${money((Number(item.quantity || 0) * Number(item.unit_price || 0)))}</td>
              ${batch ? `<td><input data-index="${index}" data-field="payee_name" value="${esc(item.payee_name || '')}" placeholder="收款方" /></td><td><input data-index="${index}" data-field="payee_account" value="${esc(item.payee_account || '')}" placeholder="账号" /></td>` : ''}
              <td><input data-index="${index}" data-field="remark" value="${esc(item.remark || '')}" placeholder="备注" /></td>
              <td><button class="icon-btn" data-remove="${index}" title="删除">${icon('trash', 14)}</button></td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table></div>`;

    itemsRoot.querySelectorAll('[data-field]').forEach((input) => {
      input.addEventListener('input', () => {
        const index = Number(input.dataset.index);
        const field = input.dataset.field;
        const value = field === 'quantity' || field === 'unit_price' ? Number(input.value || 0) : input.value;
        state.items[index][field] = value;
        if (field === 'quantity' || field === 'unit_price') {
          const amount = Number(state.items[index].quantity || 0) * Number(state.items[index].unit_price || 0);
          const cell = itemsRoot.querySelector(`[data-amount="${index}"]`);
          if (cell) cell.textContent = money(amount);
        }
        updateTotals();
      });
    });
    itemsRoot.querySelectorAll('[data-remove]').forEach((button) => {
      button.addEventListener('click', () => {
        state.items.splice(Number(button.dataset.remove), 1);
        renderItems();
      });
    });
    updateTotals();
  }

  function itemsTotal() {
    return state.items.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.unit_price || 0), 0);
  }

  function updateTotals() {
    const total = itemsTotal();
    const docTotal = Number(root.querySelector('#f-total_amount').value || 0);
    root.querySelector('#items-total').textContent = money(total);
    root.querySelector('#doc-total').textContent = money(docTotal);
    const diff = Math.abs(total - docTotal);
    const hint = root.querySelector('#items-hint');
    if (!hint) return;
    if (state.items.length && diff > 0.01) {
      hint.innerHTML = `<span style="color:var(--medium)">明细合计与单据总金额相差 ${money(diff)}，请核对</span>`;
    } else if (state.items.length) {
      hint.innerHTML = '<span style="color:var(--low)">明细合计与单据总金额一致</span>';
    } else {
      hint.textContent = '明细合计需与单据总金额保持一致';
    }
  }

  async function renderAttachments() {
    if (!docId) {
      attachmentsArea.innerHTML = `
        <div class="empty" style="padding:30px">${icon('paperclip', 32)}<h4>保存草稿后可上传附件</h4>
        <p class="small">上传发票、合同、行程单等材料后，系统会自动进行解析与字段提取</p>
        <div style="margin-top:14px"><button class="btn btn-primary btn-sm" id="btn-save-first">先保存草稿</button></div></div>`;
      attachmentsArea.querySelector('#btn-save-first').addEventListener('click', () => save(false));
      return;
    }
    let attachments = state.attachments;
    try {
      const detail = await api(`/api/v1/documents/${docId}`);
      attachments = detail.attachments || [];
      state.attachments = attachments;
      doc = detail;
    } catch (error) {
      attachmentsArea.innerHTML = emptyState('附件加载失败', error.message, 'alert');
      return;
    }

    attachmentsArea.innerHTML = `
      <div class="upload-zone" id="upload-zone">
        ${icon('upload', 26)}
        <b>点击或拖拽文件到此处上传</b>
        <p>支持 PDF / PNG / JPG，单文件不超过 15MB</p>
        <input type="file" id="file-input" accept=".pdf,.png,.jpg,.jpeg" multiple hidden />
      </div>
      <div class="attach-list" style="margin-top:14px">
        ${
          attachments.length
            ? attachments
                .map(
                  (att) => `<div class="attach-item">
                    <div class="file-badge ${att.file_type === 'pdf' ? 'file-pdf' : 'file-img'}">${att.file_type === 'pdf' ? 'PDF' : 'IMG'}</div>
                    <div style="flex:1;min-width:0">
                      <div class="attach-name">${esc(att.file_name)}</div>
                      <div class="attach-meta">${fileSize(att.file_size)} · ${parseBadge(att.parse_status)}</div>
                    </div>
                    <a class="btn btn-sm btn-ghost" href="#/attachments/${docId}/${att.id}">${icon('scan', 13)} 解析</a>
                    <button class="icon-btn" data-delete-att="${att.id}" title="删除附件">${icon('trash', 14)}</button>
                  </div>`
                )
                .join('')
            : `<div class="muted small" style="padding:8px 2px">暂无附件，提交审批前至少需要上传一个附件。</div>`
        }
      </div>`;

    const zone = attachmentsArea.querySelector('#upload-zone');
    const input = attachmentsArea.querySelector('#file-input');
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', (event) => {
      event.preventDefault();
      zone.classList.add('drag');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
    zone.addEventListener('drop', (event) => {
      event.preventDefault();
      zone.classList.remove('drag');
      if (event.dataTransfer.files.length) uploadFiles(Array.from(event.dataTransfer.files));
    });
    input.addEventListener('change', () => {
      if (input.files.length) uploadFiles(Array.from(input.files));
    });
    attachmentsArea.querySelectorAll('[data-delete-att]').forEach((button) => {
      button.addEventListener('click', async () => {
        const ok = await confirmDialog({ title: '删除附件', message: '确认删除该附件吗？删除后需重新上传。', confirmText: '删除', danger: true });
        if (!ok) return;
        try {
          await api(`/api/v1/documents/${docId}/attachments/${button.dataset.deleteAtt}`, { method: 'DELETE' });
          toast('附件已删除', 'success');
          renderAttachments();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    });
    if (attachments.some((att) => ['pending', 'parsing'].includes(att.parse_status))) {
      setTimeout(() => {
        if (document.body.contains(attachmentsArea)) renderAttachments();
      }, 2200);
    }
  }

  async function uploadFiles(files) {
    for (const file of files) {
      if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) {
        toast(`${file.name} 格式不支持，仅支持 PDF / PNG / JPG`, 'warning');
        continue;
      }
      if (file.size > 15 * 1024 * 1024) {
        toast(`${file.name} 超过 15MB`, 'warning');
        continue;
      }
      const formData = new FormData();
      formData.append('file', file);
      try {
        await api(`/api/v1/documents/${docId}/attachments`, { method: 'POST', body: formData });
        toast(`${file.name} 上传成功，正在解析`, 'success');
      } catch (error) {
        toast(`${file.name}：${error.message}`, 'error');
      }
    }
    renderAttachments();
  }

  function collectPayload() {
    const type = currentDocType();
    const value = (id) => root.querySelector(`#${id}`)?.value ?? '';
    const numberOrNull = (id) => {
      const raw = value(id);
      return raw === '' ? null : Number(raw);
    };
    return {
      document_type: type,
      applicant_department: value('f-applicant_department').trim(),
      budget_department: value('f-budget_department').trim(),
      payee_name: value('f-payee_name').trim() || null,
      payee_account: value('f-payee_account').trim() || null,
      expense_category: value('f-expense_category').trim() || null,
      total_amount: Number(value('f-total_amount') || 0),
      currency: value('f-currency') || 'CNY',
      apply_date: value('f-apply_date') || null,
      reason_text: value('f-reason_text').trim() || null,
      contract_no: value('f-contract_no') || null,
      supplier_name: value('f-supplier_name') || null,
      supplier_code: value('f-supplier_code') || null,
      payment_ratio: numberOrNull('f-payment_ratio'),
      payment_terms: value('f-payment_terms') || null,
      planned_payment_date: value('f-planned_payment_date') || null,
      batch_total_amount: numberOrNull('f-batch_total_amount'),
      batch_payment_count: numberOrNull('f-batch_payment_count'),
      travel_location: value('f-travel_location') || null,
      travel_start_date: value('f-travel_start_date') || null,
      travel_end_date: value('f-travel_end_date') || null,
    };
  }

  function validate(payload) {
    if (!payload.applicant_department) return '请填写申请部门';
    if (!payload.budget_department) return '请填写预算部门';
    if (!payload.apply_date) return '请选择申请日期';
    if (!payload.total_amount || payload.total_amount <= 0) return '单据总金额必须大于 0';
    if (PAYMENT_TYPES.includes(payload.document_type)) {
      if (!payload.payee_name) return '付款类单据必须填写收款单位';
      if (payload.document_type === '对公付款单' && !payload.contract_no) return '对公付款单必须填写合同编号';
      if (payload.document_type === '对公付款单' && payload.payment_ratio === null) return '对公付款单必须填写付款比例';
    }
    if (payload.document_type === '批量付款单' && !payload.batch_payment_count) return '批量付款单必须填写付款笔数';
    if (payload.document_type === '差旅报销单' && (!payload.travel_start_date || !payload.travel_end_date)) return '差旅报销单必须填写出差起止日期';
    return null;
  }

  async function save(submitAfter = false, button = null) {
    const payload = collectPayload();
    const error = validate(payload);
    if (error) {
      toast(error, 'warning');
      return;
    }
    if (state.items.some((item) => !item.item_name.trim())) {
      toast('存在未填写项目名称的明细', 'warning');
      return;
    }
    if (button) setLoading(button, true, '保存中…');
    try {
      if (!docId) {
        const created = await api('/api/v1/documents', {
          method: 'POST',
          body: {
            ...payload,
            line_items: state.items.map((item) => ({
              item_type: item.item_type || (isBatch() ? 'payout' : 'expense'),
              item_name: item.item_name,
              item_spec: item.item_spec || null,
              expense_category: item.expense_category || null,
              expense_date: item.expense_date || null,
              expense_location: item.expense_location || null,
              quantity: Number(item.quantity || 0) || 1,
              unit_price: Number(item.unit_price || 0),
              amount: (Math.round(Number(item.quantity || 0) * Number(item.unit_price || 0) * 100) / 100).toFixed(2),
              payee_name: item.payee_name || null,
              payee_account: item.payee_account || null,
              remark: item.remark || null,
            })),
          },
        });
        toast(`单据 ${created.document_no} 已创建`, 'success');
        window.location.hash = `#/documents/${created.id}/edit`;
        return;
      }

      const { document_type, ...changes } = payload;
      changes.revision = doc.revision;
      changes.line_items = state.items.map((item) => ({
        item_type: item.item_type || (isBatch() ? 'payout' : 'expense'),
        item_name: item.item_name, item_spec: item.item_spec || null,
        expense_category: item.expense_category || null, expense_date: item.expense_date || null,
        expense_location: item.expense_location || null, quantity: String(item.quantity ?? 1),
        unit_price: String(item.unit_price ?? 0),
        amount: (Math.round(Number(item.quantity || 0) * Number(item.unit_price || 0) * 100) / 100).toFixed(2),
        payee_name: item.payee_name || null, payee_account: item.payee_account || null,
        remark: item.remark || null,
      }));
      const saved = await api(`/api/v1/documents/${docId}`, { method: 'PATCH', body: changes });
      doc.revision = saved.revision;
      if (submitAfter) {
        const result = await api(`/api/v1/documents/${docId}/submit`, { method: 'POST' });
        toast(`单据已提交，分析任务 #${result.analysis_task.id} 已启动`, 'success');
        window.location.hash = `#/analysis/${result.analysis_task.id}`;
        return;
      }
      toast('单据草稿已保存', 'success');
      const fresh = await api(`/api/v1/documents/${docId}`);
      doc = fresh;
      state.items = (fresh.line_items || []).map((item) => ({ ...item }));
      state.initialItems = JSON.parse(JSON.stringify(state.items));
      state.attachments = fresh.attachments || [];
      renderItems();
      renderAttachments();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      if (button) setLoading(button, false);
    }
  }

  ctx.setActions(`
    <button class="btn btn-ghost" id="btn-save">${icon('archive', 15)} 保存草稿</button>
    <button class="btn btn-primary" id="btn-submit">${icon('send', 15)} 保存并提交审批</button>
  `);
  const actionBar = document.getElementById('page-actions');

  actionBar.querySelector('#btn-save').addEventListener('click', (event) => save(false, event.currentTarget));
  actionBar.querySelector('#btn-submit').addEventListener('click', async (event) => {
    const ok = await confirmDialog({
      title: '提交审批',
      message: '提交后单据将进入审批流程，系统会自动解析附件并生成风险分析报告。确认继续吗？',
      confirmText: '提交审批',
    });
    if (ok) save(true, event.currentTarget);
  });
  root.querySelector('#btn-add-item').addEventListener('click', () => {
    state.items.push(newItem());
    renderItems();
  });
  root.querySelector('#f-document_type').addEventListener('change', () => {
    state.items = [];
    renderTypeExtra();
  });
  root.querySelector('#f-total_amount').addEventListener('input', updateTotals);
  root.querySelector('#f-apply_date').addEventListener('change', updateTotals);

  renderTypeExtra();
  renderAttachments();
}
