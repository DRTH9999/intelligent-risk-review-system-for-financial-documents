import { api, session } from '../api.js';
import {
  ROLE_LABELS,
  emptyState,
  esc,
  fmtDate,
  icon,
  loadingBlock,
  openModal,
  roleLabel,
  toast,
} from '../ui.js';

export async function render(root, ctx) {
  const roles = session.user?.roles || [];
  if (!roles.includes('admin')) {
    root.innerHTML = emptyState('无访问权限', '用户管理仅系统管理员可访问', 'shield');
    return;
  }
  let users = [];
  let roleOptions = [];

  ctx.setActions(`<button class="btn btn-primary" id="btn-new-user">${icon('plus', 15)} 新建用户</button>`);
  root.innerHTML = `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">系统用户</div>
          <div class="card-sub">按角色控制数据权限与操作权限</div>
        </div>
        <div class="card-actions"><span class="badge badge-primary" id="user-count">0</span></div>
      </div>
      <div class="card-body" id="user-table">${loadingBlock('正在加载用户…')}</div>
    </div>`;

  const tableEl = root.querySelector('#user-table');

  async function load() {
    tableEl.innerHTML = loadingBlock('正在加载用户…');
    try {
      [users, roleOptions] = await Promise.all([api('/api/v1/users'), api('/api/v1/roles')]);
    } catch (error) {
      tableEl.innerHTML = emptyState('用户加载失败', error.message, 'alert');
      return;
    }
    root.querySelector('#user-count').textContent = `${users.length} 个账号`;
    tableEl.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>用户</th><th>部门 / 职级</th><th>角色</th><th>状态</th><th>创建时间</th><th style="text-align:right">操作</th></tr></thead>
      <tbody>
        ${users
          .map(
            (user) => `<tr>
              <td>
                <div style="display:flex;align-items:center;gap:10px">
                  <div class="avatar" style="width:32px;height:32px;font-size:11px">${esc((user.display_name || 'U').slice(-2))}</div>
                  <div>
                    <div class="cell-main">${esc(user.display_name)}</div>
                    <div class="cell-sub mono">${esc(user.username)}</div>
                  </div>
                </div>
              </td>
              <td>${esc(user.department || '-')}<div class="cell-sub">${esc(user.job_level || '-')}</div></td>
              <td><div class="tag-row">${(user.roles || []).map((role) => `<span class="badge badge-primary">${esc(ROLE_LABELS[role] || role)}</span>`).join('')}</div></td>
              <td><span class="badge badge-${user.status === 'active' ? 'low' : 'neutral'}">${user.status === 'active' ? '正常' : '停用'}</span></td>
              <td class="muted small">${esc(fmtDate(user.created_at))}</td>
              <td style="text-align:right"><button class="btn btn-sm btn-ghost" data-edit="${user.id}">编辑</button></td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table></div>`;
    tableEl.querySelectorAll('[data-edit]').forEach((button) => {
      button.addEventListener('click', () => {
        const user = users.find((item) => item.id === Number(button.dataset.edit));
        openUserModal(user);
      });
    });
  }

  function openUserModal(user = null) {
    const isEdit = Boolean(user);
    const { root: modal, close } = openModal({
      title: isEdit ? '编辑用户' : '新建用户',
      size: 'lg',
      body: `
        <div class="form-grid" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="field"><label class="required">用户名</label><input id="u-username" value="${esc(user?.username || '')}" ${isEdit ? 'disabled' : ''} placeholder="登录账号" /></div>
          <div class="field"><label class="required">显示名称</label><input id="u-display" value="${esc(user?.display_name || '')}" placeholder="真实姓名" /></div>
          <div class="field"><label class="${isEdit ? '' : 'required'}">密码</label><input id="u-password" type="password" placeholder="${isEdit ? '留空表示不修改' : '至少 6 位'}" /></div>
          <div class="field"><label>部门</label><input id="u-department" value="${esc(user?.department || '')}" /></div>
          <div class="field"><label>职级</label><input id="u-level" value="${esc(user?.job_level || '')}" placeholder="如：P6 / M2" /></div>
          <div class="field"><label>状态</label>
            <select id="u-status">
              <option value="active" ${user?.status !== 'inactive' ? 'selected' : ''}>正常</option>
              <option value="inactive" ${user?.status === 'inactive' ? 'selected' : ''}>停用</option>
            </select>
          </div>
          <div class="field full"><label>角色</label>
            <div class="tag-row">
              ${roleOptions
                .map(
                  (role) => `<label class="tag" style="cursor:pointer;display:inline-flex;gap:6px;align-items:center;padding:5px 10px">
                    <input type="checkbox" value="${role.role_code}" ${(user?.roles || ['applicant']).includes(role.role_code) ? 'checked' : ''} data-role-check />
                    ${esc(role.role_name)}
                  </label>`
                )
                .join('')}
            </div>
          </div>
        </div>`,
      footer: `<button class="btn btn-ghost" data-cancel>取消</button><button class="btn btn-primary" data-save>保存</button>`,
    });
    modal.querySelector('[data-cancel]').addEventListener('click', close);
    modal.querySelector('[data-save]').addEventListener('click', async () => {
      const username = modal.querySelector('#u-username').value.trim();
      const displayName = modal.querySelector('#u-display').value.trim();
      const password = modal.querySelector('#u-password').value;
      const selectedRoles = Array.from(modal.querySelectorAll('[data-role-check]:checked')).map((item) => item.value);
      if (!isEdit && (!username || !displayName || !password)) {
        toast('请填写用户名、显示名称与密码', 'warning');
        return;
      }
      if (!displayName) {
        toast('请填写显示名称', 'warning');
        return;
      }
      if (!selectedRoles.length) {
        toast('至少选择一个角色', 'warning');
        return;
      }
      const payload = {
        display_name: displayName,
        department: modal.querySelector('#u-department').value.trim() || null,
        job_level: modal.querySelector('#u-level').value.trim() || null,
        status: modal.querySelector('#u-status').value,
        roles: selectedRoles,
      };
      if (password) payload.password = password;
      try {
        if (isEdit) {
          await api(`/api/v1/users/${user.id}`, { method: 'PATCH', body: payload });
        } else {
          await api('/api/v1/users', {
            method: 'POST',
            body: { ...payload, username, password },
          });
        }
        close();
        toast('用户信息已保存', 'success');
        await load();
      } catch (error) {
        toast(error.message, 'error');
      }
    });
  }

  document.getElementById('page-actions')?.querySelector('#btn-new-user')?.addEventListener('click', () => openUserModal(null));
  await load();
}
