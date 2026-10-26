import { api, session } from './api.js';
import { ROLE_LABELS, esc, icon, parseHashQuery, roleLabel, toast } from './ui.js';
import * as LoginPage from './pages/login.js';
import * as DashboardPage from './pages/dashboard.js';
import * as DocumentsPage from './pages/documents.js';
import * as DocumentEditPage from './pages/document-edit.js';
import * as DocumentDetailPage from './pages/document-detail.js';
import * as ChatPage from './pages/chat.js';
import * as AnalysisPage from './pages/analysis.js';
import * as AttachmentPage from './pages/attachment.js';
import * as ApprovalsPage from './pages/approvals.js';
import * as ApprovalDetailPage from './pages/approval-detail.js';
import * as SuppliersPage from './pages/suppliers.js';
import * as WorkflowsPage from './pages/workflows.js';
import * as RulesPage from './pages/rules.js';
import * as RecordsPage from './pages/records.js';
import * as UsersPage from './pages/users.js';

const ROUTES = [
  { path: '/login', page: LoginPage, title: '登录', public: true },
  { path: '/dashboard', page: DashboardPage, title: '审核工作台', sub: '风险全景、待办与最近分析任务' },
  { path: '/documents', page: DocumentsPage, title: '单据管理', sub: '查询、维护与流转全部业务单据' },
  { path: '/documents/new', page: DocumentEditPage, title: '新建单据', sub: '填写单据信息、费用明细并上传附件', active: '/documents' },
  { path: '/documents/:id/edit', page: DocumentEditPage, title: '编辑单据', sub: '维护草稿或退回单据', active: '/documents' },
  { path: '/documents/:id', page: DocumentDetailPage, title: '单据详情', sub: '基本信息、明细、附件与审批进度', active: '/documents' },
  { path: '/chat', page: ChatPage, title: '智能审核对话', sub: '通过多轮对话定位单据并发起风险分析' },
  { path: '/analysis/:taskId', page: AnalysisPage, title: '风险分析', sub: '风险项、金额核对、证据与处理建议', active: '/records' },
  { path: '/attachments/:docId/:attId', page: AttachmentPage, title: '附件解析', sub: '原文、识别文本、提取字段与证据定位', active: '/documents' },
  { path: '/approvals', page: ApprovalsPage, title: '我的审批', sub: '待处理与已处理审批任务' },
  { path: '/approvals/:taskId', page: ApprovalDetailPage, title: '审批处理', sub: '审阅风险分析并提交审批结果', active: '/approvals' },
  { path: '/suppliers', page: SuppliersPage, title: '供应商风险', sub: '供应商档案、风险标签与历史付款' },
  { path: '/workflows', page: WorkflowsPage, title: '审批流程配置', sub: '按单据类型与金额区间配置审批节点' },
  { path: '/rules', page: RulesPage, title: '规则配置', sub: '金额容差、费用标准、市场价与风险阈值' },
  { path: '/records', page: RecordsPage, title: '审核记录', sub: '风险报告、人工复核与操作审计' },
  { path: '/users', page: UsersPage, title: '用户与角色', sub: '系统用户、角色与访问状态管理' },
];

let cleanupFns = [];
let currentRoute = null;

function canSeeRoles(roles, needed) {
  return needed.some((role) => roles.includes(role));
}

function navItem(href, iconName, label, active, badge = '') {
  return `<a class="nav-item ${active ? 'active' : ''}" href="#${href}">
    ${icon(iconName, 18)}<span>${esc(label)}</span>${badge ? `<span class="nav-badge" id="${badge}">0</span>` : ''}
  </a>`;
}

function shellHTML(route, path) {
  const user = session.user || {};
  const roles = user.roles || [];
  const activeBase = route.active || route.path;
  const isActive = (href) => path === href || path.startsWith(`${href}/`) || activeBase === href;
  const canApprove = canSeeRoles(roles, ['approver', 'finance', 'admin']);
  const canFinance = canSeeRoles(roles, ['finance', 'admin']);
  const isAdmin = roles.includes('admin');
  const nav = `
    ${navItem('/dashboard', 'dashboard', '审核工作台', isActive('/dashboard'))}
    <div class="nav-group-label">单据中心</div>
    ${navItem('/documents', 'file', '单据管理', isActive('/documents'))}
    ${navItem('/documents/new', 'plus', '新建单据', isActive('/documents/new'))}
    <div class="nav-group-label">智能审核</div>
    ${navItem('/chat', 'message', '智能审核对话', isActive('/chat'))}
    ${canApprove ? navItem('/approvals', 'checkSquare', '我的审批', isActive('/approvals'), 'nav-approval-badge') : ''}
    ${navItem('/records', 'archive', '风险报告与记录', isActive('/records'))}
    <div class="nav-group-label">风险数据</div>
    ${navItem('/suppliers', 'building', '供应商风险', isActive('/suppliers'))}
    ${canFinance || isAdmin ? `<div class="nav-group-label">系统配置</div>` : ''}
    ${isAdmin ? navItem('/workflows', 'branch', '审批流程', isActive('/workflows')) : ''}
    ${canFinance ? navItem('/rules', 'sliders', '审核规则', isActive('/rules')) : ''}
    ${isAdmin ? navItem('/users', 'shield', '用户与角色', isActive('/users')) : ''}
  `;
  return `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark">FR</div>
          <div class="brand-text"><strong>财务风险审核</strong><span>RISK REVIEW PLATFORM</span></div>
        </div>
        <div class="nav-scroll">${nav}</div>
        <div class="sidebar-footer">
          <div class="user-mini">
            <div class="avatar">${esc((user.display_name || 'U').slice(-2))}</div>
            <div>
              <div class="u-name">${esc(user.display_name || '未登录')}</div>
              <div class="u-role">${esc(roleLabel(roles))}</div>
            </div>
            <span class="logout-icon" id="sidebar-logout" title="退出登录">${icon('logout', 17)}</span>
          </div>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <div class="breadcrumb">财务风险审核 <span>/</span> <b>${esc(route.title)}</b></div>
          <div class="topbar-actions">
            <div class="search-box">
              ${icon('search', 15)}
              <input id="global-search" placeholder="搜索单据编号 / 收款单位" />
            </div>
            <span class="role-chip">${esc((roles[0] && ROLE_LABELS[roles[0]]) || '访客')}</span>
            <div class="avatar" title="${esc(user.display_name || '')}">${esc((user.display_name || 'U').slice(-2))}</div>
          </div>
        </header>
        <div class="content">
          <div class="page-head">
            <div>
              <h1 class="page-title" id="page-title">${esc(route.title)}</h1>
              <p class="page-sub" id="page-sub">${esc(route.sub || '')}</p>
            </div>
            <div class="page-actions" id="page-actions"></div>
          </div>
          <div id="page-content">${loadingPage()}</div>
        </div>
      </div>
    </div>`;
}

