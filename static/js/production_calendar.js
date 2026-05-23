/**
 * Production Calendar — standalone SuperGrid view for the production schedule.
 * Separate from dispatch_calendar.js to keep concerns clear.
 */
(function () {
  'use strict';

  const PART_NO = 'Part No';
  const PLANNED_QTY = 'Planned Qty';
  const BALANCE_PRODUCTION = 'Balance Qty';
  const PRODUCED_QTY = 'Produced Qty';
  const COMPLETION_PCT = '% Completion';
  const OPENING_STOCK = 'Opening Stock';
  const ESTIMATED_TIME = 'Estimated Time';
  const WORK_HOURS_PER_DAY = 6;
  const SG_LAYOUT_KEY = 'production_calendar_v7';
  const DEFAULT_ENDPOINT = '/api/production-calendar';

  let _sg = null;
  let _tipEl = null;
  let _tipHideTimer = null;
  let _dayTipEl = null;
  let _dayTipHideTimer = null;
  let _lastPayload = null;
  let _weekFilter = 'full';
  let _legendFilter = '';
  let _loadFn = null;

  // ── Utility helpers ──────────────────────────────────────────────────

  function normalizePartKey(v) {
    return String(v || '').trim().toLowerCase();
  }

  function partNoFromRow(row) {
    if (!row || typeof row !== 'object') return '';
    const prefer = ['Part No', 'part no', 'CO_PARTNO', 'CO_partNo', 'partno', 'PARTNO'];
    for (const k of prefer) {
      if (Object.prototype.hasOwnProperty.call(row, k)) {
        const v = row[k];
        if (v != null && v !== '') return normalizePartKey(v);
      }
    }
    for (const key of Object.keys(row)) {
      if (key === '_pcRowMeta') continue;
      if (/^part\s*no$/i.test(String(key).trim())) return normalizePartKey(row[key]);
    }
    return '';
  }

  function parseDayCol(name) {
    const m = /^day\s+(\d+)$/i.exec(String(name || '').trim());
    return m ? parseInt(m[1], 10) : null;
  }

  function toNum(v) {
    if (v === null || v === undefined || v === '') return 0;
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function fmtNum(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number' && !Number.isFinite(v)) return '';
    const n = typeof v === 'number' ? v : Number(v);
    if (!Number.isFinite(n)) return String(v);
    try { return n.toLocaleString('en-IN', { maximumFractionDigits: 4 }); }
    catch { return String(v); }
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Dispatch / PDD lookup ────────────────────────────────────────────

  function partDayDispatchCell(payload, pk, dayStr) {
    const mapRoot = payload && payload.partDayDispatch;
    if (!mapRoot || pk == null || pk === '') return null;
    let byPart = mapRoot[pk];
    if (!byPart) {
      for (const k of Object.keys(mapRoot)) {
        if (k.toLowerCase() === String(pk).toLowerCase()) { byPart = mapRoot[k]; break; }
      }
    }
    return byPart ? (byPart[dayStr] || null) : null;
  }

  // ── Week filtering ───────────────────────────────────────────────────

  function startOfWeekMonday(d) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    return x;
  }

  function weekRangeContaining(d) {
    const mon = startOfWeekMonday(d);
    return { start: mon, end: new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 6) };
  }

  function nextWeekRange() {
    const mon = startOfWeekMonday(new Date());
    mon.setDate(mon.getDate() + 7);
    return weekRangeContaining(mon);
  }

  function noonTs(y, m, d) { return new Date(y, m - 1, d, 12, 0, 0, 0).getTime(); }

  function dayNumbersInWeek(weekFilter, year, month, daysInMonth) {
    let range;
    if (weekFilter === 'this_week') range = weekRangeContaining(new Date());
    else if (weekFilter === 'next_week') range = nextWeekRange();
    else return new Set();
    const s = noonTs(range.start.getFullYear(), range.start.getMonth() + 1, range.start.getDate());
    const e = noonTs(range.end.getFullYear(), range.end.getMonth() + 1, range.end.getDate());
    const set = new Set();
    for (let d = 1; d <= daysInMonth; d++) { const t = noonTs(year, month, d); if (t >= s && t <= e) set.add(d); }
    return set;
  }

  function filterColumnNames(names, payload, weekFilter) {
    const dim = payload.daysInMonth || 31;
    const daySet = weekFilter === 'full' ? null : dayNumbersInWeek(weekFilter, payload.year, payload.month, dim);
    return names.filter((name) => {
      const d = parseDayCol(name);
      if (d === null) return true;
      if (weekFilter === 'full') return true;
      if (d > dim) return false;
      return daySet && daySet.has(d);
    });
  }

  // ── Legend / status helpers ──────────────────────────────────────────

  const QTY_EPS = 1e-4;

  function rowMatchesLegend(row, meta, legendFilter, payload) {
    if (!legendFilter) return true;
    if (!meta) return false;
    if (meta.isGrandTotal) return true;
    const columns = (payload && payload.columns) || [];
    for (const col of columns) {
      const dayNum = parseDayCol(col);
      if (dayNum === null || toNum(row[col]) <= QTY_EPS) continue;
      const st = partRowProductionStatus(row, dayNum, payload, row[col]);
      if (dayStatusMatchesLegend(st, legendFilter)) return true;
    }
    return false;
  }

  function dayStatusMatchesLegend(status, legendFilter) {
    if (!legendFilter) return true;
    if (!status) return false;
    return status === legendFilter;
  }

  function partRowProductionStatus(row, dayNum, payload, raw) {
    const required = toNum(raw);
    if (required <= QTY_EPS) return '';
    const pk = partNoFromRow(row);
    if (!pk || !payload) return '';
    const produced = producedQtyForScheduleWindow(payload, pk, dayNum);
    if (produced <= QTY_EPS) return 'none';
    if (Math.abs(produced - required) <= QTY_EPS) return 'exact';
    if (produced > required + QTY_EPS) return 'over';
    return 'under';
  }

  function productionStatusClass(status) {
    if (status === 'exact') return 'ti-dc-cell--ok';
    if (status === 'over') return 'ti-dc-cell--dispatched';
    if (status === 'none') return 'ti-dc-cell--short';
    if (status === 'under') return 'ti-dc-cell--partial';
    return '';
  }

  // ── Legend UI ────────────────────────────────────────────────────────

  function syncLegendUi() {
    document.querySelectorAll('#section-production-calendar [data-dc-legend-filter]').forEach((el) => {
      const key = el.getAttribute('data-dc-legend-filter') || '';
      el.classList.toggle('is-active', key === _legendFilter);
      el.setAttribute('aria-pressed', key === _legendFilter ? 'true' : 'false');
    });
  }

  function bindLegendFilter(root) {
    document.querySelectorAll('#section-production-calendar [data-dc-legend-filter]').forEach((el) => {
      if (el.dataset.pcLegendBound === '1') return;
      el.dataset.pcLegendBound = '1';
      el.addEventListener('click', () => {
        const key = el.getAttribute('data-dc-legend-filter') || '';
        _legendFilter = _legendFilter === key ? '' : key;
        syncLegendUi();
        if (_lastPayload && root) renderGrid(root, _lastPayload, _weekFilter);
      });
    });
    syncLegendUi();
  }

  // ── Grid lifecycle ──────────────────────────────────────────────────

  function destroyGrid() {
    if (_sg && typeof _sg.destroy === 'function') { try { _sg.destroy(); } catch {} }
    _sg = null;
  }

  function setLoading(root, on) {
    if (!root) return;
    if (on) {
      destroyGrid();
      root.innerHTML = '<div class="ti-dc-loading"><div class="ti-spinner"></div><span>Loading…</span></div>';
      return;
    }
    const el = root.querySelector('.ti-dc-loading');
    if (el) el.remove();
  }

  function decorateGrandTotal(root) {
    if (!root) return;
    const table = root.querySelector('.sg-table.ti-dc-sg-table');
    if (!table) return;
    const headTh = table.querySelector('thead th');
    if (headTh) root.style.setProperty('--ti-dc-head-h', `${Math.round(headTh.getBoundingClientRect().height)}px`);
    table.querySelectorAll('tbody tr.ti-dc-grand-total-row, tbody tr.sg-sticky-top-row').forEach((tr) => {
      tr.classList.remove('ti-dc-grand-total-row', 'sg-sticky-top-row');
    });
    const stRows = Array.from(table.querySelectorAll('tbody tr[data-sg-sticky-top="1"]'));
    for (const tr of stRows) {
      tr.classList.add('ti-dc-grand-total-row', 'sg-sticky-top-row');
      const top = getComputedStyle(root).getPropertyValue('--ti-dc-head-h').trim() || '42px';
      tr.querySelectorAll('td').forEach((td) => { td.style.top = top; });
      break;
    }
  }

  function ensureGridEnhancements(root) {
    if (!root || root.dataset.pcGridEnhanceBound === '1') return;
    root.dataset.pcGridEnhanceBound = '1';
    new MutationObserver(() => decorateGrandTotal(root)).observe(root, { childList: true, subtree: true });
  }

  // ── Day non-zero counts (for Grand Total label) ─────────────────────

  function buildDayNonZeroCounts(rows) {
    const out = {};
    for (const row of (rows || [])) {
      if (!row || (row._pcRowMeta && row._pcRowMeta.isGrandTotal)) continue;
      for (const key of Object.keys(row)) {
        const dayNum = parseDayCol(key);
        if (dayNum !== null && toNum(row[key]) > 0) out[String(dayNum)] = (out[String(dayNum)] || 0) + 1;
      }
    }
    return out;
  }

  const FIXED_COLUMN_ORDER = [
    PART_NO,
    BALANCE_PRODUCTION,
    PRODUCED_QTY,
    COMPLETION_PCT,
    ESTIMATED_TIME,
  ];

  function sortProductionColumnNames(names) {
    const fixed = [];
    const days = [];
    for (const name of names) {
      if (parseDayCol(name) !== null) days.push(name);
      else fixed.push(name);
    }
    const rank = (n) => {
      const i = FIXED_COLUMN_ORDER.indexOf(n);
      return i === -1 ? 999 : i;
    };
    fixed.sort((a, b) => rank(a) - rank(b));
    days.sort((a, b) => parseDayCol(a) - parseDayCol(b));
    return fixed.concat(days);
  }

  // ── Column builders ─────────────────────────────────────────────────

  function buildColumns(payload, weekFilter) {
    const daysInMonth = payload.daysInMonth || 31;
    const names = sortProductionColumnNames(
      filterColumnNames(payload.columns || [], payload, weekFilter)
    );
    const rowsWithMeta = (payload.rows || []).map((r, i) => ({
      ...r,
      _pcRowMeta: (payload.rowMeta || [])[i] || null,
    }));
    const dayNonZeroCounts = buildDayNonZeroCounts(rowsWithMeta);

    return names.map((name) => {
      const dayNum = parseDayCol(name);
      const col = { key: name, label: name, sortable: true };

      if (dayNum !== null) {
        col.width = weekFilter === 'full' ? 132 : 96;
        col.className = (raw, row) => {
          const meta = row._pcRowMeta;
          const parts = [];
          if (dayNum > daysInMonth) parts.push('ti-dc-cell--out');
          if (meta && meta.isGrandTotal) return parts.join(' ');
          const st = partRowProductionStatus(row, dayNum, payload, raw);
          const cls = productionStatusClass(st);
          if (cls) parts.push(cls);
          if (st && _legendFilter && !dayStatusMatchesLegend(st, _legendFilter)) parts.push('ti-dc-cell--legend-hidden');
          return parts.join(' ');
        };
        col.format = (raw, row) => {
          const text = raw != null && raw !== '' ? fmtNum(raw) : '';
          const meta = row._pcRowMeta;
          if (meta && meta.isGrandTotal) {
            const cnt = dayNonZeroCounts[String(dayNum)] || 0;
            return '<span class="ti-dc-day-cell ti-dc-day-cell--grand-total" data-pc-grand-total="1" data-pc-day="' + dayNum + '">' + text + ' (' + fmtNum(cnt) + ')</span>';
          }
          const pk = partNoFromRow(row);
          if (!pk) return text;
          const st = partRowProductionStatus(row, dayNum, payload, raw);
          if (st && _legendFilter && !dayStatusMatchesLegend(st, _legendFilter)) return '';
          return '<span class="ti-dc-day-cell" data-pc-part="' + escapeHtml(pk) + '" data-pc-day="' + dayNum + '">' + text + '</span>';
        };

      } else if (/^part\s*no$/i.test(String(name).trim())) {
        col.width = 220;
        col.format = (raw, row) => {
          const text = escapeHtml(String(raw ?? ''));
          const meta = row._pcRowMeta;
          const info = meta && meta.partInfo;
          if (!info || (meta && meta.isGrandTotal)) return text;
          return '<span class="ti-pc-part-pill" data-pc-lead-time="' + escapeHtml(String(info.leadTime ?? ''))
            + '" data-pc-operations="' + escapeHtml(String(info.noOfOperations ?? ''))
            + '" data-pc-tools="' + escapeHtml(String(info.tools ?? ''))
            + '" data-pc-spm="' + escapeHtml(String(info.spm ?? ''))
            + '" data-pc-cavity="' + escapeHtml(String(info.cavity ?? ''))
            + '">' + text + '</span>';
        };

      } else if (name === BALANCE_PRODUCTION) {
        col.label = PLANNED_QTY;
        col.width = 160;
        col.align = 'right';
        col.format = (raw) => (raw != null && raw !== '' && toNum(raw) !== 0 ? fmtNum(raw) : '');

      } else if (name === PRODUCED_QTY) {
        col.width = 140;
        col.align = 'right';
        col.format = (raw) => (raw != null && raw !== '' && toNum(raw) !== 0 ? fmtNum(raw) : '');

      } else if (name === COMPLETION_PCT) {
        col.width = 120;
        col.align = 'right';
        col.format = (raw) => {
          if (raw == null || raw === '') return '—';
          const n = Number(raw);
          if (!Number.isFinite(n)) return '—';
          return n.toFixed(1) + '%';
        };

      } else if (name === OPENING_STOCK) {
        col.width = 140;
        col.align = 'right';
        col.format = (raw) => (raw != null && raw !== '' && toNum(raw) !== 0 ? fmtNum(raw) : '');

      } else if (name === ESTIMATED_TIME) {
        col.width = 140;
        col.format = (raw) => {
          if (raw == null || raw === '') return '—';
          const n = Number(raw);
          if (!Number.isFinite(n)) return '—';
          if (n < 1 && n > 0) return (n * WORK_HOURS_PER_DAY).toFixed(1) + ' hrs';
          return n.toFixed(1) + ' days';
        };

      } else {
        col.format = (raw) => (raw != null && raw !== '' ? fmtNum(raw) : '');
      }

      return col;
    });
  }

  // ── Tooltips ────────────────────────────────────────────────────────

  function getTipEl() {
    if (!_tipEl || !document.body.contains(_tipEl)) {
      _tipEl = document.createElement('div');
      _tipEl.className = 'ti-dc-stock-tip';
      _tipEl.setAttribute('role', 'tooltip');
      _tipEl.hidden = true;
      document.body.appendChild(_tipEl);
    }
    return _tipEl;
  }

  function getDayTipEl() {
    if (!_dayTipEl || !document.body.contains(_dayTipEl)) {
      _dayTipEl = document.createElement('div');
      _dayTipEl.className = 'ti-dc-stock-tip ti-dc-day-dispatch-tip';
      _dayTipEl.setAttribute('role', 'tooltip');
      _dayTipEl.hidden = true;
      document.body.appendChild(_dayTipEl);
    }
    return _dayTipEl;
  }

  function positionTip(anchor, tip) {
    const pad = 10, gap = 10;
    tip.hidden = false;
    tip.style.visibility = 'hidden';
    tip.style.left = '0'; tip.style.top = '0';
    const tw = tip.offsetWidth || 280, th = tip.offsetHeight || 120;
    const r = anchor.getBoundingClientRect();
    let left = r.left + r.width / 2 - tw / 2;
    let top = r.bottom + gap;
    left = Math.max(pad, Math.min(left, window.innerWidth - tw - pad));
    if (top + th > window.innerHeight - pad) top = Math.max(pad, r.top - gap - th);
    tip.style.left = Math.round(left) + 'px';
    tip.style.top = Math.round(top) + 'px';
    tip.style.visibility = '';
  }

  function partDailyProductionMap(payload, pk) {
    const mapRoot = payload && payload.partDailyProduction;
    if (!mapRoot || pk == null || pk === '') return null;
    if (mapRoot[pk]) return mapRoot[pk];
    for (const k of Object.keys(mapRoot)) {
      if (k.toLowerCase() === String(pk).toLowerCase()) return mapRoot[k];
    }
    return null;
  }

  function productionScheduleDays(payload, pk) {
    const rows = payload && payload.rows;
    const columns = payload && payload.columns;
    if (!rows || !columns) return [];
    for (let i = 0; i < rows.length; i++) {
      if (partNoFromRow(rows[i]) !== pk) continue;
      const row = rows[i];
      const days = [];
      for (const col of columns) {
        const d = parseDayCol(col);
        if (d !== null && toNum(row[col]) > 0) days.push(d);
      }
      days.sort((a, b) => a - b);
      return days;
    }
    return [];
  }

  function previousProductionScheduleDay(scheduleDays, currentDay) {
    let prev = null;
    for (const d of scheduleDays) {
      if (d < currentDay) prev = d;
      else break;
    }
    return prev;
  }

  function producedQtyForScheduleWindow(payload, pk, currentDay) {
    const current = parseInt(String(currentDay), 10);
    if (!Number.isFinite(current) || current < 1) return 0;
    const scheduleDays = productionScheduleDays(payload, pk);
    const prev = previousProductionScheduleDay(scheduleDays, current);
    const startDay = prev != null ? prev + 1 : 1;
    const daily = partDailyProductionMap(payload, pk);
    if (!daily || startDay > current) return 0;
    let sum = 0;
    for (let d = startDay; d <= current; d++) sum += toNum(daily[String(d)]);
    return sum;
  }

  function partRowDayScheduleQty(payload, pk, dayNum) {
    const rows = payload && payload.rows;
    if (!rows || dayNum == null) return 0;
    const col = 'day ' + dayNum;
    for (let i = 0; i < rows.length; i++) {
      if (partNoFromRow(rows[i]) === pk) return toNum(rows[i][col]);
    }
    return 0;
  }

  function cumulativeProductionRequired(payload, pk, throughDay) {
    const current = parseInt(String(throughDay), 10);
    if (!Number.isFinite(current) || current < 1) return 0;
    const scheduleDays = productionScheduleDays(payload, pk);
    let sum = 0;
    for (const d of scheduleDays) {
      if (d <= current) sum += partRowDayScheduleQty(payload, pk, d);
    }
    return sum;
  }

  function cumulativeProductionProduced(payload, pk, throughDay) {
    const current = parseInt(String(throughDay), 10);
    if (!Number.isFinite(current) || current < 1) return 0;
    const daily = partDailyProductionMap(payload, pk);
    if (!daily) return 0;
    let sum = 0;
    for (let d = 1; d <= current; d++) sum += toNum(daily[String(d)]);
    return sum;
  }

  function cumProdReqForDay(payload, pk, currentDay) {
    const current = parseInt(String(currentDay), 10);
    if (!Number.isFinite(current) || current < 1) return 0;
    const cumReq = cumulativeProductionRequired(payload, pk, current);
    const cumProduced = cumulativeProductionProduced(payload, pk, current);
    return Math.max(0, cumReq - cumProduced);
  }

  function prodBalToDate(payload, pk, currentDay) {
    return cumProdReqForDay(payload, pk, currentDay);
  }

  function buildDayTipHtml(pk, dayStr, payload) {
    let conVal = 0, rmName = 'N/A', rmAvailable = 0;
    if (payload.rows && payload.rowMeta) {
      for (let i = 0; i < payload.rows.length; i++) {
        if (partNoFromRow(payload.rows[i]) === pk) {
          const meta = payload.rowMeta[i];
          if (meta && meta.partInfo) {
            conVal = toNum(meta.partInfo.conVal);
            rmName = meta.partInfo.rmName || 'N/A';
            rmAvailable = toNum(meta.partInfo.rmAvailable);
          }
          break;
        }
      }
    }
    const prodReqToDate = cumulativeProductionRequired(payload, pk, dayStr);
    const produced = producedQtyForScheduleWindow(payload, pk, dayStr);
    const producedToDate = cumulativeProductionProduced(payload, pk, dayStr);
    const prodBal = prodBalToDate(payload, pk, dayStr);
    const rmRequired = conVal > 0 ? fmtNum(prodBal / conVal) : '0';
    return (
      '<div class="ti-dc-stock-tip-inner">' +
      '<div class="ti-dc-stock-tip-head">RM Requirement</div>' +
      '<div class="ti-dc-stock-tip-rows">' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">RM</span><strong class="ti-dc-stock-tip-val">' + escapeHtml(rmName) + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Prod Since Last Req</span><strong class="ti-dc-stock-tip-val">' + fmtNum(produced) + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Prod Req To Date</span><strong class="ti-dc-stock-tip-val">' + fmtNum(prodReqToDate) + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Prod To Date</span><strong class="ti-dc-stock-tip-val">' + fmtNum(producedToDate) + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Prod Bal To Date</span><strong class="ti-dc-stock-tip-val">' + fmtNum(prodBal) + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">RM Required</span><strong class="ti-dc-stock-tip-val">' + rmRequired + '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Total RM Available</span><strong class="ti-dc-stock-tip-val">' + fmtNum(rmAvailable) + '</strong></div>' +
      '</div></div>'
    );
  }

  function ensureDayTooltip(root) {
    if (!root || root.dataset.pcDayTipBound === '1') return;
    root.dataset.pcDayTipBound = '1';
    const tip = getDayTipEl();
    let hoverCell = null;

    function hideSoon() {
      if (_dayTipHideTimer) clearTimeout(_dayTipHideTimer);
      _dayTipHideTimer = setTimeout(() => { tip.hidden = true; tip.innerHTML = ''; hoverCell = null; }, 120);
    }

    root.addEventListener('mouseover', (e) => {
      const cell = e.target.closest && e.target.closest('.ti-dc-day-cell');
      if (!cell || !root.contains(cell) || hoverCell === cell) return;
      hoverCell = cell;
      if (_dayTipHideTimer) clearTimeout(_dayTipHideTimer);
      const dayStr = cell.dataset.pcDay;
      const payload = _lastPayload;
      if (!payload || dayStr == null) return;
      if (cell.dataset.pcGrandTotal === '1') {
        tip.innerHTML = '';
        return;
      }
      const pk = cell.dataset.pcPart;
      if (!pk) return;
      tip.innerHTML = buildDayTipHtml(pk, dayStr, payload);
      tip.hidden = false;
      const stockTip = getTipEl();
      if (stockTip) stockTip.hidden = true;
      requestAnimationFrame(() => positionTip(cell, tip));
    }, false);

    root.addEventListener('mouseout', (e) => {
      const from = e.target.closest && e.target.closest('.ti-dc-day-cell');
      if (!from || !root.contains(from)) return;
      if (e.relatedTarget && from.contains(e.relatedTarget)) return;
      hoverCell = null;
      hideSoon();
    }, false);

    root.addEventListener('mousemove', (e) => {
      const cell = e.target.closest && e.target.closest('.ti-dc-day-cell');
      if (!cell || tip.hidden) return;
      requestAnimationFrame(() => positionTip(cell, tip));
    }, false);
  }

  function ensureStockTooltip(root) {
    if (!root || root.dataset.pcStockTipBound === '1') return;
    root.dataset.pcStockTipBound = '1';
    const tip = getTipEl();
    let hoverPill = null;

    function hideSoon() {
      if (_tipHideTimer) clearTimeout(_tipHideTimer);
      _tipHideTimer = setTimeout(() => { tip.hidden = true; tip.innerHTML = ''; hoverPill = null; }, 120);
    }

    function showTip(pill) {
      if (!pill || hoverPill === pill) return;
      hoverPill = pill;
      if (_tipHideTimer) clearTimeout(_tipHideTimer);
      if (_dayTipEl && document.body.contains(_dayTipEl)) _dayTipEl.hidden = true;

      if (pill.classList.contains('ti-pc-part-pill')) {
        tip.innerHTML =
          '<div class="ti-dc-stock-tip-inner"><div class="ti-dc-stock-tip-head">Part details</div><div class="ti-dc-stock-tip-rows">' +
          '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Lead Time</span><strong class="ti-dc-stock-tip-val">' + escapeHtml(pill.dataset.pcLeadTime || '-') + '</strong></div>' +
          '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">No of Operations</span><strong class="ti-dc-stock-tip-val">' + escapeHtml(pill.dataset.pcOperations || '-') + '</strong></div>' +
          '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Tool(s)</span><strong class="ti-dc-stock-tip-val ti-dc-stock-tip-val--wrap">' + escapeHtml(pill.dataset.pcTools || '-') + '</strong></div>' +
          '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">SPM</span><strong class="ti-dc-stock-tip-val">' + escapeHtml(pill.dataset.pcSpm || '-') + '</strong></div>' +
          '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Cavity</span><strong class="ti-dc-stock-tip-val">' + escapeHtml(pill.dataset.pcCavity || '-') + '</strong></div>' +
          '</div></div>';
      } else {
        return;
      }
      tip.hidden = false;
      requestAnimationFrame(() => positionTip(pill, tip));
    }

    root.addEventListener('mouseover', (e) => {
      const pill = e.target.closest && e.target.closest('.ti-pc-part-pill');
      if (pill && root.contains(pill)) showTip(pill);
    }, false);
    root.addEventListener('mouseout', (e) => {
      const from = e.target.closest && e.target.closest('.ti-pc-part-pill');
      if (!from || !root.contains(from)) return;
      if (e.relatedTarget && from.contains(e.relatedTarget)) return;
      hoverPill = null;
      hideSoon();
    }, false);
    root.addEventListener('mousemove', (e) => {
      const pill = e.target.closest && e.target.closest('.ti-pc-part-pill');
      if (pill && !tip.hidden) requestAnimationFrame(() => positionTip(pill, tip));
    }, false);
  }

  // ── Grid render ─────────────────────────────────────────────────────

  function renderGrid(root, payload, weekFilter) {
    if (typeof SuperGrid === 'undefined' || typeof SuperGrid.create !== 'function') {
      root.innerHTML = '<div class="ti-dc-error">SuperGrid not loaded.</div>';
      return;
    }

    const countEl = document.getElementById('dispatch-calendar-count');
    const searchEl = document.getElementById('dispatch-calendar-search');

    destroyGrid();
    root.innerHTML = '';

    const allRows = (payload.rows || []).map((r, i) => ({
      ...r,
      _pcRowMeta: (payload.rowMeta || [])[i] || null,
      __sgStickyTop: Boolean((payload.rowMeta || [])[i] && (payload.rowMeta || [])[i].isGrandTotal),
    }));
    const rows = allRows.filter((r) =>
      rowMatchesLegend(r, r._pcRowMeta, _legendFilter, payload)
    );

    _sg = SuperGrid.create(root, {
      columns: buildColumns(payload, weekFilter),
      rows,
      options: {
        search: true,
        countLabel: 'rows',
        emptyText: 'No production rows for this month',
        layoutKey: SG_LAYOUT_KEY,
        resizable: true,
        pinnable: true,
        reorderable: true,
        exportBtn: false,
        omitToolbar: true,
        countElement: countEl || undefined,
        searchInputElement: searchEl || undefined,
      },
    });

    const tbl = root.querySelector('.sg-table');
    if (tbl) tbl.classList.add('ti-dc-sg-table', 'ti-excel-table', 'ti-excel-table--original');
    root.classList.add('ti-dc-excel-host');
    ensureGridEnhancements(root);
    decorateGrandTotal(root);

    if (searchEl && searchEl.value) searchEl.dispatchEvent(new Event('input', { bubbles: true }));
    ensureDayTooltip(root);
  }

  // ── Data fetch + KPI ────────────────────────────────────────────────

  async function fetchPayload() {
    const res = await fetch(DEFAULT_ENDPOINT, { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || data.error || 'Failed to load Production Calendar');
    return data;
  }

  function updateSubtitle(el, payload) {
    if (!el || !payload) return;
    const names = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const mo = payload.month;
    el.textContent = (mo >= 1 && mo <= 12 ? names[mo - 1] : String(mo)) + ' ' + payload.year;
  }

  function syncWeekSelect() {
    const sel = document.getElementById('dispatch-calendar-week');
    if (sel && sel.value !== _weekFilter) sel.value = _weekFilter;
  }

  function updateProductionKpi(payload) {
    const plannedEl = document.getElementById('dc-kpi-dispatch-total-so');
    const openingEl = document.getElementById('dc-kpi-dispatch-qty');
    const pctEl = document.getElementById('dc-kpi-dispatch-pct');
    const balanceEl = document.getElementById('dc-kpi-production-balance');
    if (!plannedEl || typeof window.Hub === 'undefined' || !window.Hub.utils) return;

    const kpi = payload && payload.productionKpi;
    const fmt = window.Hub.utils.formatIndian;
    if (kpi) {
      const planned = Number(kpi.planned) || 0;
      const opening = Number(kpi.openingStock) || 0;
      const balance = Number(kpi.balance) || 0;
      const produced = Number(kpi.produced) || 0;
      const pct = kpi.pct != null
        ? Number(kpi.pct)
        : (balance > 0 ? (produced / balance) * 100 : 0);
      plannedEl.textContent = fmt(planned);
      if (openingEl) openingEl.textContent = fmt(opening);
      if (pctEl) pctEl.textContent = (Number.isFinite(pct) ? pct.toFixed(1) : '0') + '%';
      if (balanceEl) balanceEl.textContent = fmt(balance);
      return;
    }

    const rows = payload && payload.rows;
    const rowMeta = payload && payload.rowMeta;
    if (!rows || !rowMeta) return;
    for (let i = 0; i < rows.length; i++) {
      if (rowMeta[i] && rowMeta[i].isGrandTotal) {
        const row = rows[i];
        const planned = toNum(row[PLANNED_QTY]);
        const opening = toNum(row[OPENING_STOCK]);
        const balance = toNum(row[BALANCE_PRODUCTION]);
        const produced = toNum(row[PRODUCED_QTY]);
        const pct = balance > 0 ? (produced / balance) * 100 : 0;
        plannedEl.textContent = fmt(planned);
        if (openingEl) openingEl.textContent = fmt(opening);
        if (pctEl) pctEl.textContent = (Number.isFinite(pct) ? pct.toFixed(1) : '0') + '%';
        if (balanceEl) balanceEl.textContent = fmt(balance);
        break;
      }
    }
  }

  // ── Public API ──────────────────────────────────────────────────────

  const ProductionCalendarPage = {
    init() {
      const root = document.getElementById('dispatch-calendar-root');
      const subtitle = document.getElementById('dispatch-calendar-subtitle');
      const refreshBtn = document.getElementById('dispatch-calendar-refresh');
      if (!root) return;

      bindLegendFilter(root);
      ensureStockTooltip(root);
      ensureDayTooltip(root);

      const weekSel = document.getElementById('dispatch-calendar-week');
      if (weekSel) {
        weekSel.value = _weekFilter;
        weekSel.addEventListener('change', () => {
          if (!weekSel.value || weekSel.value === _weekFilter) return;
          _weekFilter = weekSel.value;
          syncWeekSelect();
          if (_lastPayload) renderGrid(root, _lastPayload, _weekFilter);
        });
      }
      syncWeekSelect();

      const load = async () => {
        setLoading(root, true);
        try {
          const payload = await fetchPayload();
          _lastPayload = payload;
          updateProductionKpi(payload);
          syncLegendUi();
          updateSubtitle(subtitle, payload);
          setLoading(root, false);
          renderGrid(root, payload, _weekFilter);
        } catch (e) {
          console.error(e);
          destroyGrid();
          _lastPayload = null;
          setLoading(root, false);
          root.innerHTML = '<div class="ti-dc-error">' + (e && e.message ? e.message : 'Failed to load') + '</div>';
        }
      };

      if (refreshBtn) refreshBtn.addEventListener('click', () => load());
      _loadFn = load;
      load();
    },
    refresh() {
      if (typeof _loadFn === 'function') _loadFn();
    },
  };

  window.ProductionCalendarPage = ProductionCalendarPage;
})();
