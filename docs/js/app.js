/**
 * API TestGen — Frontend Application
 * Handles file upload, API communication, rendering, filtering, and export.
 */

'use strict';

/* ═══════════════════════════════════════════════════════════════════
   State
═══════════════════════════════════════════════════════════════════ */
const State = {
  allTestCases: [],
  filteredTestCases: [],
  selectedFile: null,
  currentPage: 1,
  pageSize: 20,
  activeCategory: null,
  searchQuery: '',
  methodFilter: '',
  statusFilter: '',
  summary: null,
};

/* ═══════════════════════════════════════════════════════════════════
   DOM References
═══════════════════════════════════════════════════════════════════ */
const dom = {
  apiUrlInput: () => document.getElementById('api-url-input'),
  testConnBtn: () => document.getElementById('test-connection-btn'),
  connIndicator: () => document.getElementById('conn-indicator'),
  dropZone: () => document.getElementById('drop-zone'),
  fileInput: () => document.getElementById('file-input'),
  browseBtn: () => document.getElementById('browse-btn'),
  fileInfo: () => document.getElementById('file-info'),
  fileNameDisplay: () => document.getElementById('file-name-display'),
  fileSizeDisplay: () => document.getElementById('file-size-display'),
  removeFileBtn: () => document.getElementById('remove-file-btn'),
  validationResult: () => document.getElementById('validation-result'),
  generateBtn: () => document.getElementById('generate-btn'),
  generateBtnText: () => document.getElementById('generate-btn-text'),
  generateBtnSpinner: () => document.getElementById('generate-btn-spinner'),
  resultsSection: () => document.getElementById('results-section'),
  resultsCount: () => document.getElementById('results-count'),
  resultsSubtitle: () => document.getElementById('results-subtitle'),
  summaryGrid: () => document.getElementById('summary-grid'),
  searchInput: () => document.getElementById('search-input'),
  filterChips: () => document.getElementById('filter-chips'),
  methodFilter: () => document.getElementById('method-filter'),
  statusFilter: () => document.getElementById('status-filter'),
  testCasesTable: () => document.getElementById('test-cases-table'),
  paginationBar: () => document.getElementById('pagination-bar'),
  copyJsonBtn: () => document.getElementById('copy-json-btn'),
  downloadJsonBtn: () => document.getElementById('download-json-btn'),
  downloadYamlBtn: () => document.getElementById('download-yaml-btn'),
  downloadCsvBtn: () => document.getElementById('download-csv-btn'),
  toast: () => document.getElementById('toast'),
};

/* ═══════════════════════════════════════════════════════════════════
   Utilities
═══════════════════════════════════════════════════════════════════ */
const Utils = {
  formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  },

  escapeHtml(str) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' };
    return String(str).replace(/[&<>"']/g, m => map[m]);
  },

  jsonPretty(val) {
    if (val === null || val === undefined) return 'null';
    try {
      return JSON.stringify(val, null, 2);
    } catch {
      return String(val);
    }
  },

  debounce(fn, delay) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
  },

  downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  csvEscape(val) {
    const str = val === null || val === undefined ? '' : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  },

  getApiUrl() {
    return (dom.apiUrlInput()?.value || 'http://localhost:8000').replace(/\/$/, '');
  },
};

/* ═══════════════════════════════════════════════════════════════════
   Toast
═══════════════════════════════════════════════════════════════════ */
let toastTimer = null;
function showToast(message, type = 'info', duration = 3500) {
  const el = dom.toast();
  if (!el) return;
  el.textContent = message;
  el.className = `toast toast--${type}`;
  el.hidden = false;
  el.removeAttribute('aria-hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
    el.setAttribute('aria-hidden', 'true');
  }, duration);
}

