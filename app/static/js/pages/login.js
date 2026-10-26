import { api, session } from '../api.js';
import { esc, icon, setLoading, toast } from '../ui.js';

const DEMO_ACCOUNTS = [
  { username: 'zhangwei', password: 'User@123', name: '张伟', role: '单据申请人 · 市场部' },
  { username: 'lina', password: 'User@123', name: '李娜', role: '审批人员 · 财务部' },
  { username: 'wangfang', password: 'User@123', name: '王芳', role: '财务人员 · 财务部' },
  { username: 'admin', password: 'Admin@123', name: '系统管理员', role: '系统管理员' },
];

export function render(root) {
  root.innerHTML = `
    <div class="login-shell">
      <div class="login-hero">
        <div class="hero-brand">
          <div class="brand-mark">FR</div>
          <div class="brand-text">
            <strong style="color:#f5f8ff;font-size:15px">财务单据智能风险审核系统</strong>
            <span style="color:#7484a8;font-size:11px;letter-spacing:1px">INTELLIGENT RISK REVIEW</span>
          </div>
        </div>
        <h1 class="hero-title">让每一笔财务支出<br /><span>有据可查、有险可控</span></h1>
        <p class="hero-desc">
          面向对公付款、预付款、批量付款、费用报销与差旅报销五类单据，
          自动解析发票、合同与行程单，交叉核验金额、费用标准、市场价与供应商风险，
          为审批人员提供可追溯的智能审核依据。
        </p>
        <div class="hero-points">
          <div class="hero-point">
            <div class="hp-icon">${icon('scan', 17)}</div>
            <div><b>附件智能解析</b><span>PDF 文本提取与图片 OCR，定位关键字段原文位置</span></div>
          </div>
          <div class="hero-point">
            <div class="hp-icon">${icon('shield', 17)}</div>
            <div><b>十类风险规则</b><span>金额一致性、费用标准、市场价、重复票据、供应商风险</span></div>
          </div>
          <div class="hero-point">
            <div class="hp-icon">${icon('branch', 17)}</div>
            <div><b>审批全链路留痕</b><span>流程配置、多节点流转、人工复核与操作审计</span></div>
          </div>
        </div>
        <div class="hero-foot">演示环境 · 所有数据均为示例数据 · 智能分析结果仅作为审批辅助依据</div>
      </div>
      <div class="login-panel">
        <div class="login-card">
          <h2>登录审核平台</h2>
          <p class="sub">使用企业账号登录，系统将根据角色加载对应的数据权限</p>
          <div id="login-error"></div>
          <form id="login-form" autocomplete="off">
            <div class="field">
              <label class="required">用户名</label>
              <input id="username" name="username" placeholder="请输入用户名" required autocomplete="username" />
            </div>
            <div class="field">
              <label class="required">密码</label>
              <input id="password" name="password" type="password" placeholder="请输入密码" required autocomplete="current-password" />
            </div>
            <button class="btn btn-primary btn-block" type="submit" id="login-btn" style="height:44px;margin-top:8px">
              ${icon('logout', 16)} 登录系统
            </button>
          </form>
          <div class="demo-accounts">
            <div class="demo-title">演示账号（点击填充并登录）</div>
            <div class="demo-grid">
              ${DEMO_ACCOUNTS.map(
                (account) => `<button class="demo-chip" data-user="${account.username}" data-pass="${account.password}">
                  <b>${esc(account.name)}</b><span>${esc(account.role)}</span>
                </button>`
              ).join('')}
            </div>
          </div>
        </div>
      </div>
    </div>`;

  const form = root.querySelector('#login-form');
  const errorBox = root.querySelector('#login-error');

  async function login(username, password, button) {
    errorBox.innerHTML = '';
    setLoading(button, true, '登录中…');
    try {
      const data = await api('/api/v1/auth/login', { method: 'POST', body: { username, password } });
      session.set(data.access_token, data.user);
      toast(`欢迎回来，${data.user.display_name}`, 'success', '登录成功');
      if (window.location.hash === '#/login' || !window.location.hash) {
        window.location.hash = '#/dashboard';
      } else {
        window.dispatchEvent(new HashChangeEvent('hashchange'));
      }
    } catch (error) {
      errorBox.innerHTML = `<div class="login-error">${esc(error.message)}</div>`;
      setLoading(button, false);
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const username = root.querySelector('#username').value.trim();
    const password = root.querySelector('#password').value;
    if (!username || !password) {
      errorBox.innerHTML = '<div class="login-error">请输入用户名和密码</div>';
      return;
    }
    login(username, password, root.querySelector('#login-btn'));
  });

  root.querySelectorAll('.demo-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      root.querySelector('#username').value = chip.dataset.user;
      root.querySelector('#password').value = chip.dataset.pass;
      login(chip.dataset.user, chip.dataset.pass, root.querySelector('#login-btn'));
    });
  });
}
