import { api } from '../api.js';
import {
  TASK_STATUS,
  emptyState,
  esc,
  icon,
  loadingBlock,
  riskBadge,
  taskStatusBadge,
  toast,
} from '../ui.js';

const STEPS = ['querying_document', 'loading_attachments', 'parsing_attachments', 'analyzing', 'generating_report', 'succeeded'];

export async function render(root, ctx) {
  let sessions = [];
  let session = null;
  let messages = [];
  let task = null;
  let pollTimer = null;
  let suggestions = [];

  root.innerHTML = `<div class="chat-layout">
    <div class="card chat-aside">
      <div class="card-head">
        <div class="card-title">审核会话</div>
        <div class="card-actions"><button class="icon-btn" id="btn-new-session" title="新建会话">${icon('plus', 15)}</button></div>
      </div>
      <div class="session-list" id="session-list">${loadingBlock()}</div>
    </div>
    <div class="card chat-main">
      <div class="chat-head">
        <span class="chat-status"></span>
        <div>
          <div class="card-title" id="chat-title">智能审核助手</div>
          <div class="card-sub" id="chat-sub">支持单据类型 + 单据编号的多轮澄清</div>
        </div>
        <div class="card-actions"><span class="badge badge-primary" id="slot-badge">等待输入</span></div>
      </div>
      <div class="messages" id="messages">${loadingBlock('正在建立审核会话…')}</div>
      <div class="chat-input">
        <div class="suggestions" id="suggestions"></div>
        <div class="composer">
          <textarea id="chat-text" rows="1" placeholder="输入「审核对公付款单 GF-202610-0001」，或先告诉我单据类型…"></textarea>
          <button class="btn btn-primary" id="btn-send" style="height:44px">${icon('send', 16)} 发送</button>
        </div>
      </div>
    </div>
  </div>`;

  const listEl = root.querySelector('#session-list');
  const messagesEl = root.querySelector('#messages');
  const textEl = root.querySelector('#chat-text');
  const sendBtn = root.querySelector('#btn-send');
  const suggestionsEl = root.querySelector('#suggestions');

  ctx.setActions(`<a class="btn btn-ghost" href="#/records">${icon('archive', 15)} 风险报告</a>`);

  ctx.onCleanup(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  async function loadSessions() {
    try {
      sessions = await api('/api/v1/review-sessions');
    } catch (error) {
      listEl.innerHTML = emptyState('会话加载失败', error.message, 'alert');
      return;
    }
    renderSessionList();
    if (!session) {
      if (sessions.length) await openSession(sessions[0].id);
      else await newSession();
    }
  }

  function renderSessionList() {
    if (!sessions.length) {
      listEl.innerHTML = `<div class="muted small" style="padding:14px 10px">暂无会话</div>`;
      return;
    }
    listEl.innerHTML = sessions
      .map(
        (item) => `<div class="session-item ${session?.id === item.id ? 'active' : ''}" data-session="${item.id}">
          <div class="s-title">${esc(item.document_no || item.document_type || `会话 #${item.id}`)}</div>
          <div class="s-sub">${esc(item.last_message || '暂无消息')}</div>
        </div>`
      )
      .join('');
    listEl.querySelectorAll('[data-session]').forEach((el) => {
      el.addEventListener('click', () => openSession(Number(el.dataset.session)));
    });
  }

  async function newSession() {
    try {
      if (pollTimer) clearInterval(pollTimer);
      const created = await api('/api/v1/review-sessions', { method: 'POST', body: {} });
      session = created;
      messages = created.messages || [];
      task = null;
      await loadSessionsData();
      renderSessionList();
      renderMessages();
      updateHeader();
      await loadSuggestions();
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function loadSessionsData() {
    sessions = await api('/api/v1/review-sessions');
  }

  async function openSession(id) {
    try {
      if (pollTimer) clearInterval(pollTimer);
      session = await api(`/api/v1/review-sessions/${id}`);
      messages = session.messages || [];
      task = null;
      renderSessionList();
      renderMessages();
      updateHeader();
      await loadSuggestions();
      const lastAnalysis = [...messages].reverse().find((item) => item.payload?.analysis_task_id);
      if (lastAnalysis) {
        await pollTask(lastAnalysis.payload.analysis_task_id);
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function updateHeader() {
    root.querySelector('#chat-title').textContent = '智能审核助手';
    const parts = [];
    if (session?.document_type) parts.push(session.document_type);
    if (session?.document_no) parts.push(session.document_no);
    root.querySelector('#chat-sub').textContent = parts.length ? `已确认：${parts.join(' · ')}` : '支持单据类型 + 单据编号的多轮澄清';
    const badge = root.querySelector('#slot-badge');
    if (session?.document_no) {
      badge.textContent = '信息完整';
      badge.className = 'badge badge-low';
    } else if (session?.document_type) {
      badge.textContent = '待补充单据编号';
      badge.className = 'badge badge-medium';
    } else {
      badge.textContent = '等待输入';
      badge.className = 'badge badge-primary';
    }
  }

  async function loadSuggestions() {
    const parts = ['对公付款单', '费用报销单', '差旅报销单', '批量付款单', '预付款单'];
    let docs = [];
    try {
      const params = new URLSearchParams({ page_size: '6' });
      if (session?.document_type) params.set('document_type', session.document_type);
      const data = await api(`/api/v1/documents?${params.toString()}`);
      docs = (data.items || []).slice(0, 4);
    } catch {
      docs = [];
    }
    suggestions = [
      ...docs.map((doc) => ({ label: doc.document_no, text: `${doc.document_type} ${doc.document_no}` })),
      ...parts.filter((part) => part !== session?.document_type).map((part) => ({ label: `审核${part}`, text: `审核${part}` })),
    ];
    suggestionsEl.innerHTML = suggestions
      .map((item) => `<button class="slot-chip" data-suggest="${esc(item.text)}">${esc(item.label)}</button>`)
      .join('');
    suggestionsEl.querySelectorAll('[data-suggest]').forEach((button) => {
      button.addEventListener('click', () => {
        textEl.value = button.dataset.suggest;
        send();
      });
    });
  }

  function messageHTML(message) {
    const isUser = message.role === 'user';
    const payload = message.payload || {};
    let extra = '';
    if (message.message_type === 'analysis_started' && payload.analysis_task_id) {
      extra = `<div class="chat-task" data-inline-task="${payload.analysis_task_id}">
        <div class="ct-head">${icon('sparkles', 15)} 分析任务 #${payload.analysis_task_id} <span class="badge badge-info">进行中</span></div>
        <div class="small muted">单据 ${esc(payload.document_no || '')} · 正在执行附件解析与风险分析</div>
        <div class="progress" style="margin-top:8px"><div class="progress-bar" style="width:5%"></div></div>
      </div>`;
    }
    if (message.message_type === 'report' && payload.report_id) {
      extra = `<div class="chat-task">
        <div class="ct-head">${icon('fileText', 15)} 风险报告已生成 ${riskBadge(payload.overall_risk_level)}</div>
        <a class="btn btn-sm btn-primary" style="margin-top:8px" href="#/analysis/${payload.analysis_task_id}">查看风险分析</a>
      </div>`;
    }
    return `<div class="msg ${isUser ? 'user' : 'assistant'}">
      <div class="msg-avatar">${isUser ? '我' : 'AI'}</div>
      <div>
        <div class="bubble">${esc(message.content)}${extra}</div>
        <div class="b-meta" style="text-align:${isUser ? 'right' : 'left'}">${esc((message.created_at || '').slice(11, 16))}</div>
      </div>
    </div>`;
  }

  function renderMessages() {
    if (!messages.length) {
      messagesEl.innerHTML = emptyState('暂无消息', '输入单据类型和编号开始审核', 'message');
      return;
    }
    messagesEl.innerHTML = messages.map(messageHTML).join('');
    scrollBottom();
  }

  function scrollBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  async function pollTask(taskId) {
    if (!taskId) return;
    if (pollTimer) clearInterval(pollTimer);
    const taskCard = root.querySelector(`[data-inline-task="${taskId}"]`);
    const tick = async () => {
      try {
        task = await api(`/api/v1/analysis-tasks/${taskId}`);
      } catch {
        return;
      }
      const card = root.querySelector(`[data-inline-task="${taskId}"]`) || taskCard;
      if (card) {
        const steps = STEPS.map((step) => {
          const index = STEPS.indexOf(step);
          const currentIndex = STEPS.indexOf(task.current_step);
          const cls = task.task_status === 'succeeded' ? 'done' : index < currentIndex ? 'done' : step === task.current_step ? 'active' : '';
          return `<span class="step-chip ${cls}">${esc(TASK_STATUS[step] || step)}</span>`;
        }).join('');
        card.innerHTML = `<div class="ct-head">${icon('sparkles', 15)} 分析任务 #${taskId}
          ${task.task_status === 'succeeded' ? '<span class="badge badge-low">已完成</span>' : task.task_status === 'failed' ? '<span class="badge badge-high">失败</span>' : '<span class="badge badge-info">进行中</span>'}
          ${task.overall_risk_level ? riskBadge(task.overall_risk_level) : ''}</div>
          <div class="small muted">当前：${esc(TASK_STATUS[task.current_step] || task.current_step)}（${task.progress}%）${task.error_message ? ` · ${esc(task.error_message)}` : ''}</div>
          <div class="progress" style="margin:8px 0"><div class="progress-bar" style="width:${task.progress}%"></div></div>
          <div class="steps">${steps}</div>
          ${task.task_status === 'succeeded' ? `<a class="btn btn-sm btn-primary" style="margin-top:10px" href="#/analysis/${taskId}">查看风险分析</a>` : ''}`;
      }
      if (['succeeded', 'failed', 'cancelled'].includes(task.task_status)) {
        clearInterval(pollTimer);
        pollTimer = null;
        if (task.task_status === 'succeeded') {
          toast('风险分析已完成，点击「查看风险分析」查看报告', 'success');
        }
      }
    };
    await tick();
    pollTimer = setInterval(tick, 1500);
  }

  async function send() {
    const content = textEl.value.trim();
    if (!content || !session) return;
    if (sendBtn.disabled) return;
    textEl.value = '';
    autoGrow();
    sendBtn.disabled = true;
    messages.push({ role: 'user', content, message_type: 'text', created_at: new Date().toISOString(), payload: {} });
    renderMessages();

    const typing = document.createElement('div');
    typing.className = 'msg assistant';
    typing.innerHTML = `<div class="msg-avatar">AI</div><div class="bubble"><span class="spinner"></span> 正在理解您的需求…</div>`;
    messagesEl.appendChild(typing);
    scrollBottom();

    try {
      const result = await api(`/api/v1/review-sessions/${session.id}/messages`, { method: 'POST', body: { content } });
      typing.remove();
      (result.messages || []).forEach((message) => messages.push(message));
      session.document_type = result.slots?.document_type;
      session.document_no = result.slots?.document_no;
      renderMessages();
      updateHeader();
      await loadSessionsData();
      renderSessionList();
      await loadSuggestions();
      if (result.analysis_task?.id) {
        await pollTask(result.analysis_task.id);
      }
    } catch (error) {
      typing.remove();
      toast(error.message, 'error');
    } finally {
      sendBtn.disabled = false;
      textEl.focus();
    }
  }

  function autoGrow() {
    textEl.style.height = 'auto';
    textEl.style.height = `${Math.min(120, textEl.scrollHeight)}px`;
  }

  sendBtn.addEventListener('click', send);
  textEl.addEventListener('input', autoGrow);
  textEl.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send();
    }
  });
  root.querySelector('#btn-new-session').addEventListener('click', newSession);

  await loadSessions();
}