/* ═══════════════════════════════════════════════════════════════════
   Connection Test
═══════════════════════════════════════════════════════════════════ */
async function testConnection() {
  const indicator = dom.connIndicator();
  const btn = dom.testConnBtn();
  indicator.className = 'btn-indicator btn-indicator--loading';
  btn.disabled = true;
  try {
    const res = await fetch(`${Utils.getApiUrl()}/health`, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      indicator.className = 'btn-indicator btn-indicator--ok';
      showToast('✓ Connected to backend API', 'success');
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    indicator.className = 'btn-indicator btn-indicator--error';
    showToast(`✗ Cannot reach API: ${err.message}`, 'error', 5000);
  } finally {
    btn.disabled = false;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   File Handling
═══════════════════════════════════════════════════════════════════ */
function acceptFile(file) {
  if (!file) return;
  const validExtensions = ['.json', '.yaml', '.yml', '.raml'];
  const hasValidExt = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
  if (!hasValidExt) {
    showToast('Invalid file type. Please upload .json, .yaml, .yml, or .raml', 'error');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showToast('File too large. Maximum size is 10 MB.', 'error');
    return;
  }
  State.selectedFile = file;
  renderFileInfo(file);
  validateSpec(file);
}

function renderFileInfo(file) {
  const dz = dom.dropZone();
  const info = dom.fileInfo();
  dz.classList.add('drop-zone--has-file');
  dom.fileNameDisplay().textContent = file.name;
  dom.fileSizeDisplay().textContent = Utils.formatBytes(file.size);
  info.hidden = false;
  dom.generateBtn().disabled = false;
  dom.generateBtn().removeAttribute('aria-disabled');
}

function clearFile() {
  State.selectedFile = null;
  dom.dropZone().classList.remove('drop-zone--has-file');
  dom.fileInfo().hidden = true;
  dom.fileInput().value = '';
  dom.generateBtn().disabled = true;
  dom.generateBtn().setAttribute('aria-disabled', 'true');
  const vr = dom.validationResult();
  vr.hidden = true;
  vr.className = 'validation-result';
}

async function validateSpec(file) {
  const vr = dom.validationResult();
  vr.hidden = false;
  vr.className = 'validation-result';
  vr.textContent = 'Validating spec…';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${Utils.getApiUrl()}/api/validate`, { method: 'POST', body: formData, signal: AbortSignal.timeout(10000) });
    const data = await res.json();
    if (data.valid) {
      vr.className = 'validation-result validation-result--success';
      vr.innerHTML = `✓ Valid <strong>${Utils.escapeHtml(data.oas_version)}</strong> spec — <strong>${Utils.escapeHtml(data.title)}</strong> v${Utils.escapeHtml(data.version)} · ${data.endpoint_count} endpoint${data.endpoint_count !== 1 ? 's' : ''} found`;
    } else {
      vr.className = 'validation-result validation-result--error';
      vr.textContent = `✗ ${data.error || 'Invalid spec'}`;
    }
  } catch (err) {
    vr.className = 'validation-result validation-result--error';
    vr.textContent = `Could not validate: ${err.message}. You can still try generating.`;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Generate
═══════════════════════════════════════════════════════════════════ */
async function generateTestCases() {
  if (!State.selectedFile) return;

  const btn = dom.generateBtn();
  const btnText = dom.generateBtnText();
  const spinner = dom.generateBtnSpinner();

  btn.disabled = true;
  btnText.textContent = 'Generating…';
  spinner.hidden = false;

  const formData = new FormData();
  formData.append('file', State.selectedFile);

  try {
    const res = await fetch(`${Utils.getApiUrl()}/api/generate`, {
      method: 'POST',
      body: formData,
      signal: AbortSignal.timeout(60000),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    State.allTestCases = data.test_cases || [];
    State.summary = data.summary || {};
    State.currentPage = 1;
    State.activeCategory = null;
    State.searchQuery = '';
    State.methodFilter = '';
    State.statusFilter = '';

    applyFilters();
    renderResults(data);
    dom.resultsSection().hidden = false;
    dom.resultsSection().scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast(`✓ Generated ${data.total} test cases`, 'success');
  } catch (err) {
    showToast(`✗ Generation failed: ${err.message}`, 'error', 6000);
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Generate Test Cases';
    spinner.hidden = true;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Filter & Search
═══════════════════════════════════════════════════════════════════ */
function applyFilters() {
  let result = [...State.allTestCases];

  if (State.activeCategory) {
    result = result.filter(tc => tc.category === State.activeCategory);
  }
  if (State.methodFilter) {
    result = result.filter(tc => tc.method === State.methodFilter);
  }
  if (State.statusFilter) {
    result = result.filter(tc => String(tc.expected_status) === State.statusFilter);
  }
  if (State.searchQuery) {
    const q = State.searchQuery.toLowerCase();
    result = result.filter(tc =>
      tc.name.toLowerCase().includes(q) ||
      tc.path.toLowerCase().includes(q) ||
      tc.description.toLowerCase().includes(q) ||
      tc.method.toLowerCase().includes(q)
    );
  }

  State.filteredTestCases = result;
  State.currentPage = 1;
  renderTestCaseList();
  renderPagination();
}

/* ═══════════════════════════════════════════════════════════════════
   Render Functions
═══════════════════════════════════════════════════════════════════ */
function renderResults(data) {
  dom.resultsCount().textContent = data.total;
  dom.resultsSubtitle().textContent =
    `Spec: ${State.selectedFile?.name} · Generated at ${new Date().toLocaleTimeString()}`;

  renderSummaryGrid(data.summary);
  renderFilterChips(data.summary);
}

const CATEGORY_CONFIG = {
  positive: { label: 'Positive', icon: '✓' },
  negative: { label: 'Negative', icon: '✗' },
  boundary: { label: 'Boundary', icon: '◈' },
  security: { label: 'Security', icon: '⚿' },
  data_type: { label: 'Data Type', icon: '⟨⟩' },
  combinatorial: { label: 'Combinatorial', icon: '⊞' },
};

function renderSummaryGrid(summary) {
  const grid = dom.summaryGrid();
  const byCategory = summary?.by_category || {};

  const total = State.allTestCases.length;
  let html = `
    <div class="summary-card" role="listitem" tabindex="0" data-category="" aria-label="All test cases: ${total}">
      <span class="summary-card-count" style="color:var(--text-primary)">${total}</span>
      <span class="summary-card-label">All Cases</span>
    </div>`;

  for (const [cat, cfg] of Object.entries(CATEGORY_CONFIG)) {
    const count = byCategory[cat] || 0;
    if (count === 0) continue;
    html += `
      <div class="summary-card" role="listitem" tabindex="0" data-category="${cat}"
           aria-label="${cfg.label}: ${count} test cases"
           style="--card-color: var(--cat-${cat})">
        <span class="summary-card-count" style="color:var(--cat-${cat})">${count}</span>
        <span class="summary-card-label">${cfg.label}</span>
      </div>`;
  }

  grid.innerHTML = html;

  // Click handlers
  grid.querySelectorAll('.summary-card').forEach(card => {
    const handler = () => {
      State.activeCategory = card.dataset.category || null;
      grid.querySelectorAll('.summary-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      // Sync filter chips
      document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.category === (State.activeCategory || ''));
      });
      applyFilters();
    };
    card.addEventListener('click', handler);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); } });
  });

  // Mark "All" active initially
  grid.querySelector('[data-category=""]')?.classList.add('active');
}

function renderFilterChips(summary) {
  const container = dom.filterChips();
  const byCategory = summary?.by_category || {};
  let html = `<button class="filter-chip active" data-category="" style="color:var(--text-primary)" aria-pressed="true">All</button>`;

  for (const [cat, cfg] of Object.entries(CATEGORY_CONFIG)) {
    if (!byCategory[cat]) continue;
    html += `<button class="filter-chip cat-${cat}" data-category="${cat}" style="--chip-color:var(--cat-${cat})" aria-pressed="false">${cfg.label}</button>`;
  }

  container.innerHTML = html;
  container.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      State.activeCategory = chip.dataset.category || null;
      container.querySelectorAll('.filter-chip').forEach(c => {
        c.classList.remove('active');
        c.setAttribute('aria-pressed', 'false');
      });
      chip.classList.add('active');
      chip.setAttribute('aria-pressed', 'true');

      // Sync summary cards
      document.querySelectorAll('.summary-card').forEach(c => {
        c.classList.toggle('active', c.dataset.category === (State.activeCategory || ''));
      });
      applyFilters();
    });
  });
}

function renderTestCaseList() {
  const container = dom.testCasesTable();
  const { filteredTestCases, currentPage, pageSize } = State;

  if (filteredTestCases.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:3rem;color:var(--text-muted)">
        <div style="font-size:2rem;margin-bottom:0.5rem">◈</div>
        No test cases match your filters.
      </div>`;
    return;
  }

  const start = (currentPage - 1) * pageSize;
  const pageItems = filteredTestCases.slice(start, start + pageSize);

  container.innerHTML = pageItems.map(tc => renderTestCaseCard(tc)).join('');

  // Toggle expansion
  container.querySelectorAll('.test-case-header').forEach(header => {
    header.addEventListener('click', () => {
      const card = header.closest('.test-case-card');
      const expanded = card.classList.toggle('expanded');
      header.setAttribute('aria-expanded', expanded);
    });
    header.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); }
    });
  });
}

