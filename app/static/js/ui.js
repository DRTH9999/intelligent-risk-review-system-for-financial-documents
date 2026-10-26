const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  message: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>',
  checkSquare: '<rect x="3" y="3" width="18" height="18" rx="4"/><polyline points="8 12 11 15 16 9"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><line x1="8" y1="6" x2="8" y2="6.01"/><line x1="16" y1="6" x2="16" y2="6.01"/><line x1="8" y1="10" x2="8" y2="10.01"/><line x1="16" y1="10" x2="16" y2="10.01"/><line x1="8" y1="14" x2="8" y2="14.01"/><line x1="16" y1="14" x2="16" y2="14.01"/>',
  branch: '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
  sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><line x1="10" y1="12" x2="14" y2="12"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
  chevronDown: '<polyline points="6 9 12 15 18 9"/>',
  chevronRight: '<polyline points="9 18 15 12 9 6"/>',
  paperclip: '<path d="M21.4 11.6 12.3 20.7a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  xCircle: '<circle cx="12" cy="12" r="9"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
  printer: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  sparkles: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  arrowRight: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  wallet: '<path d="M20 7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h15V7H5"/><path d="M16 13h2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><line x1="3" y1="11" x2="21" y2="11"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 22a8 8 0 0 1 16 0"/>',
  filter: '<polygon points="22 3 2 3 10 12.5 10 19 14 21 14 12.5 22 3"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.5 5.5 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.5A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.5z"/>',
  info: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  fileText: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
  cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 10h.01M18 14h.01"/>',
};

