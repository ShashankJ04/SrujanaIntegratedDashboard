/* Production Scheduler — Gantt UI (Titanium Industrial layout) */
window.ProductionSchedulerPage = (() => {
  'use strict';

  const API = '/api/scheduler';
  let _runData = null;
  let _calendarData = null;
  let _currentScenario = null;
  let _initialized = false;
  let _compareMode = false;
  let _weightsOpen = false;
  let _legendFilter = null;
  let _bottomPanelMinimized = false;
  const _machineSort = { key: 'machine_name', dir: 'asc' };
  const _toolSort = { key: 'tool_no', dir: 'asc' };

  const MACHINE_COLS = [
    { key: 'machine_name', label: 'Machine' },
    { key: 'used_minutes', label: 'Used (min)', align: 'right' },
    { key: 'available_minutes', label: 'Available (min)', align: 'right' },
    { key: 'utilization_pct', label: 'Utilization' },
    { key: 'changeovers', label: 'Changeovers', align: 'right' },
    { key: 'overflow_minutes', label: 'Overflow (min)', align: 'right' },
    { key: 'status', label: 'Status' },
  ];

  const TOOL_COLS = [
    { key: 'tool_no', label: 'Tool' },
    { key: 'used_minutes', label: 'Used (min)', align: 'right' },
    { key: 'available_minutes', label: 'Available (min)', align: 'right' },
    { key: 'utilization_pct', label: 'Utilization' },
    { key: 'status', label: 'Status' },
  ];

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function api(method, path, body) {
    if (window.Hub && window.Hub.api) {
      if (method === 'GET') return window.Hub.api.get(API + path);
      if (method === 'POST') return window.Hub.api.post(API + path, body);
      if (method === 'PUT') return window.Hub.api.put(API + path, body);
    }
    const opts = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' };
    if (body) opts.body = JSON.stringify(body);
    return fetch(API + path, opts).then(async (r) => {
      if (!r.ok) {
        let msg = `Error ${r.status}`;
        try { const j = await r.json(); msg = j.message || j.error || msg; } catch { /* */ }
        throw new Error(msg);
      }
      return r.json();
    });
  }

  function toast(msg, type) {
    if (window.Hub && window.Hub.utils && typeof window.Hub.utils.snackbar === 'function') {
      window.Hub.utils.snackbar(msg, type || 4000);
    }
  }

  function today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }

  function formatQty(n) {
    const v = Math.round(n);
    if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
    return String(v);
  }

  function utilStatus(pct) {
    if (pct > 100) return { cls: 'critical', label: 'CRITICAL' };
    if (pct > 85) return { cls: 'warn', label: 'HIGH' };
    return { cls: 'ok', label: 'NORMAL' };
  }

  const COLORS = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
    '#86bcb6', '#8cd17d', '#b6992d', '#499894', '#d37295',
  ];
  const _colorMap = {};
  let _colorIdx = 0;
  function partColor(partNo) {
    if (!_colorMap[partNo]) _colorMap[partNo] = COLORS[_colorIdx++ % COLORS.length];
    return _colorMap[partNo];
  }

  const WEIGHT_IDS = [
    { id: 'ps-w-urgency', key: 'w_urgency', def: 35 },
    { id: 'ps-w-utilize', key: 'w_utilize', def: 20 },
    { id: 'ps-w-primary', key: 'w_primary', def: 15 },
    { id: 'ps-w-pm', key: 'w_pm_risk', def: 15 },
    { id: 'ps-w-changeover', key: 'w_changeover', def: 10 },
    { id: 'ps-w-idle', key: 'w_idle', def: 5 },
  ];

  // ── Drawers & modals ─────────────────────────────────────────────────

  function syncDrawerBackdrop() {
    const backdrop = $('#ps-drawer-backdrop');
    if (!backdrop) return;
    const anyOpen = $('#ps-weights-drawer')?.classList.contains('open')
      || $('#ps-explain-panel')?.classList.contains('open');
    backdrop.classList.toggle('open', !!anyOpen);
  }

  function openDrawer(id) {
    const el = $(id);
    if (el) el.classList.add('open');
    syncDrawerBackdrop();
  }

  function closeDrawer(id) {
    const el = $(id);
    if (el) el.classList.remove('open');
    if (id === '#ps-weights-drawer') {
      _weightsOpen = false;
      $('#ps-weights-toggle')?.classList.remove('active');
    }
    syncDrawerBackdrop();
  }

  function closeAllDrawers() {
    $('#ps-weights-drawer')?.classList.remove('open');
    $('#ps-explain-panel')?.classList.remove('open');
    _weightsOpen = false;
    $('#ps-weights-toggle')?.classList.remove('active');
    syncDrawerBackdrop();
    $('#ps-stats-modal')?.classList.remove('open');
  }

  function toggleWeightsDrawer() {
    _weightsOpen = !_weightsOpen;
    const btn = $('#ps-weights-toggle');
    if (_weightsOpen) {
      openDrawer('#ps-weights-drawer');
      btn?.classList.add('active');
    } else {
      closeDrawer('#ps-weights-drawer');
    }
  }

  function switchBottomTab(tab) {
    $$('#section-production-scheduler .ps-bottom-tab').forEach((b) => {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    $$('#section-production-scheduler .ps-bottom-pane').forEach((p) => {
      p.classList.toggle('active', p.id === `ps-pane-${tab}`);
    });
    if (_bottomPanelMinimized) toggleBottomPanel(false); // expand when switching tabs
  }

  function toggleBottomPanel(forceState) {
    const panel = $('#ps-bottom-panel');
    const btn = $('#ps-bottom-toggle');
    if (!panel) return;
    if (forceState != null) _bottomPanelMinimized = !!forceState;
    else _bottomPanelMinimized = !_bottomPanelMinimized;
    panel.classList.toggle('is-minimized', _bottomPanelMinimized);
    if (btn) {
      btn.innerHTML = _bottomPanelMinimized ? '&#9650;' : '&#9660;';
      btn.setAttribute('aria-label', _bottomPanelMinimized ? 'Maximize panel' : 'Minimize panel');
      btn.title = _bottomPanelMinimized ? 'Maximize panel' : 'Minimize panel';
    }
    try {
      sessionStorage.setItem('ps-bottom-minimized', _bottomPanelMinimized ? '1' : '0');
    } catch { /* */ }
  }

  function setLegendFilter(filter) {
    if (_legendFilter === filter) _legendFilter = null;
    else _legendFilter = filter;
    $$('#section-production-scheduler .ps-legend-filter').forEach((el) => {
      const f = el.dataset.filter;
      const active = _legendFilter === f;
      el.classList.toggle('is-active', active);
      el.classList.toggle('is-dimmed', _legendFilter != null && !active);
      el.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    const wrap = $('#ps-gantt-wrapper');
    if (wrap) {
      wrap.classList.remove('ps-gantt-filter-scheduled', 'ps-gantt-filter-produced');
      if (_legendFilter === 'scheduled') wrap.classList.add('ps-gantt-filter-scheduled');
      if (_legendFilter === 'produced') wrap.classList.add('ps-gantt-filter-produced');
    }
    if (_runData) {
      renderGantt(_runData.assignments || [], _runData.actuals || [], _runData.schedule_from_day || 1);
      renderMachineTable(_runData.kpi?.per_machine || []);
      renderToolTable(_runData.kpi?.per_tool || []);
    }
  }

  function usedMinutesForFilter(row) {
    if (_legendFilter === 'scheduled') return row.scheduled_minutes ?? row.used_minutes ?? 0;
    if (_legendFilter === 'produced') return row.produced_minutes ?? 0;
    return row.total_minutes ?? row.used_minutes ?? 0;
  }

  function enrichUtilRow(row) {
    const used = usedMinutesForFilter(row);
    const avail = row.available_minutes || 0;
    const pct = avail > 0 ? Math.round((used / avail) * 1000) / 10 : 0;
    return { ...row, used_minutes: used, utilization_pct: pct, status: utilStatus(pct).label };
  }

  function sortRows(rows, sortState, cols) {
    const col = cols.find((c) => c.key === sortState.key) || cols[0];
    const dir = sortState.dir === 'desc' ? -1 : 1;
    return [...rows].sort((a, b) => {
      let av = a[col.key];
      let bv = b[col.key];
      if (col.key === 'status') {
        av = utilStatus(a.utilization_pct || 0).label;
        bv = utilStatus(b.utilization_pct || 0).label;
      }
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av ?? '').localeCompare(String(bv ?? '')) * dir;
    });
  }

  function renderSortableHead(theadId, cols, sortState, onSort) {
    const thead = $(theadId);
    if (!thead) return;
    let html = '<tr>';
    cols.forEach((col) => {
      const cls = [
        'sortable',
        sortState.key === col.key ? (sortState.dir === 'asc' ? 'sort-asc' : 'sort-desc') : '',
        col.align === 'right' ? 'num' : '',
      ].filter(Boolean).join(' ');
      const arrow = sortState.key === col.key
        ? (sortState.dir === 'asc' ? '&#9650;' : '&#9660;')
        : '&#8645;';
      html += `<th class="${cls}" data-key="${col.key}">${col.label}<span class="sort-arrow">${arrow}</span></th>`;
    });
    html += '</tr>';
    thead.innerHTML = html;
    thead.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (sortState.key === key) sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
        else { sortState.key = key; sortState.dir = 'asc'; }
        onSort();
      });
    });
  }

  function metricTone(status) {
    if (status === 'good') return 'success';
    if (status === 'warn') return 'warn';
    if (status === 'bad') return 'danger';
    return '';
  }

  function buildKpiCards(kpi) {
    const util = kpi.overall_utilization_pct || 0;
    const ontime = kpi.on_time_pct || 0;
    const rm = kpi.rm_coverage_pct || 0;
    const pm = kpi.pm_risk_tool_count || 0;
    const delay = kpi.total_delay_days || 0;
    const chg = kpi.avg_changeovers_per_machine_day || 0;
    const overflow = kpi.overflow_minutes_total || 0;
    const unsched = kpi.unscheduled_count || 0;
    const schedQty = kpi.total_scheduled || 0;
    const demand = kpi.total_demand || 0;

    return [
      {
        key: 'util', label: 'Utilization', group: 'primary',
        hint: 'Machine minutes used vs total available capacity (scheduled + produced).',
        display: `${util}%`, bar: util,
        status: util > 95 ? 'warn' : util >= 40 ? 'good' : 'neutral',
      },
      {
        key: 'ontime', label: 'On-time delivery', group: 'primary',
        hint: 'Share of dispatch checkpoints met on or before the due day.',
        display: `${ontime}%`, bar: ontime,
        status: ontime >= 80 ? 'good' : ontime >= 50 ? 'warn' : 'bad',
      },
      {
        key: 'rm', label: 'RM coverage',
        hint: 'Scheduled quantity relative to total production demand.',
        display: `${rm}%`, bar: rm,
        status: rm >= 90 ? 'good' : rm >= 70 ? 'warn' : 'bad',
      },
      {
        key: 'pm', label: 'PM risk tools',
        hint: 'Tools at or above 80% of their preventive maintenance interval.',
        display: String(pm),
        status: pm === 0 ? 'good' : pm <= 5 ? 'warn' : 'bad',
      },
      {
        key: 'delay', label: 'Delay days',
        hint: 'Total days late across missed dispatch checkpoints.',
        display: String(Math.round(delay)),
        status: delay === 0 ? 'good' : delay < 100 ? 'warn' : 'bad',
      },
      {
        key: 'chg', label: 'Changeovers / day',
        hint: 'Average part switches per active machine-day.',
        display: String(chg),
        status: chg <= 1 ? 'good' : chg <= 2 ? 'warn' : 'bad',
      },
      {
        key: 'makespan', label: 'Makespan',
        hint: 'Last calendar day with a scheduled assignment.',
        display: kpi.makespan_day ? `Day ${kpi.makespan_day}` : '—',
        status: 'neutral',
      },
      {
        key: 'overflow', label: 'Overflow (min)',
        hint: 'Minutes scheduled beyond standard shift capacity.',
        display: overflow ? `${Math.round(overflow)}` : '0',
        status: overflow === 0 ? 'good' : overflow < 500 ? 'warn' : 'bad',
      },
      {
        key: 'unsched', label: 'Unscheduled parts',
        hint: 'Parts not fully placed due to capacity, tool, or RM limits.',
        display: String(unsched),
        status: unsched === 0 ? 'good' : unsched <= 3 ? 'warn' : 'bad',
      },
      {
        key: 'scheduled', label: 'Scheduled qty',
        hint: 'Total pieces placed on the plan for this run.',
        display: formatQty(schedQty), status: 'neutral',
      },
      {
        key: 'demand', label: 'Total demand',
        hint: 'Sum of effective production quantities required this month.',
        display: formatQty(demand),
        bar: demand > 0 ? Math.min(100, Math.round((schedQty / demand) * 100)) : 0,
        status: 'neutral',
      },
    ];
  }

  function renderMetricCard(card) {
    const tone = metricTone(card.status);
    const bar = card.bar != null
      ? `<div class="ps-metric-bar" role="presentation"><span class="ps-metric-bar-fill ps-metric-bar-fill--${tone || 'neutral'}" style="width:${Math.min(100, card.bar)}%"></span></div>`
      : '';
    const primary = card.group === 'primary' ? ' ps-metric-card--primary' : '';
    return `<article class="ps-metric-card${primary}">
      <div class="ps-metric-label">${card.label}</div>
      <div class="ps-metric-value${tone ? ` ps-metric-value--${tone}` : ''}">${card.display}</div>
      ${bar}
      <p class="ps-metric-hint">${card.hint}</p>
    </article>`;
  }

  function openKpiModal() {
    if (!_runData) {
      toast('Run the scheduler first to view performance summary', 'error');
      return;
    }
    populateKpiModal(_runData.kpi || {});
    renderAnalysis(_runData.analysis || {});
    $('#ps-stats-modal')?.classList.add('open');
  }

  function populateKpiModal(kpi) {
    const { month, year } = getMonthYear();
    const fromDay = kpi.schedule_from_day || _runData?.schedule_from_day || 1;
    const sub = $('#ps-perf-subtitle');
    if (sub) {
      sub.textContent = `${new Date(year, month - 1).toLocaleString('default', { month: 'long', year: 'numeric' })} · scheduling from day ${fromDay}`;
    }
    const cards = buildKpiCards(kpi);
    const dash = $('#ps-kpi-dashboard');
    if (!dash) return;
    const primary = cards.filter((c) => c.group === 'primary');
    const rest = cards.filter((c) => c.group !== 'primary');
    dash.innerHTML =
      `<div class="ps-kpi-primary">${primary.map(renderMetricCard).join('')}</div>` +
      `<div class="ps-kpi-grid">${rest.map(renderMetricCard).join('')}</div>`;
  }

  function initWeightSliders() {
    WEIGHT_IDS.forEach((w) => {
      const el = $(`#${w.id}`);
      if (!el || el.dataset.psBound) return;
      el.dataset.psBound = '1';
      el.addEventListener('input', () => {
        const span = el.closest('.ps-weight-group')?.querySelector('.ps-w-val');
        if (span) span.textContent = (el.value / 100).toFixed(2);
      });
    });
  }

  function getWeights() {
    const out = {};
    WEIGHT_IDS.forEach((w) => {
      const el = $(`#${w.id}`);
      out[w.key] = el ? el.value / 100 : w.def / 100;
    });
    return out;
  }

  function applyWeights(weights) {
    if (!weights || typeof weights !== 'object') return;
    WEIGHT_IDS.forEach((w) => {
      const el = $(`#${w.id}`);
      if (!el) return;
      const raw = weights[w.key];
      if (raw == null) return;
      const pct = Math.round(Number(raw) * 100);
      el.value = Math.min(100, Math.max(0, pct));
      const span = el.closest('.ps-weight-group')?.querySelector('.ps-w-val');
      if (span) span.textContent = (el.value / 100).toFixed(2);
    });
  }

  function resetWeights() {
    applyWeights({
      w_urgency: 0.35, w_utilize: 0.20, w_primary: 0.15,
      w_pm_risk: 0.15, w_changeover: 0.10, w_idle: 0.05,
    });
  }

  function getMonthYear() {
    const v = ($('#ps-month-input') && $('#ps-month-input').value) || today();
    const [y, m] = v.split('-').map(Number);
    return { month: m, year: y };
  }

  function getOverrides() {
    const overrides = _currentScenario?.overrides || {};
    const blockedEl = $('#ps-whatif-blocked');
    if (blockedEl && blockedEl.value.trim()) {
      overrides.blocked_machines = blockedEl.value.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n));
    }
    return overrides;
  }

  // ── Calendar ─────────────────────────────────────────────────────────

  async function loadCalendar() {
    const { month, year } = getMonthYear();
    _calendarData = await api('GET', `/working-calendar/${month}/${year}`);
    renderCalendar();
  }

  function renderCalendar() {
    const grid = $('#ps-calendar-grid');
    if (!grid || !_calendarData) return;
    const days = _calendarData.days || [];
    let html = '<div class="ps-cal-header"><span>Day</span><span>Weekday</span><span>Working</span><span>Hours</span><span>Notes</span></div>';
    days.forEach((d) => {
      const cls = d.is_working ? '' : 'ps-cal-off';
      html += `<div class="ps-cal-row ${cls}" data-date="${d.date}">` +
        `<span>${d.day}</span><span>${d.weekday}</span>` +
        `<span><input type="checkbox" class="ps-cal-working" ${d.is_working ? 'checked' : ''} data-date="${d.date}"></span>` +
        `<span>${d.shift_hours != null ? d.shift_hours : d.default_hours}h</span>` +
        `<span>${d.notes || ''}</span></div>`;
    });
    grid.innerHTML = html;
    grid.querySelectorAll('.ps-cal-working').forEach((cb) => {
      cb.addEventListener('change', async function () {
        try {
          await api('PUT', `/working-calendar/${this.dataset.date}`, { is_working: this.checked });
          await loadCalendar();
        } catch (e) { toast(e.message, 'error'); }
      });
    });
  }

  // ── Scenarios ────────────────────────────────────────────────────────

  async function loadScenarios(selectId) {
    const { month, year } = getMonthYear();
    const data = await api('GET', `/scenarios?month=${month}&year=${year}`);
    const sel = $('#ps-scenario-select');
    if (!sel) return;
    const keep = selectId != null ? String(selectId) : sel.value;
    sel.innerHTML = '<option value="">New scenario</option>';
    (data.scenarios || []).forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.scenario_id;
      opt.textContent = s.name;
      sel.appendChild(opt);
    });
    if (keep) sel.value = keep;
  }

  async function loadScenarioDetails(scenarioId) {
    if (!scenarioId) { _currentScenario = null; resetWeights(); return; }
    try {
      const data = await api('GET', `/scenario/${scenarioId}`);
      _currentScenario = data;
      applyWeights(data.weights);
      if (data.overrides?.blocked_machines) {
        const el = $('#ps-whatif-blocked');
        if (el) el.value = data.overrides.blocked_machines.join(', ');
      }
      renderWhatIfPins();
      toast(`Loaded scenario: ${data.name}`);
    } catch (e) { toast(e.message, 'error'); }
  }

  async function saveScenario() {
    const { month, year } = getMonthYear();
    const sel = $('#ps-scenario-select');
    const sid = sel && sel.value ? parseInt(sel.value, 10) : null;
    const defaultName = _currentScenario?.name || `Scenario ${new Date().toLocaleDateString()}`;
    const name = prompt('Scenario name:', defaultName);
    if (!name) return;
    try {
      const data = await api('POST', '/scenario', {
        scenario_id: sid || undefined, name, month, year,
        weights: getWeights(), overrides: getOverrides(), frozen_days: 0,
      });
      _currentScenario = data;
      await loadScenarios(data.scenario_id);
      applyWeights(data.weights);
      toast('Scenario saved');
    } catch (e) { toast(e.message, 'error'); }
  }

  // ── Run ──────────────────────────────────────────────────────────────

  async function runScheduler() {
    const { month, year } = getMonthYear();
    const sel = $('#ps-scenario-select');
    const sid = sel && sel.value ? parseInt(sel.value, 10) : null;

    const workspace = $('#ps-workspace');
    const empty = $('#ps-empty');
    const loading = $('#ps-loading');
    if (empty) empty.style.display = 'none';
    if (loading) loading.style.display = '';
    if (workspace) workspace.style.display = 'none';
    closeAllDrawers();

    try {
      _runData = await api('POST', '/run', {
        scenario_id: sid || undefined, month, year,
        weights: getWeights(), overrides: getOverrides(),
      });
      if (_runData.status === 'failed') throw new Error(_runData.error || 'Scheduler failed');
      renderResults();
      toast('Schedule generated');
    } catch (e) {
      console.error('Scheduler error:', e);
      if (loading) loading.style.display = 'none';
      if (empty) {
        empty.style.display = '';
        empty.innerHTML = `<p style="color:#ba1a1a">${e.message || 'Scheduler failed'}</p>`;
      }
      toast(e.message, 'error');
    }
  }

  // ── Render ───────────────────────────────────────────────────────────

  function renderResults() {
    const loading = $('#ps-loading');
    if (loading) loading.style.display = 'none';
    if (!_runData) return;

    const workspace = $('#ps-workspace');
    if (workspace) workspace.style.display = '';

    renderScheduleBadge();
    renderGantt(_runData.assignments || [], _runData.actuals || [], _runData.schedule_from_day || 1);
    renderMachineTable(_runData.kpi?.per_machine || []);
    renderToolTable(_runData.kpi?.per_tool || []);
    renderImprovementLog(_runData.improvement_log || []);
    renderUnscheduled(_runData.unscheduled || []);

    const bottom = $('#ps-bottom-panel');
    if (bottom) bottom.style.display = '';
  }

  function renderScheduleBadge() {
    const badge = $('#ps-schedule-badge');
    const text = $('#ps-badge-text');
    if (!badge || !text) return;
    const fromDay = _runData.schedule_from_day || 1;
    if (fromDay > 1) {
      text.innerHTML = `Scheduling from <strong>Day ${fromDay}</strong> (today) — earlier days show actual production`;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  }

  function renderAnalysis(analysis) {
    const list = $('#ps-narrative');
    if (!list) return;
    const narrative = analysis.narrative || [];
    list.innerHTML = narrative.length
      ? narrative.map((n) => `<li>${n}</li>`).join('')
      : '<li class="ps-stats-narrative-empty">No analysis narrative available for this run.</li>';
  }

  function abbrevPart(partNo, maxLen = 11) {
    const s = String(partNo || '');
    if (s.length <= maxLen) return s;
    return `${s.slice(0, maxLen - 1)}…`;
  }

  const GANTT_LAYOUT_FALLBACK = {
    blockH: 48,
    actualH: 54,
    gap: 4,
    cellPad: 10,
    minRow: 62,
  };

  function ganttLayout() {
    const root = document.getElementById('section-production-scheduler');
    if (!root) return { ...GANTT_LAYOUT_FALLBACK };
    const s = getComputedStyle(root);
    const num = (name, fallback) => {
      const v = parseFloat(s.getPropertyValue(name));
      return Number.isFinite(v) ? v : fallback;
    };
    return {
      blockH: num('--ps-gantt-block-h', GANTT_LAYOUT_FALLBACK.blockH),
      actualH: num('--ps-gantt-actual-block-h', GANTT_LAYOUT_FALLBACK.actualH),
      gap: num('--ps-gantt-block-gap', GANTT_LAYOUT_FALLBACK.gap),
      cellPad: num('--ps-gantt-cell-pad', GANTT_LAYOUT_FALLBACK.cellPad),
      minRow: num('--ps-gantt-row-h', GANTT_LAYOUT_FALLBACK.minRow),
    };
  }

  function ganttBlockHeight(isActual, layout) {
    const L = layout || ganttLayout();
    return isActual ? L.actualH : L.blockH;
  }

  function stackHeightForItems(items) {
    if (!items || !items.length) return ganttLayout().minRow;
    const L = ganttLayout();
    let h = L.cellPad;
    items.forEach((a, i) => {
      h += ganttBlockHeight(a.is_actual, L);
      if (i > 0) h += L.gap;
    });
    return Math.max(L.minRow, h);
  }

  function ganttBlockClasses(isActual) {
    let cls = isActual ? 'ps-gantt-block ps-actual' : 'ps-gantt-block';
    if (_legendFilter === 'scheduled') {
      cls += isActual ? ' ps-dimmed' : ' ps-highlighted';
    } else if (_legendFilter === 'produced') {
      cls += isActual ? ' ps-highlighted' : ' ps-dimmed';
    }
    return cls;
  }

  function renderGanttBlock(a) {
    const isActual = a.is_actual;
    const bg = partColor(a.part_no);
    const qty = Math.round(a.qty);
    const title = `${a.part_no}: ${qty.toLocaleString()} pcs, ${Math.round(a.run_minutes)} min${isActual ? ' (Produced)' : ''}`;
    const cls = ganttBlockClasses(isActual);
    const dataAttr = isActual
      ? ` data-actual-idx="${a._actualIdx}"`
      : ` data-assignment-idx="${a._assignIdx}"`;
    if (isActual) {
      return `<button type="button" class="${cls}" title="${title}"${dataAttr}>` +
        `<span class="ps-block-part">${abbrevPart(a.part_no, 18)}</span>` +
        `<span class="ps-block-qty ps-mono">${formatQty(qty)}</span>` +
        `<span class="ps-block-tag">ACTUAL</span></button>`;
    }
    return `<button type="button" class="${cls}" style="background:${bg}" title="${title}"${dataAttr}>` +
      `<span class="ps-block-part">${abbrevPart(a.part_no, 18)}</span>` +
      `<span class="ps-block-qty ps-mono">${formatQty(qty)} pcs</span></button>`;
  }

  function renderGanttCell(dayItems) {
    return `<div class="ps-gantt-stack">${dayItems.map(renderGanttBlock).join('')}</div>`;
  }

  function bindGanttInteractions(gantt) {
    gantt.querySelectorAll('.ps-gantt-block[data-assignment-idx], .ps-gantt-block[data-actual-idx]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const aIdx = el.dataset.assignmentIdx;
        const actIdx = el.dataset.actualIdx;
        if (actIdx != null && actIdx !== '') showProducedDetail(parseInt(actIdx, 10));
        else if (aIdx != null && aIdx !== '') showExplanation(parseInt(aIdx, 10));
      });
    });
  }

  function renderGantt(assignments, actuals, scheduleFromDay) {
    const wrapper = $('#ps-gantt-wrapper');
    const gantt = $('#ps-gantt');
    if (!wrapper || !gantt) return;
    wrapper.style.display = '';

    const actualItems = actuals.map((a, i) => ({ ...a, is_actual: true, _actualIdx: i }));
    const schedItems = assignments.map((a, i) => ({ ...a, is_actual: false, _assignIdx: i }));
    const allItems = [...actualItems, ...schedItems];

    const machines = {};
    let maxDay = 0;
    allItems.forEach((a) => {
      const mid = a.machine_id;
      if (mid && !machines[mid]) machines[mid] = { name: a.machine_name, id: mid };
      if (a.day > maxDay) maxDay = a.day;
    });
    if (maxDay < 28) maxDay = 28;
    const mList = Object.values(machines).sort((a, b) => a.name.localeCompare(b.name));

    const layout = ganttLayout();
    const rowHeights = {};
    mList.forEach((m) => {
      let maxH = layout.minRow;
      for (let d = 1; d <= maxDay; d++) {
        const dayItems = allItems.filter((a) => a.machine_id === m.id && a.day === d);
        if (dayItems.length) maxH = Math.max(maxH, stackHeightForItems(dayItems));
      }
      rowHeights[m.id] = maxH;
    });

    let html = '<table class="ps-gantt-table"><thead><tr>';
    html += '<th class="ps-gantt-machine-col">Machine</th>';
    for (let d = 1; d <= maxDay; d++) {
      let cls = 'ps-gantt-day-col';
      if (d < scheduleFromDay) cls += ' ps-gantt-past';
      else if (d === scheduleFromDay) cls += ' ps-gantt-today';
      html += `<th class="${cls}">${d}</th>`;
    }
    html += '</tr></thead><tbody>';

    mList.forEach((m) => {
      const rowH = rowHeights[m.id];
      html += `<tr style="--ps-gantt-row-h:${rowH}px;height:${rowH}px">`;
      html += `<td class="ps-gantt-machine-cell">${m.name}</td>`;
      for (let d = 1; d <= maxDay; d++) {
        const dayItems = allItems.filter((a) => a.machine_id === m.id && a.day === d);
        let cellCls = 'ps-gantt-cell';
        if (d < scheduleFromDay) cellCls += ' ps-gantt-past';
        else if (d === scheduleFromDay) cellCls += ' ps-gantt-today';
        else if (dayItems.length === 0) cellCls = 'ps-gantt-empty';

        if (dayItems.length === 0) {
          html += `<td class="${cellCls}"></td>`;
        } else {
          html += `<td class="${cellCls}">${renderGanttCell(dayItems)}</td>`;
        }
      }
      html += '</tr>';
    });
    html += '</tbody></table>';
    gantt.innerHTML = html;
    bindGanttInteractions(gantt);
  }

  function renderUtilBar(pct) {
    const color = pct > 85 ? '#e15759' : pct > 60 ? '#f28e2b' : '#59a14f';
    return `<div class="ps-util-cell"><div class="ps-util-bar"><div class="ps-util-fill" style="width:${Math.min(100, pct)}%;background:${color}"></div></div><span class="ps-mono">${pct}%</span></div>`;
  }

  function renderMachineTable(perMachine) {
    const tbody = $('#ps-machine-tbody');
    if (!tbody) return;
    renderSortableHead('#ps-machine-thead', MACHINE_COLS, _machineSort, () => renderMachineTable(perMachine));
    if (!perMachine || perMachine.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${MACHINE_COLS.length}" class="ps-empty-pane">No machine data</td></tr>`;
      return;
    }
    const rows = sortRows(perMachine.map(enrichUtilRow), _machineSort, MACHINE_COLS);
    tbody.innerHTML = rows.map((m) => {
      const pct = m.utilization_pct || 0;
      const st = utilStatus(pct);
      return `<tr>
        <td><strong>${m.machine_name}</strong></td>
        <td class="ps-mono" style="text-align:right">${m.used_minutes}</td>
        <td class="ps-mono" style="text-align:right">${m.available_minutes}</td>
        <td>${renderUtilBar(pct)}</td>
        <td class="ps-mono" style="text-align:right">${m.changeovers || 0}</td>
        <td class="ps-mono" style="text-align:right">${m.overflow_minutes || 0}</td>
        <td><span class="ps-status-pill ${st.cls}">${st.label}</span></td>
      </tr>`;
    }).join('');
  }

  function renderToolTable(perTool) {
    const tbody = $('#ps-tool-tbody');
    if (!tbody) return;
    renderSortableHead('#ps-tool-thead', TOOL_COLS, _toolSort, () => renderToolTable(perTool));
    if (!perTool || perTool.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${TOOL_COLS.length}" class="ps-empty-pane">No tool data</td></tr>`;
      return;
    }
    const rows = sortRows(perTool.map(enrichUtilRow), _toolSort, TOOL_COLS);
    tbody.innerHTML = rows.map((t) => {
      const pct = t.utilization_pct || 0;
      const st = utilStatus(pct);
      const label = t.tool_no || '—';
      return `<tr>
        <td><strong class="ps-mono">${label}</strong></td>
        <td class="ps-mono" style="text-align:right">${t.used_minutes}</td>
        <td class="ps-mono" style="text-align:right">${t.available_minutes}</td>
        <td>${renderUtilBar(pct)}</td>
        <td><span class="ps-status-pill ${st.cls}">${st.label}</span></td>
      </tr>`;
    }).join('');
  }

  function renderImprovementLog(log) {
    const list = $('#ps-improve-list');
    const empty = $('#ps-improve-empty');
    if (!list) return;
    if (!log || log.length === 0) {
      list.innerHTML = '';
      if (empty) empty.style.display = '';
      return;
    }
    if (empty) empty.style.display = 'none';
    list.innerHTML = log.map((l) => `<li>${l}</li>`).join('');
  }

  function renderUnscheduled(items) {
    const tbody = $('#ps-unsched-tbody');
    const empty = $('#ps-unsched-empty');
    const countEl = $('#ps-unsched-count');
    const n = items?.length || 0;
    if (countEl) countEl.textContent = n > 0 ? `(${n})` : '';

    if (!tbody) return;
    if (!items || items.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.style.display = '';
      return;
    }
    if (empty) empty.style.display = 'none';
    tbody.innerHTML = items.map((u) =>
      `<tr><td><strong>${u.part_no}</strong></td><td>${u.part_name || ''}</td>` +
      `<td class="ps-mono" style="text-align:right">${Math.round(u.qty_remaining).toLocaleString()}</td>` +
      `<td>${u.reason}</td></tr>`
    ).join('');
  }

  // ── Explanation panel ────────────────────────────────────────────────

  function showExplanation(idx) {
    const panel = $('#ps-explain-panel');
    if (!panel || !_runData) return;
    const a = (_runData.assignments || [])[idx];
    if (!a) return;
    panel.dataset.mode = 'scheduled';
    panel.dataset.currentIdx = idx;
    delete panel.dataset.actualIdx;
    const title = $('#ps-explain-title');
    if (title) title.textContent = 'Assignment Details';
    const tabs = $('#ps-explain-tabs');
    if (tabs) tabs.style.display = '';
    openDrawer('#ps-explain-panel');
    renderExplainTab('assignment');
  }

  function showProducedDetail(idx) {
    const panel = $('#ps-explain-panel');
    if (!panel || !_runData) return;
    const a = (_runData.actuals || [])[idx];
    if (!a) return;
    panel.dataset.mode = 'produced';
    panel.dataset.actualIdx = idx;
    delete panel.dataset.currentIdx;
    const title = $('#ps-explain-title');
    if (title) title.textContent = 'Assignment Details';
    const tabs = $('#ps-explain-tabs');
    if (tabs) tabs.style.display = '';
    openDrawer('#ps-explain-panel');
    renderExplainTab('assignment');
  }

  function getExplainRecord() {
    const panel = $('#ps-explain-panel');
    if (!panel || !_runData) return null;
    if (panel.dataset.mode === 'produced') {
      const idx = parseInt(panel.dataset.actualIdx, 10);
      const a = (_runData.actuals || [])[idx];
      return a ? { a, isProduced: true } : null;
    }
    const idx = parseInt(panel.dataset.currentIdx, 10);
    const a = (_runData.assignments || [])[idx];
    return a ? { a, isProduced: false } : null;
  }

  function machineDayItems(machineId, day) {
    const sched = (_runData.assignments || [])
      .filter((x) => x.machine_id === machineId && x.day === day)
      .map((x) => ({ ...x, is_actual: false }));
    const produced = (_runData.actuals || [])
      .filter((x) => x.machine_id === machineId && x.day === day)
      .map((x) => ({ ...x, is_actual: true }));
    return [...produced, ...sched];
  }

  function renderExplainTab(tab) {
    const body = $('#ps-explain-body');
    const panel = $('#ps-explain-panel');
    if (!body || !panel || !_runData) return;
    const ctx = getExplainRecord();
    if (!ctx) return;
    const { a, isProduced } = ctx;

    $$('#ps-explain-tabs .ps-explain-tab').forEach((t) => {
      t.classList.toggle('active', t.dataset.tab === tab);
    });

    if (tab === 'assignment') {
      if (isProduced) {
        const qty = Math.round(a.qty || 0);
        body.innerHTML = `
          <div class="ps-explain-summary">
            <span class="ps-status-pill ok" style="margin-bottom:8px;display:inline-block">Produced (actual)</span><br>
            <strong>${a.part_no}</strong>${a.part_name ? ` — ${a.part_name}` : ''}<br>
            Machine: <strong>${a.machine_name || a.machine_id}</strong> &middot; Day: <strong>${a.day}</strong><br>
            ${a.tool_no ? `Tool: <strong class="ps-mono">${a.tool_no}</strong> &middot; ` : ''}
            Qty: <strong class="ps-mono">${qty.toLocaleString()}</strong> &middot;
            Time: <strong class="ps-mono">${Math.round(a.run_minutes || 0)} min</strong>
          </div>
          <p class="ps-section-title">Source</p>
          <p class="ps-hint">Recorded from historical production before or during the scheduling horizon. No optimizer score applies to completed runs.</p>`;
        return;
      }
      const score = a.score || {};
      const breakdown = (score.breakdown || []).map((f) => {
        const barWidth = Math.min(100, Math.abs(f.contribution) * 200);
        const barColor = f.contribution >= 0 ? '#59a14f' : '#e15759';
        return `<div class="ps-explain-factor">
          <div class="ps-explain-factor-head"><span>${f.key}</span><span class="ps-mono">${f.contribution >= 0 ? '+' : ''}${Number(f.contribution).toFixed(3)}</span></div>
          <div class="ps-explain-bar-bg"><div class="ps-explain-bar" style="width:${barWidth}%;background:${barColor}"></div></div>
          <div class="ps-explain-factor-reason">${f.reason}</div>
        </div>`;
      }).join('');
      const alts = (score.alternatives_rejected || []).map((r) =>
        `<div class="ps-explain-alt"><strong>${r.machine || r.machine_id}</strong>: ${r.reason}</div>`
      ).join('') || '<em>None</em>';
      const constraints = Object.entries(a.constraints_checked || {}).map(([k, v]) =>
        `<span class="ps-explain-constraint ${v ? 'ps-ok' : 'ps-fail'}">${k.replace(/_/g, ' ')}</span>`
      ).join(' ');
      body.innerHTML = `
        <div class="ps-explain-summary">
          <strong>${a.part_no}</strong>${a.part_name ? ` — ${a.part_name}` : ''}<br>
          Machine: <strong>${a.machine_name}</strong> &middot; Day: <strong>${a.day}</strong><br>
          ${a.tool_no ? `Tool: <strong class="ps-mono">${a.tool_no}</strong> &middot; ` : ''}
          Qty: <strong class="ps-mono">${Math.round(a.qty).toLocaleString()}</strong> &middot;
          Time: <strong class="ps-mono">${Math.round(a.run_minutes)} min</strong> &middot;
          Strokes: <strong class="ps-mono">${a.strokes}</strong>
        </div>
        <p class="ps-section-title">Score: <span class="ps-mono">${score.total != null ? Number(score.total).toFixed(4) : '—'}</span></p>
        ${breakdown}
        <p class="ps-section-title" style="margin-top:14px">Constraints</p>
        <div>${constraints}</div>
        <p class="ps-section-title" style="margin-top:14px">Other Machines Considered</p>
        ${alts}`;

    } else if (tab === 'machine-day') {
      const dayItems = machineDayItems(a.machine_id, a.day);
      const producedMin = dayItems.filter((x) => x.is_actual).reduce((s, x) => s + (x.run_minutes || 0), 0);
      const schedMin = dayItems.filter((x) => !x.is_actual).reduce((s, x) => s + (x.run_minutes || 0), 0);
      const totalUsed = producedMin + schedMin;
      const pmd = (_runData.kpi?.per_machine_per_day || [])
        .find((d) => d.machine_id === a.machine_id && d.day === a.day);
      const avail = pmd?.available_minutes;
      const utilPct = avail > 0 ? Math.round((totalUsed / avail) * 1000) / 10 : null;
      const otherParts = dayItems.filter((x) => x.part_no !== a.part_no);
      body.innerHTML = `
        <div class="ps-explain-summary">
          <strong>${a.machine_name || a.machine_id}</strong> — Day ${a.day}<br>
          ${avail != null ? `Used: <strong class="ps-mono">${Math.round(totalUsed)} min</strong> / ${avail} min${utilPct != null ? ` (${utilPct}%)` : ''}<br>` : ''}
          Produced: <strong class="ps-mono">${Math.round(producedMin)} min</strong> &middot;
          Scheduled: <strong class="ps-mono">${Math.round(schedMin)} min</strong>
          ${pmd ? `<br>Overflow: <strong class="ps-mono">${pmd.overflow_used} min</strong> &middot; Changeovers: <strong>${pmd.changeovers}</strong>` : ''}
        </div>
        <p class="ps-section-title">All jobs this machine-day</p>
        ${otherParts.length
          ? otherParts.map((o) => {
            const kind = o.is_actual ? 'Produced' : 'Scheduled';
            return `<div class="ps-explain-day-item"><span class="ps-status-pill ${o.is_actual ? 'ok' : 'warn'}">${kind}</span> ` +
              `<strong>${o.part_no}</strong>: <span class="ps-mono">${formatQty(o.qty)}</span> pcs, ${Math.round(o.run_minutes || 0)} min</div>`;
          }).join('')
          : '<em>Only this job on this machine-day.</em>'}`;

    } else if (tab === 'part-trace') {
      const traces = (_runData.analysis?.part_traces || []).filter((t) => t.part_no === a.part_no);
      const trace = traces[0];
      const producedHistory = (_runData.actuals || []).filter((x) => x.part_no === a.part_no);
      const schedHistory = (_runData.assignments || []).filter((x) => x.part_no === a.part_no);
      if (!trace && producedHistory.length === 0 && schedHistory.length === 0) {
        body.innerHTML = '<em>No trace data for this part.</em>';
        return;
      }
      const checkpoints = trace ? (trace.dispatch_checkpoints || []).map((c) => {
        const pill = c.status === 'on-time' ? 'ok' : c.status === 'at-risk' ? 'warn' : 'critical';
        return `<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin:4px 0">
          <span class="ps-status-pill ${pill}">${c.status}</span>
          <span>Day <strong>${c.dispatch_day}</strong>: need <span class="ps-mono">${formatQty(c.required_qty)}</span> &middot; scheduled <span class="ps-mono">${formatQty(c.scheduled_by_day)}</span>
        </div>`;
      }).join('') : '';
      const producedLines = producedHistory.map((x) =>
        `<div class="ps-explain-day-item"><span class="ps-status-pill ok">Produced</span> Day ${x.day} on ${x.machine_name || x.machine_id}: <span class="ps-mono">${formatQty(x.qty)}</span> pcs</div>`
      ).join('');
      const schedLines = schedHistory.map((x) =>
        `<div class="ps-explain-day-item"><span class="ps-status-pill warn">Scheduled</span> Day ${x.day} on ${x.machine_name}: <span class="ps-mono">${formatQty(x.qty)}</span> pcs</div>`
      ).join('');
      body.innerHTML = `
        <div class="ps-explain-summary">
          <strong>${a.part_no}</strong>${a.part_name || trace?.part_name ? ` — ${a.part_name || trace.part_name}` : ''}<br>
          ${trace ? `Total demand: <strong class="ps-mono">${formatQty(trace.total_qty)}</strong> &middot; Scheduled: <strong class="ps-mono">${formatQty(trace.total_scheduled)}</strong>` : ''}
          ${trace?.unscheduled_qty > 0 ? `<br><span style="color:#ba1a1a">Unscheduled: <span class="ps-mono">${formatQty(trace.unscheduled_qty)}</span></span>` : ''}
          ${producedHistory.length ? `<br>Produced entries: <strong>${producedHistory.length}</strong>` : ''}
        </div>
        ${checkpoints ? `<p class="ps-section-title">Dispatch Checkpoints</p>${checkpoints}` : ''}
        ${producedLines ? `<p class="ps-section-title" style="margin-top:14px">Production History</p>${producedLines}` : ''}
        ${schedLines ? `<p class="ps-section-title" style="margin-top:14px">Scheduled Assignments</p>${schedLines}` : ''}`;
    }
  }

  // ── Compare ──────────────────────────────────────────────────────────

  async function loadRunsForCompare() {
    const { month, year } = getMonthYear();
    try {
      const data = await api('GET', `/runs?month=${month}&year=${year}`);
      const runs = data.runs || [];
      ['ps-compare-a', 'ps-compare-b'].forEach((id) => {
        const sel = $(`#${id}`);
        if (!sel) return;
        sel.innerHTML = '<option value="">Select run</option>';
        runs.forEach((r) => {
          const opt = document.createElement('option');
          opt.value = r.run_id;
          opt.textContent = `#${r.run_id} ${r.scenario_name} (${(r.completed_at || '').substring(0, 16)})`;
          sel.appendChild(opt);
        });
      });
    } catch (e) { toast(e.message, 'error'); }
  }

  async function runCompare() {
    const runA = $('#ps-compare-a')?.value;
    const runB = $('#ps-compare-b')?.value;
    if (!runA || !runB) { toast('Select both runs', 'error'); return; }
    try {
      const diff = await api('POST', '/compare', { run_a: parseInt(runA, 10), run_b: parseInt(runB, 10) });
      toast(`Compare: ${diff.added_count} added, ${diff.removed_count} removed, ${diff.changed_count} changed`);
    } catch (e) { toast(e.message, 'error'); }
  }

  // ── What-if ──────────────────────────────────────────────────────────

  function addWhatIf() {
    const part = $('#ps-whatif-part')?.value?.trim();
    const action = $('#ps-whatif-action')?.value;
    const value = $('#ps-whatif-value')?.value?.trim();
    if (!part || !value) { toast('Enter part and value', 'error'); return; }
    if (!_currentScenario) _currentScenario = { overrides: {} };
    const ov = _currentScenario.overrides = _currentScenario.overrides || {};

    if (action === 'boost') {
      ov.boosts = ov.boosts || {};
      ov.boosts[part.toLowerCase()] = parseInt(value, 10);
    } else if (action === 'pin_machine') {
      ov.pins = ov.pins || {};
      ov.pins[part.toLowerCase()] = { ...(ov.pins[part.toLowerCase()] || {}), machine_id: parseInt(value, 10) };
    } else if (action === 'pin_day') {
      ov.pins = ov.pins || {};
      ov.pins[part.toLowerCase()] = { ...(ov.pins[part.toLowerCase()] || {}), day: parseInt(value, 10) };
    }
    renderWhatIfPins();
    $('#ps-whatif-part').value = '';
    $('#ps-whatif-value').value = '';
  }

  function renderWhatIfPins() {
    const el = $('#ps-whatif-pins');
    if (!el) return;
    const ov = _currentScenario?.overrides || {};
    const pins = ov.pins || {};
    const boosts = ov.boosts || {};
    let html = '';
    for (const [pk, pin] of Object.entries(pins)) {
      html += `<div class="ps-whatif-pin"><strong>${pk}</strong>: `;
      if (pin.machine_id) html += `Machine=${pin.machine_id} `;
      if (pin.day) html += `Day=${pin.day} `;
      html += '</div>';
    }
    for (const [pk, boost] of Object.entries(boosts)) {
      html += `<div class="ps-whatif-pin"><strong>${pk}</strong>: Priority +${boost}</div>`;
    }
    el.innerHTML = html || '<p class="ps-hint">No overrides set</p>';
  }

  // ── Event binding ───────────────────────────────────────────────────

  function bindEvents() {
    const monthInput = $('#ps-month-input');
    if (monthInput && !monthInput.dataset.psBound) {
      monthInput.dataset.psBound = '1';
      if (!monthInput.value) monthInput.value = today();
      monthInput.addEventListener('change', () => { _currentScenario = null; loadScenarios(''); });
    }

    const runBtn = $('#ps-run-btn');
    if (runBtn && !runBtn.dataset.psBound) {
      runBtn.dataset.psBound = '1';
      runBtn.addEventListener('click', runScheduler);
    }

    const wToggle = $('#ps-weights-toggle');
    if (wToggle && !wToggle.dataset.psBound) {
      wToggle.dataset.psBound = '1';
      wToggle.addEventListener('click', toggleWeightsDrawer);
    }

    const wClose = $('#ps-weights-close');
    if (wClose && !wClose.dataset.psBound) {
      wClose.dataset.psBound = '1';
      wClose.addEventListener('click', () => closeDrawer('#ps-weights-drawer'));
    }

    const backdrop = $('#ps-drawer-backdrop');
    if (backdrop && !backdrop.dataset.psBound) {
      backdrop.dataset.psBound = '1';
      backdrop.addEventListener('click', closeAllDrawers);
    }

    const calBtn = $('#ps-calendar-btn');
    if (calBtn && !calBtn.dataset.psBound) {
      calBtn.dataset.psBound = '1';
      calBtn.addEventListener('click', () => {
        const p = $('#ps-calendar-panel');
        if (p) { p.style.display = p.style.display === 'none' ? '' : 'none'; loadCalendar(); }
      });
    }

    const compareToggle = $('#ps-compare-toggle');
    if (compareToggle && !compareToggle.dataset.psBound) {
      compareToggle.dataset.psBound = '1';
      compareToggle.addEventListener('click', () => {
        _compareMode = !_compareMode;
        const bar = $('#ps-compare-bar');
        if (bar) bar.style.display = _compareMode ? '' : 'none';
        if (_compareMode) loadRunsForCompare();
      });
    }

    const compareRun = $('#ps-compare-run');
    if (compareRun && !compareRun.dataset.psBound) {
      compareRun.dataset.psBound = '1';
      compareRun.addEventListener('click', runCompare);
    }

    const resetBtn = $('#ps-weights-reset');
    if (resetBtn && !resetBtn.dataset.psBound) {
      resetBtn.dataset.psBound = '1';
      resetBtn.addEventListener('click', resetWeights);
    }

    const saveBtn = $('#ps-save-scenario-btn');
    if (saveBtn && !saveBtn.dataset.psBound) {
      saveBtn.dataset.psBound = '1';
      saveBtn.addEventListener('click', saveScenario);
    }

    const closeExplain = $('#ps-explain-close');
    if (closeExplain && !closeExplain.dataset.psBound) {
      closeExplain.dataset.psBound = '1';
      closeExplain.addEventListener('click', () => closeDrawer('#ps-explain-panel'));
    }

    const scenarioSel = $('#ps-scenario-select');
    if (scenarioSel && !scenarioSel.dataset.psBound) {
      scenarioSel.dataset.psBound = '1';
      scenarioSel.addEventListener('change', () => {
        const id = scenarioSel.value ? parseInt(scenarioSel.value, 10) : null;
        loadScenarioDetails(id);
      });
    }

    const whatifAdd = $('#ps-whatif-add');
    if (whatifAdd && !whatifAdd.dataset.psBound) {
      whatifAdd.dataset.psBound = '1';
      whatifAdd.addEventListener('click', addWhatIf);
    }

    const kpiTrigger = $('#ps-kpi-trigger');
    if (kpiTrigger && !kpiTrigger.dataset.psBound) {
      kpiTrigger.dataset.psBound = '1';
      kpiTrigger.addEventListener('click', openKpiModal);
    }

    $$('#section-production-scheduler .ps-legend-filter').forEach((el) => {
      if (el.dataset.psBound) return;
      el.dataset.psBound = '1';
      el.addEventListener('click', () => setLegendFilter(el.dataset.filter));
    });

    const bottomToggle = $('#ps-bottom-toggle');
    if (bottomToggle && !bottomToggle.dataset.psBound) {
      bottomToggle.dataset.psBound = '1';
      bottomToggle.addEventListener('click', () => toggleBottomPanel());
    }

    const statsClose = $('#ps-stats-close');
    if (statsClose && !statsClose.dataset.psBound) {
      statsClose.dataset.psBound = '1';
      statsClose.addEventListener('click', () => $('#ps-stats-modal')?.classList.remove('open'));
    }

    const statsModal = $('#ps-stats-modal');
    if (statsModal && !statsModal.dataset.psBound) {
      statsModal.dataset.psBound = '1';
      statsModal.addEventListener('click', (e) => {
        if (e.target === statsModal) statsModal.classList.remove('open');
      });
    }

    $$('#section-production-scheduler .ps-bottom-tab').forEach((tab) => {
      if (tab.dataset.psBound) return;
      tab.dataset.psBound = '1';
      tab.addEventListener('click', () => switchBottomTab(tab.dataset.tab));
    });

    $$('#ps-explain-tabs .ps-explain-tab').forEach((tab) => {
      if (tab.dataset.psBound) return;
      tab.dataset.psBound = '1';
      tab.addEventListener('click', () => renderExplainTab(tab.dataset.tab));
    });

    if (!document.body.dataset.psEscBound) {
      document.body.dataset.psEscBound = '1';
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeAllDrawers();
      });
    }
  }

  async function init() {
    if (!$('#section-production-scheduler')) return;

    initWeightSliders();
    bindEvents();

    const monthInput = $('#ps-month-input');
    if (monthInput && !monthInput.value) monthInput.value = today();

    try { await loadScenarios(); } catch (e) { toast(e.message, 'error'); }

    renderWhatIfPins();

    try {
      if (sessionStorage.getItem('ps-bottom-minimized') === '1') toggleBottomPanel(true);
    } catch { /* */ }

    if (!_initialized) { resetWeights(); _initialized = true; }
  }

  return { init };
})();