function renderTestCaseCard(tc) {
  const methodClass = `method-${tc.method}`;
  const catClass = `cat-${tc.category}`;
  const statusClass = tc.expected_status < 300 ? 'status-2xx' : tc.expected_status < 500 ? 'status-4xx' : 'status-5xx';

  const headersStr = Utils.jsonPretty(tc.headers);
  const bodyStr = tc.body !== null && tc.body !== undefined ? Utils.jsonPretty(tc.body) : 'null';
  const pathParamsStr = Object.keys(tc.path_params || {}).length > 0 ? Utils.jsonPretty(tc.path_params) : null;
  const queryStr = Object.keys(tc.query_params || {}).length > 0 ? Utils.jsonPretty(tc.query_params) : null;

  return `
    <div class="test-case-card" role="listitem">
      <div class="test-case-header"
           tabindex="0"
           role="button"
           aria-expanded="false"
           aria-controls="tc-body-${Utils.escapeHtml(tc.id)}"
           aria-label="${Utils.escapeHtml(tc.name)}">
        <span class="tc-method-badge ${methodClass}">${Utils.escapeHtml(tc.method)}</span>
        <span class="tc-cat-badge ${catClass}">${Utils.escapeHtml(tc.category)}</span>
        <span class="tc-name" title="${Utils.escapeHtml(tc.name)}">${Utils.escapeHtml(tc.name)}</span>
        <span class="tc-status-badge ${statusClass}" aria-label="Expected status ${tc.expected_status}">${tc.expected_status}</span>
        <span class="tc-expand-icon" aria-hidden="true">▼</span>
      </div>
      <div class="test-case-body" id="tc-body-${Utils.escapeHtml(tc.id)}">
        <p class="tc-description">${Utils.escapeHtml(tc.description)}</p>
        <div class="tc-detail-grid">
          <div class="tc-detail-block">
            <div class="tc-detail-label">Headers</div>
            <div class="tc-detail-code">${Utils.escapeHtml(headersStr)}</div>
          </div>
          <div class="tc-detail-block">
            <div class="tc-detail-label">Request Body</div>
            <div class="tc-detail-code">${Utils.escapeHtml(bodyStr)}</div>
          </div>
          ${pathParamsStr ? `
          <div class="tc-detail-block">
            <div class="tc-detail-label">Path Parameters</div>
            <div class="tc-detail-code">${Utils.escapeHtml(pathParamsStr)}</div>
          </div>` : ''}
          ${queryStr ? `
          <div class="tc-detail-block">
            <div class="tc-detail-label">Query Parameters</div>
            <div class="tc-detail-code">${Utils.escapeHtml(queryStr)}</div>
          </div>` : ''}
        </div>
        <div class="tc-expected">
          <span>Expected:</span>
          <strong>HTTP ${tc.expected_status}</strong>
          <span>·</span>
          <span>${Utils.escapeHtml(tc.expected_behavior)}</span>
        </div>
      </div>
    </div>`;
}