export function icon(name, size = 18, extra = '') {
  const path = ICONS[name] || ICONS.info;
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${path}</svg>`;
}

export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function money(value) {
  const n = Number(value || 0);
  const sign = n < 0 ? '-' : '';
  return `${sign}¥${Math.abs(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function compactMoney(value) {
  const n = Number(value || 0);
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs >= 100000000) return `${sign}¥${(abs / 100000000).toFixed(2)} 亿`;
  if (abs >= 10000) return `${sign}¥${(abs / 10000).toFixed(1)} 万`;
  return money(n);
}

export function fmtDate(value) {
  return value ? String(value).slice(0, 10) : '-';
}

export function fmtDateTime(value) {
  if (!value) return '-';
  const text = String(value).replace('T', ' ');
  return text.slice(0, 16);
}

export function fileSize(bytes) {
  const n = Number(bytes || 0);
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n > 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

export const STATUS = {
  draft: { label: '草稿', cls: 'neutral' },
  pending_review: { label: '待审批', cls: 'warning' },
  reviewing: { label: '审批中', cls: 'info' },
  returned: { label: '已退回', cls: 'medium' },
  approved: { label: '已通过', cls: 'low' },
  rejected: { label: '已驳回', cls: 'high' },
  withdrawn: { label: '已撤回', cls: 'neutral' },
  voided: { label: '已作废', cls: 'neutral' },
};

export function statusBadge(status) {
  const meta = STATUS[status] || { label: status || '-', cls: 'neutral' };
  return `<span class="badge badge-${meta.cls} badge-dot">${esc(meta.label)}</span>`;
}

export const RISK = {
  high: { label: '高风险', short: '高', cls: 'high' },
  medium: { label: '中风险', short: '中', cls: 'medium' },
  low: { label: '低风险', short: '低', cls: 'low' },
};

export function riskBadge(level) {
  if (!level) return '<span class="badge badge-neutral">未分析</span>';
  const meta = RISK[level] || { label: level, cls: 'neutral' };
  return `<span class="badge badge-${meta.cls} badge-dot">${meta.label}</span>`;
}

export const TASK_STATUS = {
  queued: '等待分析',
  querying_document: '查询单据',
  loading_attachments: '加载附件',
  parsing_attachments: '解析附件',
  analyzing: '规则分析',
  generating_report: '生成报告',
  succeeded: '已完成',
  failed: '分析失败',
  cancelled: '已取消',
};

export function parseBadge(status) {
  const map = {
    pending: ['待解析', 'neutral'],
    parsing: ['解析中', 'info'],
    succeeded: ['解析成功', 'low'],
    failed: ['解析失败', 'high'],
    manual_review: ['需人工核对', 'medium'],
  };
  const [label, cls] = map[status] || [status || '-', 'neutral'];
  return `<span class="badge badge-${cls}">${label}</span>`;
}

export function recommendationBadge(text) {
  const map = {
    建议通过: 'low',
    补充材料: 'medium',
    人工复核: 'medium',
    建议驳回: 'high',
    通过: 'low',
    退回: 'medium',
    驳回: 'high',
  };
  return `<span class="badge badge-${map[text] || 'neutral'}">${esc(text || '-')}</span>`;
}

export function taskStatusBadge(status) {
  const map = {
    pending: ['待处理', 'warning'],
    approved: ['已通过', 'low'],
    returned: ['已退回', 'medium'],
    rejected: ['已驳回', 'high'],
    cancelled: ['已取消', 'neutral'],
    running: ['审批中', 'info'],
  };
  const [label, cls] = map[status] || [status || '-', 'neutral'];
  return `<span class="badge badge-${cls}">${label}</span>`;
}

export const ROLE_LABELS = {
  applicant: '单据申请人',
  approver: '审批人员',
  finance: '财务人员',
  admin: '系统管理员',
};

export function roleLabel(roles) {
  const list = Array.isArray(roles) ? roles : [];
  return list.map((role) => ROLE_LABELS[role] || role).join(' / ') || '未分配角色';
}

export function docTypeClass(type) {
  return {
    对公付款单: 'primary',
    预付款单: 'purple',
    批量付款单: 'info',
    费用报销单: 'low',
    差旅报销单: 'medium',
  }[type] || 'neutral';
}

export function docTypeBadge(type) {
  return `<span class="badge badge-${docTypeClass(type)}">${esc(type || '-')}</span>`;
}

export function emptyState(title = '暂无数据', desc = '', iconName = 'inbox') {
  return `<div class="empty">${icon(iconName, 38)}<h4>${esc(title)}</h4>${desc ? `<p class="small">${esc(desc)}</p>` : ''}</div>`;
}

export function loadingBlock(text = '正在加载…') {
  return `<div class="loading-block"><span class="spinner"></span><span>${esc(text)}</span></div>`;
}

export function toast(message, type = 'info', title = '') {
  const root = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<div class="t-title">${esc(title || (type === 'error' ? '操作失败' : type === 'success' ? '操作成功' : '提示'))}</div><div class="t-desc">${esc(message)}</div>`;
  root.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(18px)';
    el.style.transition = 'all .22s';
    setTimeout(() => el.remove(), 240);
  }, 3200);
}

let modalCloser = null;

export function openModal({ title, body, footer = '', size = '', onMount }) {
  const root = document.getElementById('modal-root');
  root.innerHTML = `
    <div class="modal-backdrop">
      <div class="modal ${size}" role="dialog" aria-modal="true">
        <div class="modal-head">
          <div class="modal-title">${esc(title)}</div>
          <button class="icon-btn modal-close" data-modal-close>${icon('x', 16)}</button>
        </div>
        <div class="modal-body">${body}</div>
        ${footer ? `<div class="modal-foot">${footer}</div>` : ''}
      </div>
    </div>`;
  const backdrop = root.querySelector('.modal-backdrop');
  const close = () => {
    if (modalCloser === close) modalCloser = null;
    root.innerHTML = '';
  };
  modalCloser = close;
  backdrop.addEventListener('mousedown', (event) => {
    if (event.target === backdrop) close();
  });
  root.querySelectorAll('[data-modal-close]').forEach((btn) => btn.addEventListener('click', close));
  const onKey = (event) => {
    if (event.key === 'Escape') {
      close();
      document.removeEventListener('keydown', onKey);
    }
  };
  document.addEventListener('keydown', onKey);
  if (onMount) onMount(root, close);
  return { root, close };
}

export function closeModal() {
  if (modalCloser) modalCloser();
}

export function confirmDialog({ title = '确认操作', message = '', confirmText = '确认', danger = false }) {
  return new Promise((resolve) => {
    const { root, close } = openModal({
      title,
      size: '',
      body: `<p style="font-size:13px;color:var(--text-2);line-height:1.9">${esc(message)}</p>`,
      footer: `<button class="btn btn-ghost" data-cancel>取消</button><button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-ok>${esc(confirmText)}</button>`,
    });
    root.querySelector('[data-cancel]').addEventListener('click', () => {
      close();
      resolve(false);
    });
    root.querySelector('[data-ok]').addEventListener('click', () => {
      close();
      resolve(true);
    });
  });
}

export function donutChart(data, { size = 156, thickness = 18, centerValue = '', centerLabel = '' } = {}) {
  const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const rings = data
    .filter((item) => Number(item.value || 0) > 0)
    .map((item) => {
      const length = (Number(item.value) / total) * circumference;
      const circle = `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${item.color}" stroke-width="${thickness}" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" stroke-linecap="butt" transform="rotate(-90 ${size / 2} ${size / 2})"></circle>`;
      offset += length;
      return circle;
    })
    .join('');
  return `<div style="position:relative;width:${size}px;height:${size}px;flex:none">
      <svg width="${size}" height="${size}">
        <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="#eef2f9" stroke-width="${thickness}"></circle>
        ${rings}
      </svg>
      <div style="position:absolute;inset:0;display:grid;place-content:center;text-align:center">
        <b style="font-size:22px;line-height:1.2">${esc(centerValue)}</b>
        <span style="font-size:11px;color:var(--text-3)">${esc(centerLabel)}</span>
      </div>
    </div>`;
}

export function lineChart(points, { width = 660, height = 190, color = '#2f6fed' } = {}) {
  if (!points.length) return '<div class="empty">暂无趋势数据</div>';
  const padding = { left: 34, right: 14, top: 16, bottom: 30 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const max = Math.max(4, ...points.map((p) => Number(p.value || 0)));
  const stepX = points.length > 1 ? innerW / (points.length - 1) : 0;
  const coords = points.map((point, index) => {
    const x = padding.left + stepX * index;
    const y = padding.top + innerH - (Number(point.value || 0) / max) * innerH;
    return { x, y, ...point };
  });
  const line = coords.map((p) => `${p.x},${p.y}`).join(' ');
  const area = `${padding.left},${padding.top + innerH} ${line} ${coords[coords.length - 1].x},${padding.top + innerH}`;
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const y = padding.top + innerH * ratio;
      const label = Math.round(max * (1 - ratio));
      return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#eef2f9"/>
        <text x="${padding.left - 8}" y="${y + 4}" text-anchor="end" font-size="9" fill="#9aa6bd">${label}</text>`;
    })
    .join('');
  const labels = coords
    .map(
      (p, index) =>
        `<text x="${p.x}" y="${height - 8}" text-anchor="middle" font-size="9" fill="#9aa6bd">${esc(
          index % 2 === 0 ? p.label.slice(5) : ''
        )}</text>`
    )
    .join('');
  const dots = coords
    .map((p) =>
      Number(p.value) > 0
        ? `<circle cx="${p.x}" cy="${p.y}" r="3.2" fill="#fff" stroke="${color}" stroke-width="2"><title>${esc(p.label)}：${p.value}</title></circle>`
        : ''
    )
    .join('');
  return `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity=".22"/><stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      ${grid}
      <polygon points="${area}" fill="url(#areaGrad)"></polygon>
      <polyline points="${line}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"></polyline>
      ${dots}
      ${labels}
    </svg>`;
}

export function setLoading(button, loading, text = '处理中…') {
  if (!button) return;
  if (loading) {
    button.dataset.original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner" style="border-top-color:#fff"></span>${esc(text)}`;
  } else {
    button.disabled = false;
    if (button.dataset.original) button.innerHTML = button.dataset.original;
  }
}

export function debounce(fn, wait = 320) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function parseHashQuery() {
  const hash = window.location.hash.replace(/^#/, '') || '/dashboard';
  const [path, queryString] = hash.split('?');
  const query = {};
  new URLSearchParams(queryString || '').forEach((value, key) => {
    query[key] = value;
  });
  return { path, query };
}

export function pretty(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function percent(value, digits = 1) {
  return `${Number(value || 0).toFixed(digits)}%`;
}

export function confidenceBar(value) {
  const pct = Math.max(0, Math.min(1, Number(value || 0))) * 100;
  return `<span class="confidence"><span class="conf-bar"><span style="width:${pct}%;background:${pct >= 80 ? '#16a34a' : pct >= 55 ? '#e08a00' : '#e5484d'}"></span></span>${pct.toFixed(0)}%</span>`;
}