function loadingPage() {
  return `<div class="loading-block"><span class="spinner"></span><span>正在加载页面…</span></div>`;
}

function errorPage(message) {
  return `<div class="card"><div class="empty">${icon('alert', 40)}<h4>页面加载失败</h4><p class="small">${esc(message)}</p>
    <div style="margin-top:16px"><button class="btn btn-primary" onclick="location.reload()">重新加载</button></div></div></div>`;
}

function matchRoute(path) {
  const segments = path.split('/').filter(Boolean);
  for (const route of ROUTES) {
    const routeSegments = route.path.split('/').filter(Boolean);
    if (routeSegments.length !== segments.length) continue;
    const params = {};
    let ok = true;
    for (let index = 0; index < routeSegments.length; index += 1) {
      const part = routeSegments[index];
      if (part.startsWith(':')) params[part.slice(1)] = decodeURIComponent(segments[index]);
      else if (part !== segments[index]) {
        ok = false;
        break;
      }
    }
    if (ok) return { route, params };
  }
  return null;
}

function runCleanup() {
  cleanupFns.forEach((fn) => {
    try {
      fn();
    } catch {
      /* ignore */
    }
  });
  cleanupFns = [];
}

async function refreshPendingBadge() {
  const badge = document.getElementById('nav-approval-badge');
  if (!badge) return;
  try {
    const data = await api('/api/v1/approval-tasks?status=pending');
    const count = (data.items || []).length;
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.style.display = count ? 'inline-block' : 'none';
  } catch {
    /* ignore */
  }
}

function renderLogin() {
  runCleanup();
  document.getElementById('app').innerHTML = `<div id="login-root"></div>`;
  LoginPage.render(document.getElementById('login-root'));
}

async function renderRoute() {
  const { path, query } = parseHashQuery();

  if (!session.token) {
    if (path !== '/login') {
      history.replaceState(null, '', '#/login');
    }
    renderLogin();
    return;
  }
  if (path === '/login') {
    window.location.hash = '#/dashboard';
    return;
  }

  const matched = matchRoute(path);
  if (!matched) {
    document.getElementById('app').innerHTML = shellHTML({ title: '页面不存在', path }, path);
    document.getElementById('page-content').innerHTML = errorPage('未找到对应页面');
    attachShellEvents();
    return;
  }

  runCleanup();
  currentRoute = matched;
  const { route, params } = matched;
  document.getElementById('app').innerHTML = shellHTML(route, path);
  attachShellEvents();
  document.title = `${route.title} · 财务单据智能风险审核系统`;

  const content = document.getElementById('page-content');
  const ctx = {
    params,
    query,
    path,
    setTitle(title, sub) {
      document.getElementById('page-title').textContent = title;
      if (sub !== undefined) document.getElementById('page-sub').textContent = sub;
      document.title = `${title} · 财务单据智能风险审核系统`;
    },
    setActions(html) {
      document.getElementById('page-actions').innerHTML = html;
    },
    onCleanup(fn) {
      cleanupFns.push(fn);
    },
    navigate(hash) {
      window.location.hash = hash;
    },
  };

  try {
    await route.page.render(content, ctx);
  } catch (error) {
    console.error(error);
    content.innerHTML = errorPage(error.message || '未知错误');
  }
  refreshPendingBadge();
}

function attachShellEvents() {
  const logout = document.getElementById('sidebar-logout');
  if (logout) {
    logout.addEventListener('click', async () => {
      try {
        await api('/api/v1/auth/logout', { method: 'POST' });
      } catch {
        /* ignore */
      }
      session.clear();
      toast('已安全退出登录', 'success');
      window.location.hash = '#/login';
      renderLogin();
    });
  }
  const search = document.getElementById('global-search');
  if (search) {
    search.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && search.value.trim()) {
        window.location.hash = `#/documents?keyword=${encodeURIComponent(search.value.trim())}`;
      }
    });
  }
}

async function boot() {
  if (session.token) {
    try {
      const user = await api('/api/v1/auth/me');
      session.updateUser(user);
    } catch {
      session.clear();
    }
  }
  window.addEventListener('hashchange', renderRoute);
  window.addEventListener('auth:expired', () => {
    session.clear();
    toast('登录已失效，请重新登录', 'warning');
    history.replaceState(null, '', '#/login');
    renderLogin();
  });
  await renderRoute();
}

boot();