function renderPagination() {
  const bar = dom.paginationBar();
  const total = State.filteredTestCases.length;
  const totalPages = Math.ceil(total / State.pageSize);

  if (totalPages <= 1) { bar.innerHTML = ''; return; }

  const { currentPage } = State;
  let html = '';

  const makeBtn = (label, page, disabled = false, active = false) =>
    `<button class="page-btn${active ? ' active' : ''}" data-page="${page}" ${disabled ? 'disabled' : ''}
      aria-label="Page ${page}" ${active ? 'aria-current="page"' : ''}>${label}</button>`;

  html += makeBtn('‹', currentPage - 1, currentPage === 1);

  const delta = 2;
  let pages = new Set([1, totalPages]);
  for (let p = Math.max(1, currentPage - delta); p <= Math.min(totalPages, currentPage + delta); p++) pages.add(p);
  pages = [...pages].sort((a, b) => a - b);

  let prev = null;
  for (const p of pages) {
    if (prev && p - prev > 1) html += `<span class="page-btn" aria-hidden="true" style="border:none;cursor:default;color:var(--text-muted)">…</span>`;
    html += makeBtn(p, p, false, p === currentPage);
    prev = p;
  }

  html += makeBtn('›', currentPage + 1, currentPage === totalPages);

  // Info
  const start = (currentPage - 1) * State.pageSize + 1;
  const end = Math.min(currentPage * State.pageSize, total);
  html += `<span style="font-size:0.78rem;color:var(--text-muted);font-family:var(--font-mono);margin-left:0.5rem" aria-live="polite">${start}–${end} of ${total}</span>`;

  bar.innerHTML = html;
  bar.querySelectorAll('.page-btn[data-page]').forEach(btn => {
    if (!btn.disabled && !btn.classList.contains('active')) {
      btn.addEventListener('click', () => {
        State.currentPage = parseInt(btn.dataset.page, 10);
        renderTestCaseList();
        renderPagination();
        dom.testCasesTable().scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════
   Export
═══════════════════════════════════════════════════════════════════ */
function exportJson() {
  const data = JSON.stringify(State.filteredTestCases, null, 2);
  Utils.downloadFile(data, 'test-cases.json', 'application/json');
  showToast('✓ JSON downloaded', 'success');
}

async function exportYaml() {
  if (!State.filteredTestCases || State.filteredTestCases.length === 0) {
    showToast('No test cases to export', 'error');
    return;
  }

  try {
    let yamlDump;
    if (window.jsyaml && window.jsyaml.dump) {
      yamlDump = window.jsyaml.dump;
    } else {
      showToast('Loading YAML engine...', 'info', 1000);
      const module = await import('https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/+esm');
      yamlDump = module.default.dump;
      window.jsyaml = module.default;
    }

    // Stringify body objects so they don't become nested YAML mappings if users prefer raw JSON bodies in YAML
    const cleanCases = State.filteredTestCases.map(tc => {
      const copy = { ...tc };
      if (copy.body && typeof copy.body === 'object') {
        copy.body = JSON.stringify(copy.body, null, 2);
      }
      return copy;
    });

    const yamlString = yamlDump(cleanCases, { indent: 2, lineWidth: -1 });
    Utils.downloadFile(yamlString, 'test-cases.yaml', 'application/x-yaml');
    showToast('✓ YAML downloaded', 'success');
  } catch (err) {
    console.error('YAML Export Error:', err);
    showToast('✗ YAML export failed', 'error');
  }
}

function exportCsv() {
  const headers = ['id', 'name', 'category', 'method', 'path', 'expected_status', 'expected_behavior', 'headers', 'body', 'path_params', 'query_params', 'description'];
  const rows = [headers.map(Utils.csvEscape).join(',')];
  for (const tc of State.filteredTestCases) {
    rows.push(headers.map(h => {
      const val = typeof tc[h] === 'object' ? JSON.stringify(tc[h]) : tc[h];
      return Utils.csvEscape(val ?? '');
    }).join(','));
  }
  Utils.downloadFile(rows.join('\n'), 'test-cases.csv', 'text/csv');
  showToast('✓ CSV downloaded', 'success');
}

async function copyJson() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(State.filteredTestCases, null, 2));
    showToast('✓ Copied to clipboard', 'success');
  } catch {
    showToast('✗ Clipboard copy failed', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Drag & Drop
═══════════════════════════════════════════════════════════════════ */
function initDragAndDrop() {
  const dz = dom.dropZone();
  ['dragenter', 'dragover'].forEach(evt => {
    dz.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); dz.classList.add('drag-over'); dz.setAttribute('aria-dropeffect', 'copy'); });
  });
  ['dragleave', 'dragend', 'drop'].forEach(evt => {
    dz.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); dz.classList.remove('drag-over'); dz.setAttribute('aria-dropeffect', 'none'); });
  });
  dz.addEventListener('drop', e => {
    const file = e.dataTransfer?.files?.[0];
    if (file) acceptFile(file);
  });
}

