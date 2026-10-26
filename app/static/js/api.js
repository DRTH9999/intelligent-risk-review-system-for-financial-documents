const TOKEN_KEY = 'risk_review_token';
const USER_KEY = 'risk_review_user';

export const session = {
  get token() {
    return localStorage.getItem(TOKEN_KEY) || '';
  },
  get user() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch {
      return null;
    }
  },
  set(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  updateUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function extractMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === 'string') return payload;
  if (payload.detail) {
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg || JSON.stringify(item)).join('；');
    }
    if (payload.detail.message) {
      const issues = payload.detail.issues || [];
      return issues.length ? `${payload.detail.message}：${issues.join('；')}` : payload.detail.message;
    }
  }
  if (payload.message) return payload.message;
  return fallback;
}

export async function api(path, options = {}) {
  const { method = 'GET', body, headers = {}, raw = false } = options;
  const init = { method, headers: { ...headers } };
  if (session.token) init.headers.Authorization = `Bearer ${session.token}`;
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new ApiError('网络请求失败，请确认服务已启动', 0, null);
  }
  if (response.status === 401) {
    session.clear();
    window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new ApiError('登录已失效，请重新登录', 401, null);
  }
  if (raw) return response;
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    throw new ApiError(extractMessage(payload, `请求失败（${response.status}）`), response.status, payload?.detail ?? payload);
  }
  return payload;
}

export async function downloadFile(path, fallbackName = 'download') {
  const response = await api(path, { raw: true });
  if (!response.ok) {
    throw new ApiError('文件导出失败', response.status, null);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') || '';
  let filename = fallbackName;
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  if (utf8) filename = decodeURIComponent(utf8[1]);
  else if (plain) filename = plain[1];
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
