import { api, downloadFile } from '../api.js';
import {
  confidenceBar,
  emptyState,
  esc,
  fileSize,
  fmtDateTime,
  icon,
  loadingBlock,
  parseBadge,
  setLoading,
  toast,
} from '../ui.js';

const FIELD_LABELS = {
  invoice_code: '发票代码',
  invoice_no: '发票号码',
  invoice_date: '开票日期',
  buyer_name: '购买方名称',
  seller_name: '销售方名称',
  invoice_total: '价税合计',
  amount_excluding_tax: '不含税金额',
  tax_amount: '税额',
  amount_including_tax: '价税合计',
  contract_no: '合同编号',
  contract_amount: '合同金额',
  party_a: '甲方',
  party_b: '乙方',
  payment_ratio: '付款比例',
  payee_name: '收款单位',
  payee_account: '收款账号',
  payment_amount: '付款金额',
  payment_date: '付款日期',
  travel_location: '出差地点',
  travel_start_date: '出差开始日期',
  travel_end_date: '出差结束日期',
  transport_fee: '交通费',
  hotel_fee: '住宿费',
  meal_fee: '餐费',
  allowance: '补贴',
};

const CATEGORY_LABELS = {
  invoice: '发票',
  contract: '合同',
  itinerary: '行程单',
  payment_proof: '付款依据',
  other: '其他材料',
};

