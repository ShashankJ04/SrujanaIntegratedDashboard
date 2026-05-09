/**
 * Dispatch Calendar — Monthly Order + FG/WIP coloring via SuperGrid
 * (sort, search, pin, resize, column reorder — same as other hub Excel-style grids).
 */
(function () {
  'use strict';

  const TOTAL_QTY = 'Total Scheduled Qty';
  const TOTAL_DISPATCHED_QTY = 'Total Dispatched Qty';
  const DISPATCHED_PCT = 'Dispatched %';
  const SG_LAYOUT_KEY = 'dispatch_calendar_v5';

  let _dcSg = null;
  let _dcTipEl = null;
  let _dcTipHideTimer = null;
  let _dcDayTipEl = null;
  let _dcDayTipHideTimer = null;
  let _lastPayload = null;
  let _dcWeekFilter = 'full';
  let _dcLegendFilter = '';
  let _dcVisibleRows = [];

  function normalizePartKey(partNo) {
    return String(partNo || '')
      .trim()
      .toLowerCase();
  }

  /** Same keys as backend `_mo_part_no_raw` — row dict keys vary by driver/API casing. */
  function partNoFromRow(row) {
    if (!row || typeof row !== 'object') return '';
    const prefer = [
      'Part No',
      'part no',
      'CO_PARTNO',
      'CO_partNo',
      'partno',
      'PARTNO',
    ];
    for (let i = 0; i < prefer.length; i++) {
      const k = prefer[i];
      if (Object.prototype.hasOwnProperty.call(row, k)) {
        const v = row[k];
        if (v != null && v !== '') return normalizePartKey(v);
      }
    }
    const keys = Object.keys(row);
    for (let j = 0; j < keys.length; j++) {
      const key = keys[j];
      if (key === '_dcRowMeta') continue;
      if (/^part\s*no$/i.test(String(key).trim())) {
        return normalizePartKey(row[key]);
      }
    }
    return '';
  }

  function partDayDispatchCell(payload, pk, dayStr) {
    const mapRoot = payload && payload.partDayDispatch;
    if (!mapRoot || pk == null || pk === '') return null;
    let byPart = mapRoot[pk];
    if (!byPart) {
      const keys = Object.keys(mapRoot);
      for (let i = 0; i < keys.length; i++) {
        if (keys[i].toLowerCase() === String(pk).toLowerCase()) {
          byPart = mapRoot[keys[i]];
          break;
        }
      }
    }
    if (!byPart) return null;
    return byPart[dayStr] || null;
  }

  /** Grand Total row day cells: color by aggregate dispatched vs Grand Total scheduled for that day */
  function grandTotalDayDispatchClass(dayNum, payload) {
    const dd = payload.dayDispatch;
    if (!dd) return '';
    const sch = toNum(dd.scheduled && dd.scheduled[String(dayNum)]);
    const dis = toNum(dd.dispatched && dd.dispatched[String(dayNum)]);
    const eps = 1e-9;
    if (sch <= eps) return '';
    if (dis + eps >= sch) return 'ti-dc-cell--ok';
    if (dis > eps) return 'ti-dc-cell--partial';
    return 'ti-dc-cell--short';
  }

  function buildDayDispatchTipHtml(pk, dayStr, payload) {
    const cell = partDayDispatchCell(payload, pk, dayStr);
    const scheduled = cell ? toNum(cell.scheduledQty) : 0;
    const dispatched = cell ? toNum(cell.dispatched) : 0;
    const eps = 1e-9;
    let pctLabel = '–';
    if (scheduled > eps) {
      pctLabel = `${((dispatched / scheduled) * 100).toFixed(1)}%`;
    }
    let status = 'No schedule';
    if (scheduled > eps) {
      if (dispatched + eps >= scheduled) status = 'Fully dispatched';
      else if (dispatched > eps) status = 'Partially dispatched';
      else status = 'Not dispatched';
    }
    return (
      '<div class="ti-dc-stock-tip-inner">' +
      '<div class="ti-dc-stock-tip-head">Dispatch vs schedule</div>' +
      '<div class="ti-dc-stock-tip-rows">' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Scheduled</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      fmtNum(scheduled) +
      '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Dispatched</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      fmtNum(dispatched) +
      '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">% of schedule</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      pctLabel +
      '</strong></div>' +
      '<div class="ti-dc-day-tip-status">' +
      escapeHtml(status) +
      '</div></div></div>'
    );
  }

  /** Same tooltip layout as part rows, sourced from aggregate dayDispatch (Grand Total row cells). */
  function buildGrandTotalDayDispatchTipHtml(dayStr, payload) {
    const dd = payload.dayDispatch;
    const scheduled = dd ? toNum(dd.scheduled && dd.scheduled[dayStr]) : 0;
    const dispatched = dd ? toNum(dd.dispatched && dd.dispatched[dayStr]) : 0;
    const pctStored = dd && dd.pct ? dd.pct[dayStr] : null;
    const eps = 1e-9;
    let pctLabel = '–';
    if (scheduled > eps) {
      if (pctStored !== null && pctStored !== undefined) {
        pctLabel = `${Number(pctStored).toFixed(1)}%`;
      } else {
        pctLabel = `${((dispatched / scheduled) * 100).toFixed(1)}%`;
      }
    }
    let status = 'No schedule';
    if (scheduled > eps) {
      if (dispatched + eps >= scheduled) status = 'Fully dispatched';
      else if (dispatched > eps) status = 'Partially dispatched';
      else status = 'Not dispatched';
    }
    return (
      '<div class="ti-dc-stock-tip-inner">' +
      '<div class="ti-dc-stock-tip-head">Dispatch vs schedule</div>' +
      '<div class="ti-dc-stock-tip-rows">' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Scheduled</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      fmtNum(scheduled) +
      '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">Dispatched</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      fmtNum(dispatched) +
      '</strong></div>' +
      '<div class="ti-dc-stock-tip-row"><span class="ti-dc-stock-tip-label">% of schedule</span>' +
      '<strong class="ti-dc-stock-tip-val">' +
      pctLabel +
      '</strong></div>' +
      '<div class="ti-dc-day-tip-status">' +
      escapeHtml(status) +
      '</div></div></div>'
    );
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
    try {
      return n.toLocaleString('en-IN', { maximumFractionDigits: 4 });
    } catch {
      return String(v);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** Monday-based week containing `d` (local timezone). */
  function startOfWeekMonday(d) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const day = x.getDay();
    const diff = (day + 6) % 7;
    x.setDate(x.getDate() - diff);
    return x;
  }

  function weekRangeContaining(d) {
    const mon = startOfWeekMonday(d);
    const sun = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 6);
    return { start: mon, end: sun };
  }

  function nextWeekRangeFromToday() {
    const thisRange = weekRangeContaining(new Date());
    const nextMonday = new Date(thisRange.start);
    nextMonday.setDate(nextMonday.getDate() + 7);
    return weekRangeContaining(nextMonday);
  }

  function noonTs(y, month1, day) {
    return new Date(y, month1 - 1, day, 12, 0, 0, 0).getTime();
  }

  /** Calendar day numbers within displayed month that fall in the selected week (Mon–Sun). */
  function getDayNumbersInMonthForWeekFilter(weekFilter, year, month, daysInMonth) {
    let range;
    if (weekFilter === 'this_week') {
      range = weekRangeContaining(new Date());
    } else if (weekFilter === 'next_week') {
      range = nextWeekRangeFromToday();
    } else {
      return new Set();
    }

    const startTs = noonTs(
      range.start.getFullYear(),
      range.start.getMonth() + 1,
      range.start.getDate()
    );
    const endTs = noonTs(
      range.end.getFullYear(),
      range.end.getMonth() + 1,
      range.end.getDate()
    );
    const set = new Set();
    for (let d = 1; d <= daysInMonth; d++) {
      const t = noonTs(year, month, d);
      if (t >= startTs && t <= endTs) set.add(d);
    }
    return set;
  }

  function filterColumnNames(names, payload, weekFilter) {
    const dim = payload.daysInMonth || 31;
    const y = payload.year;
    const mo = payload.month;
    const daySet =
      weekFilter === 'full' ? null : getDayNumbersInMonthForWeekFilter(weekFilter, y, mo, dim);

    return names.filter((name) => {
      const d = parseDayCol(name);
      if (d === null) return true;
      if (weekFilter === 'full') return true;
      if (d > dim) return false;
      return daySet && daySet.has(d);
    });
  }

  function rowMatchesLegendFilter(row, meta, payload, legendFilter) {
    if (!legendFilter) return true;
    if (!meta) return false;
    if (meta.isGrandTotal) return true;
    const dayStatus = meta.dayStatus || {};
    const targetStatus =
      legendFilter === 'ok'
        ? 'full'
        : legendFilter === 'partial'
          ? 'partial'
          : legendFilter === 'short'
            ? 'short'
            : legendFilter === 'dispatched'
              ? 'dispatched'
              : '';
    if (!targetStatus) return true;
    const keys = Object.keys(dayStatus);
    for (let i = 0; i < keys.length; i++) {
      const st = dayStatus[keys[i]] && dayStatus[keys[i]].status;
      if (st === targetStatus) return true;
    }
    return false;
  }

  function dayStatusMatchesLegendFilter(status, legendFilter) {
    if (!legendFilter) return true;
    if (!status) return false;
    if (legendFilter === 'ok') return status === 'ok' || status === 'full';
    if (legendFilter === 'partial') return status === 'partial';
    if (legendFilter === 'short') return status === 'short';
    if (legendFilter === 'dispatched') return status === 'dispatched';
    return true;
  }

  function grandTotalDayStatus(dayNum, payload) {
    const dd = payload.dayDispatch;
    if (!dd) return '';
    const sch = toNum(dd.scheduled && dd.scheduled[String(dayNum)]);
    const dis = toNum(dd.dispatched && dd.dispatched[String(dayNum)]);
    const eps = 1e-9;
    if (sch <= eps) return '';
    if (dis + eps >= sch) return 'ok';
    if (dis > eps) return 'partial';
    return 'short';
  }

  function partRowDayStatus(row, dayNum, payload, daysInMonth, raw) {
    const meta = row && row._dcRowMeta;
    if (!meta || dayNum > daysInMonth) return '';
    const pk = partNoFromRow(row);
    const eps = 1e-9;
    if (pk) {
      const dcell = partDayDispatchCell(payload, pk, String(dayNum));
      const sched = dcell ? toNum(dcell.scheduledQty) : 0;
      const disp = dcell ? toNum(dcell.dispatched) : 0;
      if (sched > eps && disp + eps >= sched) return 'dispatched';
    }
    const q = toNum(raw);
    if (q !== 0 && meta.dayStatus && meta.dayStatus[String(dayNum)]) {
      return meta.dayStatus[String(dayNum)].status || '';
    }
    return '';
  }

  function syncLegendFilterUi() {
    const items = document.querySelectorAll('[data-dc-legend-filter]');
    for (let i = 0; i < items.length; i++) {
      const el = items[i];
      const key = el.getAttribute('data-dc-legend-filter') || '';
      const active = key === _dcLegendFilter;
      el.classList.toggle('is-active', active);
      el.setAttribute('aria-pressed', active ? 'true' : 'false');
    }
  }

  function bindLegendFilter(root) {
    const items = document.querySelectorAll('[data-dc-legend-filter]');
    if (!items.length) return;
    for (let i = 0; i < items.length; i++) {
      const el = items[i];
      if (el.dataset.dcLegendBound === '1') continue;
      el.dataset.dcLegendBound = '1';
      el.addEventListener('click', () => {
        const key = el.getAttribute('data-dc-legend-filter') || '';
        _dcLegendFilter = _dcLegendFilter === key ? '' : key;
        syncLegendFilterUi();
        if (_lastPayload && root) renderSuperGrid(root, _lastPayload, _dcWeekFilter);
      });
    }
    syncLegendFilterUi();
  }

  function destroyGrid() {
    if (_dcSg && typeof _dcSg.destroy === 'function') {
      try {
        _dcSg.destroy();
      } catch (e) {
        /* ignore */
      }
    }
    _dcSg = null;
  }

  function decorateGrandTotalRow(root) {
    if (!root) return;
    const table = root.querySelector('.sg-table.ti-dc-sg-table');
    if (!table) return;
    const headTh = table.querySelector('thead th');
    if (headTh) {
      root.style.setProperty('--ti-dc-head-h', `${Math.round(headTh.getBoundingClientRect().height)}px`);
    }
    table.querySelectorAll('tbody tr.ti-dc-grand-total-row, tbody tr.sg-sticky-top-row').forEach((tr) => {
      tr.classList.remove('ti-dc-grand-total-row');
      tr.classList.remove('sg-sticky-top-row');
    });
    const bodyRows = Array.from(table.querySelectorAll('tbody tr[data-sg-sticky-top="1"]'));
    for (let i = 0; i < bodyRows.length; i++) {
      const tr = bodyRows[i];
      tr.classList.add('ti-dc-grand-total-row');
      tr.classList.add('sg-sticky-top-row');
      const topPx = getComputedStyle(root).getPropertyValue('--ti-dc-head-h').trim() || '42px';
      tr.querySelectorAll('td').forEach((td) => {
        td.style.top = topPx;
      });
      break;
    }
  }

  function buildDayNonZeroCounts(rows) {
    const out = {};
    const dataRows = Array.isArray(rows) ? rows : [];
    for (let i = 0; i < dataRows.length; i++) {
      const row = dataRows[i];
      if (!row || (row._dcRowMeta && row._dcRowMeta.isGrandTotal)) continue;
      const keys = Object.keys(row);
      for (let k = 0; k < keys.length; k++) {
        const key = keys[k];
        const dayNum = parseDayCol(key);
        if (dayNum === null) continue;
        if (toNum(row[key]) > 0) {
          out[String(dayNum)] = (out[String(dayNum)] || 0) + 1;
        }
      }
    }
    return out;
  }

  function ensureGridEnhancements(root) {
    if (!root || root.dataset.dcGridEnhanceBound === '1') return;
    root.dataset.dcGridEnhanceBound = '1';
    const observer = new MutationObserver(() => {
      decorateGrandTotalRow(root);
    });
    observer.observe(root, { childList: true, subtree: true });
  }

  function setLoading(root, loading) {
    if (!root) return;
    if (loading) {
      destroyGrid();
      root.innerHTML = '';
      const el = document.createElement('div');
      el.className = 'ti-dc-loading';
      el.innerHTML = '<div class="ti-spinner"></div><span>Loading…</span>';
      root.appendChild(el);
      return;
    }
    root.querySelector('.ti-dc-loading')?.remove();
  }

  function buildColumns(payload, weekFilter) {
    const daysInMonth = payload.daysInMonth || 31;
    const names = filterColumnNames(payload.columns || [], payload, weekFilter);
    const rowsWithMeta = (payload.rows || []).map((r, i) => ({
      ...r,
      _dcRowMeta: (payload.rowMeta || [])[i] || null,
    }));
    const dayNonZeroCounts = buildDayNonZeroCounts(rowsWithMeta);
    return names.map((name) => {
      const dayNum = parseDayCol(name);
      const col = {
        key: name,
        label: name,
        sortable: true,
      };

      if (dayNum !== null) {
        /* Full month: wide enough for two-line headers ("DAY N"); week views slightly narrower */
        col.width = weekFilter === 'full' ? 132 : 96;
        col.className = (raw, row) => {
          const meta = row._dcRowMeta;
          const parts = [];
          if (dayNum > daysInMonth) parts.push('ti-dc-cell--out');
          if (meta && meta.isGrandTotal) {
            const gtStatus = grandTotalDayStatus(dayNum, payload);
            if (gtStatus) {
              if (gtStatus === 'ok') parts.push('ti-dc-cell--ok');
              else if (gtStatus === 'partial') parts.push('ti-dc-cell--partial');
              else if (gtStatus === 'short') parts.push('ti-dc-cell--short');
            }
            return parts.filter(Boolean).join(' ');
          }
          const st = partRowDayStatus(row, dayNum, payload, daysInMonth, raw);
          if (st === 'full') parts.push('ti-dc-cell--ok');
          else if (st === 'partial') parts.push('ti-dc-cell--partial');
          else if (st === 'dispatched') parts.push('ti-dc-cell--dispatched');
          else if (st === 'short') parts.push('ti-dc-cell--short');
          if (st && _dcLegendFilter && !dayStatusMatchesLegendFilter(st, _dcLegendFilter)) {
            parts.push('ti-dc-cell--legend-hidden');
          }
          return parts.join(' ');
        };
        col.format = (raw, row) => {
          const text = raw != null && raw !== '' ? fmtNum(raw) : '';
          const meta = row._dcRowMeta;
          if (meta && meta.isGrandTotal) {
            const dayCount = dayNonZeroCounts[String(dayNum)] || 0;
            const gtLabel = `${text} (${fmtNum(dayCount)})`;
            return (
              '<span class="ti-dc-day-cell ti-dc-day-cell--grand-total" data-dc-grand-total="1" data-dc-day="' +
              String(dayNum) +
              '">' +
              gtLabel +
              '</span>'
            );
          }
          const pk = partNoFromRow(row);
          if (!pk) return text;
          const st = partRowDayStatus(row, dayNum, payload, daysInMonth, raw);
          if (st && _dcLegendFilter && !dayStatusMatchesLegendFilter(st, _dcLegendFilter)) {
            return '';
          }
          return (
            '<span class="ti-dc-day-cell" data-dc-part="' +
            escapeHtml(pk) +
            '" data-dc-day="' +
            String(dayNum) +
            '">' +
            text +
            '</span>'
          );
        };
      } else if (name === TOTAL_QTY) {
        col.width = 152;
        col.className = (raw, row) => (row._dcRowMeta ? 'ti-dc-total-cell' : '');
        col.format = (raw, row) => {
          const text = raw != null && raw !== '' ? fmtNum(raw) : '';
          const meta = row._dcRowMeta;
          if (!meta) return text;
          let fg = meta.stockFg;
          let wip = meta.stockWip;
          if (meta.isGrandTotal && meta.grandTotalStock) {
            fg = meta.grandTotalStock.stockFg;
            wip = meta.grandTotalStock.stockWip;
          }
          return (
            '<span class="ti-dc-total-pill" data-dc-fg="' +
            String(fg) +
            '" data-dc-wip="' +
            String(wip) +
            '">' +
            text +
            '</span>'
          );
        };
      } else if (name === TOTAL_DISPATCHED_QTY) {
        col.width = 168;
        col.format = (raw) => (raw != null && raw !== '' ? fmtNum(raw) : '');
      } else if (name === DISPATCHED_PCT) {
        col.width = 132;
        col.format = (raw) => {
          const n = toNum(raw);
          if (raw == null || raw === '' || !Number.isFinite(n)) return '';
          return `${n.toFixed(2)}%`;
        };
      } else if (name && /^part\s*no$/i.test(String(name).trim())) {
        col.width = 220;
        col.format = (raw) => escapeHtml(String(raw ?? ''));
      } else {
        col.format = (raw) => (raw != null && raw !== '' ? fmtNum(raw) : '');
      }
      return col;
    });
  }

  function syncSearchAfterGridCreate() {
    const searchEl = document.getElementById('dispatch-calendar-search');
    if (searchEl && searchEl.value) {
      searchEl.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function renderSuperGrid(root, payload, weekFilter) {
    if (typeof SuperGrid === 'undefined' || typeof SuperGrid.create !== 'function') {
      root.innerHTML =
        '<div class="ti-dc-error">SuperGrid is not loaded. Ensure supergrid.js is included before dispatch_calendar.js.</div>';
      return;
    }

    const countEl = document.getElementById('dispatch-calendar-count');
    const searchEl = document.getElementById('dispatch-calendar-search');

    destroyGrid();
    root.innerHTML = '';

    const allRows = (payload.rows || []).map((r, i) => ({
      ...r,
      _dcRowMeta: (payload.rowMeta || [])[i] || null,
      __sgStickyTop: Boolean((payload.rowMeta || [])[i] && (payload.rowMeta || [])[i].isGrandTotal),
    }));
    const rows = allRows.filter((r) =>
      rowMatchesLegendFilter(r, r._dcRowMeta, payload, _dcLegendFilter)
    );
    _dcVisibleRows = rows;

    const columns = buildColumns(payload, weekFilter);

    _dcSg = SuperGrid.create(root, {
      columns,
      rows,
      options: {
        search: true,
        countLabel: 'rows',
        emptyText: 'No schedule rows for this month',
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
    if (tbl) {
      tbl.classList.add('ti-dc-sg-table', 'ti-excel-table', 'ti-excel-table--original');
    }
    root.classList.add('ti-dc-excel-host');
    ensureGridEnhancements(root);
    decorateGrandTotalRow(root);

    syncSearchAfterGridCreate();
    ensureDayTooltipDelegation(root);
  }

  function getDcDayTipEl() {
    if (!_dcDayTipEl || !document.body.contains(_dcDayTipEl)) {
      _dcDayTipEl = document.createElement('div');
      _dcDayTipEl.className = 'ti-dc-stock-tip ti-dc-day-dispatch-tip';
      _dcDayTipEl.setAttribute('role', 'tooltip');
      _dcDayTipEl.hidden = true;
      document.body.appendChild(_dcDayTipEl);
    }
    return _dcDayTipEl;
  }

  function ensureDayTooltipDelegation(root) {
    if (!root || root.dataset.dcDayTipDelegation === '1') return;
    root.dataset.dcDayTipDelegation = '1';

    const tip = getDcDayTipEl();
    let hoverCell = null;

    function hideSoon() {
      if (_dcDayTipHideTimer) clearTimeout(_dcDayTipHideTimer);
      _dcDayTipHideTimer = setTimeout(() => {
        tip.hidden = true;
        tip.innerHTML = '';
        hoverCell = null;
      }, 120);
    }

    root.addEventListener(
      'mouseover',
      (e) => {
        const cell = e.target.closest && e.target.closest('.ti-dc-day-cell');
        if (!cell || !root.contains(cell)) return;
        if (hoverCell === cell) return;
        hoverCell = cell;
        if (_dcDayTipHideTimer) clearTimeout(_dcDayTipHideTimer);
        const dayStr = cell.dataset.dcDay;
        const payload = _lastPayload;
        if (!payload || dayStr == null) return;
        if (cell.dataset.dcGrandTotal === '1') {
          tip.innerHTML = buildGrandTotalDayDispatchTipHtml(dayStr, payload);
        } else {
          const pk = cell.dataset.dcPart;
          if (pk == null || pk === '') return;
          tip.innerHTML = buildDayDispatchTipHtml(pk, dayStr, payload);
        }
        tip.hidden = false;
        const stockTip = getDcTipEl();
        if (stockTip) {
          stockTip.hidden = true;
        }
        requestAnimationFrame(() => positionDcTip(cell, tip));
      },
      false
    );

    root.addEventListener(
      'mouseout',
      (e) => {
        const from = e.target.closest && e.target.closest('.ti-dc-day-cell');
        if (!from || !root.contains(from)) return;
        const to = e.relatedTarget;
        if (to && from.contains(to)) return;
        hoverCell = null;
        hideSoon();
      },
      false
    );

    root.addEventListener(
      'mousemove',
      (e) => {
        const cell = e.target.closest && e.target.closest('.ti-dc-day-cell');
        if (!cell || tip.hidden) return;
        requestAnimationFrame(() => positionDcTip(cell, tip));
      },
      false
    );
  }

  /**
   * Delegated listeners on #dispatch-calendar-root survive SuperGrid tbody refresh (sort/pin/resize).
   */
  function ensureStockTooltipDelegation(root) {
    if (!root || root.dataset.dcStockTipDelegation === '1') return;
    root.dataset.dcStockTipDelegation = '1';

    const tip = getDcTipEl();
    let hoverPill = null;

    function hideSoon() {
      if (_dcTipHideTimer) clearTimeout(_dcTipHideTimer);
      _dcTipHideTimer = setTimeout(() => {
        tip.hidden = true;
        tip.innerHTML = '';
        hoverPill = null;
      }, 120);
    }

    function showTipForPill(pill) {
      if (!pill || hoverPill === pill) return;
      hoverPill = pill;
      if (_dcTipHideTimer) clearTimeout(_dcTipHideTimer);
      if (_dcDayTipEl && document.body.contains(_dcDayTipEl)) {
        _dcDayTipEl.hidden = true;
      }
      const fg = pill.dataset.dcFg;
      const wip = pill.dataset.dcWip;
      tip.innerHTML =
        '<div class="ti-dc-stock-tip-inner">' +
        '<div class="ti-dc-stock-tip-head">Stock availability</div>' +
        '<div class="ti-dc-stock-tip-rows">' +
        '<div class="ti-dc-stock-tip-row">' +
        '<span class="ti-dc-stock-tip-label">FG (Stock)</span>' +
        '<strong class="ti-dc-stock-tip-val">' +
        fmtNum(fg) +
        '</strong></div>' +
        '<div class="ti-dc-stock-tip-row">' +
        '<span class="ti-dc-stock-tip-label">WIP (other stages)</span>' +
        '<strong class="ti-dc-stock-tip-val">' +
        fmtNum(wip) +
        '</strong></div></div></div>';
      tip.hidden = false;
      requestAnimationFrame(() => positionDcTip(pill, tip));
    }

    root.addEventListener(
      'mouseover',
      (e) => {
        const pill = e.target.closest && e.target.closest('.ti-dc-total-pill');
        if (!pill || !root.contains(pill)) return;
        showTipForPill(pill);
      },
      false
    );

    root.addEventListener(
      'mouseout',
      (e) => {
        const from = e.target.closest && e.target.closest('.ti-dc-total-pill');
        if (!from || !root.contains(from)) return;
        const to = e.relatedTarget;
        if (to && from.contains(to)) return;
        hoverPill = null;
        hideSoon();
      },
      false
    );

    root.addEventListener(
      'mousemove',
      (e) => {
        const pill = e.target.closest && e.target.closest('.ti-dc-total-pill');
        if (!pill || tip.hidden) return;
        requestAnimationFrame(() => positionDcTip(pill, tip));
      },
      false
    );
  }

  function getDcTipEl() {
    if (!_dcTipEl || !document.body.contains(_dcTipEl)) {
      _dcTipEl = document.createElement('div');
      _dcTipEl.className = 'ti-dc-stock-tip';
      _dcTipEl.setAttribute('role', 'tooltip');
      _dcTipEl.hidden = true;
      document.body.appendChild(_dcTipEl);
    }
    return _dcTipEl;
  }

  function positionDcTip(anchor, tip) {
    const pad = 10;
    const gap = 10;
    tip.hidden = false;
    tip.style.visibility = 'hidden';
    tip.style.left = '0';
    tip.style.top = '0';
    const tw = tip.offsetWidth || 280;
    const th = tip.offsetHeight || 120;
    const r = anchor.getBoundingClientRect();
    let left = r.left + r.width / 2 - tw / 2;
    let top = r.bottom + gap;
    left = Math.max(pad, Math.min(left, window.innerWidth - tw - pad));
    if (top + th > window.innerHeight - pad) {
      top = Math.max(pad, r.top - gap - th);
    }
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
    tip.style.visibility = '';
  }

  async function fetchPayload() {
    const res = await fetch('/api/dispatch-calendar', { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || data.error || 'Failed to load Dispatch Calendar');
    }
    return data;
  }

  function updateSubtitle(el, payload) {
    if (!el || !payload) return;
    const mo = payload.month;
    const yr = payload.year;
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const label = mo >= 1 && mo <= 12 ? monthNames[mo - 1] : String(mo);
    el.textContent = `${label} ${yr}`;
  }

  function syncWeekSelect() {
    const sel = document.getElementById('dispatch-calendar-week');
    if (sel && sel.value !== _dcWeekFilter) sel.value = _dcWeekFilter;
  }

  async function loadDispatchMtdKpi() {
    const elTotal = document.getElementById('dc-kpi-dispatch-total-so');
    if (!elTotal || typeof window.Hub === 'undefined' || !window.Hub.api || !window.Hub.utils) return;
    try {
      const summary = await window.Hub.api.getReportSummary();
      const totalSo = Number(summary.total_so_qty) || 0;
      const dispatchQtyMtd = Number(summary.dispatch_qty_mtd) || 0;
      const dispatchPct = totalSo > 0 ? Math.round((dispatchQtyMtd / totalSo) * 100) : 0;
      elTotal.textContent = window.Hub.utils.formatIndian(totalSo);
      const qEl = document.getElementById('dc-kpi-dispatch-qty');
      const pEl = document.getElementById('dc-kpi-dispatch-pct');
      if (qEl) qEl.textContent = window.Hub.utils.formatIndian(dispatchQtyMtd);
      if (pEl) pEl.textContent = `${dispatchPct}%`;
    } catch (e) {
      console.error('Dispatch MTD KPI:', e);
    }
  }

  const DispatchCalendarPage = {
    init() {
      const root = document.getElementById('dispatch-calendar-root');
      const subtitle = document.getElementById('dispatch-calendar-subtitle');
      const refreshBtn = document.getElementById('dispatch-calendar-refresh');
      if (!root) return;
      bindLegendFilter(root);

      ensureStockTooltipDelegation(root);
      ensureDayTooltipDelegation(root);

      const weekSel = document.getElementById('dispatch-calendar-week');
      if (weekSel) {
        weekSel.value = _dcWeekFilter;
        weekSel.addEventListener('change', () => {
          const mode = weekSel.value;
          if (!mode || mode === _dcWeekFilter) return;
          _dcWeekFilter = mode;
          syncWeekSelect();
          if (_lastPayload) {
            renderSuperGrid(root, _lastPayload, _dcWeekFilter);
          }
        });
      }
      syncWeekSelect();

      const load = async () => {
        setLoading(root, true);
        try {
          const [payload] = await Promise.all([fetchPayload(), loadDispatchMtdKpi()]);
          _lastPayload = payload;
          syncLegendFilterUi();
          updateSubtitle(subtitle, payload);
          setLoading(root, false);
          renderSuperGrid(root, payload, _dcWeekFilter);
        } catch (e) {
          console.error(e);
          destroyGrid();
          _lastPayload = null;
          setLoading(root, false);
          root.innerHTML =
            '<div class="ti-dc-error">' +
            (e && e.message ? e.message : 'Failed to load') +
            '</div>';
        }
      };

      if (refreshBtn) refreshBtn.addEventListener('click', () => load());

      load();
    },
  };

  window.DispatchCalendarPage = DispatchCalendarPage;
})();
