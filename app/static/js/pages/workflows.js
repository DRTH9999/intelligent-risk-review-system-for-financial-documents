import { api, session } from '../api.js';
import {
  ROLE_LABELS,
  emptyState,
  esc,
  icon,
  loadingBlock,
  money,
  openModal,
  toast,
} from '../ui.js';

const DOCUMENT_TYPES = ['对公付款单', '预付款单', '批量付款单', '费用报销单', '差旅报销单'];
const ROLES = ['approver', 'finance', 'admin'];

export async function render(root, ctx) {
  const roles = session.user?.roles || [];
  if (!roles.includes('admin')) {
    root.innerHTML = emptyState('无访问权限', '审批流程配置仅系统管理员可访问', 'shield');
    return;
  }
  let workflows = [];

  ctx.setActions(`<button class="btn btn-primary" id="btn-new-workflow">${icon('plus', 15)} 新建审批流程</button>`);
  root.innerHTML = `<div id="workflow-list">${loadingBlock('正在加载审批流程…')}</div>`;

  const listEl = root.querySelector('#workflow-list');

  async function load() {
    listEl.innerHTML = loadingBlock('正在加载审批流程…');
    try {
      workflows = await api('/api/v1/approval-workflows');
    } catch (error) {
      listEl.innerHTML = emptyState('审批流程加载失败', error.message, 'alert');
      return;
    }
    if (!workflows.length) {
      listEl.innerHTML = emptyState('暂无审批流程', '点击右上角新建流程', 'branch');
      return;
    }
    const grouped = {};
    workflows.forEach((workflow) => {
      grouped[workflow.document_type] = grouped[workflow.document_type] || [];
      grouped[workflow.document_type].push(workflow);
    });
    listEl.innerHTML = Object.entries(grouped)
      .map(
        ([type, items]) => `<div class="card" style="margin-bottom:16px">
          <div class="card-head">
            <div>
              <div class="card-title">${esc(type)}</div>
              <div class="card-sub">共 ${items.length} 条流程，按金额区间匹配</div>
            </div>
          </div>
          <div class="card-body">
            <div class="grid grid-2">
              ${items
                .map(
                  (workflow) => `<div class="workflow-card">
                    <div class="workflow-head">
                      <div style="flex:1;min-width:0">
                        <div style="font-weight:700;font-size:13.5px">${esc(workflow.workflow_name)}</div>
                        <div class="cell-sub">${conditionText(workflow.match_conditions)}</div>
                      </div>
                      <span class="badge badge-${workflow.status === 'active' ? 'low' : 'neutral'}">${workflow.status === 'active' ? '启用' : '停用'}</span>
                      <button class="btn btn-sm btn-ghost" data-edit="${workflow.id}">${icon('edit', 13)} 配置</button>
                    </div>
                    <div class="workflow-nodes">
                      ${workflow.nodes
                        .map(
                          (node, index) => `${index ? '<span class="node-arrow">' + icon('arrowRight', 14) + '</span>' : ''}
                            <span class="node-pill"><span class="node-index">${index + 1}</span>${esc(node.node_name)}
                              <span class="muted small">${esc(ROLE_LABELS[node.approver_role] || node.approver_role)}</span>
                            </span>`
                        )
                        .join('')}
                    </div>
                  </div>`
                )
                .join('')}
            </div>
          </div>
        </div>`
      )
      .join('');

    listEl.querySelectorAll('[data-edit]').forEach((button) => {
      button.addEventListener('click', () => {
        const workflow = workflows.find((item) => item.id === Number(button.dataset.edit));
        openWorkflowModal(workflow);
      });
    });
  }

  function conditionText(conditions = {}) {
    const parts = [];
    if (conditions.amount_min !== undefined) parts.push(`金额 ≥ ${money(conditions.amount_min)}`);
    if (conditions.amount_max !== undefined && conditions.amount_max !== null) parts.push(`金额 ≤ ${money(conditions.amount_max)}`);
    if ((conditions.departments || []).length) parts.push(`部门：${conditions.departments.join('、')}`);
    return parts.length ? parts.join(' · ') : '适用于全部金额';
  }

  function nodeRow(node = {}, index = 0) {
    return `<div class="node-row" style="display:grid;grid-template-columns:1fr 150px 32px;gap:8px;margin-bottom:8px" data-node-row>
      <input data-node-name placeholder="节点名称，如：部门负责人审批" value="${esc(node.node_name || '')}" style="height:34px;border:1px solid var(--line);border-radius:7px;padding:0 9px" />
      <select data-node-role style="height:34px;border:1px solid var(--line);border-radius:7px;padding:0 6px">
        ${ROLES.map((role) => `<option value="${role}" ${node.approver_role === role ? 'selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}
      </select>
      <button class="icon-btn" data-remove-node title="删除节点">${icon('x', 14)}</button>
    </div>`;
  }

  function openWorkflowModal(workflow = null) {
    const isEdit = Boolean(workflow);
    const conditions = workflow?.match_conditions || {};
    const nodes = workflow?.nodes?.length ? workflow.nodes : [{ node_name: '部门负责人审批', approver_role: 'approver' }];
    const { root: modal, close } = openModal({
      title: isEdit ? '配置审批流程' : '新建审批流程',
      size: 'lg',
      body: `
        <div class="form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="field full"><label class="required">流程名称</label><input id="w-name" value="${esc(workflow?.workflow_name || '')}" placeholder="如：费用报销标准流程（5000 元以下）" /></div>
          <div class="field"><label class="required">适用单据类型</label>
            <select id="w-type">
              ${DOCUMENT_TYPES.map((type) => `<option value="${type}" ${workflow?.document_type === type ? 'selected' : ''}>${type}</option>`).join('')}
            </select>
          </div>
          <div class="field"><label>流程状态</label>
            <select id="w-status">
              <option value="active" ${workflow?.status !== 'inactive' ? 'selected' : ''}>启用</option>
              <option value="inactive" ${workflow?.status === 'inactive' ? 'selected' : ''}>停用</option>
            </select>
          </div>
          <div class="field"><label>适用金额下限</label><input id="w-min" type="number" step="0.01" value="${conditions.amount_min ?? 0}" /></div>
          <div class="field"><label>适用金额上限</label><input id="w-max" type="number" step="0.01" value="${conditions.amount_max ?? ''}" placeholder="留空表示不限制" /></div>
          <div class="field full"><label>适用部门（逗号分隔，留空表示全部）</label><input id="w-departments" value="${esc((conditions.departments || []).join('，'))}" placeholder="如：市场部，研发部" /></div>
        </div>
        <div class="divider"></div>
        <div class="section-title">审批节点</div>
        ${isEdit ? `<label class="small muted" style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><input type="checkbox" id="w-replace-nodes" /> 重建审批节点（仅未被审批实例引用的流程可用）</label>` : ''}
        <div id="node-list">${nodes.map((node, index) => nodeRow(node, index)).join('')}</div>
        <button class="btn btn-sm btn-ghost" id="btn-add-node">${icon('plus', 13)} 添加节点</button>
        <p class="small muted" style="margin-top:10px">审批节点按顺序流转。若流程已被审批实例引用，则不能重建节点。</p>`,
      footer: `<button class="btn btn-ghost" data-cancel>取消</button><button class="btn btn-primary" data-save>${isEdit ? '保存配置' : '创建流程'}</button>`,
    });

    const nodeList = modal.querySelector('#node-list');
    modal.querySelector('#btn-add-node').addEventListener('click', () => {
      nodeList.insertAdjacentHTML('beforeend', nodeRow({ approver_role: 'approver' }, nodeList.children.length));
      bindRemove();
    });
    function bindRemove() {
      nodeList.querySelectorAll('[data-remove-node]').forEach((button) => {
        if (button.dataset.bound) return;
        button.dataset.bound = '1';
        button.addEventListener('click', () => {
          if (nodeList.children.length <= 1) {
            toast('至少保留一个审批节点', 'warning');
            return;
          }
          button.closest('[data-node-row]').remove();
        });
      });
    }
    bindRemove();
    modal.querySelector('[data-cancel]').addEventListener('click', close);
    modal.querySelector('[data-save]').addEventListener('click', async () => {
      const name = modal.querySelector('#w-name').value.trim();
      if (!name) {
        toast('请填写流程名称', 'warning');
        return;
      }
      const nodeRows = Array.from(nodeList.querySelectorAll('[data-node-row]'));
      const payloadNodes = nodeRows.map((row, index) => ({
        node_name: row.querySelector('[data-node-name]').value.trim(),
        node_order: index + 1,
        approver_role: row.querySelector('[data-node-role]').value,
        approval_mode: 'single',
      }));
      if (payloadNodes.some((node) => !node.node_name)) {
        toast('审批节点名称不能为空', 'warning');
        return;
      }
      const maxRaw = modal.querySelector('#w-max').value;
      const matchConditions = {
        amount_min: Number(modal.querySelector('#w-min').value || 0),
      };
      if (maxRaw !== '') matchConditions.amount_max = Number(maxRaw);
      const departments = modal
        .querySelector('#w-departments')
        .value.split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (departments.length) matchConditions.departments = departments;

      const payload = {
        workflow_name: name,
        document_type: modal.querySelector('#w-type').value,
        match_conditions: matchConditions,
        status: modal.querySelector('#w-status').value,
      };
      const replaceNodes = !isEdit || modal.querySelector('#w-replace-nodes')?.checked;
      if (replaceNodes) payload.nodes = payloadNodes;
      try {
        if (isEdit) {
          await api(`/api/v1/approval-workflows/${workflow.id}`, { method: 'PATCH', body: payload });
        } else {
          await api('/api/v1/approval-workflows', { method: 'POST', body: payload });
        }
        close();
        toast('审批流程已保存', 'success');
        await load();
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  }

  document.getElementById('page-actions')?.querySelector('#btn-new-workflow')?.addEventListener('click', () => openWorkflowModal(null));
  await load();
}