export async function render(root, ctx) {
  const docId = Number(ctx.params.docId);
  const attId = Number(ctx.params.attId);
  const historicalTask = ctx.query?.task_id;
  const suffix = historicalTask ? `?task_id=${encodeURIComponent(historicalTask)}` : '';
  root.innerHTML = loadingBlock('正在加载附件与解析结果…');

  let data;
  let siblings = [];
  try {
    const [result, list] = await Promise.all([
      api(`/api/v1/documents/${docId}/attachments/${attId}/parse-result${suffix}`),
      api(`/api/v1/documents/${docId}/parsed-attachments`),
    ]);
    data = result;
    siblings = list;
  } catch (error) {
    root.innerHTML = emptyState('附件加载失败', error.message, 'alert');
    return;
  }

  const attachment = data.attachment;
  const parse = data.parse_result;
  const docNo = attachment.file_name;
  ctx.setTitle('附件解析', `${docNo} · ${fileSize(attachment.file_size)} · ${parse ? `置信度 ${(parse.confidence * 100).toFixed(0)}%` : '尚未解析'}`);
  ctx.setActions(`
    <a class="btn btn-ghost" href="#/documents/${docId}">返回单据</a>
    <button class="btn btn-ghost" data-act="download">${icon('download', 15)} 下载附件</button>
    <button class="btn btn-primary" data-act="reparse">${icon('refresh', 15)} 重新解析</button>
  `);

  if (historicalTask) {
    ctx.setTitle('历史附件证据', `${docNo} · 第 ${data.document_version} 版分析时的识别结果`);
    document.getElementById('page-actions').querySelector('[data-act="reparse"]').hidden = true;
    siblings = [{attachment_id: attId, file_name: attachment.file_name}];
  }
  let blobUrl = null;
  ctx.onCleanup(() => {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
  });

  const evidence = parse?.evidence || [];
  const fields = parse?.fields || {};

  root.innerHTML = `
    <div class="viewer-layout">
      <div class="card viewer-pane">
        <div class="viewer-head">
          <div class="file-badge ${attachment.file_type === 'pdf' ? 'file-pdf' : 'file-img'}">${attachment.file_type === 'pdf' ? 'PDF' : 'IMG'}</div>
          <div style="flex:1;min-width:0">
            <div class="attach-name">${esc(attachment.file_name)}</div>
            <div class="attach-meta">${esc(parse?.document_category ? CATEGORY_LABELS[parse.document_category] || parse.document_category : '识别中')} · ${parseBadge(attachment.parse_status)}</div>
          </div>
          <select id="att-select" style="height:32px;border:1px solid var(--line);border-radius:7px;padding:0 8px;max-width:220px">
            ${siblings.map((item) => `<option value="${item.attachment_id}" ${item.attachment_id === attId ? 'selected' : ''}>${esc(item.file_name)}</option>`).join('')}
          </select>
        </div>
        <div class="viewer-body" id="preview-area">${loadingBlock('正在加载原文…')}</div>
      </div>
      <div class="card viewer-pane">
        <div class="viewer-head" style="padding-bottom:0">
          <div class="tabs" style="margin:0;border:none;flex:1">
            <div class="tab active" data-tab="fields">提取字段</div>
            <div class="tab" data-tab="text">识别文本</div>
            <div class="tab" data-tab="evidence">证据定位</div>
          </div>
        </div>
        <div class="viewer-body" style="background:#fff;padding:16px">
          ${
            !parse
              ? emptyState('尚未生成解析结果', '点击右上角「重新解析」创建解析任务', 'scan')
              : parse.error_message && !fields
                ? `<div class="empty">${icon('alert', 36)}<h4>解析失败</h4><p class="small">${esc(parse.error_message)}</p></div>`
                : `<div data-panel="fields">
                    <div class="grid grid-3" style="gap:10px;margin-bottom:14px">
                      <div class="amount-cell"><div class="a-label">文档分类</div><div class="a-value" style="font-size:15px">${esc(CATEGORY_LABELS[parse.document_category] || parse.document_category)}</div></div>
                      <div class="amount-cell"><div class="a-label">整体置信度</div><div class="a-value" style="font-size:15px">${(parse.confidence * 100).toFixed(0)}%</div></div>
                      <div class="amount-cell"><div class="a-label">解析方式</div><div class="a-value" style="font-size:15px">${esc(parse.parser_source)}</div></div>
                    </div>
                    <table class="field-table" style="width:100%;border-collapse:collapse">
                      <tbody>
                        ${
                          Object.keys(fields).length
                            ? Object.entries(fields)
                                .map(([key, value]) => {
                                  const ev = evidence.find((item) => item.field === key);
                                  return `<tr>
                                    <td>${esc(FIELD_LABELS[key] || key)}<div class="cell-sub mono">${esc(key)}</div></td>
                                    <td><b>${esc(typeof value === 'number' ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : value)}</b></td>
                                    <td style="text-align:right">${ev ? confidenceBar(ev.confidence) : ''}</td>
                                  </tr>`;
                                })
                                .join('')
                            : '<tr><td colspan="3" class="muted small">未识别到结构化字段，请查看识别文本或人工核对</td></tr>'
                        }
                      </tbody>
                    </table>
                    ${parse.error_message ? `<div class="finding-block" style="margin-top:14px"><div class="fb-label">解析提示</div>${esc(parse.error_message)}</div>` : ''}
                  </div>
                  <div data-panel="text" hidden>
                    ${
                      (parse.page_texts || []).length
                        ? parse.page_texts
                            .map(
                              (page) => `<div class="section-title">第 ${page.page} 页 ${page.ocr ? '<span class="badge badge-purple">OCR</span>' : '<span class="badge badge-info">文本层</span>'}</div>
                                <div class="text-scroll" style="margin-bottom:14px">${highlightText(page.text, evidence, page.page)}</div>`
                            )
                            .join('')
                        : `<div class="text-scroll">${esc(parse.full_text)}</div>`
                    }
                  </div>
                  <div data-panel="evidence" hidden>
                    ${
                      evidence.length
                        ? evidence
                            .map(
                              (item) => `<div class="evidence-row" style="cursor:default">
                                <span class="ev-source">第 ${item.page || '?'} 页</span>
                                <div style="flex:1;min-width:0">
                                  <div style="display:flex;gap:8px;align-items:center">
                                    <b>${esc(FIELD_LABELS[item.field] || item.field || '字段')}</b>
                                    ${confidenceBar(item.confidence)}
                                  </div>
                                  <div class="small muted" style="margin-top:3px">${esc(item.snippet || '')}</div>
                                  ${item.bbox ? `<div class="cell-sub mono">坐标 ${item.bbox.join(', ')}</div>` : `<div class="cell-sub mono">字符位置 ${item.char_start}-${item.char_end}</div>`}
                                </div>
                              </div>`
                            )
                            .join('')
                        : emptyState('暂无证据定位', '解析结果中未包含字段原文位置', 'scan')
                    }
                  </div>`
          }
        </div>
      </div>
    </div>`;

  function highlightText(text, evidenceList, page) {
    let html = esc(text || '');
    evidenceList
      .filter((item) => item.page === page)
      .forEach((item) => {
        const raw = item.value === null || item.value === undefined ? '' : String(item.value);
        if (!raw) return;
        const escaped = esc(raw);
        if (html.includes(escaped)) {
          html = html.replace(escaped, `<span class="highlight">${escaped}</span>`);
        }
      });
    return html;
  }

  async function loadPreview() {
    const area = root.querySelector('#preview-area');
    try {
      const response = await api(attachment.preview_url, { raw: true });
      if (!response.ok) throw new Error('原文加载失败');
      const blob = await response.blob();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      blobUrl = URL.createObjectURL(blob);
      if (attachment.file_type === 'pdf' || blob.type === 'application/pdf') {
        area.innerHTML = `<iframe class="doc-frame" src="${blobUrl}" title="PDF 预览"></iframe>`;
      } else {
        area.innerHTML = `<img class="doc-image" src="${blobUrl}" alt="附件预览" />`;
      }
    } catch (error) {
      area.innerHTML = emptyState('原文预览失败', error.message, 'alert');
    }
  }

  root.querySelectorAll('[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      root.querySelectorAll('[data-tab]').forEach((item) => item.classList.toggle('active', item === tab));
      root.querySelectorAll('[data-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.panel !== tab.dataset.tab;
      });
    });
  });

  const select = root.querySelector('#att-select');
  select.addEventListener('change', () => {
    window.location.hash = `#/attachments/${docId}/${select.value}`;
  });

  const actionBar = document.getElementById('page-actions');
  actionBar.querySelector('[data-act="download"]').addEventListener('click', async () => {
    try {
      await downloadFile(attachment.download_url, attachment.file_name);
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  actionBar.querySelector('[data-act="reparse"]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setLoading(button, true, '解析中…');
    try {
      await api(`/api/v1/documents/${docId}/attachments/${attId}/parse`, { method: 'POST' });
      toast('解析任务已启动，完成后页面将自动刷新', 'success');
      let attempts = 0;
      const timer = setInterval(async () => {
        attempts += 1;
        try {
          const latest = await api(`/api/v1/documents/${docId}/attachments/${attId}/parse-result${suffix}`);
          if (latest.attachment.parse_status !== 'parsing' && latest.attachment.parse_status !== 'pending') {
            clearInterval(timer);
            window.dispatchEvent(new HashChangeEvent('hashchange'));
          }
        } catch {
          /* ignore */
        }
        if (attempts > 25) clearInterval(timer);
      }, 1800);
      ctx.onCleanup(() => clearInterval(timer));
    } catch (error) {
      toast(error.message, 'error');
      setLoading(button, false);
    }
  });

  loadPreview();
}