/* ═══════════════════════════════════════════════════════════════════
   Initialisation
═══════════════════════════════════════════════════════════════════ */
function init() {
  // Settings panel toggle (Backend URL — tucked away at the bottom)
  const settingsToggle = document.getElementById('settings-toggle');
  const settingsBody = document.getElementById('settings-body');
  settingsToggle?.addEventListener('click', () => {
    const expanded = settingsBody.hidden;
    settingsBody.hidden = !expanded;
    settingsToggle.setAttribute('aria-expanded', expanded);
  });

  // Connection test
  dom.testConnBtn()?.addEventListener('click', testConnection);

  // Drop zone keyboard activation
  dom.dropZone()?.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dom.fileInput()?.click(); }
  });
  dom.browseBtn()?.addEventListener('click', () => dom.fileInput()?.click());
  dom.fileInput()?.addEventListener('change', e => {
    const file = e.target.files?.[0];
    if (file) acceptFile(file);
  });
  dom.removeFileBtn()?.addEventListener('click', clearFile);

  // Generate
  dom.generateBtn()?.addEventListener('click', generateTestCases);

  // Drag & drop
  initDragAndDrop();

  // Search & Filters
  dom.searchInput()?.addEventListener('input', Utils.debounce(e => {
    State.searchQuery = e.target.value;
    applyFilters();
  }, 250));

  dom.methodFilter()?.addEventListener('change', e => {
    State.methodFilter = e.target.value;
    applyFilters();
  });

  dom.statusFilter()?.addEventListener('change', e => {
    State.statusFilter = e.target.value;
    applyFilters();
  });

  // Export
  dom.copyJsonBtn()?.addEventListener('click', copyJson);
  dom.downloadJsonBtn()?.addEventListener('click', exportJson);
  dom.downloadYamlBtn()?.addEventListener('click', exportYaml);
  dom.downloadCsvBtn()?.addEventListener('click', exportCsv);

  // Smooth scroll for anchor nav links
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', e => {
      const target = document.querySelector(link.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth' }); }
    });
  });

  // Auto-test connection if URL is already populated
  const url = dom.apiUrlInput()?.value;
  if (url && url !== 'http://localhost:8000') testConnection();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
