'use strict';

// ── State ────────────────────────────────────────────────────────
const S = {
  tab:            'reports',
  reports:        {},          // { ticker: [{date, signal, file_count}] }
  events:         [],          // [{name, size, mtime}]
  expanded:       new Set(),   // "ticker" or "ticker/date" keys
  currentTicker:  null,
  currentDate:    null,
  currentFile:    null,        // relative path within the run
  currentEvtFile: null,
  filter:         '',
  runFiles:       {},          // cache: "ticker/date" -> [{path, ...}]
  isinNames:      {},          // { ISIN: "Fund Name" }
  baseDir:        '',          // resolved ~/.tradingagents path from server
  selected:       new Set(),   // "ticker/date" keys of selected runs
  selectedEvts:   new Set(),   // event log filenames selected for bulk delete
  pendingOk:      null,        // function to call on modal confirm
};

// ── Clock ────────────────────────────────────────────────────────
(function clock() {
  const el = document.getElementById('clock');
  const tick = () => {
    const n = new Date();
    const pad = v => String(v).padStart(2, '0');
    el.textContent = `${n.getFullYear()}-${pad(n.getMonth()+1)}-${pad(n.getDate())}  ${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
  };
  tick();
  setInterval(tick, 1000);
})();

// ── Keyboard shortcuts ────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeModal(); return; }
  if (e.key === 'F1') { e.preventDefault(); switchTab('reports'); }
  if (e.key === 'F2') { e.preventDefault(); switchTab('events'); }
});

// ── Fetch helpers ─────────────────────────────────────────────────
async function apiFetch(method, path, params) {
  const url = new URL(path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const r = await fetch(url.toString(), { method });
  if (!r.ok) {
    let msg;
    try { msg = (await r.json()).detail; } catch { msg = r.statusText; }
    throw new Error(msg || r.statusText);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('application/json') ? r.json() : r.text();
}

// ── Status bar ────────────────────────────────────────────────────
function status(text, path) {
  document.getElementById('status-text').textContent = text;
  if (path !== undefined) document.getElementById('status-path').textContent = path;
}

// ── Stats ─────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const d = await apiFetch('GET', '/api/stats');
    document.getElementById('s-tickers').textContent = d.tickers;
    document.getElementById('s-runs').textContent    = d.runs;
    document.getElementById('s-events').textContent  = d.event_logs;
  } catch {}
}

async function loadIsinNames() {
  try { S.isinNames = await apiFetch('GET', '/api/isin-names'); } catch {}
}

async function loadBaseDir() {
  try { S.baseDir = (await apiFetch('GET', '/api/base-dir')).path; } catch {}
}

// ── Tab switch ────────────────────────────────────────────────────
function switchTab(tab) {
  S.tab = tab;
  document.getElementById('tab-reports').classList.toggle('active', tab === 'reports');
  document.getElementById('tab-events').classList.toggle('active', tab === 'events');
  S.selected.clear();
  S.selectedEvts.clear();
  updateBulkBar();
  clearContent();
  tab === 'reports' ? loadReports() : loadEventsTab();
}

// ── Filter ────────────────────────────────────────────────────────
function filterTree(val) {
  S.filter = val.trim().toUpperCase();
  S.tab === 'reports' ? renderTree() : renderEvtList();
}

// ══════════════════════════════════════════════════════════════════
//  REPORTS
// ══════════════════════════════════════════════════════════════════

async function loadReports() {
  status('LOADING...', '');
  document.getElementById('tree-container').innerHTML =
    '<div class="msg-empty">LOADING...</div>';
  try {
    S.reports = await apiFetch('GET', '/api/reports');
    renderTree();
    status('READY', 'NO FILE SELECTED');
  } catch (e) {
    status('ERROR', e.message);
    document.getElementById('tree-container').innerHTML =
      `<div class="msg-empty">ERROR: ${esc(e.message)}</div>`;
  }
}

function renderTree() {
  const tickers = Object.keys(S.reports).sort();
  const filtered = S.filter
    ? tickers.filter(t => t.includes(S.filter) || (S.isinNames[t] || '').toUpperCase().includes(S.filter))
    : tickers;
  const tc = document.getElementById('tree-container');

  if (!filtered.length) {
    tc.innerHTML = `<div class="msg-empty">${S.filter ? 'NO MATCHES' : 'NO REPORTS FOUND'}</div>`;
    return;
  }

  tc.innerHTML = filtered.map(t => renderTickerNode(t)).join('');
}

function renderTickerNode(t) {
  const runs     = S.reports[t] || [];
  const isOpen   = S.expanded.has(t);
  const fundName = S.isinNames[t] || '';
  const allSel   = runs.length > 0 && runs.every(r => S.selected.has(`${t}/${r.date}`));
  const someSel  = !allSel && runs.some(r => S.selected.has(`${t}/${r.date}`));
  const chkCls   = allSel ? 'checked' : someSel ? 'partial' : '';
  const chkChar  = allSel ? '&#x25A0;' : someSel ? '&#x25AA;' : '&#x25A1;';
  return `
    <div class="tree-ticker">
      <div class="tree-ticker-hdr ${isOpen ? 'open' : ''}" data-action="ticker" data-ticker="${at(t)}">
        <span class="chk ${chkCls}" data-action="check-ticker" data-ticker="${at(t)}">${chkChar}</span>
        <span class="chevron">&#x25BA;</span>
        <span class="ticker-label">
          <span class="ticker-name">${esc(t)}</span>
          ${fundName ? `<span class="ticker-fund-name">${esc(fundName)}</span>` : ''}
        </span>
        <span class="ticker-meta">${runs.length}&nbsp;run${runs.length !== 1 ? 's' : ''}</span>
      </div>
      ${isOpen ? `<div class="tree-dates visible">${runs.map(r => renderDateNode(t, r)).join('')}</div>` : ''}
    </div>`;
}

function renderDateNode(t, run) {
  const key     = `${t}/${run.date}`;
  const isOpen  = S.expanded.has(key);
  const isSel   = S.selected.has(key);
  const sigHtml = run.signal
    ? `<span class="sig sig-${run.signal}">${esc(run.signal)}</span>`
    : '';
  const filesHtml = isOpen ? renderFilesSection(t, run.date) : '';
  return `
    <div class="tree-date">
      <div class="tree-date-hdr ${isOpen ? 'open' : ''} ${isSel ? 'sel' : ''}" data-action="date" data-ticker="${at(t)}" data-date="${at(run.date)}">
        <span class="chk ${isSel ? 'checked' : ''}" data-action="check-date" data-ticker="${at(t)}" data-date="${at(run.date)}">${isSel ? '&#x25A0;' : '&#x25A1;'}</span>
        <span class="chevron">&#x25BA;</span>
        <span class="date-label">${esc(run.date)}</span>
        ${sigHtml}
      </div>
      ${filesHtml}
    </div>`;
}

function renderFilesSection(t, date) {
  const key   = `${t}/${date}`;
  const files = S.runFiles[key];
  let inner;
  if (!files) {
    inner = '<div class="msg-empty" style="font-size:10px;padding:4px 8px;">LOADING...</div>';
    // Kick off async load
    loadRunFiles(t, date);
  } else if (!files.length) {
    inner = '<div class="msg-empty" style="font-size:10px;padding:4px 8px;">NO FILES</div>';
  } else {
    inner = files.map(f => renderFileItem(t, date, f)).join('');
  }
  return `
    <div class="tree-files visible" id="files-${safeId(key)}">
      <div class="run-actions">
        <button class="btn-del-run" data-action="del-run" data-ticker="${at(t)}" data-date="${at(date)}">&#x2715;&nbsp;DEL RUN</button>
      </div>
      ${inner}
    </div>`;
}

function renderFileItem(t, date, f) {
  const isActive = S.currentTicker === t && S.currentDate === date && S.currentFile === f;
  const fname    = f.split('/').pop();
  const icon     = f.endsWith('.md') ? '&#x25A0;' : '&#x25C6;';
  return `
    <div class="tree-file-item ${isActive ? 'active' : ''}"
         data-action="file"
         data-ticker="${at(t)}" data-date="${at(date)}" data-file="${at(f)}"
         title="${esc(f)}">
      <span class="file-icon">${icon}</span>
      <span class="file-label">${esc(fname)}</span>
    </div>`;
}

async function loadRunFiles(t, date) {
  const key = `${t}/${date}`;
  try {
    const run = await apiFetch('GET', `/api/reports/${enc(t)}/${enc(date)}`);
    S.runFiles[key] = run.files || [];
    // Patch in the files without full re-render to avoid collapsing the tree
    const section = document.getElementById(`files-${safeId(key)}`);
    if (section) {
      const inner = S.runFiles[key].length
        ? S.runFiles[key].map(f => renderFileItem(t, date, f)).join('')
        : '<div class="msg-empty" style="font-size:10px;padding:4px 8px;">NO FILES</div>';
      // Replace everything after the run-actions div
      const actionsDiv = section.querySelector('.run-actions');
      if (actionsDiv) actionsDiv.insertAdjacentHTML('afterend', inner);
      const loading = section.querySelector('.msg-empty');
      if (loading) loading.remove();
    }
  } catch (e) {
    const section = document.getElementById(`files-${safeId(key)}`);
    if (section) {
      const loading = section.querySelector('.msg-empty');
      if (loading) loading.textContent = `ERROR: ${e.message}`;
    }
  }
}

// ── Event delegation for the tree ────────────────────────────────
document.getElementById('tree-container').addEventListener('click', e => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  const t      = el.dataset.ticker;
  const date   = el.dataset.date;

  if (action === 'ticker') {
    S.expanded.has(t) ? S.expanded.delete(t) : S.expanded.add(t);
    renderTree();
  } else if (action === 'date') {
    const key = `${t}/${date}`;
    if (S.expanded.has(key)) {
      S.expanded.delete(key);
    } else {
      S.expanded.add(key);
    }
    renderTree();
  } else if (action === 'file') {
    openFile(t, date, el.dataset.file);
  } else if (action === 'check-date') {
    e.stopPropagation();
    const key = `${t}/${date}`;
    S.selected.has(key) ? S.selected.delete(key) : S.selected.add(key);
    updateBulkBar();
    renderTree();
  } else if (action === 'check-ticker') {
    e.stopPropagation();
    const runs   = S.reports[t] || [];
    const allSel = runs.length > 0 && runs.every(r => S.selected.has(`${t}/${r.date}`));
    runs.forEach(r => allSel ? S.selected.delete(`${t}/${r.date}`) : S.selected.add(`${t}/${r.date}`));
    updateBulkBar();
    renderTree();
  } else if (action === 'del-run') {
    e.stopPropagation();
    confirmDeleteRun(t, date);
  } else if (action === 'del-evt') {
    e.stopPropagation();
    confirmDeleteEvt(el.dataset.name);
  }
});

// ── Open a report file ────────────────────────────────────────────
async function openFile(t, date, file) {
  S.currentTicker  = t;
  S.currentDate    = date;
  S.currentFile    = file;
  S.currentEvtFile = null;

  const pathStr = `${S.baseDir}/logs/${t}/${date}/${file}`;
  status('LOADING...', pathStr);

  // Update header
  showContentHeader(pathStr, null, true, true);

  try {
    const content = await apiFetch(
      'GET',
      `/api/reports/${enc(t)}/${enc(date)}/content`,
      { path: file }
    );

    const sig = detectSignal(content);
    updateContentSignal(sig);

    hideAllViews();
    if (file.endsWith('.md')) {
      const el = document.getElementById('md-view');
      el.classList.remove('hidden');
      el.innerHTML = marked.parse(content);
      highlightSignalsInDom(el);
    } else {
      const el = document.getElementById('raw-view');
      el.classList.remove('hidden');
      el.textContent = content;
    }

    // Re-render tree to show active file
    renderTree();
    status('READY', pathStr);
  } catch (err) {
    status('ERROR', err.message);
    hideAllViews();
    const el = document.getElementById('raw-view');
    el.classList.remove('hidden');
    el.textContent = `Error loading file:\n${err.message}`;
  }
}

// ══════════════════════════════════════════════════════════════════
//  EVENTS TAB
// ══════════════════════════════════════════════════════════════════

async function loadEventsTab() {
  status('LOADING...', '');
  document.getElementById('tree-container').innerHTML =
    '<div class="msg-empty">LOADING...</div>';
  try {
    S.events = await apiFetch('GET', '/api/events');
    renderEvtList();
    status('READY', 'NO FILE SELECTED');
  } catch (e) {
    status('ERROR', e.message);
    document.getElementById('tree-container').innerHTML =
      `<div class="msg-empty">ERROR: ${esc(e.message)}</div>`;
  }
}

function renderEvtList() {
  let list = S.events;
  if (S.filter) list = list.filter(e => e.name.toUpperCase().includes(S.filter));

  const tc = document.getElementById('tree-container');
  if (!list.length) {
    tc.innerHTML = `<div class="msg-empty">${S.filter ? 'NO MATCHES' : 'NO EVENT LOGS'}</div>`;
    return;
  }

  tc.innerHTML = list.map(ev => {
    const isActive = S.currentEvtFile === ev.name;
    const isSel    = S.selectedEvts.has(ev.name);
    const dt = new Date(ev.mtime * 1000);
    const dateStr = `${dt.getFullYear()}-${pad2(dt.getMonth()+1)}-${pad2(dt.getDate())} ${pad2(dt.getHours())}:${pad2(dt.getMinutes())}`;
    const sizeStr = ev.size < 1024 ? `${ev.size} B` : `${Math.round(ev.size/1024)} KB`;
    return `
      <div class="evt-item ${isActive ? 'active' : ''} ${isSel ? 'sel' : ''}" data-action="evt-open" data-name="${at(ev.name)}">
        <span class="chk ${isSel ? 'checked' : ''}" data-action="check-evt" data-name="${at(ev.name)}">${isSel ? '&#x25A0;' : '&#x25A1;'}</span>
        <div class="evt-item-body">
          <div class="evt-name">${esc(ev.name)}</div>
          <div class="evt-meta">
            <span>${dateStr}</span>
            <span>${sizeStr}</span>
          </div>
          <div class="evt-del-wrap">
            <button class="btn-del-run" data-action="del-evt" data-name="${at(ev.name)}">&#x2715;&nbsp;DEL</button>
          </div>
        </div>
      </div>`;
  }).join('');
}

// Open an event JSONL file
async function openEvtFile(name) {
  S.currentEvtFile = name;
  S.currentTicker  = null;
  S.currentDate    = null;
  S.currentFile    = null;

  const pathStr = `${S.baseDir}/visualizer_events/${name}`;
  status('LOADING...', pathStr);

  showContentHeader(pathStr, null, false, false);
  renderEvtList();

  try {
    const rows = await apiFetch('GET', `/api/events/${enc(name)}`);
    hideAllViews();
    const el = document.getElementById('evt-view');
    el.classList.remove('hidden');
    el.innerHTML = buildEvtTimeline(rows, name);
    status('READY', pathStr);
  } catch (err) {
    status('ERROR', err.message);
  }
}

function buildEvtTimeline(rows, name) {
  const delBtn = `<div class="evt-view-header">
    <button class="btn-danger" data-action="del-evt-cur">&#x2715;&nbsp;DELETE LOG</button>
  </div>`;
  document.getElementById('evt-view').addEventListener('click', e => {
    if (e.target.closest('[data-action="del-evt-cur"]')) confirmDeleteEvt(S.currentEvtFile);
  }, { once: true });

  if (!rows.length) return delBtn + '<div class="msg-empty">NO EVENTS IN LOG</div>';

  const rowsHtml = rows.map(entry => {
    const ts  = entry.ts  || '';
    const ev  = entry.event || {};
    const typ = (ev.type || 'unknown').toLowerCase();
    const tsd = ts.slice(0, 10);
    const tst = ts.slice(11, 19);
    const detail = fmtEvtDetail(typ, ev);
    return `<div class="evt-row">
      <div class="evt-ts"><span>${esc(tsd)}</span><br><span class="ts-time">${esc(tst)}</span></div>
      <div class="evt-type t-${esc(typ)}">${esc(typ.replace(/_/g, ' ').toUpperCase())}</div>
      <div class="evt-detail">${detail}</div>
    </div>`;
  }).join('');

  return delBtn + `
    <div class="evt-table-hdr">
      <span>TIMESTAMP</span><span>EVENT&nbsp;TYPE</span><span>DETAILS</span>
    </div>
    ${rowsHtml}`;
}

function fmtEvtDetail(typ, ev) {
  if (typ === 'workflow_start')    return `TICKER: <b>${esc(ev.ticker||'')}</b>  DATE: ${esc(ev.date||'')}`;
  if (typ === 'workflow_complete') {
    const cls = ev.signal ? `sig sig-${ev.signal}` : '';
    return `SIGNAL: <span class="${cls}">${esc(ev.signal||'—')}</span>  TICKER: ${esc(ev.ticker||'')}`;
  }
  if (typ === 'agent_active')  return `AGENT: <b>${esc(ev.agent||'')}</b>`;
  if (typ === 'agent_idle')    return esc(ev.agent||'');
  if (typ === 'handoff')       return `${esc(ev.from||'?')} &rarr; ${esc(ev.to||'?')}`;
  // Fallback: dump remaining keys
  const { type: _, ...rest } = ev;
  return esc(JSON.stringify(rest).replace(/^{|}$/g, ''));
}

// ── Tree event delegation (extends click handler for evt items) ───
document.getElementById('tree-container').addEventListener('click', e => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  if (el.dataset.action === 'evt-open') openEvtFile(el.dataset.name);
  else if (el.dataset.action === 'check-evt') {
    e.stopPropagation();
    const name = el.dataset.name;
    S.selectedEvts.has(name) ? S.selectedEvts.delete(name) : S.selectedEvts.add(name);
    updateBulkBar();
    renderEvtList();
  }
  // del-evt handled by the first delegation block above
});

// ══════════════════════════════════════════════════════════════════
//  CONTENT HEADER HELPERS
// ══════════════════════════════════════════════════════════════════

function showContentHeader(path, sig, showDelFile, showDelRun) {
  document.getElementById('content-header').classList.remove('hidden');
  document.getElementById('content-path').textContent = path;
  updateContentSignal(sig);
  document.getElementById('btn-del-file').classList.toggle('hidden', !showDelFile);
  document.getElementById('btn-del-run').classList.toggle('hidden', !showDelRun);
}

function updateContentSignal(sig) {
  const el = document.getElementById('content-signal');
  if (sig) {
    el.textContent  = sig;
    el.className    = `sig sig-${sig}`;
  } else {
    el.textContent  = '';
    el.className    = '';
  }
}

function clearContent() {
  S.currentTicker = S.currentDate = S.currentFile = S.currentEvtFile = null;
  hideAllViews();
  document.getElementById('welcome').classList.remove('hidden');
  document.getElementById('content-header').classList.add('hidden');
}

function hideAllViews() {
  ['welcome','md-view','raw-view','evt-view'].forEach(id =>
    document.getElementById(id).classList.add('hidden')
  );
}

// ══════════════════════════════════════════════════════════════════
//  SIGNAL DETECTION
// ══════════════════════════════════════════════════════════════════

const SIG_RE = /\b(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)\b/i;

function detectSignal(text) {
  const m = text.match(SIG_RE);
  return m ? m[1].toUpperCase() : null;
}

function highlightSignalsInDom(root) {
  // Walk text nodes and wrap signal words
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const toReplace = [];
  let node;
  while ((node = walker.nextNode())) toReplace.push(node);

  toReplace.forEach(tn => {
    if (!SIG_RE.test(tn.textContent)) return;
    const span = document.createElement('span');
    span.innerHTML = tn.textContent.replace(
      /\b(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)\b/gi,
      w => `<span class="hl-${w.toLowerCase()}">${w}</span>`
    );
    tn.replaceWith(span);
  });
}

// ══════════════════════════════════════════════════════════════════
//  DELETE ACTIONS (header buttons)
// ══════════════════════════════════════════════════════════════════

// ── Bulk selection helpers ────────────────────────────────────────
function updateBulkBar() {
  const isReports = S.tab === 'reports';
  const n   = isReports ? S.selected.size : S.selectedEvts.size;
  const bar = document.getElementById('bulk-bar');
  bar.classList.toggle('hidden', n === 0);
  const noun = isReports ? `RUN${n !== 1 ? 'S' : ''}` : `LOG${n !== 1 ? 'S' : ''}`;
  document.getElementById('bulk-count').textContent = `${n} ${noun} SELECTED`;
}

function clearSelection() {
  if (S.tab === 'reports') S.selected.clear();
  else S.selectedEvts.clear();
  updateBulkBar();
  S.tab === 'reports' ? renderTree() : renderEvtList();
}

async function execBulkDelete() {
  if (S.tab === 'reports') {
    const keys = [...S.selected].sort();
    showModal(
      `CONFIRM — DELETE ${keys.length} RUN${keys.length !== 1 ? 'S' : ''}`,
      keys.join('\n') + '\n\nThis action cannot be undone.',
      async () => {
        status('DELETING...', `${keys.length} runs`);
        let errors = 0;
        for (const key of keys) {
          const slash = key.indexOf('/');
          const t     = key.slice(0, slash);
          const date  = key.slice(slash + 1);
          try {
            await apiFetch('DELETE', `/api/reports/${enc(t)}/${enc(date)}`);
            S.expanded.delete(key);
            S.expanded.delete(t);
            delete S.runFiles[key];
          } catch { errors++; }
          S.selected.delete(key);
        }
        clearContent();
        await Promise.all([loadReports(), loadStats()]);
        updateBulkBar();
        status(errors ? 'PARTIAL ERROR' : 'DELETED',
               errors ? `${errors} of ${keys.length} failed` : `${keys.length} runs`);
      }
    );
  } else {
    const names = [...S.selectedEvts].sort();
    showModal(
      `CONFIRM — DELETE ${names.length} LOG${names.length !== 1 ? 'S' : ''}`,
      names.join('\n') + '\n\nThis action cannot be undone.',
      async () => {
        status('DELETING...', `${names.length} logs`);
        let errors = 0;
        for (const name of names) {
          try {
            await apiFetch('DELETE', `/api/events/${enc(name)}`);
          } catch { errors++; }
          S.selectedEvts.delete(name);
        }
        clearContent();
        await Promise.all([loadEventsTab(), loadStats()]);
        updateBulkBar();
        status(errors ? 'PARTIAL ERROR' : 'DELETED',
               errors ? `${errors} of ${names.length} failed` : `${names.length} logs`);
      }
    );
  }
}

function deleteCurrentFile() {
  if (S.currentTicker && S.currentDate && S.currentFile)
    confirmDeleteFile(S.currentTicker, S.currentDate, S.currentFile);
}

function deleteCurrentRun() {
  if (S.currentTicker && S.currentDate)
    confirmDeleteRun(S.currentTicker, S.currentDate);
}

// ── Confirm modal ─────────────────────────────────────────────────
function showModal(title, body, onOk) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent  = body;
  S.pendingOk = onOk;
  document.getElementById('modal-overlay').classList.remove('hidden');
  document.getElementById('modal-ok').focus();
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  S.pendingOk = null;
}

function modalConfirm() {
  const cb = S.pendingOk;
  closeModal();
  if (cb) cb();
}

function confirmDeleteRun(t, date) {
  showModal(
    'CONFIRM — DELETE RUN',
    `Delete all reports for:\n  ${t} / ${date}\n\nThis action cannot be undone.`,
    () => execDeleteRun(t, date)
  );
}

function confirmDeleteFile(t, date, file) {
  showModal(
    'CONFIRM — DELETE FILE',
    `Delete file:\n  ${file}\n\nFrom run: ${t} / ${date}\n\nThis action cannot be undone.`,
    () => execDeleteFile(t, date, file)
  );
}

function confirmDeleteEvt(name) {
  showModal(
    'CONFIRM — DELETE LOG',
    `Delete visualizer event log:\n  ${name}\n\nThis action cannot be undone.`,
    () => execDeleteEvt(name)
  );
}

// ── Execute deletes ───────────────────────────────────────────────
async function execDeleteRun(t, date) {
  const label = `${t}/${date}`;
  status('DELETING...', label);
  try {
    await apiFetch('DELETE', `/api/reports/${enc(t)}/${enc(date)}`);
    const key = label;
    S.expanded.delete(t);
    S.expanded.delete(key);
    delete S.runFiles[key];
    clearContent();
    await Promise.all([loadReports(), loadStats()]);
    status('DELETED', label);
  } catch (e) {
    status('ERROR', e.message);
    alert(`Delete failed: ${e.message}`);
  }
}

async function execDeleteFile(t, date, file) {
  status('DELETING...', file);
  try {
    await apiFetch('DELETE', `/api/reports/${enc(t)}/${enc(date)}/file`, { path: file });
    const key = `${t}/${date}`;
    delete S.runFiles[key];   // invalidate cache so file list reloads
    clearContent();
    await Promise.all([loadReports(), loadStats()]);
    status('DELETED', file);
  } catch (e) {
    status('ERROR', e.message);
    alert(`Delete failed: ${e.message}`);
  }
}

async function execDeleteEvt(name) {
  status('DELETING...', name);
  try {
    await apiFetch('DELETE', `/api/events/${enc(name)}`);
    clearContent();
    await Promise.all([loadEventsTab(), loadStats()]);
    status('DELETED', name);
  } catch (e) {
    status('ERROR', e.message);
    alert(`Delete failed: ${e.message}`);
  }
}

// ══════════════════════════════════════════════════════════════════
//  SIDEBAR RESIZE
// ══════════════════════════════════════════════════════════════════

function startResize(e) {
  e.preventDefault();
  const sidebar = document.getElementById('sidebar');
  const handle  = document.getElementById('resize-handle');
  handle.classList.add('active');
  const startX = e.clientX;
  const startW = sidebar.getBoundingClientRect().width;

  const onMove = ev => {
    const w = Math.max(160, Math.min(600, startW + ev.clientX - startX));
    sidebar.style.width = w + 'px';
  };
  const onUp = () => {
    handle.classList.remove('active');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ══════════════════════════════════════════════════════════════════
//  UTIL
// ══════════════════════════════════════════════════════════════════

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function at(s) { return String(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function enc(s)    { return encodeURIComponent(s); }
function pad2(n)   { return String(n).padStart(2, '0'); }
function safeId(s) { return s.replace(/[^a-zA-Z0-9_-]/g, '_'); }

// ── Boot ──────────────────────────────────────────────────────────
loadStats();
Promise.all([loadBaseDir(), loadIsinNames()]).then(() => loadReports());
