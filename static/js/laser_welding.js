/* ═══════════════════════════════════════════════════════════════════════════
   LASER_WELDING.JS — Laser Welding unified tab workflow
   ═══════════════════════════════════════════════════════════════════════════ */

window.LaserWeldingPage = (() => {
  const GRID_PRIMARY_QTY_LABELS = {
    inspection: 'Inspected',
    sa_cleaning: 'Inspected',
    lw_cleaning: 'Inspected',
    qa: 'Disposition',
    packing: 'Consumed',
  };

  const TAB_LABELS = {
    inspection: 'Inspection',
    sub_assembly: 'Sub-Assembly',
    sa_cleaning: 'SA Inspection',
    sa_rework: 'SA Re-Work',
    laser_welding: 'Laser Welding',
    lw_cleaning: 'LW Cleaning/Inspection',
    lw_rework: 'LW Re-Work',
    packing: 'Packing',
    trays_carton: 'Trays/Carton',
    qa: 'QA',
    tracking: 'Tracking — pipeline snapshot & build capacity',
    reports: 'Reports — activity, stock, QA & scrap',
  };

  const GRID_TABS = new Set(['inspection', 'sa_cleaning', 'lw_cleaning', 'qa', 'packing']);
  const SA_TABS = new Set(['sub_assembly', 'sa_rework']);
  const ASM_TABS = new Set(['laser_welding', 'lw_rework']);
  const TRACK_TABS = new Set(['tracking', 'reports']);

  let _tab = 'inspection';
  let _workDate = '';
  let _parts = [];
  let _operators = [];
  let _machines = [];
  let _saMachines = [];
  let _rows = [];
  let _expanded = {};
  let _sourceLotsCache = {};
  let _childLotsCache = {};
  let _asmRows = [];
  let _saRows = [];
  let _asmEligibleRows = [];
  let _saEligibleRows = [];
  let _qaEligibleRows = [];
  let _boms = [];
  let _saPartsList = [];
  let _bomCustomers = [];
  let _asmExpanded = {};
  let _saExpanded = {};
  let _saLoading = false;
  let _reworkTargetLotsCache = {};
  let _filterQuery = '';
  let _loading = false;
  let _loadGridRowsPending = false;
  let _asmLoading = false;
  let _prodModalLines = [];
  let _prodModalMode = 'production';
  let _prodModalDraftLineId = null;
  let _prodModalBomId = null;
  let _cleaningLotsCache = {};
  let _qaLotsCache = {};
  let _packingLotsCache = {};
  let _packMaterials = { trays: [], cartons: [], hasMapping: false, mapping: null };
  let _traysCartonRows = [];
  let _tcLegend = null;
  let _tcPartsList = [];
  let _tcPreviewTimer = null;
  let _tcEditTraySeq = null;
  let _tcEditBinSeq = null;
  let _weldModalDraftLineId = null;
  let _weldModalBomId = null;
  let _weldModalOperatorIds = [];
  let _weldModalTargetLotId = null;
  let _weldModalChildren = [];
  let _weldModalContext = 'assembly';
  let _weldModalSubAssemblyPartNo = null;
  let _prodModalSubAssemblyPartNo = null;
  let _prodModalIsBo = false;

  let _trackingDataRaw = null;
  let _trackCache = {};
  let _trackLoadedKey = '';
  let _trackReportView = 'history';
  let _trackCustId = '';
  let _trackPhase = '';
  let _trackFlowStep = '';
  let _trackSearch = '';
  let _trackLoading = false;
  let _trackCapacityExpanded = {};
  let _trackSelectedCardKey = '';
  let _visibilityRefreshBound = false;
  let _actionHistoryRows = [];
  let _historyFrom = '';
  let _historyTo = '';
  let _historyStep = '';
  let _historySearch = '';
  let _historyLoading = false;
  let _historyExpanded = {};
  let _historyGrid = null;
  let _stockGrid = null;
  let _qaGrid = null;
  let _scrapGrid = null;
  let _stockRows = [];
  let _qaRows = [];
  let _scrapRows = [];
  let _stockLoading = false;
  let _qaLoading = false;
  let _scrapLoading = false;

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];

  const canEdit = () => !!window.LW_EDIT_ALLOWED;

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
  }

  function todayIso() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function isoDaysAgo(days) {
    const d = new Date();
    d.setDate(d.getDate() - Math.max(0, Number(days) || 0));
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  async function apiFetch(url, opts) {
    if (typeof window.apiFetch === 'function') return window.apiFetch(url, opts);
    const r = await fetch(url, opts);
    if (!r.ok) {
      let m = `Error ${r.status}`;
      try {
        const b = await r.json();
        if (b.error) m = b.error;
      } catch (_) { /* ignore */ }
      throw new Error(m);
    }
    return r.json();
  }

  async function apiPost(url, body) {
    if (typeof window.apiPost === 'function') return window.apiPost(url, body);
    return apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  async function apiDownload(path, body, fileName) {
    if (window.Hub?.api?.download) {
      return window.Hub.api.download(path, body, fileName);
    }
    const res = await fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      credentials: 'same-origin',
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
      window.location.href = '/login';
      throw new Error('Session expired');
    }
    if (!res.ok) {
      let msg = `Download error: ${res.status}`;
      try {
        const j = await res.json();
        msg = j.error || j.message || msg;
      } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName || 'download.xlsx';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }

  function isReworkWeldingMode() {
    return _tab === 'lw_rework';
  }

  function isReworkSubAssemblyMode() {
    return _tab === 'sa_rework';
  }

  function isWeldReworkMode() {
    if (_weldModalContext === 'sub_assembly') return isReworkSubAssemblyMode();
    return isReworkWeldingMode();
  }

  function isSubAssemblyWeldContext() {
    return _weldModalContext === 'sub_assembly';
  }

  function isGridTab(tab) {
    return GRID_TABS.has(tab || _tab);
  }

  function isCleaningTab(tab) {
    const t = tab || _tab;
    return t === 'sa_cleaning' || t === 'lw_cleaning';
  }

  function gridApiMode(tab) {
    const t = tab || _tab;
    if (t === 'inspection') return 'inspection';
    if (t === 'sa_cleaning') return 'sa_cleaning';
    if (t === 'lw_cleaning') return 'lw_cleaning';
    return t;
  }

  function partsApiMode(tab) {
    const t = tab || _tab;
    if (t === 'inspection') return 'inspection';
    if (t === 'qa') return 'qa';
    if (isCleaningTab(t)) return t;
    return 'production';
  }

  function completeActionLabel(isRework, forSubAssembly) {
    if (isRework) return 'Re-work';
    return forSubAssembly ? 'Assembled' : 'Welded';
  }

  function completeQtyLabel(forSubAssembly) {
    return forSubAssembly ? 'Assembly QTY' : 'Weld QTY';
  }

  function completeTotalLabel(forSubAssembly) {
    return forSubAssembly ? 'Assembled' : 'Welded';
  }

  function partNoKey(part) {
    return String(part?.part_no || part?.partNo || '').trim().toLowerCase();
  }

  function partNameFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => partNoKey(x) === key);
    return p ? String(p.part_name || p.partName || '').trim() : '';
  }

  function emptyLine() {
    return {
      sourceLotNo: '',
      targetLotId: null,
      productionDate: '',
      noOfComp: 0,
      availableQty: 0,
      inspectedQty: 0,
      qaQty: 0,
      scrapQty: 0,
      qaPassed: 0,
      reworkQty: 0,
      packQty: 0,
      scrapRemark: '',
      reworkRemark: '',
    };
  }

  function sumLinesQaScrap(lines) {
    let qa = 0;
    let scrap = 0;
    (lines || []).forEach(ln => {
      qa += Number(ln.qaQty) || 0;
      scrap += Number(ln.scrapQty) || 0;
    });
    return { qa, scrap };
  }

  function formatQtyDisplay(n) {
    const v = Number(n) || 0;
    return v > 0 ? String(v) : '—';
  }

  function primaryQtyCellHtml(row) {
    return formatQtyDisplay(row.totalQty ?? row.weldQty);
  }

  function qaTotalCellHtml(row) {
    if (!row.isProcessed) return '—';
    const { qa } = sumLinesQaScrap(row.lines);
    return formatQtyDisplay(qa);
  }

  function scrapTotalCellHtml(row) {
    if (!row.isProcessed) return '—';
    const { scrap } = sumLinesQaScrap(row.lines);
    return formatQtyDisplay(scrap);
  }

  function qtyMetaPlaceholderCells() {
    return '<td class="lw-col-qa">—</td><td class="lw-col-scrap">—</td>';
  }

  function timePlaceholderCell() {
    return '<td class="lw-col-time">—</td>';
  }

  function asmTimeCellHtml(row) {
    if (!row?.isProcessed) return '—';
    const timeStr = rowTimeTakenDisplay(row);
    return escapeHtml(timeStr || '—');
  }

  function packLotCellHtml(row) {
    if (!row.packLotNo) return '—';
    return `<span class="lw-lot-badge" title="Packed output lot">${escapeHtml(row.packLotNo)}</span>`;
  }

  function lotPackPlaceholderCell() {
    return '<td class="lw-col-lot lw-col-lot--pack">—</td>';
  }

  function lotAvailableQty(lot) {
    if (!lot) return 0;
    const avail = Number(lot.availableQty);
    if (Number.isFinite(avail) && avail > 0) return avail;
    const qa = Number(lot.totalQa);
    if (Number.isFinite(qa) && qa > 0) return qa;
    const ok = Number(lot.totalOkayed);
    if (Number.isFinite(ok) && ok > 0) return ok;
    return Number(lot.noOfComp) || 0;
  }

  function sourceLotsInfo(partNo) {
    const cached = _sourceLotsCache[partNo];
    if (!cached) return { lots: [], boMode: false, availableQty: 0 };
    if (Array.isArray(cached)) {
      return { lots: cached, boMode: false, availableQty: 0 };
    }
    return {
      lots: cached.lots || [],
      boMode: !!cached.boMode,
      availableQty: Number(cached.availableQty) || 0,
    };
  }

  function rowHasOt(row) {
    const lines = row?.lines || [];
    if (lines.some(ln => String(ln.otFlag || '').toUpperCase() === 'Y')) return true;
    return String(row?.otFlag || '').toUpperCase() === 'Y';
  }

  function otBadgeHtml(row) {
    return rowHasOt(row) ? '<span class="lw-ot-badge" title="Overtime">OT</span>' : '—';
  }

  function isLwModalOpen() {
    const prodOpen = $('#lw-production-modal-overlay')?.getAttribute('aria-hidden') === 'false';
    const weldOpen = $('#lw-weld-modal-overlay')?.getAttribute('aria-hidden') === 'false';
    return !!(prodOpen || weldOpen);
  }

  function invalidateLwCaches(force) {
    if (!force && isLwModalOpen()) return;
    _sourceLotsCache = {};
    _cleaningLotsCache = {};
    _childLotsCache = {};
    _reworkTargetLotsCache = {};
    _qaLotsCache = {};
    _packingLotsCache = {};
  }

  function updateGridTableHeaders() {
    const primaryTh = document.querySelector('#lw-table-head .lw-col-qty-primary');
    if (primaryTh) {
      primaryTh.textContent = GRID_PRIMARY_QTY_LABELS[_tab] || 'Inspected';
    }
  }

  function isLaserWeldingVisible() {
    return !!$('#lw-root');
  }

  async function refreshActiveTab(preserveFilter) {
    if (!isLaserWeldingVisible()) return;
    invalidateLwCaches();
    if (isGridTab()) {
      try {
        await refreshPartsDatalist();
      } catch (err) {
        console.error('Failed to refresh parts list', err);
      }
      await loadGridRows(preserveFilter);
    } else if (ASM_TABS.has(_tab)) {
      await loadBomCatalog();
      await loadAssemblyRows(preserveFilter);
    } else if (SA_TABS.has(_tab)) {
      await loadSubAssemblyPartCatalog();
      await loadSubAssemblyRows(preserveFilter);
    } else if (_tab === 'trays_carton') {
      await loadTraysCartonTab(preserveFilter);
    } else if (TRACK_TABS.has(_tab)) {
      await loadTracking();
      if (_trackReportView === 'history') await loadActionHistory();
      else if (_trackReportView === 'stock') await loadStockReport();
      else if (_trackReportView === 'qa') await loadQaHistory();
      else if (_trackReportView === 'scrap') await loadScrapHistory();
    } else {
      updateRowCount();
    }
  }

  function partIsBo(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const meta = _parts.find(p => partNoKey(p) === key);
    if (meta?.isBoPart) return true;
    return sourceLotsInfo(partNo).boMode;
  }

  function filteredRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = _rows;
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.partNumber,
        r.partName || partNameFor(r.partNumber),
        r.partNo,
        r.productName,
        r.operatorNames,
        r.operatorName,
        r.newLotNo,
        r.workDate,
        isoToDisplayDate(r.workDate),
        ...(r.lines || []).map(ln => ln.sourceLotNo),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function groupDisplayKey(row) {
    const op = String(row.operatorIds?.join(',') ?? '');
    if (isCleaningTab()) {
      const bom = String(row.bomId || bomIdForPartNo(row.partNumber) || row.partNumber || '').trim();
      return `${bom}|${op}`;
    }
    const part = String(row.partNumber || row.partNo || '').trim().toLowerCase();
    return `${part}|${op}`;
  }

  function mergeGroupedDisplayRow(group, row) {
    if (row.isDraft) {
      group.isDraft = true;
      group.draftLineId = row.draftLineId || row.lineId;
      group.lineId = group.draftLineId;
    }
    if (row.isProcessed) group.isProcessed = true;
    if (row.lines?.length) group.lines.push(...row.lines);
    if (!group.timeTakenMinutes && row.timeTakenMinutes) {
      group.timeTakenMinutes = row.timeTakenMinutes;
    }
    group.totalQty = (Number(group.totalQty) || 0) + (Number(row.totalQty) || 0);
    if (rowHasOt(row)) group._hasOt = true;
  }

  function tableDisplayRows() {
    return filteredRows();
  }

  function findRow(rowKey) {
    const grouped = tableDisplayRows().find(r => r.rowKey === rowKey);
    if (grouped) return grouped;
    return _rows.find(r => r.rowKey === rowKey);
  }

  function updateRowCount() {
    const el = $('#lw-item-count');
    if (!el) return;
    if (isGridTab()) {
      let n = tableDisplayRows().length;
      if (_tab === 'qa') n += filteredEligibleRows(_qaEligibleRows).length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (ASM_TABS.has(_tab)) {
      let n = filteredAsmRows().length;
      if (isReworkWeldingMode()) n += filteredEligibleRows(_asmEligibleRows).length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (SA_TABS.has(_tab)) {
      let n = filteredSaRows().length;
      if (isReworkSubAssemblyMode()) n += filteredEligibleRows(_saEligibleRows).length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'trays_carton') {
      const n = filteredTraysCartonRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else {
      el.textContent = '—';
    }
  }

  function isoToDisplayDate(iso) {
    if (!iso) return '';
    const parts = String(iso).split('-');
    if (parts.length !== 3) return iso;
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }

  function formatTimeTaken(minutes) {
    const total = Number(minutes);
    if (!Number.isFinite(total) || total <= 0) return '';
    const h = Math.floor(total / 60);
    const m = total % 60;
    if (h > 0 && m > 0) return `${h}h ${m}m`;
    if (h > 0) return `${h}h`;
    return `${m}m`;
  }

  function rowTimeTakenDisplay(row) {
    const fromRow = formatTimeTaken(row.timeTakenMinutes);
    if (fromRow) return fromRow;
    const lines = row.lines || [];
    const withTime = lines.find(ln => Number(ln.timeTakenMinutes) > 0);
    return withTime ? formatTimeTaken(withTime.timeTakenMinutes) : '';
  }

  function detailRemarkColumnsForTab(tab) {
    const t = tab || _tab;
    if (t === 'qa') return { scrap: true, rework: true };
    if (ASM_TABS.has(t) || SA_TABS.has(t)) return { scrap: true, rework: false };
    return { scrap: true, rework: false };
  }

  function detailRemarkColCount(tab) {
    const cols = detailRemarkColumnsForTab(tab);
    return (cols.scrap ? 1 : 0) + (cols.rework ? 1 : 0);
  }

  function detailRemarkHeaderHtml(tab) {
    const cols = detailRemarkColumnsForTab(tab);
    let html = '';
    if (cols.scrap) html += '<th class="lw-detail-col-remark">Remark</th>';
    if (cols.rework) html += '<th class="lw-detail-col-remark">Rework remark</th>';
    return html;
  }

  function detailRemarkCellsHtml(ln, tab) {
    const cols = detailRemarkColumnsForTab(tab);
    let html = '';
    if (cols.scrap) {
      const scrap = Number(ln.scrapQty) || 0;
      const remark = String(ln.scrapRemark || '').trim();
      html += `<td class="lw-detail-col-remark">${scrap > 0 && remark ? escapeHtml(remark) : '—'}</td>`;
    }
    if (cols.rework) {
      const rework = Number(ln.reworkQty) || 0;
      const remark = String(ln.reworkRemark || '').trim();
      html += `<td class="lw-detail-col-remark">${rework > 0 && remark ? escapeHtml(remark) : '—'}</td>`;
    }
    return html;
  }

  function detailLotCellHtml(ln) {
    const sourceLabel = ln.sourceLotNo || ln.newLotNo || '—';
    const partHint = ln.sourcePartNumber || '';
    if (partHint && partHint !== sourceLabel && !String(sourceLabel).includes(partHint)) {
      return `${escapeHtml(sourceLabel)} <span class="lw-pack-source-part">(${escapeHtml(partHint)})</span>`;
    }
    return escapeHtml(sourceLabel);
  }

  function lineHasSourceTrace(ln) {
    return !!(ln.sourceTrace?.length);
  }

  function isTraceSubAssemblyLine(ln) {
    if (ln.nestedLines?.length) return true;
    const pn = String(ln.partNumber || '').trim().toUpperCase();
    const lot = String(ln.sourceLotNo || '').trim().toUpperCase();
    return pn.startsWith('SA') || lot.startsWith('SA/');
  }

  function traceNodeKindLabel(ln) {
    return isTraceSubAssemblyLine(ln) ? 'Sub-Assembly' : 'Part';
  }

  function lwTreeToggleBtn(hasChildren, expanded) {
    if (!hasChildren) {
      return '<span class="lw-tree-toggle lw-tree-toggle--leaf" aria-hidden="true"></span>';
    }
    const expCls = expanded ? ' is-expanded' : '';
    return `<button type="button" class="lw-tree-toggle lw-tree-toggle--btn${expCls}" `
      + `aria-expanded="${expanded ? 'true' : 'false'}" title="Show/hide parts">`
      + '<span class="lw-tree-chevron" aria-hidden="true">▸</span></button>';
  }

  function consumeTraceTreeHtml(lines, level) {
    const depth = Number(level) || 0;
    if (!lines?.length) return '';
    let html = `<ul class="lw-trace-tree" data-depth="${depth}">`;
    lines.forEach(ln => {
      const hasNested = !!(ln.nestedLines?.length);
      const kind = isTraceSubAssemblyLine(ln) ? 'sa' : 'part';
      const levelLabel = traceNodeKindLabel(ln);
      const part = escapeHtml(ln.partNumber || '—');
      const lot = escapeHtml(ln.sourceLotNo || '—');
      html += `<li class="lw-trace-node lw-trace-node--${hasNested ? 'branch' : 'leaf'}" data-level="${depth}" data-kind="${kind}">`;
      html += '<div class="lw-trace-node-row lw-trace-node-row--depth-' + depth + '">';
      html += lwTreeToggleBtn(hasNested, false);
      html += `<span class="lw-trace-level-tag">${levelLabel}</span>`;
      html += `<span class="lw-trace-primary"><span class="lw-trace-part">${part}</span>`
        + `<span class="lw-trace-sep">·</span><span class="lw-trace-lot">${lot}</span></span>`;
      html += '</div>';
      if (hasNested) {
        html += '<div class="lw-trace-children" hidden>';
        html += consumeTraceTreeHtml(ln.nestedLines, depth + 1);
        html += '</div>';
      }
      html += '</li>';
    });
    html += '</ul>';
    return html;
  }

  function tracePanelHtml(treeHtml) {
    if (!treeHtml) return '';
    return `<div class="lw-trace-panel">${treeHtml}</div>`;
  }

  function traceBranchRowHtml(colspan, lines, level) {
    const treeHtml = consumeTraceTreeHtml(lines, level || 0);
    if (!treeHtml) return '';
    return `<tr class="lw-trace-branch-row" hidden>`
      + `<td colspan="${colspan}" class="lw-trace-branch-cell">`
      + tracePanelHtml(treeHtml)
      + '</td></tr>';
  }

  function cellWithTreeToggle(innerHtml, hasBranch) {
    if (!hasBranch) return innerHtml;
    return `<div class="lw-tree-cell-inner">${lwTreeToggleBtn(true, false)}<span class="lw-tree-cell-label">${innerHtml}</span></div>`;
  }

  function handleLwTreeToggle(e) {
    const btn = e.target.closest('.lw-tree-toggle--btn');
    if (!btn) return false;
    e.preventDefault();
    e.stopPropagation();
    const expanded = btn.classList.toggle('is-expanded');
    btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');

    const branchRow = btn.closest('.lw-detail-lot-row--branch, .lw-detail-consume-row--branch, .lw-detail-source-row--branch');
    if (branchRow) {
      const sibling = branchRow.nextElementSibling;
      if (sibling?.classList.contains('lw-trace-branch-row')) {
        sibling.hidden = !expanded;
      }
      return true;
    }

    const node = btn.closest('.lw-trace-node--branch');
    if (node) {
      const children = node.querySelector(':scope > .lw-trace-children');
      if (children) children.hidden = !expanded;
    }
    return true;
  }

  function packDetailLinesHtml(row) {
    const lines = row.lines || [];
    const remarkCols = detailRemarkColCount('packing');
    const baseCols = 4;
    const totalCols = baseCols + remarkCols;
    let html = '';

    if (row.packLotNo) {
      html += `<div class="lw-pack-output-lot"><span class="lw-detail-label">PCK Lot</span> `
        + `<span class="lw-lot-badge">${escapeHtml(row.packLotNo)}</span></div>`;
    }

    html += '<table class="ti-table lw-detail-table"><thead><tr>';
    html += '<th>Source Lot</th><th>Consumed</th><th>QA</th><th>Scrap</th>';
    html += detailRemarkHeaderHtml('packing');
    html += '</tr></thead><tbody>';

    if (!lines.length) {
      html += `<tr><td colspan="${totalCols}" class="lw-detail-empty">No lot lines saved.</td></tr>`;
    }

    lines.forEach(ln => {
      const consumed = Number(ln.inspectedQty) || Number(ln.packQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      const lotCell = detailLotCellHtml(ln);
      const hasTrace = lineHasSourceTrace(ln);

      html += '<tr';
      if (hasTrace) html += ' class="lw-detail-source-row--branch"';
      html += '>';
      html += `<td class="lw-detail-lot-cell">${cellWithTreeToggle(lotCell, hasTrace)}</td>`;
      html += `<td>${consumed > 0 ? consumed : '—'}</td>`;
      html += `<td>${qa > 0 ? qa : '—'}</td>`;
      html += `<td>${scrap > 0 ? scrap : '—'}</td>`;
      html += detailRemarkCellsHtml(ln, 'packing');
      html += '</tr>';

      if (hasTrace) {
        html += traceBranchRowHtml(totalCols, ln.sourceTrace, 0);
      }
    });

    html += '</tbody></table>';

    if (row.packMaterials?.length) {
      html += '<table class="ti-table lw-detail-table lw-detail-table--materials"><thead><tr>';
      html += '<th>Material</th><th>Qty</th>';
      html += '</tr></thead><tbody>';
      row.packMaterials.forEach(ln => {
        html += '<tr>';
        html += `<td>${escapeHtml(ln.partNumber || '—')}</td>`;
        html += `<td>${Number(ln.inspectedQty) || '—'}</td>`;
        html += '</tr>';
      });
      html += '</tbody></table>';
    }

    return html;
  }

  function detailLinesHtml(row) {
    if (_tab === 'packing') return packDetailLinesHtml(row);
    const lines = row.lines || [];
    const remarkCols = detailRemarkColCount(_tab);
    let baseCols = 4;
    let html = '<table class="ti-table lw-detail-table"><thead><tr>';
    if (_tab === 'qa') {
      html += '<th>Lot No</th><th>Passed</th><th>Scrap</th><th>Rework</th>';
    } else {
      html += '<th>Lot No</th>';
      html += '<th>Inspected QTY</th><th>QA</th><th>Scrap</th>';
    }
    html += detailRemarkHeaderHtml(_tab);
    html += '</tr></thead><tbody>';

    if (!lines.length) {
      html += `<tr><td colspan="${baseCols + remarkCols}" class="lw-detail-empty">No lot lines saved.</td></tr>`;
    }

    lines.forEach(ln => {
      const lotCell = detailLotCellHtml(ln);
      const hasTrace = lineHasSourceTrace(ln);

      html += `<tr class="lw-detail-lot-row${hasTrace ? ' lw-detail-lot-row--branch' : ''}">`;
      html += `<td class="lw-detail-lot-cell">${cellWithTreeToggle(lotCell, hasTrace)}</td>`;
      if (_tab === 'qa') {
        const passed = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const rework = Number(ln.reworkQty) || 0;
        html += `<td>${passed > 0 ? passed : '—'}</td>`;
        html += `<td>${scrap > 0 ? scrap : '—'}</td>`;
        html += `<td>${rework > 0 ? rework : '—'}</td>`;
      } else {
        const insp = Number(ln.inspectedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        html += `<td>${insp > 0 ? insp : '—'}</td>`;
        html += `<td>${qa > 0 ? qa : '—'}</td>`;
        html += `<td>${scrap > 0 ? scrap : '—'}</td>`;
      }
      html += detailRemarkCellsHtml(ln, _tab);
      html += '</tr>';

      if (hasTrace) {
        html += traceBranchRowHtml(baseCols + remarkCols, ln.sourceTrace, 0);
      }
    });

    html += '</tbody></table>';

    return html;
  }

  function buildDraftDismissBtn(row) {
    if (!row?.isDraft || !canEdit()) return '';
    const lineId = row.draftLineId || row.lineId;
    if (!lineId) return '';
    return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-dismiss" `
      + `data-row-key="${escapeAttr(row.rowKey)}" `
      + `title="Remove pending row" aria-label="Remove pending row">×</button>`;
  }

  async function dismissDraftRow(row) {
    if (!row?.isDraft || !canEdit()) return;
    const lineId = row.draftLineId || row.lineId;
    if (!lineId) return;
    try {
      await apiPost('/api/laser-welding/draft-line/delete', { draftLineId: lineId });
      showSnackbar('Pending row removed', 'success');
      await refreshActiveTab(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to remove row', 'error');
    }
  }

  function inspectActionLabel() {
    if (_tab === 'qa') return 'QA';
    if (_tab === 'packing') return 'Pack';
    return 'Inspect';
  }

  function buildActionsHtml(row) {
    const key = row.rowKey;
    const expCls = _expanded[key] ? ' is-expanded' : '';
    let actions = '';

    if (row.isProcessed) {
      actions += `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Lot lines">▤</button>`;
    }
    if (row.isDraft) {
      if (!canEdit()) return actions || '<span class="lw-view-only">View only</span>';
      actions += `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-inspect" data-row-key="${escapeAttr(key)}">${inspectActionLabel()}</button>`;
      actions += buildDraftDismissBtn(row);
    }
    if (actions) return actions;
    if (!canEdit()) return '<span class="lw-view-only">View only</span>';
    return '';
  }

  function buildDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;

    const partNo = row.partNumber || row.partNo || '';
    const partName = row.partName || partNameFor(partNo);
    const operatorName = operatorDisplayName(row);
    const timeStr = rowTimeTakenDisplay(row) || '—';

    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(partNo)}">${escapeHtml(partNo)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-qty">${primaryQtyCellHtml(row)}</td>
      <td class="lw-col-qa">${qaTotalCellHtml(row)}</td>
      <td class="lw-col-scrap">${scrapTotalCellHtml(row)}</td>
      <td class="lw-col-lot lw-col-lot--pack">${packLotCellHtml(row)}</td>
      <td class="lw-col-time">${escapeHtml(timeStr)}</td>
      <td class="lw-col-ot">${otBadgeHtml(row)}</td>
      <td class="lw-col-actions lw-actions-cell">${buildActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;

    const td = document.createElement('td');
    td.colSpan = 10;
    td.className = 'lw-detail-cell';
    td.innerHTML = `<div class="lw-detail-inline lw-detail-body" data-row-key="${escapeAttr(row.rowKey)}">${detailLinesHtml(row)}</div>`;
    tr.appendChild(td);
    return tr;
  }

  function operatorSelectHtml(selectedId) {
    let html = '<option value="">Select operator…</option>';
    _operators.forEach(op => {
      const sel = Number(selectedId) === Number(op.id) ? ' selected' : '';
      html += `<option value="${op.id}"${sel}>${escapeHtml(op.label || op.name || '')}</option>`;
    });
    return html;
  }

  function operatorDisplayName(row) {
    const names = String(row?.operatorNames || row?.operatorName || '').trim();
    return names || '—';
  }

  function operatorMultiSelectHtml(selectedIds) {
    const selected = new Set((selectedIds || []).map(id => Number(id)).filter(id => id > 0));
    let checks = '';
    _operators.forEach(op => {
      const checked = selected.has(Number(op.id)) ? ' checked' : '';
      checks += `<label class="lw-operator-multi-item"><input type="checkbox" value="${op.id}"${checked} /><span>${escapeHtml(op.label || op.name || '')}</span></label>`;
    });
    const labels = _operators
      .filter(op => selected.has(Number(op.id)))
      .map(op => op.label || op.name || '')
      .filter(Boolean);
    const summary = labels.length ? labels.join(', ') : 'Select operators…';
    return `<div class="lw-operator-multi">
      <button type="button" class="lw-operator-multi-toggle ti-input">${escapeHtml(summary)}</button>
      <div class="lw-operator-multi-menu">${checks || '<span class="lw-operator-multi-empty">No operators</span>'}</div>
    </div>`;
  }

  function updateOperatorMultiLabel(wrap) {
    if (!wrap) return;
    const btn = wrap.querySelector('.lw-operator-multi-toggle');
    const checked = [...wrap.querySelectorAll('input[type="checkbox"]:checked')];
    const labels = checked.map(inp => {
      const span = inp.closest('label')?.querySelector('span');
      return String(span?.textContent || '').trim();
    }).filter(Boolean);
    const summary = labels.length ? labels.join(', ') : 'Select operators…';
    if (btn) {
      btn.textContent = summary;
      btn.title = summary;
    }
  }

  function positionOperatorMultiMenu(wrap) {
    const btn = wrap?.querySelector('.lw-operator-multi-toggle');
    const menu = wrap?.querySelector('.lw-operator-multi-menu');
    if (!btn || !menu) return;
    const rect = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.left = `${Math.max(8, rect.left)}px`;
    menu.style.top = `${rect.bottom + 4}px`;
    menu.style.width = `${Math.max(rect.width, 180)}px`;
    menu.style.right = 'auto';
  }

  function resetOperatorMultiMenuPosition(wrap) {
    const menu = wrap?.querySelector('.lw-operator-multi-menu');
    if (!menu) return;
    menu.style.position = '';
    menu.style.left = '';
    menu.style.top = '';
    menu.style.width = '';
    menu.style.right = '';
  }

  function initOperatorMultiSelect(root) {
    const scope = root || document;
    scope.querySelectorAll('.lw-operator-multi:not([data-bound])').forEach(wrap => {
      wrap.dataset.bound = '1';
      const btn = wrap.querySelector('.lw-operator-multi-toggle');
      const menu = wrap.querySelector('.lw-operator-multi-menu');
      btn?.addEventListener('click', e => {
        e.stopPropagation();
        const willOpen = !wrap.classList.contains('is-open');
        document.querySelectorAll('.lw-operator-multi.is-open').forEach(other => {
          if (other !== wrap) {
            other.classList.remove('is-open');
            resetOperatorMultiMenuPosition(other);
          }
        });
        wrap.classList.toggle('is-open', willOpen);
        if (willOpen) positionOperatorMultiMenu(wrap);
        else resetOperatorMultiMenuPosition(wrap);
      });
      menu?.addEventListener('change', () => updateOperatorMultiLabel(wrap));
      updateOperatorMultiLabel(wrap);
    });
  }

  function getOperatorIdsFromMulti(container) {
    if (!container) return [];
    const wrap = container.classList?.contains('lw-operator-multi')
      ? container
      : (container.querySelector?.('.lw-operator-multi') || container.closest?.('.lw-operator-multi'));
    if (!wrap) return [];
    return [...wrap.querySelectorAll('input[type="checkbox"]:checked')]
      .map(inp => parseInt(inp.value, 10))
      .filter(id => Number.isFinite(id) && id > 0);
  }

  function resetOperatorMulti(container) {
    if (!container) return;
    const wrap = container.classList?.contains('lw-operator-multi')
      ? container
      : (container.querySelector?.('.lw-operator-multi') || container.closest?.('.lw-operator-multi'));
    if (!wrap) return;
    wrap.querySelectorAll('input[type="checkbox"]').forEach(inp => { inp.checked = false; });
    wrap.classList.remove('is-open');
    resetOperatorMultiMenuPosition(wrap);
    updateOperatorMultiLabel(wrap);
  }

  function operatorPayloadFromMulti(container) {
    const ids = getOperatorIdsFromMulti(container);
    if (!ids.length) return null;
    return { operatorId: ids[0], operatorIds: ids };
  }

  function machineSelectHtml(selectedId) {
    let html = '<option value="">Select machine…</option>';
    _machines.forEach(mc => {
      const sel = Number(selectedId) === Number(mc.id) ? ' selected' : '';
      html += `<option value="${mc.id}"${sel}>${escapeHtml(mc.label || mc.name || '')}</option>`;
    });
    return html;
  }

  function saMachineSelectHtml(selectedId) {
    let html = '<option value="">Select machine…</option>';
    _saMachines.forEach(mc => {
      const sel = Number(selectedId) === Number(mc.id) ? ' selected' : '';
      html += `<option value="${mc.id}"${sel}>${escapeHtml(mc.label || mc.name || '')}</option>`;
    });
    return html;
  }

  function bomIdForPartNo(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => partNoKey(x) === key);
    return p?.bomId || p?.bom_id || null;
  }

  function appendNewRow(tbody) {
    if (!canEdit() || !isGridTab()) return;
    if (_tab === 'qa') return;

    if (isCleaningTab()) {
      appendCleaningNewRow(tbody);
      return;
    }

    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-part lw-edit-cell">
        <input type="text" class="lw-cell-input lw-new-part"
               list="lw-parts-datalist" placeholder="Select part…" autocomplete="off" />
      </td>
      <td class="lw-col-name lw-new-part-name"></td>
      <td class="lw-col-operator lw-edit-cell">
        <select class="ti-input lw-new-operator">${operatorSelectHtml()}</select>
      </td>
      <td class="lw-col-qty">—</td>
      ${qtyMetaPlaceholderCells()}
      ${lotPackPlaceholderCell()}
      <td class="lw-col-time">—</td>
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const partInput = tr.querySelector('.lw-new-part');
    const operatorSel = tr.querySelector('.lw-new-operator');
    const tryCommit = () => tryCommitNewRow(partInput, operatorSel);

    partInput?.addEventListener('input', () => {
      const nameEl = tr.querySelector('.lw-new-part-name');
      if (nameEl) nameEl.textContent = partNameFor(partInput.value) || '';
    });
    partInput?.addEventListener('change', tryCommit);
    operatorSel?.addEventListener('change', tryCommit);
    partInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        tryCommit();
      }
    });
  }

  function appendCleaningNewRow(tbody) {
    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-part lw-edit-cell">
        <input type="text" class="lw-cell-input lw-new-bom"
               list="lw-parts-datalist" placeholder="Select BOM…" autocomplete="off" />
      </td>
      <td class="lw-col-name lw-new-bom-name"></td>
      <td class="lw-col-operator lw-edit-cell">
        <select class="ti-input lw-new-operator">${operatorSelectHtml()}</select>
      </td>
      <td class="lw-col-qty">—</td>
      ${qtyMetaPlaceholderCells()}
      ${lotPackPlaceholderCell()}
      <td class="lw-col-time">—</td>
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const bomInput = tr.querySelector('.lw-new-bom');
    const operatorSel = tr.querySelector('.lw-new-operator');
    const tryCommit = () => tryCommitCleaningNewRow(bomInput, operatorSel);

    bomInput?.addEventListener('input', () => {
      const nameEl = tr.querySelector('.lw-new-bom-name');
      if (nameEl) nameEl.textContent = partNameFor(bomInput.value) || '';
    });
    bomInput?.addEventListener('change', tryCommit);
    operatorSel?.addEventListener('change', tryCommit);
    bomInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        tryCommit();
      }
    });
  }

  async function tryCommitCleaningNewRow(bomInput, operatorSel) {
    const bomNo = (bomInput?.value || '').trim();
    const operatorId = parseInt(operatorSel?.value, 10);
    if (!bomNo || !operatorId) return;

    const partMatch = _parts.find(p => partNoKey(p) === bomNo.toLowerCase());
    if (!partMatch) {
      showSnackbar('BOM not found or has no lots pending inspection', 'error');
      return;
    }
    const bomId = partMatch.bomId || partMatch.bom_id;
    if (!bomId) {
      showSnackbar('BOM id missing for selected part', 'error');
      return;
    }

    try {
      await apiPost('/api/laser-welding/cleaning/pending', {
        bomId,
        operatorId,
        operatorIds: [operatorId],
        workDate: _workDate,
        subAssemblyPartNo: partMatch.isSubAssembly ? (partMatch.subAssemblyPartNo || bomNo) : undefined,
      });
      bomInput.value = '';
      if (operatorSel) operatorSel.value = '';
      const nameEl = bomInput.closest('tr')?.querySelector('.lw-new-bom-name');
      if (nameEl) nameEl.textContent = '';
      invalidateLwCaches();
      await loadGridRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add row', 'error');
    }
  }

  async function tryCommitNewRow(partInput, operatorSel) {
    const partNumber = (partInput?.value || '').trim();
    const operatorId = parseInt(operatorSel?.value, 10);
    if (!partNumber || !operatorId) return;

    const partMatch = _parts.find(p => partNoKey(p) === partNumber.toLowerCase());
    if (_tab === 'packing' && !partMatch) {
      showSnackbar('Part not found or has no lots ready for packing', 'error');
      return;
    }

    if (_tab === 'inspection') {
      if (!partMatch) {
        showSnackbar('Part not found or has no lots with available stock', 'error');
        return;
      }
      const lotInfo = await fetchSourceLots(partNumber);
      if (partIsBo(partNumber)) {
        if (lotInfo.availableQty <= 0) {
          showSnackbar('No inventory stock available for this part', 'warning');
          return;
        }
      } else if (!lotInfo.lots.length) {
        showSnackbar('No lots with available stock for this part', 'warning');
        return;
      }
    }

    const pendingUrl = _tab === 'qa'
      ? '/api/laser-welding/qa/pending'
      : _tab === 'packing'
        ? '/api/laser-welding/packing/pending'
        : '/api/laser-welding/child-parts/pending';

    try {
      await apiPost(pendingUrl, {
        partNumber,
        operatorId,
        operatorIds: [operatorId],
        workDate: _workDate,
      });
      partInput.value = '';
      if (operatorSel) operatorSel.value = '';
      const nameEl = partInput.closest('tr')?.querySelector('.lw-new-part-name');
      if (nameEl) nameEl.textContent = '';
      await loadGridRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add row', 'error');
    }
  }

  function renderTable() {
    const tbody = $('#lw-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    tableDisplayRows().forEach(row => {
      tbody.appendChild(buildDataRow(row));
      if (_expanded[row.rowKey]) {
        tbody.appendChild(buildDetailRow(row));
      }
    });
    if (_tab === 'qa') {
      filteredEligibleRows(_qaEligibleRows).forEach(row => {
        tbody.appendChild(buildEligibleQaRow(row));
      });
    }
    appendNewRow(tbody);
    updateRowCount();
  }

  async function fetchSourceLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return { lots: [], boMode: false, availableQty: 0 };
    const data = await apiFetch('/api/laser-welding/source-lots?partNo=' + encodeURIComponent(pn));
    _sourceLotsCache[pn] = {
      lots: data.lots || [],
      boMode: !!data.boMode,
      availableQty: Number(data.availableQty) || 0,
    };
    return sourceLotsInfo(pn);
  }

  async function fetchQaSourceLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    const data = await apiFetch('/api/laser-welding/qa/source-lots?partNo=' + encodeURIComponent(pn));
    _qaLotsCache[pn] = data.lots || [];
    return _qaLotsCache[pn];
  }

  async function fetchPackingSourceLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    const data = await apiFetch('/api/laser-welding/packing/source-lots?partNo=' + encodeURIComponent(pn));
    _packingLotsCache[pn] = data.lots || [];
    return _packingLotsCache[pn];
  }

  async function fetchCleaningSourceLots(bomId, subAssemblyPartNo) {
    const bid = String(bomId || '').trim();
    if (!bid) return [];
    const saPart = String(subAssemblyPartNo || '').trim();
    const cacheKey = saPart ? `${bid}:${saPart}` : bid;
    let url = '/api/laser-welding/cleaning/source-lots?bomId=' + encodeURIComponent(bid);
    if (saPart) url += '&subAssemblyPartNo=' + encodeURIComponent(saPart);
    const data = await apiFetch(url);
    _cleaningLotsCache[cacheKey] = data.lots || [];
    return _cleaningLotsCache[cacheKey];
  }

  function cleaningLotsCacheKey() {
    const bid = bomIdKey(_prodModalBomId);
    if (_prodModalSubAssemblyPartNo) return `${bid}:${_prodModalSubAssemblyPartNo}`;
    return bid;
  }

  function packMaterialOptionsHtml(items, selectedCode) {
    let html = '<option value="">Select item…</option>';
    (items || []).forEach(item => {
      const code = String(item.itemCode || '').trim();
      if (!code) return;
      const sel = code === String(selectedCode || '').trim() ? ' selected' : '';
      const avail = Number(item.availableQty) || 0;
      const label = item.label || code;
      html += `<option value="${escapeAttr(code)}"${sel}>${escapeHtml(label)} (avail: ${avail})</option>`;
    });
    return html;
  }

  function updatePackMaterialAvailability(kind) {
    const isTray = kind === 'tray';
    const sel = $(isTray ? '#lw-prod-tray-item' : '#lw-prod-carton-item');
    const availEl = $(isTray ? '#lw-prod-tray-avail' : '#lw-prod-carton-avail');
    const qtyInp = $(isTray ? '#lw-prod-tray-qty' : '#lw-prod-carton-qty');
    const items = isTray ? (_packMaterials.trays || []) : (_packMaterials.cartons || []);
    const code = String(sel?.value || '').trim();
    const match = items.find(item => String(item.itemCode || '').trim() === code);
    const avail = Number(match?.availableQty) || 0;
    if (availEl) availEl.textContent = code ? String(avail) : '—';
    if (qtyInp && avail > 0) qtyInp.max = String(avail);
    else if (qtyInp) qtyInp.removeAttribute('max');
  }

  function renderPackMaterialSelects() {
    const traySel = $('#lw-prod-tray-item');
    const cartonSel = $('#lw-prod-carton-item');
    const cartonRow = cartonSel?.closest('.lw-pack-material-row');
    const mapping = _packMaterials.mapping;
    const mappedTray = String(mapping?.trayItemCode || '').trim();
    const mappedCarton = String(mapping?.cartonItemCode || '').trim();
    const hasMapping = !!_packMaterials.hasMapping;

    let trayDefault = hasMapping ? mappedTray : '';
    let cartonDefault = hasMapping ? mappedCarton : '';

    if (traySel) {
      traySel.innerHTML = packMaterialOptionsHtml(_packMaterials.trays, trayDefault);
      if (trayDefault) traySel.value = trayDefault;
      traySel.disabled = hasMapping && !!mappedTray;
    }

    if (cartonSel) {
      if (hasMapping && !mappedCarton) {
        if (cartonRow) cartonRow.style.display = 'none';
        cartonSel.innerHTML = packMaterialOptionsHtml([], '');
        cartonSel.value = '';
        cartonSel.disabled = true;
      } else {
        if (cartonRow) cartonRow.style.display = '';
        cartonSel.innerHTML = packMaterialOptionsHtml(_packMaterials.cartons, cartonDefault);
        if (cartonDefault) cartonSel.value = cartonDefault;
        cartonSel.disabled = hasMapping && !!mappedCarton;
      }
    }

    updatePackMaterialAvailability('tray');
    updatePackMaterialAvailability('carton');
  }

  async function loadPackMaterials(partNo) {
    const pn = String(partNo || '').trim();
    const q = pn ? `?partNo=${encodeURIComponent(pn)}` : '';
    const data = await apiFetch('/api/laser-welding/packing/pack-materials' + q);
    _packMaterials = {
      trays: data.trays || (data.materials || []).filter(m => m.type === 'tray'),
      cartons: data.cartons || (data.materials || []).filter(m => m.type === 'carton'),
      hasMapping: !!data.hasMapping,
      mapping: data.mapping || null,
    };
    renderPackMaterialSelects();
  }

  function filteredTraysCartonRows() {
    const q = _filterQuery.trim().toLowerCase();
    if (!q) return _traysCartonRows;
    return _traysCartonRows.filter(r => {
      const hay = [
        r.customerName, r.partNumber, r.partName,
        r.trayItemCode, r.cartonItemCode,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  async function ensureTcLegend() {
    if (_tcLegend) return _tcLegend;
    _tcLegend = await apiFetch('/api/laser-welding/packing/trays-carton/legend');
    return _tcLegend;
  }

  async function loadTcPartsCatalog() {
    const data = await apiFetch('/api/laser-welding/packing/trays-carton/parts');
    _tcPartsList = data.parts || [];
    return _tcPartsList;
  }

  function filteredTcParts(custId) {
    const cid = custId ? Number(custId) : null;
    if (!cid) return _tcPartsList;
    return _tcPartsList.filter(p => Number(p.custId) === cid);
  }

  function tcPartFromCatalog(partNo, custId) {
    const pn = String(partNo || '').trim();
    const cid = custId != null && custId !== ''
      ? Number(custId)
      : Number($('#lw-tc-cust')?.value || 0) || null;
    const matches = _tcPartsList.filter(p => String(p.partNo || '').trim() === pn);
    if (!matches.length) return null;
    if (cid) return matches.find(p => Number(p.custId) === cid) || matches[0];
    return matches[0];
  }

  function populateTcPartSelect(custId, selectedPartNo) {
    const sel = $('#lw-tc-part');
    if (!sel) return;
    const selPn = String(selectedPartNo || '').trim();
    let html = '<option value="">Select part…</option>';
    filteredTcParts(custId).forEach(p => {
      const pn = String(p.partNo || '').trim();
      if (!pn) return;
      const label = `${pn} — ${p.partName || ''}`.trim();
      const selected = pn === selPn ? ' selected' : '';
      html += `<option value="${escapeAttr(pn)}"${selected}>${escapeHtml(label)}</option>`;
    });
    sel.innerHTML = html;
    if (selPn && !sel.value) sel.value = selPn;
  }

  function refreshTcPartSelect() {
    const custId = $('#lw-tc-cust')?.value || '';
    const prev = $('#lw-tc-part')?.value || '';
    populateTcPartSelect(custId, prev);
    const stillValid = !prev || filteredTcParts(custId).some(p => String(p.partNo || '').trim() === prev);
    if (!stillValid) {
      if ($('#lw-tc-part')) $('#lw-tc-part').value = '';
      if ($('#lw-tc-part-name')) $('#lw-tc-part-name').value = '';
    }
  }

  function renderTraysCartonTable() {
    const tbody = $('#lw-tc-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    const rows = filteredTraysCartonRows();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="lw-detail-empty">No tray/carton mappings yet.</td></tr>';
      updateRowCount();
      return;
    }
    rows.forEach(row => {
      const tr = document.createElement('tr');
      tr.dataset.mapId = String(row.mapId || '');
      tr.innerHTML = `
        <td>${escapeHtml(row.customerName || '—')}</td>
        <td class="val-bold">${escapeHtml(row.partNumber || '—')}</td>
        <td>${escapeHtml(row.partName || '—')}</td>
        <td>${escapeHtml(row.trayItemCode || '—')}</td>
        <td>${escapeHtml(row.cartonItemCode || '—')}</td>
        <td>${row.trayCavity != null ? row.trayCavity : '—'}</td>
        <td>${row.trayCapacity != null ? row.trayCapacity : '—'}</td>
        <td>${row.cartonCapacity != null ? row.cartonCapacity : '—'}</td>
        <td class="lw-actions-cell">
          ${canEdit()
            ? `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-tc-edit" data-map-id="${escapeAttr(row.mapId)}">Edit</button>`
            : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });
    updateRowCount();
  }

  async function loadTraysCartonTab(preserveFilter) {
    const loadingEl = $('#lw-tc-loading');
    const errorEl = $('#lw-tc-error');
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';
    try {
      await Promise.all([
        loadBomCatalog(),
        loadTcPartsCatalog(),
        ensureTcLegend(),
      ]);
      const data = await apiFetch('/api/laser-welding/packing/trays-carton');
      _traysCartonRows = data.rows || [];
      if (!preserveFilter) {
        _filterQuery = '';
        const search = $('#lw-grid-search');
        if (search) search.value = '';
      }
      renderTraysCartonTable();
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load tray/carton mappings';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
    }
  }

  function populateTcCustomerSelect(selectedId) {
    const sel = $('#lw-tc-cust');
    if (!sel) return;
    let html = '<option value="">Select customer…</option>';
    _bomCustomers.forEach(c => {
      const selAttr = Number(selectedId) === Number(c.custId) ? ' selected' : '';
      html += `<option value="${c.custId}"${selAttr}>${escapeHtml(c.customerName || '')}</option>`;
    });
    sel.innerHTML = html;
  }

  function tcCustId() {
    const v = parseInt($('#lw-tc-cust')?.value, 10);
    return Number.isFinite(v) && v > 0 ? v : null;
  }

  function tcCustomerName() {
    const cid = tcCustId();
    if (!cid) return '';
    const c = _bomCustomers.find(x => Number(x.custId) === cid);
    return String(c?.customerName || '').trim();
  }

  function tcTrayTypeCode() {
    const mode = ($('#lw-tc-type-mode')?.value || 'S').trim().toUpperCase();
    if (mode === 'S') return 'S';
    const n = parseInt($('#lw-tc-no-parts')?.value, 10);
    return n >= 2 ? `${n}P` : '';
  }

  function defaultBinSeqForCustomer() {
    const name = tcCustomerName().toUpperCase();
    if (name.includes('ATHER')) return 1;
    if (name.includes('REML')) return 2;
    return null;
  }

  function syncTcTypeModeUi() {
    const mode = ($('#lw-tc-type-mode')?.value || 'S').trim().toUpperCase();
    const noPartsWrap = $('#lw-tc-no-parts-wrap');
    const existingWrap = $('#lw-tc-tray-existing-wrap');
    if (noPartsWrap) noPartsWrap.style.display = mode === 'P' ? '' : 'none';
    if (existingWrap) existingWrap.style.display = mode === 'P' ? '' : 'none';
    if (mode === 'S' && $('#lw-tc-tray-existing')) $('#lw-tc-tray-existing').value = '';
  }

  function syncTcBoxTypeUi() {
    const boxType = ($('#lw-tc-box-type')?.value || 'C').trim().toUpperCase();
    const binWrap = $('#lw-tc-bin-seq-wrap');
    const hint = $('#lw-tc-bin-seq-hint');
    if (binWrap) binWrap.style.display = boxType === 'B' ? '' : 'none';
    if (boxType === 'B') {
      const def = defaultBinSeqForCustomer();
      const binInp = $('#lw-tc-bin-seq');
      if (binInp && !binInp.value && def != null) binInp.value = String(def);
      if (hint) {
        hint.textContent = def != null
          ? `Default for ${tcCustomerName() || 'customer'}: ${def}`
          : '';
      }
    } else if (hint) {
      hint.textContent = '';
    }
  }

  function populateTcExistingSelect(selId, items, selectedCode) {
    const sel = $(selId);
    if (!sel) return;
    const prev = selectedCode || sel.value || '';
    let html = '<option value="">Generate new code</option>';
    (items || []).forEach(item => {
      const code = String(item.itemCode || '').trim();
      if (!code) return;
      const selected = code === prev ? ' selected' : '';
      html += `<option value="${escapeAttr(code)}"${selected}>${escapeHtml(code)}</option>`;
    });
    sel.innerHTML = html;
    if (prev) sel.value = prev;
  }

  async function refreshTcExistingTrays() {
    const mode = ($('#lw-tc-type-mode')?.value || 'S').trim().toUpperCase();
    const sel = $('#lw-tc-tray-existing');
    if (mode !== 'P' || !sel) {
      populateTcExistingSelect('#lw-tc-tray-existing', [], '');
      return;
    }
    const trayType = tcTrayTypeCode();
    const cavity = parseInt($('#lw-tc-tray-cavity')?.value, 10) || 0;
    if (!trayType || cavity <= 0) {
      populateTcExistingSelect('#lw-tc-tray-existing', [], sel.value);
      return;
    }
    const q = new URLSearchParams({ trayType, cavity: String(cavity) });
    const custId = tcCustId();
    if (custId) q.set('custId', String(custId));
    try {
      const data = await apiFetch('/api/laser-welding/packing/trays-carton/matching-trays?' + q.toString());
      populateTcExistingSelect('#lw-tc-tray-existing', data.items || [], sel.value);
    } catch (_) {
      populateTcExistingSelect('#lw-tc-tray-existing', [], sel.value);
    }
  }

  function tcPreviewTrayBody() {
    const existing = ($('#lw-tc-tray-existing')?.value || '').trim();
    const mode = ($('#lw-tc-type-mode')?.value || 'S').trim().toUpperCase();
    const body = {
      kind: 'tray',
      typeMode: mode,
      noParts: parseInt($('#lw-tc-no-parts')?.value, 10) || undefined,
      cavity: parseInt($('#lw-tc-tray-cavity')?.value, 10),
      custId: tcCustId(),
    };
    if (mode === 'P' && existing) body.existingItemCode = existing;
    if (mode === 'S' && _tcEditTraySeq != null) body.seq = _tcEditTraySeq;
    return body;
  }

  function tcPreviewBoxBody() {
    const boxType = ($('#lw-tc-box-type')?.value || 'C').trim().toUpperCase();
    const body = {
      kind: 'box',
      boxType,
      lengthMm: parseInt($('#lw-tc-box-l')?.value, 10),
      widthMm: parseInt($('#lw-tc-box-w')?.value, 10),
      heightMm: parseInt($('#lw-tc-box-h')?.value, 10),
      custId: tcCustId(),
    };
    if (boxType === 'B') {
      const binSeq = parseInt($('#lw-tc-bin-seq')?.value, 10);
      body.binSeq = Number.isFinite(binSeq) && binSeq > 0
        ? binSeq
        : (_tcEditBinSeq != null ? _tcEditBinSeq : defaultBinSeqForCustomer());
    }
    return body;
  }

  async function previewTcTray() {
    syncTcTypeModeUi();
    const body = tcPreviewTrayBody();
    const existing = ($('#lw-tc-tray-existing')?.value || '').trim();
    const previewEl = $('#lw-tc-tray-preview');
    if (!previewEl) return;
    if (body.typeMode === 'P' && existing) {
      previewEl.textContent = existing;
      return;
    }
    if (!body.cavity) {
      previewEl.textContent = '—';
      return;
    }
    try {
      const data = await apiPost('/api/laser-welding/packing/trays-carton/preview', body);
      previewEl.textContent = data.itemCode || '—';
    } catch (_) {
      previewEl.textContent = '—';
    }
  }

  async function previewTcBox() {
    syncTcBoxTypeUi();
    const body = tcPreviewBoxBody();
    const previewEl = $('#lw-tc-box-preview');
    if (!previewEl) return;
    if (!body.lengthMm || !body.widthMm || !body.heightMm) {
      previewEl.textContent = '—';
      return;
    }
    try {
      const data = await apiPost('/api/laser-welding/packing/trays-carton/preview', body);
      previewEl.textContent = data.itemCode || '—';
      if (data.binSeq != null && body.boxType === 'B' && !$('#lw-tc-bin-seq')?.value) {
        $('#lw-tc-bin-seq').value = String(data.binSeq);
      }
    } catch (_) {
      previewEl.textContent = '—';
    }
  }

  function scheduleTcPreview() {
    clearTimeout(_tcPreviewTimer);
    _tcPreviewTimer = setTimeout(() => {
      void refreshTcExistingTrays().then(() => previewTcTray());
      void previewTcBox();
    }, 250);
  }

  function onTcPartChange() {
    const partNo = ($('#lw-tc-part')?.value || '').trim();
    const custId = tcCustId();
    const cached = partNo ? tcPartFromCatalog(partNo, custId) : null;
    if ($('#lw-tc-part-name')) {
      $('#lw-tc-part-name').value = cached?.partName || '';
    }
    if (cached?.custId && $('#lw-tc-cust') && !$('#lw-tc-cust').value) {
      $('#lw-tc-cust').value = String(cached.custId);
      refreshTcPartSelect();
    }
  }

  async function openTcModal(row) {
    const overlay = $('#lw-tc-modal-overlay');
    if (!overlay) return;
    await Promise.all([loadBomCatalog(), ensureTcLegend(), loadTcPartsCatalog()]);
    _tcEditTraySeq = null;
    _tcEditBinSeq = null;
    populateTcCustomerSelect(row?.custId);
    if ($('#lw-tc-map-id')) $('#lw-tc-map-id').value = row?.mapId ? String(row.mapId) : '';
    populateTcPartSelect(row?.custId, row?.partNumber || '');
    if ($('#lw-tc-part') && row?.partNumber) $('#lw-tc-part').value = row.partNumber;
    if ($('#lw-tc-part-name')) {
      $('#lw-tc-part-name').value = row?.partName || tcPartFromCatalog(row?.partNumber, row?.custId)?.partName || '';
    }
    if ($('#lw-tc-tray-capacity')) {
      $('#lw-tc-tray-capacity').value = row?.trayCapacity != null ? String(row.trayCapacity) : '';
    }
    if ($('#lw-tc-carton-capacity')) {
      $('#lw-tc-carton-capacity').value = row?.cartonCapacity != null ? String(row.cartonCapacity) : '';
    }
    if ($('#lw-tc-type-mode')) $('#lw-tc-type-mode').value = 'S';
    if ($('#lw-tc-no-parts')) $('#lw-tc-no-parts').value = '';
    populateTcExistingSelect('#lw-tc-tray-existing', [], '');
    if (row?.trayItemCode) {
      const m = row.trayItemCode.match(/^SE-(\d)-((?:\d+P|S))-(\d+)C-(\d+)$/);
      if (m) {
        const ttype = m[2];
        if (ttype === 'S') {
          if ($('#lw-tc-type-mode')) $('#lw-tc-type-mode').value = 'S';
          _tcEditTraySeq = parseInt(m[4], 10);
        } else {
          if ($('#lw-tc-type-mode')) $('#lw-tc-type-mode').value = 'P';
          const np = parseInt(ttype.replace(/P$/, ''), 10);
          if ($('#lw-tc-no-parts')) $('#lw-tc-no-parts').value = String(np);
          populateTcExistingSelect('#lw-tc-tray-existing', [{ itemCode: row.trayItemCode }], row.trayItemCode);
        }
        if ($('#lw-tc-tray-cavity')) $('#lw-tc-tray-cavity').value = m[3];
      }
    } else if ($('#lw-tc-tray-cavity')) {
      $('#lw-tc-tray-cavity').value = '';
    }
    if (row?.cartonItemCode) {
      const c = row.cartonItemCode;
      const binM = c.match(/^SE-B-(\d{3})(\d{3})(\d{3})-(\d+)$/);
      const cartM = c.match(/^SE-C-(\d{3})(\d{3})(\d{3})$/);
      if (binM) {
        if ($('#lw-tc-box-type')) $('#lw-tc-box-type').value = 'B';
        if ($('#lw-tc-box-l')) $('#lw-tc-box-l').value = String(parseInt(binM[1], 10));
        if ($('#lw-tc-box-w')) $('#lw-tc-box-w').value = String(parseInt(binM[2], 10));
        if ($('#lw-tc-box-h')) $('#lw-tc-box-h').value = String(parseInt(binM[3], 10));
        if ($('#lw-tc-bin-seq')) $('#lw-tc-bin-seq').value = binM[4];
        _tcEditBinSeq = parseInt(binM[4], 10);
      } else if (cartM) {
        if ($('#lw-tc-box-type')) $('#lw-tc-box-type').value = 'C';
        if ($('#lw-tc-box-l')) $('#lw-tc-box-l').value = String(parseInt(cartM[1], 10));
        if ($('#lw-tc-box-w')) $('#lw-tc-box-w').value = String(parseInt(cartM[2], 10));
        if ($('#lw-tc-box-h')) $('#lw-tc-box-h').value = String(parseInt(cartM[3], 10));
      }
    } else {
      if ($('#lw-tc-box-type')) $('#lw-tc-box-type').value = 'C';
      ['lw-tc-box-l', 'lw-tc-box-w', 'lw-tc-box-h', 'lw-tc-bin-seq'].forEach(id => {
        const el = $(`#${id}`);
        if (el) el.value = '';
      });
    }
    syncTcTypeModeUi();
    syncTcBoxTypeUi();
    await refreshTcExistingTrays();
    await previewTcTray();
    await previewTcBox();
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeTcModal() {
    const overlay = $('#lw-tc-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
  }

  async function saveTcModal() {
    if (!canEdit()) return;
    const mapId = ($('#lw-tc-map-id')?.value || '').trim();
    const partNo = ($('#lw-tc-part')?.value || '').trim();
    const custId = tcCustId();
    const typeMode = ($('#lw-tc-type-mode')?.value || 'S').trim().toUpperCase();
    const noParts = parseInt($('#lw-tc-no-parts')?.value, 10);
    const trayCapacity = parseInt($('#lw-tc-tray-capacity')?.value, 10);
    const cartonCapacity = parseInt($('#lw-tc-carton-capacity')?.value, 10);
    const boxType = ($('#lw-tc-box-type')?.value || 'C').trim().toUpperCase();
    const boxL = parseInt($('#lw-tc-box-l')?.value, 10);
    const boxW = parseInt($('#lw-tc-box-w')?.value, 10);
    const boxH = parseInt($('#lw-tc-box-h')?.value, 10);
    const hasBox = boxL > 0 && boxW > 0 && boxH > 0;
    const trayExisting = ($('#lw-tc-tray-existing')?.value || '').trim();
    const catalogPart = tcPartFromCatalog(partNo, custId);
    const payload = {
      partNumber: partNo,
      partName: ($('#lw-tc-part-name')?.value || '').trim(),
      custId,
      coId: catalogPart?.coId ?? undefined,
      bomId: catalogPart?.bomId ?? undefined,
      cartonCapacity: Number.isFinite(cartonCapacity) && cartonCapacity > 0 ? cartonCapacity : null,
      tray: {
        typeMode,
        noParts: typeMode === 'P' && Number.isFinite(noParts) ? noParts : undefined,
        cavity: parseInt($('#lw-tc-tray-cavity')?.value, 10),
        trayCapacity: Number.isFinite(trayCapacity) && trayCapacity > 0 ? trayCapacity : null,
        existingItemCode: typeMode === 'P' && trayExisting ? trayExisting : undefined,
        seq: typeMode === 'S' && _tcEditTraySeq != null ? _tcEditTraySeq : undefined,
      },
      carton: hasBox ? {
        boxType,
        lengthMm: boxL,
        widthMm: boxW,
        heightMm: boxH,
        binSeq: boxType === 'B'
          ? (parseInt($('#lw-tc-bin-seq')?.value, 10) || _tcEditBinSeq || defaultBinSeqForCustomer() || undefined)
          : undefined,
      } : {},
    };
    try {
      if (mapId) {
        await apiFetch('/api/laser-welding/packing/trays-carton/' + encodeURIComponent(mapId), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        await apiPost('/api/laser-welding/packing/trays-carton', payload);
      }
      showSnackbar('Tray/carton mapping saved', 'success');
      closeTcModal();
      await loadTraysCartonTab(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to save mapping', 'error');
    }
  }

  function onTcTableClick(e) {
    const editBtn = e.target.closest('.lw-tc-edit');
    if (editBtn) {
      const mapId = editBtn.getAttribute('data-map-id');
      const row = _traysCartonRows.find(r => String(r.mapId) === String(mapId));
      if (row) void openTcModal(row);
    }
  }

  function prodLotOptionsHtml(partNo, selectedLot, usedLots, selectedTargetId, usedTargetIds) {
    if (_prodModalMode === 'sa_cleaning' || _prodModalMode === 'lw_cleaning') {
      const lots = _cleaningLotsCache[cleaningLotsCacheKey()] || [];
      let html = '<option value="">Select lot…</option>';
      lots.forEach(l => {
        const lotId = Number(l.lotId);
        const lotNo = l.newLotNo || '';
        if (!lotId || !lotNo) return;
        if (usedTargetIds.has(lotId) && lotId !== Number(selectedTargetId)) return;
        const sel = lotId === Number(selectedTargetId) ? ' selected' : '';
        const pending = Number(l.inspectionPending || l.noOfComp) || 0;
        html += `<option value="${lotId}"${sel}>${escapeHtml(lotNo)} (pending: ${pending})</option>`;
      });
      return html;
    }

    if (_prodModalMode === 'qa') {
      const lots = _qaLotsCache[partNo] || [];
      let html = '<option value="">Select lot…</option>';
      lots.forEach(l => {
        const lotId = Number(l.lotId);
        const lotNo = l.newLotNo || '';
        if (!lotId || !lotNo) return;
        if (usedTargetIds.has(lotId) && lotId !== Number(selectedTargetId)) return;
        const sel = lotId === Number(selectedTargetId) ? ' selected' : '';
        const qa = Number(l.totalQa || l.noOfComp) || 0;
        html += `<option value="${lotId}"${sel}>${escapeHtml(lotNo)} (QA: ${qa})</option>`;
      });
      return html;
    }

    if (_prodModalMode === 'packing') {
      const lots = _packingLotsCache[partNo] || [];
      let html = '<option value="">Select lot…</option>';
      lots.forEach(l => {
        const lotId = Number(l.lotId);
        const lotNo = l.newLotNo || '';
        if (!lotId || !lotNo) return;
        if (usedTargetIds.has(lotId) && lotId !== Number(selectedTargetId)) return;
        const sel = lotId === Number(selectedTargetId) ? ' selected' : '';
        const avail = Number(l.totalOkayed || l.noOfComp) || 0;
        html += `<option value="${lotId}"${sel}>${escapeHtml(lotNo)} (avail: ${avail})</option>`;
      });
      return html;
    }

    const lots = sourceLotsInfo(partNo).lots;
    let html = '<option value="">Select lot…</option>';
    lots.forEach(l => {
      const lotNo = l.lotNo;
      if (!lotNo) return;
      if (usedLots.has(lotNo) && lotNo !== selectedLot) return;
      const sel = lotNo === selectedLot ? ' selected' : '';
      html += `<option value="${escapeAttr(lotNo)}"${sel}>${escapeHtml(lotNo)}</option>`;
    });
    return html;
  }

  function isModalLineEmpty(ln) {
    if (_prodModalMode === 'qa') {
      return !ln?.targetLotId
        && Number(ln?.qaPassed) <= 0 && Number(ln?.scrapQty) <= 0 && Number(ln?.reworkQty) <= 0;
    }
    if (_prodModalMode === 'packing') {
      return !ln?.targetLotId
        && Number(ln?.inspectedQty) <= 0 && Number(ln?.packQty) <= 0
        && Number(ln?.qaQty) <= 0 && Number(ln?.scrapQty) <= 0;
    }
    return !ln?.sourceLotNo && !ln?.targetLotId
      && Number(ln?.inspectedQty) <= 0 && Number(ln?.qaQty) <= 0 && Number(ln?.scrapQty) <= 0;
  }

  function ensureProdModalTrailingLine() {
    const last = _prodModalLines[_prodModalLines.length - 1];
    const hasLot = last && (last.sourceLotNo || last.targetLotId);
    if (!last || hasLot) {
      _prodModalLines.push(emptyLine());
    }
  }

  function syncProdScrapRemarkVisibility(idx) {
    const scrap = parseInt($(`.lw-prod-line-scrap[data-idx="${idx}"]`)?.value, 10) || 0;
    const wrap = $(`.lw-prod-scrap-remark-wrap[data-idx="${idx}"]`);
    if (wrap) wrap.style.display = scrap > 0 ? '' : 'none';
  }

  function syncProdLineQtyCaps(idx, changedField) {
    if (_prodModalMode === 'qa') {
      syncQaLineCaps(idx);
      return;
    }
    if (_prodModalMode === 'packing') {
      syncPackLineCaps(idx);
      return;
    }

    if (_prodModalIsBo && _prodModalMode === 'production') {
      const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
      const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
      if (!inspInp || !scrapInp) return;

      const maxAvail = Number(inspInp.max) || 0;
      let insp = parseInt(inspInp.value, 10);
      let scrap = parseInt(scrapInp.value, 10);
      if (Number.isNaN(insp) || insp < 0) insp = 0;
      if (Number.isNaN(scrap) || scrap < 0) scrap = 0;

      if (maxAvail > 0 && insp > maxAvail) {
        insp = maxAvail;
        inspInp.value = String(insp);
        showSnackbar('Inspected QTY cannot exceed available quantity', 'warning');
      }
      if (scrap > insp) {
        scrap = insp;
        showSnackbar('Scrap cannot exceed Inspected QTY', 'warning');
      }
      scrapInp.value = String(scrap);
      scrapInp.max = String(insp);
      syncProdScrapRemarkVisibility(idx);

      if (_prodModalLines[idx]) {
        _prodModalLines[idx].inspectedQty = insp;
        _prodModalLines[idx].qaQty = 0;
        _prodModalLines[idx].scrapQty = scrap;
      }
      return;
    }

    const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
    const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
    const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
    if (!inspInp || !qaInp || !scrapInp) return;

    const maxAvail = Number(inspInp.max) || 0;
    let insp = parseInt(inspInp.value, 10);
    if (Number.isNaN(insp) || insp < 0) insp = 0;
    if (maxAvail > 0 && insp > maxAvail) {
      insp = maxAvail;
      inspInp.value = String(insp);
      showSnackbar('Inspected QTY cannot exceed available quantity', 'warning');
    }

    let qa = parseInt(qaInp.value, 10);
    let scrap = parseInt(scrapInp.value, 10);
    if (Number.isNaN(qa) || qa < 0) qa = 0;
    if (Number.isNaN(scrap) || scrap < 0) scrap = 0;

    if (changedField === 'insp') {
      if (qa + scrap > insp) {
        insp = qa + scrap;
        if (maxAvail > 0 && insp > maxAvail) {
          insp = maxAvail;
          showSnackbar('Inspected QTY cannot exceed available quantity', 'warning');
        } else {
          showSnackbar('Inspected QTY must be at least QA + Scrap', 'warning');
        }
        inspInp.value = String(insp);
      }
    } else if (changedField === 'qa') {
      const maxQa = Math.max(0, insp - scrap);
      if (qa > maxQa) {
        qa = maxQa;
        showSnackbar('QA + Scrap cannot exceed Inspected QTY', 'warning');
      }
    } else if (changedField === 'scrap') {
      const maxScrap = Math.max(0, insp - qa);
      if (scrap > maxScrap) {
        scrap = maxScrap;
        showSnackbar('QA + Scrap cannot exceed Inspected QTY', 'warning');
      }
    }

    qaInp.value = String(qa);
    scrapInp.value = String(scrap);
    qaInp.max = String(Math.max(0, insp - scrap));
    scrapInp.max = String(Math.max(0, insp - qa));
    syncProdScrapRemarkVisibility(idx);

    if (_prodModalLines[idx]) {
      _prodModalLines[idx].inspectedQty = insp;
      _prodModalLines[idx].qaQty = qa;
      _prodModalLines[idx].scrapQty = scrap;
    }
  }

  function syncQaLineCaps(idx) {
    const passedInp = $(`.lw-prod-line-passed[data-idx="${idx}"]`);
    const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
    const reworkInp = $(`.lw-prod-line-rework[data-idx="${idx}"]`);
    if (!passedInp || !scrapInp || !reworkInp) return;

    const max = Number(passedInp.max) || 0;
    let passed = parseInt(passedInp.value, 10) || 0;
    let scrap = parseInt(scrapInp.value, 10) || 0;
    let rework = parseInt(reworkInp.value, 10) || 0;

    if (max > 0 && passed + scrap + rework > max) {
      if (passed > max) passed = max;
      const remainder = max - passed;
      if (scrap + rework > remainder) {
        scrap = Math.min(scrap, remainder);
        rework = remainder - scrap;
      }
      showSnackbar('Passed + Scrap + Rework cannot exceed QA quantity', 'warning');
    }

    passedInp.value = String(passed);
    scrapInp.value = String(scrap);
    reworkInp.value = String(rework);

    const scrapWrap = $(`.lw-prod-scrap-remark-wrap[data-idx="${idx}"]`);
    const reworkWrap = $(`.lw-prod-rework-remark-wrap[data-idx="${idx}"]`);
    if (scrapWrap) scrapWrap.style.display = scrap > 0 ? '' : 'none';
    if (reworkWrap) reworkWrap.style.display = rework > 0 ? '' : 'none';

    if (_prodModalLines[idx]) {
      _prodModalLines[idx].qaPassed = passed;
      _prodModalLines[idx].scrapQty = scrap;
      _prodModalLines[idx].reworkQty = rework;
    }
  }

  function syncPackLineCaps(idx) {
    const consumedInp = $(`.lw-prod-line-pack[data-idx="${idx}"]`);
    const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
    const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
    if (!consumedInp) return;

    const max = Number(consumedInp.max) || 0;
    let consumed = parseInt(consumedInp.value, 10) || 0;
    let qa = parseInt(qaInp?.value, 10) || 0;
    let scrap = parseInt(scrapInp?.value, 10) || 0;

    if (max > 0 && consumed > max) {
      consumed = max;
      consumedInp.value = String(consumed);
      showSnackbar('Consumed cannot exceed available quantity', 'warning');
    }
    if (qa + scrap > consumed) {
      const remainder = consumed;
      if (qa > remainder) qa = remainder;
      scrap = Math.min(scrap, remainder - qa);
      showSnackbar('QA + Scrap cannot exceed Consumed', 'warning');
    }

    consumedInp.value = String(consumed);
    if (qaInp) qaInp.max = String(consumed);
    if (scrapInp) scrapInp.max = String(Math.max(0, consumed - qa));
    if (qaInp) qaInp.value = String(qa);
    if (scrapInp) scrapInp.value = String(scrap);

    const scrapWrap = $(`.lw-prod-scrap-remark-wrap[data-idx="${idx}"]`);
    if (scrapWrap) scrapWrap.style.display = scrap > 0 ? '' : 'none';

    if (_prodModalLines[idx]) {
      _prodModalLines[idx].packQty = consumed;
      _prodModalLines[idx].inspectedQty = consumed;
      _prodModalLines[idx].qaQty = qa;
      _prodModalLines[idx].scrapQty = scrap;
    }
  }

  function renderProductionModalLines() {
    const body = $('#lw-prod-modal-lines');
    if (!body) return;

    if (!(_prodModalIsBo && _prodModalMode === 'production')) {
      ensureProdModalTrailingLine();
    }

    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const usedLots = new Set(_prodModalLines.map(l => l.sourceLotNo).filter(Boolean));
    const usedTargetIds = new Set(_prodModalLines.map(l => Number(l.targetLotId)).filter(Boolean));
    const isBo = _prodModalIsBo && _prodModalMode === 'production';

    let html = '<table class="ti-table lw-prod-modal-table"><thead><tr>';

    if (_prodModalMode === 'qa') {
      html += '<th>Lot</th><th>QA QTY</th>';
      html += '<th>Passed</th><th>Scrap</th><th>Rework</th>';
      html += '<th class="lw-prod-col-remark">Remark</th><th class="lw-prod-col-remark">Rework remark</th><th class="lw-prod-col-action"></th>';
    } else if (_prodModalMode === 'packing') {
      html += '<th>Lot</th><th>Available</th><th>Consumed</th>';
      html += '<th>QA</th><th>Scrap</th>';
      html += '<th class="lw-prod-col-remark">Remark</th><th></th>';
    } else if (isBo) {
      html += '<th>Available</th>';
      html += '<th>Inspected</th><th>Scrap</th><th class="lw-prod-col-remark">Remark</th>';
    } else {
      html += '<th>Lot No</th><th>Available</th>';
      html += '<th>Inspected</th><th>QA</th><th>Scrap</th>';
      html += '<th class="lw-prod-col-remark">Remark</th><th class="lw-prod-col-action"></th>';
    }
    html += '</tr></thead><tbody>';

    if (isBo) {
      const info = sourceLotsInfo(partNo);
      const max = info.availableQty;
      const ln = _prodModalLines[0] || emptyLine();
      const insp = Number(ln.inspectedQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      const remark = escapeAttr(ln.scrapRemark || '');
      html += '<tr>';
      html += `<td class="lw-prod-line-comp" data-idx="0">${max || '—'}</td>`;
      html += `<td><input type="number" class="ti-input lw-prod-line-insp" data-idx="0" min="0" max="${max}" value="${insp}" /></td>`;
      html += `<td><input type="number" class="ti-input lw-prod-line-scrap" data-idx="0" min="0" max="${insp}" value="${scrap}" /></td>`;
      html += `<td><div class="lw-prod-scrap-remark-wrap" data-idx="0" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="0" value="${remark}" placeholder="Remark" /></div></td>`;
      html += '</tr>';
    } else {
      _prodModalLines.forEach((ln, idx) => {
        const isTrailingEmpty = idx === _prodModalLines.length - 1 && isModalLineEmpty(ln);

        if (_prodModalMode === 'qa') {
          const max = lotAvailableQty(ln);
          const passed = Number(ln.qaPassed) || 0;
          const scrap = Number(ln.scrapQty) || 0;
          const rework = Number(ln.reworkQty) || 0;
          html += '<tr>';
          html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
          html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots, ln.targetLotId, usedTargetIds);
          html += '</select></td>';
          html += `<td class="lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-passed" data-idx="${idx}" min="0" max="${max}" value="${passed}" /></td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" value="${scrap}" /></td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-rework" data-idx="${idx}" min="0" value="${rework}" /></td>`;
          html += `<td class="lw-prod-col-remark"><div class="lw-prod-scrap-remark-wrap" data-idx="${idx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="${idx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Remark" /></div></td>`;
          html += `<td class="lw-prod-col-remark"><div class="lw-prod-rework-remark-wrap" data-idx="${idx}" style="display:${rework > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-rework-remark" data-idx="${idx}" value="${escapeAttr(ln.reworkRemark || '')}" placeholder="Rework remark" /></div></td>`;
          html += !isTrailingEmpty
            ? `<td class="lw-prod-col-action"><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`
            : '<td class="lw-prod-col-action"></td>';
          html += '</tr>';
          return;
        }

        if (_prodModalMode === 'packing') {
          const max = lotAvailableQty(ln);
          const consumed = Number(ln.inspectedQty) || Number(ln.packQty) || 0;
          const qa = Number(ln.qaQty) || 0;
          const scrap = Number(ln.scrapQty) || 0;
          const scrapMax = Math.max(0, consumed - qa);
          html += '<tr>';
          html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
          html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots, ln.targetLotId, usedTargetIds);
          html += '</select></td>';
          html += `<td class="lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-pack" data-idx="${idx}" min="0" max="${max}" value="${consumed}" /></td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-qa" data-idx="${idx}" min="0" max="${consumed}" value="${qa}" /></td>`;
          html += `<td><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
          html += `<td class="lw-prod-col-remark"><div class="lw-prod-scrap-remark-wrap" data-idx="${idx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="${idx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Remark" /></div></td>`;
          html += !isTrailingEmpty
            ? `<td><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`
            : '<td></td>';
          html += '</tr>';
          return;
        }

        const max = lotAvailableQty(ln);
        const insp = Number(ln.inspectedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const scrapMax = Math.max(0, insp - qa);
        html += '<tr>';
        html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
        html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots, ln.targetLotId, usedTargetIds);
        html += '</select></td>';
        html += `<td class="lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
        html += `<td><input type="number" class="ti-input lw-prod-line-insp" data-idx="${idx}" min="0" max="${max}" value="${insp}" /></td>`;
        html += `<td><input type="number" class="ti-input lw-prod-line-qa" data-idx="${idx}" min="0" max="${insp}" value="${qa}" /></td>`;
        html += `<td><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
        html += `<td class="lw-prod-col-remark"><div class="lw-prod-scrap-remark-wrap" data-idx="${idx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="${idx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Remark" /></div></td>`;
        html += !isTrailingEmpty
          ? `<td class="lw-prod-col-action"><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`
          : '<td class="lw-prod-col-action"></td>';
        html += '</tr>';
      });
    }

    html += '</tbody></table>';
    body.innerHTML = html;
  }

  function cleaningSubAssemblyPartNo(row) {
    if (!row) return null;
    if (row.isSubAssembly) {
      return row.subAssemblyPartNo || row.partNumber || null;
    }
    const pn = String(row.partNumber || '').trim();
    if (!pn) return null;
    const match = _parts.find(p => partNoKey(p) === pn.toLowerCase() && p.isSubAssembly);
    if (match) return match.subAssemblyPartNo || match.partNo || pn;
    return null;
  }

  function prodModalModeForTab() {
    if (_tab === 'sa_cleaning') return 'sa_cleaning';
    if (_tab === 'lw_cleaning') return 'lw_cleaning';
    if (_tab === 'qa') return 'qa';
    if (_tab === 'packing') return 'packing';
    return 'production';
  }

  function prodModalTitleForMode(mode) {
    const titles = {
      production: 'Part Inspection',
      sa_cleaning: 'SA Cleaning Inspection',
      lw_cleaning: 'LW Cleaning Inspection',
      qa: 'QA Disposition',
      packing: 'Packing',
    };
    return titles[mode] || 'Inspect';
  }

  async function openProductionModal(row) {
    const overlay = $('#lw-production-modal-overlay');
    if (!overlay) return;

    const mode = prodModalModeForTab();
    _prodModalMode = mode;
    _prodModalDraftLineId = row?.draftLineId || row?.lineId || null;
    _prodModalBomId = isCleaningTab() ? (row?.bomId || bomIdForPartNo(row?.partNumber)) : null;
    _prodModalSubAssemblyPartNo = isCleaningTab() ? cleaningSubAssemblyPartNo(row) : null;

    const partNo = row?.partNumber || row?.partNo || '';
    const title = $('#lw-production-modal-title');
    const partEl = $('#lw-prod-modal-part');
    const operatorEl = $('#lw-prod-modal-operator');
    const packMatEl = $('#lw-prod-modal-pack-materials');
    const otInp = $('#lw-prod-modal-ot');

    if (title) title.textContent = prodModalTitleForMode(mode);
    if (partEl) {
      const label = isCleaningTab()
        ? `${partNo} — ${row.productName || row.partName || ''}`
        : `${partNo} — ${row.partName || partNameFor(partNo)}`;
      partEl.textContent = partNo ? label : '—';
      partEl.dataset.partNumber = partNo;
    }
    if (operatorEl) operatorEl.textContent = operatorDisplayName(row);
    if (otInp) otInp.checked = false;

    const hoursInp = $('#lw-prod-modal-hours');
    const minsInp = $('#lw-prod-modal-mins');
    if (hoursInp) hoursInp.value = '0';
    if (minsInp) minsInp.value = '0';

    if (packMatEl) packMatEl.style.display = mode === 'packing' ? '' : 'none';
    if (mode === 'packing') {
      const trayQty = $('#lw-prod-tray-qty');
      const cartonQty = $('#lw-prod-carton-qty');
      const trayItem = $('#lw-prod-tray-item');
      const cartonItem = $('#lw-prod-carton-item');
      if (trayQty) trayQty.value = '0';
      if (cartonQty) cartonQty.value = '0';
      if (trayItem) {
        trayItem.value = '';
        trayItem.disabled = false;
      }
      if (cartonItem) {
        cartonItem.value = '';
        cartonItem.disabled = false;
      }
      const cartonRow = cartonItem?.closest('.lw-pack-material-row');
      if (cartonRow) cartonRow.style.display = '';
      await loadPackMaterials(partNo);
      await fetchPackingSourceLots(partNo);
      _prodModalIsBo = false;
      _prodModalLines = [emptyLine()];
    } else if (mode === 'qa') {
      await fetchQaSourceLots(partNo);
      _prodModalIsBo = false;
      _prodModalLines = [emptyLine()];
    } else if (isCleaningTab() && _prodModalBomId) {
      await fetchCleaningSourceLots(_prodModalBomId, _prodModalSubAssemblyPartNo);
      _prodModalIsBo = false;
      _prodModalLines = [emptyLine()];
    } else {
      const lotInfo = await fetchSourceLots(partNo);
      _prodModalIsBo = partIsBo(partNo);
      if (_prodModalIsBo) {
        _prodModalLines = [{
          ...emptyLine(),
          noOfComp: lotInfo.availableQty,
          availableQty: lotInfo.availableQty,
        }];
      } else {
        _prodModalLines = [emptyLine()];
      }
    }

    renderProductionModalLines();
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeProductionModal() {
    const overlay = $('#lw-production-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _prodModalLines = [];
    _prodModalMode = 'production';
    _prodModalDraftLineId = null;
    _prodModalBomId = null;
    _prodModalIsBo = false;
    _prodModalSubAssemblyPartNo = null;
    const otInp = $('#lw-prod-modal-ot');
    if (otInp) otInp.checked = false;
    const packMatEl = $('#lw-prod-modal-pack-materials');
    if (packMatEl) packMatEl.style.display = 'none';
  }

  function collectProductionModalLines() {
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const isCleaning = _prodModalMode === 'sa_cleaning' || _prodModalMode === 'lw_cleaning';
    const isBo = _prodModalIsBo && _prodModalMode === 'production';
    const lines = [];

    if (_prodModalMode === 'qa') {
      const qaLots = _qaLotsCache[partNo] || [];
      $$('.lw-prod-line-lot').forEach(sel => {
        const idx = Number(sel.getAttribute('data-idx'));
        const targetLotId = parseInt(sel.value, 10) || null;
        const passed = parseInt($(`.lw-prod-line-passed[data-idx="${idx}"]`)?.value, 10) || 0;
        const scrap = parseInt($(`.lw-prod-line-scrap[data-idx="${idx}"]`)?.value, 10) || 0;
        const rework = parseInt($(`.lw-prod-line-rework[data-idx="${idx}"]`)?.value, 10) || 0;
        const scrapRemark = ($(`.lw-prod-line-scrap-remark[data-idx="${idx}"]`)?.value || '').trim();
        const reworkRemark = ($(`.lw-prod-line-rework-remark[data-idx="${idx}"]`)?.value || '').trim();
        const match = qaLots.find(l => Number(l.lotId) === targetLotId);
        const lotNo = match?.newLotNo || '';
        const max = Number(match?.totalQa || match?.noOfComp) || 0;
        if (passed + scrap + rework > max && max > 0) {
          throw new Error(`Passed + Scrap + Rework cannot exceed QA QTY (${max}) for lot ${lotNo || targetLotId}`);
        }
        if (targetLotId && (passed > 0 || scrap > 0 || rework > 0)) {
          if (passed + scrap + rework !== max) {
            throw new Error(`Passed + Scrap + Rework must equal QA QTY (${max}) for lot ${lotNo}`);
          }
          lines.push({
            targetLotId,
            qaPassed: passed,
            scrapQty: scrap,
            reworkQty: rework,
            scrapRemark: scrap > 0 ? scrapRemark : undefined,
            reworkRemark: rework > 0 ? reworkRemark : undefined,
          });
        }
      });
      return lines;
    }

    if (_prodModalMode === 'packing') {
      const packLots = _packingLotsCache[partNo] || [];
      $$('.lw-prod-line-lot').forEach(sel => {
        const idx = Number(sel.getAttribute('data-idx'));
        const targetLotId = parseInt(sel.value, 10) || null;
        const consumed = parseInt($(`.lw-prod-line-pack[data-idx="${idx}"]`)?.value, 10) || 0;
        const qa = parseInt($(`.lw-prod-line-qa[data-idx="${idx}"]`)?.value, 10) || 0;
        const scrap = parseInt($(`.lw-prod-line-scrap[data-idx="${idx}"]`)?.value, 10) || 0;
        const scrapRemark = ($(`.lw-prod-line-scrap-remark[data-idx="${idx}"]`)?.value || '').trim();
        const match = packLots.find(l => Number(l.lotId) === targetLotId);
        const lotNo = match?.newLotNo || '';
        const max = Number(match?.totalOkayed || match?.noOfComp) || 0;
        if (consumed > max && max > 0) {
          throw new Error(`Consumed cannot exceed available (${max}) for lot ${lotNo}`);
        }
        if (qa + scrap > consumed) {
          throw new Error(`QA + Scrap cannot exceed Consumed for lot ${lotNo || targetLotId}`);
        }
        if (targetLotId && consumed > 0) {
          lines.push({
            targetLotId,
            inspectedQty: consumed,
            qaQty: qa,
            scrapQty: scrap,
            scrapRemark: scrap > 0 ? scrapRemark : undefined,
          });
        }
      });
      return lines;
    }

    if (isBo) {
      const info = sourceLotsInfo(partNo);
      const max = info.availableQty;
      const inspInp = $('.lw-prod-line-insp[data-idx="0"]');
      const scrapInp = $('.lw-prod-line-scrap[data-idx="0"]');
      const scrapRemark = ($('.lw-prod-line-scrap-remark[data-idx="0"]')?.value || '').trim();
      const insp = parseInt(inspInp?.value, 10) || 0;
      const scrap = parseInt(scrapInp?.value, 10) || 0;
      if (scrap > insp) throw new Error('Scrap cannot exceed Inspected QTY');
      if (insp > max && max > 0) throw new Error(`Inspected QTY cannot exceed available stock (${max})`);
      if (insp > 0 || scrap > 0) {
        lines.push({
          noOfComp: max,
          availableQty: max,
          inspectedQty: insp,
          qaQty: 0,
          scrapQty: scrap,
          scrapRemark: scrap > 0 ? scrapRemark : undefined,
        });
      }
      return lines;
    }

    const asmLots = _cleaningLotsCache[cleaningLotsCacheKey()] || [];
    const erpLots = sourceLotsInfo(partNo).lots;

    $$('.lw-prod-line-lot').forEach(sel => {
      const idx = Number(sel.getAttribute('data-idx'));
      const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
      const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
      const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
      const scrapRemark = ($(`.lw-prod-line-scrap-remark[data-idx="${idx}"]`)?.value || '').trim();
      let insp = parseInt(inspInp?.value, 10) || 0;
      let qa = parseInt(qaInp?.value, 10) || 0;
      let scrap = parseInt(scrapInp?.value, 10) || 0;

      if (isCleaning) {
        const targetLotId = parseInt(sel.value, 10) || null;
        const match = asmLots.find(l => Number(l.lotId) === targetLotId);
        const lotNo = match?.newLotNo || '';
        const max = Number(match?.inspectionPending || match?.noOfComp) || 0;
        if (qa + scrap > insp) {
          throw new Error(`QA + Scrap cannot exceed Inspected QTY for lot ${lotNo || targetLotId}`);
        }
        if (insp > max && max > 0) {
          throw new Error(`Inspected QTY cannot exceed inspection pending (${max}) for lot ${lotNo}`);
        }
        if (targetLotId || insp > 0 || qa > 0 || scrap > 0) {
          if (!targetLotId) throw new Error('Select a lot for lines with quantity');
          lines.push({
            targetLotId,
            sourceLotNo: lotNo,
            noOfComp: max,
            availableQty: max,
            inspectedQty: insp,
            qaQty: qa,
            scrapQty: scrap,
            scrapRemark: scrap > 0 ? scrapRemark : undefined,
          });
        }
        return;
      }

      const lotNo = sel.value || '';
      const match = erpLots.find(l => l.lotNo === lotNo);
      const max = lotAvailableQty(match);
      if (qa + scrap > insp) {
        throw new Error(`QA + Scrap cannot exceed Inspected QTY for lot ${lotNo}`);
      }
      if (insp > max && max > 0) {
        throw new Error(`Inspected QTY cannot exceed available stock (${max}) for lot ${lotNo}`);
      }
      if (lotNo || insp > 0 || qa > 0 || scrap > 0) {
        if (!lotNo) throw new Error('Select a lot number for lines with quantity');
        lines.push({
          sourceLotNo: lotNo,
          productionDate: match?.productionDate || '',
          noOfComp: max,
          availableQty: max,
          inspectedQty: insp,
          qaQty: qa,
          scrapQty: scrap,
          scrapRemark: scrap > 0 ? scrapRemark : undefined,
        });
      }
    });
    return lines;
  }

  async function saveProductionModal() {
    const draftLineId = _prodModalDraftLineId;
    if (!draftLineId) {
      showSnackbar('Pending row not found — add part/BOM and operator first', 'warning');
      return;
    }

    let lines;
    try {
      lines = collectProductionModalLines();
    } catch (err) {
      showSnackbar(err.message, 'error');
      return;
    }

    const otFlag = $('#lw-prod-modal-ot')?.checked ? 'Y' : 'N';

    if (_prodModalMode === 'qa') {
      if (!lines.length) {
        showSnackbar('Enter at least one lot with QA disposition', 'warning');
        return;
      }
    } else if (_prodModalMode === 'packing') {
      if (!lines.length) {
        showSnackbar('Enter at least one lot with Consumed > 0', 'warning');
        return;
      }
    } else {
      const nonZero = lines.filter(l => Number(l.inspectedQty) > 0);
      if (!nonZero.length) {
        showSnackbar('Enter at least one line with Inspected QTY > 0', 'warning');
        return;
      }
    }

    const hours = parseInt($('#lw-prod-modal-hours')?.value, 10) || 0;
    const mins = parseInt($('#lw-prod-modal-mins')?.value, 10) || 0;
    if (mins < 0 || mins > 60) {
      showSnackbar('Minutes must be between 0 and 60', 'error');
      return;
    }
    const timeTakenMinutes = hours * 60 + mins;
    if (timeTakenMinutes <= 0) {
      showSnackbar('Time taken is required — enter hours and/or minutes', 'error');
      return;
    }

    let endpoint = '/api/laser-welding/child-parts/inspect';
    const payload = { draftLineId, workDate: _workDate, lines, timeTakenMinutes, otFlag };

    if (_prodModalMode === 'sa_cleaning' || _prodModalMode === 'lw_cleaning') {
      endpoint = '/api/laser-welding/cleaning/inspect';
    } else if (_prodModalMode === 'qa') {
      endpoint = '/api/laser-welding/qa/inspect';
    } else if (_prodModalMode === 'packing') {
      endpoint = '/api/laser-welding/packing/inspect';
      payload.trayQty = parseInt($('#lw-prod-tray-qty')?.value, 10) || 0;
      payload.cartonQty = parseInt($('#lw-prod-carton-qty')?.value, 10) || 0;
      payload.trayItemCode = ($('#lw-prod-tray-item')?.value || '').trim();
      payload.cartonItemCode = ($('#lw-prod-carton-item')?.value || '').trim();
      if (payload.trayQty > 0 && !payload.trayItemCode) {
        showSnackbar('Select a tray item code', 'error');
        return;
      }
      if (payload.cartonQty > 0 && !payload.cartonItemCode) {
        showSnackbar('Select a carton item code', 'error');
        return;
      }
    }

    try {
      const data = await apiPost(endpoint, payload);
      const successMsgs = {
        production: `Inspected — Lot No: ${data.newLotNo || data.lots?.[0]?.newLotNo || ''}`,
        sa_cleaning: 'SA cleaning inspection saved',
        lw_cleaning: 'LW cleaning inspection saved',
        qa: 'QA disposition saved',
        packing: data.packLotNo
          ? `Packing saved — PCK lot: ${data.packLotNo}`
          : 'Packing saved',
      };
      showSnackbar(successMsgs[_prodModalMode] || 'Saved', 'success');
      closeProductionModal();
      invalidateLwCaches(true);
      await loadGridRows(true);
      if (_tab === 'inspection') {
        try { await refreshPartsDatalist(); } catch (err) {
          console.error('Failed to refresh parts list after inspect', err);
        }
      }
    } catch (err) {
      showSnackbar(err.message || 'Save failed', 'error');
    }
  }

  function onProductionModalLotChange(sel) {
    const idx = Number(sel.getAttribute('data-idx'));
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const isCleaning = _prodModalMode === 'sa_cleaning' || _prodModalMode === 'lw_cleaning';

    if (!_prodModalLines[idx]) _prodModalLines[idx] = emptyLine();

    if (_prodModalMode === 'qa') {
      const targetLotId = parseInt(sel.value, 10) || null;
      const match = (_qaLotsCache[partNo] || []).find(l => Number(l.lotId) === targetLotId);
      _prodModalLines[idx].targetLotId = targetLotId;
      _prodModalLines[idx].sourceLotNo = match?.newLotNo || '';
      const avail = Number(match?.totalQa || match?.noOfComp) || 0;
      _prodModalLines[idx].noOfComp = avail;
      _prodModalLines[idx].availableQty = avail;
    } else if (_prodModalMode === 'packing') {
      const targetLotId = parseInt(sel.value, 10) || null;
      const match = (_packingLotsCache[partNo] || []).find(l => Number(l.lotId) === targetLotId);
      _prodModalLines[idx].targetLotId = targetLotId;
      _prodModalLines[idx].sourceLotNo = match?.newLotNo || '';
      const avail = Number(match?.totalOkayed || match?.noOfComp) || 0;
      _prodModalLines[idx].noOfComp = avail;
      _prodModalLines[idx].availableQty = avail;
    } else if (isCleaning) {
      const targetLotId = parseInt(sel.value, 10) || null;
      const match = (_cleaningLotsCache[cleaningLotsCacheKey()] || []).find(l => Number(l.lotId) === targetLotId);
      _prodModalLines[idx].targetLotId = targetLotId;
      _prodModalLines[idx].sourceLotNo = match?.newLotNo || '';
      const avail = Number(match?.inspectionPending || match?.noOfComp) || 0;
      _prodModalLines[idx].noOfComp = avail;
      _prodModalLines[idx].availableQty = avail;
    } else {
      const lotNo = sel.value;
      const match = sourceLotsInfo(partNo).lots.find(l => l.lotNo === lotNo);
      _prodModalLines[idx].sourceLotNo = lotNo;
      if (match) {
        const avail = lotAvailableQty(match);
        _prodModalLines[idx].productionDate = match.productionDate || '';
        _prodModalLines[idx].noOfComp = avail;
        _prodModalLines[idx].availableQty = avail;
      }
    }

    const compEl = $(`.lw-prod-line-comp[data-idx="${idx}"]`);
    const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
    const passedInp = $(`.lw-prod-line-passed[data-idx="${idx}"]`);
    const packInp = $(`.lw-prod-line-pack[data-idx="${idx}"]`);
    const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
    if (compEl) compEl.textContent = String(_prodModalLines[idx].noOfComp || '—');
    if (inspInp) inspInp.max = String(_prodModalLines[idx].noOfComp || 0);
    if (passedInp) passedInp.max = String(_prodModalLines[idx].noOfComp || 0);
    if (packInp) packInp.max = String(_prodModalLines[idx].noOfComp || 0);
    if (qaInp && _prodModalMode === 'packing') qaInp.max = String(packInp?.value || _prodModalLines[idx].noOfComp || 0);
    syncProdLineQtyCaps(idx, 'insp');

    const hasLot = (_prodModalMode === 'production')
      ? _prodModalLines[idx].sourceLotNo
      : _prodModalLines[idx].targetLotId;
    if (hasLot && idx === _prodModalLines.length - 1) {
      renderProductionModalLines();
    }
  }

  async function loadGridRows(preserveFilter) {
    if (!isGridTab()) return;

    const loadingEl = $('#lw-loading');
    const errorEl = $('#lw-error');
    if (_loading) {
      _loadGridRowsPending = true;
      return;
    }
    _loading = true;
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      let data;
      let eligibleData = { items: [] };
      if (_tab === 'qa') {
        [data, eligibleData] = await Promise.all([
          apiFetch('/api/laser-welding/qa/rows?date=' + encodeURIComponent(_workDate)),
          apiFetch('/api/laser-welding/qa/eligible?date=' + encodeURIComponent(_workDate)),
        ]);
      } else if (_tab === 'packing') {
        data = await apiFetch('/api/laser-welding/packing/rows?date=' + encodeURIComponent(_workDate));
      } else {
        data = await apiFetch(
          '/api/laser-welding/child-parts/rows?date=' + encodeURIComponent(_workDate)
          + '&mode=' + encodeURIComponent(gridApiMode())
        );
      }
      _rows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || `row:${r.partNumber || r.partNo}:${r.lineId || r.lotId || ''}`,
        partNumber: r.partNumber || r.partNo,
        lines: r.lines || [],
      }));
      if (_tab === 'qa') {
        _qaEligibleRows = (eligibleData.items || []).map(r => ({
          ...r,
          eligibleKey: r.eligibleKey || `qa:eligible:${r.partNumber || r.partNo}`,
          rowKey: r.eligibleKey || `qa:eligible:${r.partNumber || r.partNo}`,
          partNumber: r.partNumber || r.partNo,
        }));
      } else {
        _qaEligibleRows = [];
      }
      renderTable();
      if (!preserveFilter) {
        _filterQuery = '';
        const search = $('#lw-grid-search');
        if (search) search.value = '';
      }
      await refreshMeta();
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load rows';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
      _loading = false;
      if (_loadGridRowsPending) {
        _loadGridRowsPending = false;
        await loadGridRows(preserveFilter);
      }
    }
  }

  async function refreshPartsDatalist() {
    let parts = [];
    if (_tab === 'packing') {
      const data = await apiFetch('/api/laser-welding/packing/parts');
      parts = data.parts || [];
    } else {
      const data = await apiFetch('/api/laser-welding/parts?mode=' + encodeURIComponent(partsApiMode()));
      parts = data.parts || [];
    }
    _parts = parts;
    const dl = $('#lw-parts-datalist');
    if (dl) {
      dl.innerHTML = '';
      _parts.forEach(p => {
        const partNo = String(p.part_no || p.partNo || '').trim();
        if (!partNo) return;
        const opt = document.createElement('option');
        opt.value = partNo;
        opt.label = String(p.part_name || p.partName || '').trim();
        dl.appendChild(opt);
      });
    }
  }

  async function loadOperators() {
    try {
      const data = await apiFetch('/api/laser-welding/operators');
      _operators = data.operators || [];
    } catch (err) {
      console.error('Failed to load operators', err);
      _operators = [];
    }
  }

  async function loadMachines() {
    try {
      const [weldData, saData] = await Promise.all([
        apiFetch('/api/laser-welding/machines?type=3'),
        apiFetch('/api/laser-welding/machines?type=4'),
      ]);
      _machines = weldData.machines || [];
      _saMachines = saData.machines || [];
    } catch (err) {
      console.error('Failed to load machines', err);
      _machines = [];
      _saMachines = [];
    }
  }

  async function refreshMeta() {
    try {
      const meta = await apiFetch('/api/laser-welding/meta?date=' + encodeURIComponent(_workDate));
      if (meta.workDate) _workDate = meta.workDate;
    } catch (_) { /* ignore */ }
  }

  function filteredAsmRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = _asmRows;
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.customerName, r.partNumber, r.productName, r.partName,
        r.operatorNames,
        r.operatorName, r.machineName, r.newLotNo,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function filteredEligibleRows(rows) {
    const q = _filterQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.customerName, r.partNumber, r.productName, r.partName,
        r.subAssemblyPartNo, r.bomNo, r.operatorNames, r.operatorName, r.machineName,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function updateEligibleAssignButton(tr, requireMachine) {
    const machineSel = tr?.querySelector('.lw-eligible-machine');
    const btn = tr?.querySelector('.lw-eligible-act-assign');
    if (!btn) return;
    const singleSel = tr?.querySelector('.lw-eligible-operator');
    let hasOperator;
    if (singleSel) {
      hasOperator = !!parseInt(singleSel.value, 10);
    } else {
      hasOperator = getOperatorIdsFromMulti(tr?.querySelector('.lw-col-operator')).length > 0;
    }
    const machineId = requireMachine ? parseInt(machineSel?.value, 10) : true;
    btn.disabled = !(hasOperator && machineId);
  }

  function buildEligibleAsmRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row lw-data-row--eligible';
    tr.dataset.eligibleKey = row.eligibleKey;
    const customerName = row.customerName || '—';
    const product = row.productName || row.partName || '';
    const partNo = row.partNumber || row.bomNo || '';
    const pendingQty = Number(row.pendingQty) || 0;
    const btnLabel = completeActionLabel(true, false);
    const editable = canEdit();
    const operatorCell = editable ? operatorMultiSelectHtml() : '—';
    const machineCell = editable
      ? `<select class="ti-input lw-eligible-machine">${machineSelectHtml()}</select>`
      : '—';
    const actionCell = editable
      ? `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-eligible-act-assign"
                data-eligible-key="${escapeAttr(row.eligibleKey)}" disabled>${btnLabel}</button>`
      : '<span class="lw-view-only">View only</span>';
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(partNo)}">${escapeHtml(partNo)}</td>
      <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
      <td class="lw-col-operator lw-edit-cell">${operatorCell}</td>
      <td class="lw-col-machine lw-edit-cell">${machineCell}</td>
      <td class="lw-col-qty">${pendingQty > 0 ? pendingQty : '—'}</td>
      ${qtyMetaPlaceholderCells()}
      <td class="lw-col-lot">—</td>
      ${timePlaceholderCell()}
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions lw-actions-cell">${actionCell}</td>
    `;
    if (editable) {
      initOperatorMultiSelect(tr);
      const onChange = () => updateEligibleAssignButton(tr, true);
      tr.querySelector('.lw-col-operator')?.addEventListener('change', onChange);
      tr.querySelector('.lw-eligible-machine')?.addEventListener('change', onChange);
    }
    return tr;
  }

  function buildEligibleSaRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row lw-data-row--eligible';
    tr.dataset.eligibleKey = row.eligibleKey;
    const customerName = row.customerName || '—';
    const saPart = row.subAssemblyPartNo || row.partName || '—';
    const pendingQty = Number(row.pendingQty) || 0;
    const btnLabel = completeActionLabel(true, true);
    const editable = canEdit();
    const operatorCell = editable
      ? `<select class="ti-input lw-eligible-operator">${operatorSelectHtml()}</select>`
      : '—';
    const machineCell = editable
      ? `<select class="ti-input lw-eligible-machine">${saMachineSelectHtml()}</select>`
      : '—';
    const actionCell = editable
      ? `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-eligible-act-assign"
                data-eligible-key="${escapeAttr(row.eligibleKey)}" disabled>${btnLabel}</button>`
      : '<span class="lw-view-only">View only</span>';
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber || row.bomNo || '')}">${escapeHtml(row.partNumber || row.bomNo || '—')}</td>
      <td class="lw-col-part" title="${escapeAttr(saPart)}">${escapeHtml(saPart)}</td>
      <td class="lw-col-operator lw-edit-cell">${operatorCell}</td>
      <td class="lw-col-machine lw-edit-cell">${machineCell}</td>
      <td class="lw-col-qty">${pendingQty > 0 ? pendingQty : '—'}</td>
      ${qtyMetaPlaceholderCells()}
      <td class="lw-col-lot">—</td>
      ${timePlaceholderCell()}
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions lw-actions-cell">${actionCell}</td>
    `;
    if (editable) {
      const onChange = () => updateEligibleAssignButton(tr, true);
      tr.querySelector('.lw-eligible-operator')?.addEventListener('change', onChange);
      tr.querySelector('.lw-eligible-machine')?.addEventListener('change', onChange);
    }
    return tr;
  }

  function buildEligibleQaRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row lw-data-row--eligible';
    tr.dataset.eligibleKey = row.eligibleKey;
    const partNo = row.partNumber || row.partNo || '';
    const partName = row.partName || partNameFor(partNo);
    const pendingQty = Number(row.pendingQty) || 0;
    const editable = canEdit();
    const operatorCell = editable
      ? `<select class="ti-input lw-eligible-operator">${operatorSelectHtml()}</select>`
      : '—';
    const actionCell = editable
      ? `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-eligible-act-assign"
                data-eligible-key="${escapeAttr(row.eligibleKey)}" disabled>QA</button>`
      : '<span class="lw-view-only">View only</span>';
    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(partNo)}">${escapeHtml(partNo)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-operator lw-edit-cell">${operatorCell}</td>
      <td class="lw-col-qty">${pendingQty > 0 ? pendingQty : '—'}</td>
      ${qtyMetaPlaceholderCells()}
      ${lotPackPlaceholderCell()}
      <td class="lw-col-time">—</td>
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions lw-actions-cell">${actionCell}</td>
    `;
    if (editable) {
      const onChange = () => updateEligibleAssignButton(tr, false);
      tr.querySelector('.lw-eligible-operator')?.addEventListener('change', onChange);
    }
    return tr;
  }

  async function assignEligibleAsmRow(eligibleKey, tr) {
    const row = _asmEligibleRows.find(r => r.eligibleKey === eligibleKey);
    if (!row || !canEdit()) return;
    const opPayload = operatorPayloadFromMulti(tr?.querySelector('.lw-col-operator'));
    const machineId = parseInt(tr?.querySelector('.lw-eligible-machine')?.value, 10);
    if (!row.bomId || !opPayload || !machineId) return;
    try {
      const draft = await apiPost('/api/laser-welding/assembly/rework/pending', {
        bomId: row.bomId,
        ...opPayload,
        machineId,
        workDate: _workDate,
      });
      await loadAssemblyRows(true);
      await openWeldModal(draft);
    } catch (err) {
      showSnackbar(err.message || 'Failed to assign row', 'error');
    }
  }

  async function assignEligibleSaRow(eligibleKey, tr) {
    const row = _saEligibleRows.find(r => r.eligibleKey === eligibleKey);
    if (!row || !canEdit()) return;
    const operatorId = parseInt(tr?.querySelector('.lw-eligible-operator')?.value, 10);
    const machineId = parseInt(tr?.querySelector('.lw-eligible-machine')?.value, 10);
    const saPart = row.subAssemblyPartNo || '';
    if (!row.bomId || !saPart || !operatorId || !machineId) return;
    try {
      const draft = await apiPost('/api/laser-welding/sub-assembly/rework/pending', {
        bomId: row.bomId,
        subAssemblyPartNo: saPart,
        operatorId,
        operatorIds: [operatorId],
        machineId,
        workDate: _workDate,
      });
      await loadSubAssemblyRows(true);
      await openWeldModal(draft);
    } catch (err) {
      showSnackbar(err.message || 'Failed to assign row', 'error');
    }
  }

  async function assignEligibleQaRow(eligibleKey, tr) {
    const row = _qaEligibleRows.find(r => r.eligibleKey === eligibleKey);
    if (!row || !canEdit()) return;
    const operatorId = parseInt(tr?.querySelector('.lw-eligible-operator')?.value, 10);
    const partNumber = row.partNumber || row.partNo || '';
    if (!partNumber || !operatorId) return;
    try {
      const draft = await apiPost('/api/laser-welding/qa/pending', {
        partNumber,
        operatorId,
        operatorIds: [operatorId],
        workDate: _workDate,
      });
      await loadGridRows(true);
      await openProductionModal(draft);
    } catch (err) {
      showSnackbar(err.message || 'Failed to assign row', 'error');
    }
  }

  function findAsmRow(rowKey) {
    return _asmRows.find(r => r.rowKey === rowKey);
  }

  function asmDetailLinesHtml(row) {
    const lines = row.lines || [];
    const baseCols = 5;
    const remarkCols = detailRemarkColCount(_tab);
    const totalCols = baseCols + remarkCols;
    let html = '<table class="ti-table lw-detail-table"><thead><tr>';
    html += '<th>Child Part</th><th>Child Lot</th><th>Consumed</th><th>QA</th><th>Scrap</th>';
    html += detailRemarkHeaderHtml(_tab);
    html += '</tr></thead><tbody>';
    if (!lines.length) {
      html += `<tr><td colspan="${totalCols}" class="lw-detail-empty">No consumption lines.</td></tr>`;
    }
    lines.forEach(ln => {
      const hasNested = !!(ln.nestedLines?.length);
      const partCell = escapeHtml(ln.partNumber || '—');
      html += `<tr class="lw-detail-consume-row${hasNested ? ' lw-detail-consume-row--branch' : ''}">`;
      html += `<td class="lw-consume-part-cell">${cellWithTreeToggle(partCell, hasNested)}</td>`;
      html += `<td>${escapeHtml(ln.sourceLotNo || '—')}</td>`;
      html += `<td>${Number(ln.inspectedQty) || 0}</td>`;
      html += `<td>${Number(ln.qaQty) || 0}</td>`;
      html += `<td>${Number(ln.scrapQty) || 0}</td>`;
      html += detailRemarkCellsHtml(ln, _tab);
      html += '</tr>';
      if (hasNested) {
        html += traceBranchRowHtml(totalCols, ln.nestedLines, 1);
      }
    });
    html += '</tbody></table>';
    return html;
  }

  function buildAsmActionsHtml(row, isRework) {
    const isRw = isRework !== undefined ? isRework : isReworkWeldingMode();
    const isSa = !!(row.isSubAssembly || String(row.rowKey || '').startsWith('sa'));
    const key = row.rowKey;
    const expCls = _asmExpanded[key] ? ' is-expanded' : '';
    if (row.isProcessed) {
      return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-asm-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Consumption lines">▤</button>`;
    }
    if (!canEdit()) return '<span class="lw-view-only">View only</span>';
    if (!row.isDraft) return '';
    const btnLabel = completeActionLabel(isRw, isSa);
    return `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-asm-act-weld" data-row-key="${escapeAttr(key)}">${btnLabel}</button>`
      + buildDraftDismissBtn(row);
  }

  function buildAsmDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;
    const product = row.productName || row.partName || '';
    const operatorName = operatorDisplayName(row);
    const machineName = row.machineName || '—';
    const customerName = row.customerName || '—';
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-machine" title="${escapeAttr(machineName)}">${escapeHtml(machineName)}</td>
      <td class="lw-col-qty">${primaryQtyCellHtml(row)}</td>
      <td class="lw-col-qa">${qaTotalCellHtml(row)}</td>
      <td class="lw-col-scrap">${scrapTotalCellHtml(row)}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-time">${asmTimeCellHtml(row)}</td>
      <td class="lw-col-ot">${otBadgeHtml(row)}</td>
      <td class="lw-col-actions lw-actions-cell">${buildAsmActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildAsmDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;
    const td = document.createElement('td');
    td.colSpan = 12;
    td.className = 'lw-detail-cell';
    td.innerHTML = `<div class="lw-detail-inline lw-detail-body">${asmDetailLinesHtml(row)}</div>`;
    tr.appendChild(td);
    return tr;
  }

  function customerSelectHtml(selectedId) {
    let html = '<option value="">(optional)</option>';
    _bomCustomers.forEach(c => {
      const sel = Number(selectedId) === Number(c.custId) ? ' selected' : '';
      html += `<option value="${c.custId}"${sel}>${escapeHtml(c.customerName || `Customer ${c.custId}`)}</option>`;
    });
    return html;
  }

  function bomIdKey(id) {
    return String(id || '').trim();
  }

  function bomsForCustomer(custId, catalog) {
    const list = catalog || _boms;
    const cid = custId ? Number(custId) : null;
    return cid ? list.filter(b => Number(b.custId) === cid) : list;
  }

  function bomSelectHtml(custId, selectedBomId, catalog) {
    const list = bomsForCustomer(custId, catalog);
    const selKey = bomIdKey(selectedBomId);
    let html = '<option value="">Select BOM…</option>';
    list.forEach(b => {
      const sel = selKey && selKey === bomIdKey(b.bomId) ? ' selected' : '';
      html += `<option value="${escapeAttr(bomIdKey(b.bomId))}"${sel}>${escapeHtml(b.label || b.bomNo || '')}</option>`;
    });
    return html;
  }

  function refreshAsmNewRowBomSelect(tr) {
    const custSel = tr.querySelector('.lw-asm-new-customer');
    const bomSel = tr.querySelector('.lw-asm-new-bom');
    const productEl = tr.querySelector('.lw-asm-new-product');
    if (!bomSel) return;
    const custId = custSel?.value || '';
    const prevBom = bomSel.value;
    bomSel.innerHTML = bomSelectHtml(custId, prevBom);
    const stillValid = prevBom && bomsForCustomer(custId).some(b => bomIdKey(b.bomId) === bomIdKey(prevBom));
    if (!stillValid) {
      bomSel.value = '';
      if (productEl) productEl.textContent = '—';
    }
  }

  function appendAsmNewRow(tbody) {
    if (!canEdit() || !ASM_TABS.has(_tab)) return;
    if (isReworkWeldingMode()) return;
    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-customer lw-edit-cell">
        <select class="ti-input lw-asm-new-customer">${customerSelectHtml()}</select>
      </td>
      <td class="lw-col-bom lw-edit-cell">
        <select class="ti-input lw-asm-new-bom">${bomSelectHtml('', '')}</select>
      </td>
      <td class="lw-col-name lw-asm-new-product">—</td>
      <td class="lw-col-operator lw-edit-cell lw-new-operator-cell">${operatorMultiSelectHtml()}</td>
      <td class="lw-col-machine lw-edit-cell">
        <select class="ti-input lw-asm-new-machine">${machineSelectHtml()}</select>
      </td>
      <td class="lw-col-qty">—</td>
      ${qtyMetaPlaceholderCells()}
      <td class="lw-col-lot">—</td>
      ${timePlaceholderCell()}
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);
    const custSel = tr.querySelector('.lw-asm-new-customer');
    const bomSel = tr.querySelector('.lw-asm-new-bom');
    const operatorWrap = tr.querySelector('.lw-new-operator-cell');
    const machineSel = tr.querySelector('.lw-asm-new-machine');
    const productEl = tr.querySelector('.lw-asm-new-product');
    initOperatorMultiSelect(tr);

    custSel?.addEventListener('change', () => refreshAsmNewRowBomSelect(tr));
    bomSel?.addEventListener('change', () => {
      const bom = _boms.find(b => bomIdKey(b.bomId) === bomIdKey(bomSel.value));
      if (productEl) productEl.textContent = bom ? (bom.productName || '—') : '—';
      if (bom?.custId && custSel && !custSel.value) custSel.value = String(bom.custId);
      tryCommitAsmNewRow(custSel, bomSel, operatorWrap, machineSel);
    });
    operatorWrap?.addEventListener('change', () => tryCommitAsmNewRow(custSel, bomSel, operatorWrap, machineSel));
    machineSel?.addEventListener('change', () => tryCommitAsmNewRow(custSel, bomSel, operatorWrap, machineSel));
  }

  async function tryCommitAsmNewRow(custSel, bomSel, operatorWrap, machineSel) {
    const bomId = bomIdKey(bomSel?.value);
    const opPayload = operatorPayloadFromMulti(operatorWrap);
    const machineId = parseInt(machineSel?.value, 10);
    if (!bomId || !opPayload || !machineId) return;

    const bom = _boms.find(b => bomIdKey(b.bomId) === bomId);
    const custId = parseInt(custSel?.value, 10);
    if (custId && bom && Number(bom.custId) !== custId) {
      showSnackbar('Selected BOM does not belong to this customer', 'error');
      return;
    }

    try {
      const pendingUrl = isReworkWeldingMode()
        ? '/api/laser-welding/assembly/rework/pending'
        : '/api/laser-welding/assembly/pending';
      await apiPost(pendingUrl, { bomId, ...opPayload, machineId, workDate: _workDate });
      if (custSel) custSel.value = '';
      if (bomSel) { bomSel.value = ''; bomSel.innerHTML = bomSelectHtml('', ''); }
      resetOperatorMulti(operatorWrap);
      if (machineSel) machineSel.value = '';
      const productEl = custSel?.closest('tr')?.querySelector('.lw-asm-new-product');
      if (productEl) productEl.textContent = '—';
      await loadAssemblyRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add assembly row', 'error');
    }
  }

  function renderAssemblyTable() {
    const tbody = $('#lw-asm-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    filteredAsmRows().forEach(row => {
      tbody.appendChild(buildAsmDataRow(row));
      if (_asmExpanded[row.rowKey]) tbody.appendChild(buildAsmDetailRow(row));
    });
    if (isReworkWeldingMode()) {
      filteredEligibleRows(_asmEligibleRows).forEach(row => {
        tbody.appendChild(buildEligibleAsmRow(row));
      });
    }
    appendAsmNewRow(tbody);
    initOperatorMultiSelect(tbody);
    updateRowCount();
  }

  async function loadBomCatalog() {
    try {
      const custData = await apiFetch('/api/laser-welding/bom-customers');
      _bomCustomers = custData.customers || [];
    } catch (err) {
      _bomCustomers = [];
    }
    try {
      const bomUrl = isReworkWeldingMode()
        ? '/api/laser-welding/assembly/rework/boms'
        : '/api/laser-welding/boms';
      const bomData = await apiFetch(bomUrl);
      _boms = bomData.boms || [];
    } catch (err) {
      _boms = [];
      showSnackbar(err.message || 'Failed to load BOM list', 'error');
    }
  }

  async function loadAssemblyRows(preserveFilter) {
    if (!ASM_TABS.has(_tab)) return;
    const loadingEl = $('#lw-asm-loading');
    const errorEl = $('#lw-asm-error');
    if (_asmLoading) return;
    _asmLoading = true;
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';
    try {
      const rowsUrl = isReworkWeldingMode()
        ? '/api/laser-welding/assembly/rework/rows?date='
        : '/api/laser-welding/assembly/rows?date=';
      const eligibleUrl = isReworkWeldingMode()
        ? '/api/laser-welding/assembly/rework/eligible?date='
        : null;
      const [data, eligibleData] = await Promise.all([
        apiFetch(rowsUrl + encodeURIComponent(_workDate)),
        eligibleUrl
          ? apiFetch(eligibleUrl + encodeURIComponent(_workDate))
          : Promise.resolve({ items: [] }),
      ]);
      _asmRows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || (r.draftLineId
          ? `draft:${r.batchMode || 'assembly'}:${r.draftLineId}`
          : (isReworkWeldingMode() ? `rweld:lot:${r.lotId}` : `asm:${r.lotId}`)),
        lines: r.lines || [],
      }));
      if (isReworkWeldingMode()) {
        _asmEligibleRows = (eligibleData.items || []).map(r => ({
          ...r,
          eligibleKey: r.eligibleKey || `rweld:eligible:${r.bomId}`,
          rowKey: r.eligibleKey || `rweld:eligible:${r.bomId}`,
        }));
      } else {
        _asmEligibleRows = [];
      }
      renderAssemblyTable();
      if (!preserveFilter) {
        _filterQuery = '';
        const search = $('#lw-grid-search');
        if (search) search.value = '';
      }
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load assembly rows';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
      _asmLoading = false;
    }
  }

  function filteredSaRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = _saRows;
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.customerName, r.partNumber, r.subAssemblyPartNo, r.partName,
        r.productName, r.operatorNames, r.operatorName, r.machineName, r.newLotNo,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function findSaRow(rowKey) {
    return _saRows.find(r => r.rowKey === rowKey);
  }

  function buildSaDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;
    const saPart = row.subAssemblyPartNo || row.partName || '—';
    const operatorName = operatorDisplayName(row);
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(row.customerName || '')}">${escapeHtml(row.customerName || '—')}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber || '—')}</td>
      <td class="lw-col-part" title="${escapeAttr(saPart)}">${escapeHtml(saPart)}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-machine" title="${escapeAttr(row.machineName || '')}">${escapeHtml(row.machineName || '—')}</td>
      <td class="lw-col-qty">${primaryQtyCellHtml(row)}</td>
      <td class="lw-col-qa">${qaTotalCellHtml(row)}</td>
      <td class="lw-col-scrap">${scrapTotalCellHtml(row)}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-time">${asmTimeCellHtml(row)}</td>
      <td class="lw-col-ot">${otBadgeHtml(row)}</td>
      <td class="lw-col-actions lw-actions-cell">${buildAsmActionsHtml(row, isReworkSubAssemblyMode())}</td>
    `;
    return tr;
  }

  function buildSaDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;
    const td = document.createElement('td');
    td.colSpan = 12;
    td.className = 'lw-detail-cell';
    td.innerHTML = `<div class="lw-detail-inline lw-detail-body">${asmDetailLinesHtml(row)}</div>`;
    tr.appendChild(td);
    return tr;
  }

  function saPartOptionValue(bomId, partNo) {
    return `${bomIdKey(bomId)}|${String(partNo || '').trim()}`;
  }

  function parseSaPartOptionValue(value) {
    const raw = String(value || '').trim();
    if (!raw) return { bomId: '', partNo: '' };
    const idx = raw.indexOf('|');
    if (idx < 0) return { bomId: '', partNo: raw };
    return { bomId: raw.slice(0, idx), partNo: raw.slice(idx + 1) };
  }

  function saBomsFromParts() {
    const seen = new Set();
    const result = [];
    _saPartsList.forEach(p => {
      const key = bomIdKey(p.bomId);
      if (!key || seen.has(key)) return;
      seen.add(key);
      result.push({
        bomId: p.bomId,
        bomNo: p.bomNo || '',
        custId: p.custId,
        label: `${p.bomNo || ''} — ${p.productName || ''}`.trim(' —'),
      });
    });
    return result.sort((a, b) => String(a.bomNo || '').localeCompare(String(b.bomNo || '')));
  }

  function saCustomersForCatalog() {
    const ids = new Set(_saPartsList.map(p => Number(p.custId)).filter(id => Number.isFinite(id) && id > 0));
    if (!ids.size) return _bomCustomers;
    return _bomCustomers.filter(c => ids.has(Number(c.custId)));
  }

  function saCustomerSelectHtml(selectedId) {
    let html = '<option value="">(optional)</option>';
    saCustomersForCatalog().forEach(c => {
      const sel = Number(selectedId) === Number(c.custId) ? ' selected' : '';
      html += `<option value="${c.custId}"${sel}>${escapeHtml(c.customerName || `Customer ${c.custId}`)}</option>`;
    });
    return html;
  }

  function saBomSelectHtml(custId, selectedBomId) {
    const list = bomsForCustomer(custId, saBomsFromParts());
    const selKey = bomIdKey(selectedBomId);
    let html = '<option value="">(optional)</option>';
    list.forEach(b => {
      const sel = selKey && selKey === bomIdKey(b.bomId) ? ' selected' : '';
      html += `<option value="${escapeAttr(bomIdKey(b.bomId))}"${sel}>${escapeHtml(b.label || b.bomNo || '')}</option>`;
    });
    return html;
  }

  function filteredSaParts(custId, bomId) {
    const cid = custId ? Number(custId) : null;
    const bid = bomIdKey(bomId);
    return _saPartsList.filter(p => {
      if (cid && Number(p.custId) !== cid) return false;
      if (bid && bomIdKey(p.bomId) !== bid) return false;
      return true;
    });
  }

  function saCatalogSelectHtml(selectedValue, custId, bomId) {
    const sel = String(selectedValue || '').trim();
    let html = '<option value="">Select sub-assembly part…</option>';
    filteredSaParts(custId, bomId).forEach(p => {
      const val = saPartOptionValue(p.bomId, p.partNo);
      const selected = val === sel ? ' selected' : '';
      const label = p.label || `${p.partNo} — ${p.partName || ''} (${p.bomNo || ''})`;
      html += `<option value="${escapeAttr(val)}"${selected}>${escapeHtml(label)}</option>`;
    });
    return html;
  }

  function refreshSaNewRowFilters(tr) {
    const custSel = tr.querySelector('.lw-sa-new-customer');
    const bomSel = tr.querySelector('.lw-sa-new-bom');
    if (!bomSel) return;
    const custId = custSel?.value || '';
    const prevBom = bomSel.value;
    bomSel.innerHTML = saBomSelectHtml(custId, prevBom);
    const stillValid = prevBom
      && bomsForCustomer(custId, saBomsFromParts()).some(b => bomIdKey(b.bomId) === bomIdKey(prevBom));
    if (!stillValid) bomSel.value = '';
    refreshSaNewRowPartSelect(tr);
  }

  function refreshSaNewRowPartSelect(tr) {
    const custSel = tr.querySelector('.lw-sa-new-customer');
    const bomSel = tr.querySelector('.lw-sa-new-bom');
    const partSel = tr.querySelector('.lw-sa-new-part');
    if (!partSel) return;
    const prev = partSel.value;
    partSel.innerHTML = saCatalogSelectHtml(prev, custSel?.value, bomSel?.value);
    if (prev && ![...partSel.options].some(o => o.value === prev)) partSel.value = '';
  }

  function appendSaNewRow(tbody) {
    if (!canEdit() || !SA_TABS.has(_tab)) return;
    if (isReworkSubAssemblyMode()) return;
    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-customer lw-edit-cell">
        <select class="ti-input lw-sa-new-customer">${saCustomerSelectHtml()}</select>
      </td>
      <td class="lw-col-bom lw-edit-cell">
        <select class="ti-input lw-sa-new-bom">${saBomSelectHtml('', '')}</select>
      </td>
      <td class="lw-col-part lw-edit-cell">
        <select class="ti-input lw-sa-new-part">${saCatalogSelectHtml('', '', '')}</select>
      </td>
      <td class="lw-col-operator lw-edit-cell">
        <select class="ti-input lw-sa-new-operator">${operatorSelectHtml()}</select>
      </td>
      <td class="lw-col-machine lw-edit-cell">
        <select class="ti-input lw-sa-new-machine">${saMachineSelectHtml()}</select>
      </td>
      <td class="lw-col-qty">—</td>
      ${qtyMetaPlaceholderCells()}
      <td class="lw-col-lot">—</td>
      ${timePlaceholderCell()}
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const custSel = tr.querySelector('.lw-sa-new-customer');
    const bomSel = tr.querySelector('.lw-sa-new-bom');
    const partSel = tr.querySelector('.lw-sa-new-part');
    const opSel = tr.querySelector('.lw-sa-new-operator');
    const machineSel = tr.querySelector('.lw-sa-new-machine');

    custSel?.addEventListener('change', () => refreshSaNewRowFilters(tr));
    bomSel?.addEventListener('change', () => refreshSaNewRowPartSelect(tr));
    partSel?.addEventListener('change', () => tryCommitSaNewRow(partSel, opSel, machineSel));
    opSel?.addEventListener('change', () => tryCommitSaNewRow(partSel, opSel, machineSel));
    machineSel?.addEventListener('change', () => tryCommitSaNewRow(partSel, opSel, machineSel));
  }

  async function tryCommitSaNewRow(partSel, opSel, machineSel) {
    const { bomId, partNo: saPart } = parseSaPartOptionValue(partSel?.value);
    const operatorId = parseInt(opSel?.value, 10);
    const machineId = parseInt(machineSel?.value, 10);
    if (!bomId || !saPart || !operatorId || !machineId) return;

    try {
      const pendingUrl = isReworkSubAssemblyMode()
        ? '/api/laser-welding/sub-assembly/rework/pending'
        : '/api/laser-welding/sub-assembly/pending';
      await apiPost(pendingUrl, {
        bomId,
        subAssemblyPartNo: saPart,
        operatorId,
        operatorIds: [operatorId],
        machineId,
        workDate: _workDate,
      });
      const newRow = partSel?.closest('tr');
      if (partSel) {
        const custId = newRow?.querySelector('.lw-sa-new-customer')?.value || '';
        const bomIdFilter = newRow?.querySelector('.lw-sa-new-bom')?.value || '';
        partSel.innerHTML = saCatalogSelectHtml('', custId, bomIdFilter);
        partSel.value = '';
      }
      if (opSel) opSel.value = '';
      if (machineSel) machineSel.value = '';
      await loadSubAssemblyRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add sub-assembly row', 'error');
    }
  }

  function renderSubAssemblyTable() {
    const tbody = $('#lw-sa-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    filteredSaRows().forEach(row => {
      tbody.appendChild(buildSaDataRow(row));
      if (_saExpanded[row.rowKey]) tbody.appendChild(buildSaDetailRow(row));
    });
    if (isReworkSubAssemblyMode()) {
      filteredEligibleRows(_saEligibleRows).forEach(row => {
        tbody.appendChild(buildEligibleSaRow(row));
      });
    }
    appendSaNewRow(tbody);
    updateRowCount();
  }

  async function loadSubAssemblyPartCatalog() {
    try {
      const custData = await apiFetch('/api/laser-welding/bom-customers');
      _bomCustomers = custData.customers || [];
    } catch (err) {
      _bomCustomers = [];
    }
    try {
      const partsUrl = isReworkSubAssemblyMode()
        ? '/api/laser-welding/sub-assembly/rework/parts'
        : '/api/laser-welding/sub-assembly/parts';
      const data = await apiFetch(partsUrl);
      _saPartsList = data.parts || [];
    } catch (err) {
      _saPartsList = [];
      showSnackbar(err.message || 'Failed to load sub-assembly parts', 'error');
    }
  }

  async function loadSubAssemblyRows(preserveFilter) {
    if (!SA_TABS.has(_tab)) return;
    const loadingEl = $('#lw-sa-loading');
    const errorEl = $('#lw-sa-error');
    if (_saLoading) return;
    _saLoading = true;
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';
    try {
      const rowsUrl = isReworkSubAssemblyMode()
        ? '/api/laser-welding/sub-assembly/rework/rows?date='
        : '/api/laser-welding/sub-assembly/rows?date=';
      const eligibleUrl = isReworkSubAssemblyMode()
        ? '/api/laser-welding/sub-assembly/rework/eligible?date='
        : null;
      const [data, eligibleData] = await Promise.all([
        apiFetch(rowsUrl + encodeURIComponent(_workDate)),
        eligibleUrl
          ? apiFetch(eligibleUrl + encodeURIComponent(_workDate))
          : Promise.resolve({ items: [] }),
      ]);
      _saRows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || (r.draftLineId
          ? `draft:${r.batchMode || 'sub_assembly'}:${r.draftLineId}`
          : (isReworkSubAssemblyMode() ? `sa-rw:lot:${r.lotId}` : `sa:${r.lotId}`)),
        lines: r.lines || [],
      }));
      if (isReworkSubAssemblyMode()) {
        _saEligibleRows = (eligibleData.items || []).map(r => ({
          ...r,
          eligibleKey: r.eligibleKey || `sa-rw:eligible:${r.bomId}:${r.subAssemblyPartNo}`,
          rowKey: r.eligibleKey || `sa-rw:eligible:${r.bomId}:${r.subAssemblyPartNo}`,
        }));
      } else {
        _saEligibleRows = [];
      }
      renderSubAssemblyTable();
      if (!preserveFilter) {
        _filterQuery = '';
        const search = $('#lw-grid-search');
        if (search) search.value = '';
      }
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load sub-assembly rows';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
      _saLoading = false;
    }
  }

  function reworkTargetCacheKey(bomId, subAssemblyPartNo) {
    const bid = bomIdKey(bomId);
    if (_weldModalContext === 'sub_assembly') {
      const saPart = String(subAssemblyPartNo || _weldModalSubAssemblyPartNo || '').trim();
      return saPart ? `${bid}:${saPart}` : `${bid}:all`;
    }
    return bid;
  }

  async function fetchReworkTargetLots(bomId, subAssemblyPartNo) {
    const bid = bomIdKey(bomId);
    if (!bid) return [];
    const cacheKey = reworkTargetCacheKey(bid, subAssemblyPartNo);
    let url = _weldModalContext === 'sub_assembly'
      ? '/api/laser-welding/sub-assembly/rework/target-lots?bomId=' + encodeURIComponent(bid)
      : '/api/laser-welding/assembly/rework/target-lots?bomId=' + encodeURIComponent(bid);
    const saPart = String(subAssemblyPartNo || '').trim();
    if (_weldModalContext === 'sub_assembly' && saPart) {
      url += '&subAssemblyPartNo=' + encodeURIComponent(saPart);
    }
    const data = await apiFetch(url);
    _reworkTargetLotsCache[cacheKey] = data.lots || [];
    return _reworkTargetLotsCache[cacheKey];
  }

  function updateWeldModalChrome() {
    const isRw = isWeldReworkMode();
    const isSa = isSubAssemblyWeldContext();
    const title = $('#lw-weld-modal-title');
    const qtyLabel = $('#lw-weld-modal-qty-label');
    const targetWrap = $('#lw-weld-target-lot-wrap');
    const qtyInp = $('#lw-weld-modal-qty');
    if (title) {
      if (isSa) title.textContent = isRw ? 'Re-Work Sub-Assembly' : 'Assembled';
      else title.textContent = isRw ? 'Re-Work Welding' : 'Welded';
    }
    if (qtyLabel) {
      qtyLabel.innerHTML = isRw
        ? 'Re-work QTY <span class="lw-required">*</span>'
        : `${completeQtyLabel(isSa)} <span class="lw-required">*</span>`;
    }
    if (targetWrap) targetWrap.style.display = isRw ? '' : 'none';
    if (qtyInp) qtyInp.removeAttribute('max');
    syncWeldParentScrapRemarkVisibility();
  }

  function syncWeldParentScrapRemarkVisibility() {
    const qa = parseInt($('#lw-weld-modal-parent-qa')?.value, 10) || 0;
    const scrap = parseInt($('#lw-weld-modal-parent-scrap')?.value, 10) || 0;
    const remarkWrap = $('#lw-weld-modal-parent-scrap-remark-wrap');
    if (remarkWrap) remarkWrap.style.display = scrap > 0 ? '' : 'none';
    const timeWrap = $('#lw-weld-modal-parent-time-wrap');
    if (timeWrap) timeWrap.style.display = (qa > 0 || scrap > 0) ? '' : 'none';
  }

  function populateWeldTargetLotSelect(lots, selectedLotId) {
    const sel = $('#lw-weld-modal-target-lot');
    if (!sel) return;
    let html = '<option value="">Select lot…</option>';
    (lots || []).forEach(l => {
      const lid = Number(l.lotId);
      const selAttr = lid === Number(selectedLotId) ? ' selected' : '';
      html += `<option value="${lid}" data-rework-pending="${Number(l.reworkPending) || 0}"${selAttr}>${escapeHtml(l.newLotNo)} (pending: ${l.reworkPending})</option>`;
    });
    sel.innerHTML = html;
  }

  function onWeldTargetLotChange() {
    const sel = $('#lw-weld-modal-target-lot');
    const lotId = parseInt(sel?.value, 10) || null;
    _weldModalTargetLotId = lotId;
    const cacheKey = reworkTargetCacheKey(_weldModalBomId, _weldModalSubAssemblyPartNo);
    const lots = _reworkTargetLotsCache[cacheKey] || [];
    const match = lots.find(l => Number(l.lotId) === lotId);
    const selectedOpt = sel?.selectedOptions?.[0];
    let pending = null;
    if (match) pending = Number(match.reworkPending) || 0;
    else if (selectedOpt?.dataset?.reworkPending != null) {
      pending = Number(selectedOpt.dataset.reworkPending) || 0;
    }
    const qtyInp = $('#lw-weld-modal-qty');
    if (qtyInp) {
      if (pending != null) qtyInp.max = String(pending);
      else qtyInp.removeAttribute('max');
    }
  }

  async function fetchChildLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    const prefix = _weldModalContext === 'sub_assembly' ? 'sa:' : '';
    const url = _weldModalContext === 'sub_assembly'
      ? '/api/laser-welding/sub-assembly/child-lots?partNo='
      : '/api/laser-welding/assembly/child-lots?partNo=';
    const data = await apiFetch(url + encodeURIComponent(pn));
    _childLotsCache[prefix + pn] = data.lots || [];
    return _childLotsCache[prefix + pn];
  }

  function emptyWeldLine() {
    return { childLotId: null, consumedQty: 0, qaQty: 0, scrapQty: 0, scrapRemark: '' };
  }

  function weldRequiredForPart(ch, weldQty) {
    return (Number(ch.bomQty) || 0) * weldQty;
  }

  function weldWeldedTotal(ch) {
    return (ch.lines || []).reduce((sum, ln) => {
      const consumed = Number(ln.consumedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      if (ch.isBoPart) return sum + Math.max(0, consumed - scrap);
      return sum + Math.max(0, consumed - qa - scrap);
    }, 0);
  }

  function weldRemovedTotal(ch) {
    return weldWeldedTotal(ch);
  }

  function isWeldLineEmpty(ln) {
    return !ln?.childLotId
      && Number(ln?.consumedQty) <= 0
      && Number(ln?.qaQty) <= 0
      && Number(ln?.scrapQty) <= 0;
  }

  function ensureWeldTrailingLine(ch) {
    if (!ch.lines?.length) ch.lines = [emptyWeldLine()];
    const last = ch.lines[ch.lines.length - 1];
    if (!isWeldLineEmpty(last)) ch.lines.push(emptyWeldLine());
  }

  function weldLotsUsedInPart(ch, excludeLineIdx) {
    const used = new Set();
    (ch.lines || []).forEach((ln, i) => {
      if (i !== excludeLineIdx && ln.childLotId) used.add(Number(ln.childLotId));
    });
    return used;
  }

  function getWeldLine(partIdx, lineIdx) {
    return _weldModalChildren[partIdx]?.lines?.[lineIdx] || null;
  }

  function syncWeldScrapRemarkVisibility(partIdx, lineIdx) {
    const scrap = parseInt($(`.lw-weld-scrap[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`)?.value, 10) || 0;
    const wrap = $(`.lw-weld-scrap-remark-wrap[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
    if (wrap) wrap.style.display = scrap > 0 ? '' : 'none';
  }

  function syncWeldLineQtyCaps(partIdx, lineIdx, changedField) {
    const ch = _weldModalChildren[partIdx];
    const consumedInp = $(`.lw-weld-consumed[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
    const qaInp = $(`.lw-weld-qa[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
    const scrapInp = $(`.lw-weld-scrap[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
    const ln = getWeldLine(partIdx, lineIdx);
    if (!consumedInp || !scrapInp || !ln) return;

    let consumed = parseInt(consumedInp.value, 10);
    let scrap = parseInt(scrapInp.value, 10);
    if (Number.isNaN(consumed) || consumed < 0) consumed = 0;
    if (Number.isNaN(scrap) || scrap < 0) scrap = 0;

    if (ch?.isBoPart) {
      if (scrap > consumed) {
        scrap = consumed;
        showSnackbar('Scrap cannot exceed Consumed QTY', 'warning');
      }
      scrapInp.value = String(scrap);
      scrapInp.max = String(consumed);
      ln.consumedQty = consumed;
      ln.qaQty = 0;
      ln.scrapQty = scrap;
      syncWeldScrapRemarkVisibility(partIdx, lineIdx);
      updateWeldPartSummary(partIdx);
      return;
    }

    if (!qaInp) return;
    let qa = parseInt(qaInp.value, 10);
    if (Number.isNaN(qa) || qa < 0) qa = 0;

    if (changedField === 'consumed') {
      if (qa + scrap > consumed) {
        consumed = qa + scrap;
        showSnackbar('Consumed QTY must be at least QA + Scrap', 'warning');
        consumedInp.value = String(consumed);
      }
    } else if (changedField === 'qa') {
      const maxQa = Math.max(0, consumed - scrap);
      if (qa > maxQa) {
        qa = maxQa;
        showSnackbar('QA + Scrap cannot exceed Consumed QTY', 'warning');
      }
    } else if (changedField === 'scrap') {
      const maxScrap = Math.max(0, consumed - qa);
      if (scrap > maxScrap) {
        scrap = maxScrap;
        showSnackbar('QA + Scrap cannot exceed Consumed QTY', 'warning');
      }
    }

    consumedInp.value = String(consumed);
    qaInp.value = String(qa);
    scrapInp.value = String(scrap);
    qaInp.max = String(Math.max(0, consumed - scrap));
    scrapInp.max = String(Math.max(0, consumed - qa));
    ln.consumedQty = consumed;
    ln.qaQty = qa;
    ln.scrapQty = scrap;
    syncWeldScrapRemarkVisibility(partIdx, lineIdx);
    updateWeldPartSummary(partIdx);
  }

  function updateWeldPartSummary(partIdx) {
    const block = document.querySelector(`.lw-weld-part-block[data-part-idx="${partIdx}"]`);
    if (!block) return;
    const weldQty = parseInt($('#lw-weld-modal-qty')?.value, 10) || 0;
    const ch = _weldModalChildren[partIdx];
    if (!ch) return;
    const required = weldRequiredForPart(ch, weldQty);
    const weldedTotal = weldWeldedTotal(ch);
    const summary = block.querySelector('.lw-weld-part-welded');
    const removedSummary = block.querySelector('.lw-weld-part-removed strong');
    const strong = summary?.querySelector('strong');
    const reqStrong = block.querySelector('.lw-weld-part-req strong');
    if (reqStrong) reqStrong.textContent = String(required);
    if (strong) strong.textContent = String(weldedTotal);
    if (removedSummary && isWeldReworkMode()) {
      removedSummary.textContent = String(weldRemovedTotal(ch));
    }
    if (summary) {
      summary.classList.remove('lw-weld-part-welded--ok', 'lw-weld-part-welded--over');
      if (required > 0) {
        if (isWeldReworkMode()) {
          if (weldedTotal > 0 && weldedTotal <= required) summary.classList.add('lw-weld-part-welded--ok');
          else if (weldedTotal > required) summary.classList.add('lw-weld-part-welded--over');
        } else if (weldedTotal === required) {
          summary.classList.add('lw-weld-part-welded--ok');
        } else {
          summary.classList.add('lw-weld-part-welded--over');
        }
      }
    }
  }

  async function resolveReworkPending(targetLotId) {
    const saPart = _weldModalSubAssemblyPartNo || null;
    const cacheKey = reworkTargetCacheKey(_weldModalBomId, saPart);
    let lots = _reworkTargetLotsCache[cacheKey] || [];
    let match = lots.find(l => Number(l.lotId) === targetLotId);
    if (match) return Number(match.reworkPending) || 0;

    const selectedOpt = $('#lw-weld-modal-target-lot')?.selectedOptions?.[0];
    if (selectedOpt?.dataset?.reworkPending != null) {
      return Number(selectedOpt.dataset.reworkPending) || 0;
    }

    if (_weldModalContext === 'sub_assembly' && saPart) {
      const altKey = reworkTargetCacheKey(_weldModalBomId, null);
      lots = _reworkTargetLotsCache[altKey] || [];
      match = lots.find(l => Number(l.lotId) === targetLotId);
      if (match) return Number(match.reworkPending) || 0;
    }

    lots = await fetchReworkTargetLots(_weldModalBomId, saPart);
    match = lots.find(l => Number(l.lotId) === targetLotId);
    return Number(match?.reworkPending) || 0;
  }

  function renderWeldModalChildren() {
    const body = $('#lw-weld-modal-children');
    if (!body) return;
    const weldQty = parseInt($('#lw-weld-modal-qty')?.value, 10) || 0;
    const isRw = isWeldReworkMode();
    const isSa = isSubAssemblyWeldContext();
    const totalLabel = completeTotalLabel(isSa);

    let html = '';
    _weldModalChildren.forEach((ch, partIdx) => {
      const required = weldRequiredForPart(ch, weldQty);
      const weldedTotal = weldWeldedTotal(ch);
      const removedTotal = isRw ? weldRemovedTotal(ch) : 0;
      if (!ch.lines?.length) ch.lines = [emptyWeldLine()];
      ensureWeldTrailingLine(ch);

      let weldedCls = '';
      if (required > 0) {
        if (isRw) {
          weldedCls = weldedTotal > 0 && weldedTotal <= required
            ? ' lw-weld-part-welded--ok' : (weldedTotal > required ? ' lw-weld-part-welded--over' : '');
        } else {
          weldedCls = weldedTotal === required
            ? ' lw-weld-part-welded--ok' : ' lw-weld-part-welded--over';
        }
      }

      html += `<div class="lw-weld-part-block" data-part-idx="${partIdx}">`;
      html += '<div class="lw-weld-part-head">';
      html += `<span class="lw-weld-part-no" title="${escapeAttr(ch.partName || '')}">${escapeHtml(ch.partNo)}</span>`;
      if (ch.partName) html += `<span class="lw-weld-part-name">${escapeHtml(ch.partName)}</span>`;
      html += `<span class="lw-weld-part-req">Required: <strong>${required}</strong></span>`;
      html += `<span class="lw-weld-part-welded${weldedCls}">${totalLabel}: <strong>${weldedTotal}</strong></span>`;
      if (isRw) {
        html += `<span class="lw-weld-part-removed">Removed: <strong>${removedTotal}</strong></span>`;
      }
      html += '</div>';

      html += '<table class="ti-table lw-weld-part-table"><thead><tr>';
      html += '<th class="lw-weld-col-lot">Child Lot</th>';
      html += '<th class="lw-weld-col-num">Consumed</th>';
      html += '<th class="lw-weld-col-num">QA</th>';
      html += '<th class="lw-weld-col-num">Scrap</th>';
      html += '<th class="lw-weld-col-remark">Remark</th>';
      html += '<th class="lw-weld-col-action"></th></tr></thead><tbody>';

      ch.lines.forEach((ln, lineIdx) => {
        const usedLots = weldLotsUsedInPart(ch, lineIdx);
        const isTrailing = lineIdx === ch.lines.length - 1 && isWeldLineEmpty(ln);
        const consumed = Number(ln.consumedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const scrapMax = ch.isBoPart ? consumed : Math.max(0, consumed - qa);

        html += '<tr>';
        html += `<td class="lw-weld-col-lot"><select class="ti-input lw-weld-child-lot" data-part-idx="${partIdx}" data-line-idx="${lineIdx}">`;
        html += '<option value="">Select lot…</option>';
        (ch.lots || []).forEach(l => {
          const lid = Number(l.lotId);
          if (usedLots.has(lid) && Number(ln.childLotId) !== lid) return;
          const sel = Number(ln.childLotId) === lid ? ' selected' : '';
          html += `<option value="${l.lotId}"${sel}>${escapeHtml(l.newLotNo)} (ok: ${l.totalOkayed})</option>`;
        });
        html += '</select></td>';
        html += `<td class="lw-weld-col-num"><input type="number" class="ti-input lw-weld-consumed" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" value="${consumed}" /></td>`;
        if (ch.isBoPart) {
          html += '<td class="lw-weld-col-num lw-weld-qa-placeholder">—</td>';
        } else {
          html += `<td class="lw-weld-col-num"><input type="number" class="ti-input lw-weld-qa" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${consumed}" value="${qa}" /></td>`;
        }
        html += `<td class="lw-weld-col-num"><input type="number" class="ti-input lw-weld-scrap" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
        html += `<td class="lw-weld-col-remark"><div class="lw-weld-scrap-remark-wrap" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-weld-scrap-remark" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Remark" /></div></td>`;
        html += !isTrailing
          ? `<td class="lw-weld-col-action"><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-weld-line-remove" data-part-idx="${partIdx}" data-line-idx="${lineIdx}">✕</button></td>`
          : '<td class="lw-weld-col-action"></td>';
        html += '</tr>';
      });

      html += '</tbody></table></div>';
    });
    body.innerHTML = html;
  }

  async function openWeldModal(row) {
    const overlay = $('#lw-weld-modal-overlay');
    if (!overlay || !row) return;
    _weldModalContext = SA_TABS.has(_tab) ? 'sub_assembly' : 'assembly';
    _weldModalDraftLineId = row.draftLineId || row.lineId || null;
    _weldModalBomId = row.bomId;
    _weldModalOperatorIds = row.operatorIds || [];
    _weldModalSubAssemblyPartNo = _weldModalContext === 'sub_assembly'
      ? (row.subAssemblyPartNo || row.partNumber || null)
      : null;
    _weldModalTargetLotId = null;

    updateWeldModalChrome();

    const bomLabel = _weldModalContext === 'sub_assembly'
      ? `${row.partNumber || ''} / ${row.subAssemblyPartNo || row.partName || ''}`
      : (row.partNumber ? `${row.partNumber} — ${row.productName || ''}` : '—');
    $('#lw-weld-modal-bom').textContent = bomLabel;
    $('#lw-weld-modal-bom').dataset.bomId = String(row.bomId || '');
    $('#lw-weld-modal-operator').textContent = operatorDisplayName(row);
    const machineEl = $('#lw-weld-modal-machine');
    if (machineEl) machineEl.textContent = row.machineName || '—';
    $('#lw-weld-modal-hours').value = '0';
    $('#lw-weld-modal-mins').value = '0';
    $('#lw-weld-modal-qty').value = '0';
    const parentQa = $('#lw-weld-modal-parent-qa');
    const parentScrap = $('#lw-weld-modal-parent-scrap');
    const parentScrapRemark = $('#lw-weld-modal-parent-scrap-remark');
    if (parentQa) parentQa.value = '0';
    if (parentScrap) parentScrap.value = '0';
    if (parentScrapRemark) parentScrapRemark.value = '';
    const parentHours = $('#lw-weld-modal-parent-hours');
    const parentMins = $('#lw-weld-modal-parent-mins');
    if (parentHours) parentHours.value = '0';
    if (parentMins) parentMins.value = '0';
    syncWeldParentScrapRemarkVisibility();
    const otInp = $('#lw-weld-modal-ot');
    if (otInp) otInp.checked = false;

    if (isWeldReworkMode()) {
      const saPart = row.subAssemblyPartNo || row.partNumber;
      const targetLots = await fetchReworkTargetLots(row.bomId, saPart);
      populateWeldTargetLotSelect(targetLots, null);
      const targetSel = $('#lw-weld-modal-target-lot');
      if (targetSel) targetSel.value = '';
    }

    const childrenUrl = _weldModalContext === 'sub_assembly'
      ? '/api/laser-welding/sub-assembly/boms/' + encodeURIComponent(row.bomId)
        + '/children?subAssemblyPartNo=' + encodeURIComponent(row.subAssemblyPartNo || row.partNumber || '')
      : '/api/laser-welding/boms/' + encodeURIComponent(row.bomId) + '/children';
    const data = await apiFetch(childrenUrl);
    const children = data.children || [];
    _weldModalChildren = [];
    for (const ch of children) {
      const lots = await fetchChildLots(ch.partNo);
      _weldModalChildren.push({
        partNo: ch.partNo,
        partName: ch.partName,
        bomQty: ch.qty,
        isBoPart: !!ch.isBoPart,
        lots,
        lines: [emptyWeldLine()],
      });
    }
    renderWeldModalChildren();
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeWeldModal() {
    const overlay = $('#lw-weld-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _weldModalDraftLineId = null;
    _weldModalBomId = null;
    _weldModalOperatorIds = [];
    _weldModalTargetLotId = null;
    _weldModalChildren = [];
    _weldModalSubAssemblyPartNo = null;
    _weldModalContext = 'assembly';
    const otInp = $('#lw-weld-modal-ot');
    if (otInp) otInp.checked = false;
    const parentQa = $('#lw-weld-modal-parent-qa');
    const parentScrap = $('#lw-weld-modal-parent-scrap');
    const parentScrapRemark = $('#lw-weld-modal-parent-scrap-remark');
    if (parentQa) parentQa.value = '0';
    if (parentScrap) parentScrap.value = '0';
    if (parentScrapRemark) parentScrapRemark.value = '';
    const parentHours = $('#lw-weld-modal-parent-hours');
    const parentMins = $('#lw-weld-modal-parent-mins');
    if (parentHours) parentHours.value = '0';
    if (parentMins) parentMins.value = '0';
  }

  async function saveWeldModal() {
    const draftLineId = _weldModalDraftLineId;
    if (!draftLineId) {
      showSnackbar('Pending assembly row not found', 'warning');
      return;
    }
    const isRw = isWeldReworkMode();
    const isSa = isSubAssemblyWeldContext();
    const otFlag = $('#lw-weld-modal-ot')?.checked ? 'Y' : 'N';
    const weldQty = parseInt($('#lw-weld-modal-qty')?.value, 10) || 0;
    if (weldQty <= 0) {
      showSnackbar(
        isRw ? 'Re-work QTY must be greater than 0' : `${completeQtyLabel(isSa)} must be greater than 0`,
        'error',
      );
      return;
    }
    if (isRw) {
      const targetLotId = parseInt($('#lw-weld-modal-target-lot')?.value, 10) || null;
      if (!targetLotId) {
        showSnackbar('Select assembly lot for re-work', 'error');
        return;
      }
      const pending = await resolveReworkPending(targetLotId);
      if (weldQty > pending) {
        showSnackbar(`Re-work QTY cannot exceed rework pending (${pending})`, 'error');
        return;
      }
      _weldModalTargetLotId = targetLotId;
    }

    const hours = parseInt($('#lw-weld-modal-hours')?.value, 10) || 0;
    const mins = parseInt($('#lw-weld-modal-mins')?.value, 10) || 0;
    if (mins < 0 || mins > 60) {
      showSnackbar('Minutes must be between 0 and 60', 'error');
      return;
    }
    const timeTakenMinutes = hours * 60 + mins;
    if (timeTakenMinutes <= 0) {
      showSnackbar('Time taken is required', 'error');
      return;
    }

    const parentQa = parseInt($('#lw-weld-modal-parent-qa')?.value, 10) || 0;
    const parentScrap = parseInt($('#lw-weld-modal-parent-scrap')?.value, 10) || 0;
    const parentScrapRemark = ($('#lw-weld-modal-parent-scrap-remark')?.value || '').trim();
    if (parentQa < 0 || parentScrap < 0) {
      showSnackbar('QA and Scrap QTY cannot be negative', 'error');
      return;
    }
    if (parentQa + parentScrap > weldQty) {
      showSnackbar('QA + Scrap cannot exceed weld QTY', 'error');
      return;
    }
    if (parentScrap > 0 && !parentScrapRemark) {
      showSnackbar('Remark is required when scrap QTY > 0', 'error');
      return;
    }
    let parentInspection = null;
    if (parentQa > 0 || parentScrap > 0) {
      const pHours = parseInt($('#lw-weld-modal-parent-hours')?.value, 10) || 0;
      const pMins = parseInt($('#lw-weld-modal-parent-mins')?.value, 10) || 0;
      const inspectionTimeTakenMinutes = pHours * 60 + pMins;
      if (inspectionTimeTakenMinutes <= 0) {
        showSnackbar('Inspection time is required when QA or Scrap > 0', 'error');
        return;
      }
      parentInspection = {
        qaQty: parentQa,
        scrapQty: parentScrap,
        scrapRemark: parentScrap > 0 ? parentScrapRemark : undefined,
        inspectionTimeTakenMinutes,
      };
    }

    const consumptions = [];
    for (let partIdx = 0; partIdx < _weldModalChildren.length; partIdx++) {
      const ch = _weldModalChildren[partIdx];
      const required = weldRequiredForPart(ch, weldQty);
      let partWelded = 0;
      const seenLots = new Set();
      for (let lineIdx = 0; lineIdx < (ch.lines || []).length; lineIdx++) {
        const ln = ch.lines[lineIdx];
        const consumed = Number(ln.consumedQty) || 0;
        let qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const scrapRemark = ($(`.lw-weld-scrap-remark[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`)?.value || '').trim();
        if (!ln.childLotId && consumed <= 0 && qa <= 0 && scrap <= 0) continue;
        if (!ln.childLotId) {
          showSnackbar(`Select child lot for ${ch.partNo}`, 'error');
          return;
        }
        if (consumed <= 0) {
          showSnackbar(`Enter Consumed QTY for ${ch.partNo}`, 'error');
          return;
        }
        if (ch.isBoPart) {
          qa = 0;
          if (scrap > consumed) {
            showSnackbar(`Scrap cannot exceed Consumed for ${ch.partNo}`, 'error');
            return;
          }
        } else if (qa + scrap > consumed) {
          showSnackbar(`QA + Scrap cannot exceed Consumed for ${ch.partNo}`, 'error');
          return;
        }
        const lotKey = Number(ln.childLotId);
        if (seenLots.has(lotKey)) {
          showSnackbar(`Duplicate child lot for ${ch.partNo}`, 'error');
          return;
        }
        seenLots.add(lotKey);
        const welded = ch.isBoPart ? consumed - scrap : consumed - qa - scrap;
        partWelded += welded;
        consumptions.push({
          partNumber: ch.partNo,
          childLotId: ln.childLotId,
          consumedQty: consumed,
          qaQty: qa,
          scrapQty: scrap,
          scrapRemark: scrap > 0 ? scrapRemark : undefined,
        });
      }
      if (isRw) {
        if (partWelded > required) {
          showSnackbar(
            `${completeTotalLabel(isSa)} total for ${ch.partNo} cannot exceed ${required} (BOM × re-work qty), got ${partWelded}`,
            'error',
          );
          return;
        }
      } else if (partWelded !== required) {
        const qtyWord = isSa ? 'assembly' : 'weld';
        showSnackbar(
          `${completeTotalLabel(isSa)} total for ${ch.partNo} must be ${required} (BOM × ${qtyWord} qty), got ${partWelded}`,
          'error',
        );
        return;
      }
    }

    try {
      if (isRw) {
        const reworkUrl = isSa
          ? '/api/laser-welding/sub-assembly/rework/weld'
          : '/api/laser-welding/assembly/rework/weld';
        const data = await apiPost(reworkUrl, {
          draftLineId,
          workDate: _workDate,
          targetLotId: _weldModalTargetLotId,
          reworkQty: weldQty,
          timeTakenMinutes,
          operatorIds: _weldModalOperatorIds.length ? _weldModalOperatorIds : undefined,
          consumptions,
          otFlag,
          ...(parentInspection || {}),
        });
        showSnackbar(`Re-work saved — Lot No: ${data.newLotNo || ''}`, 'success');
      } else {
        const weldUrl = isSa
          ? '/api/laser-welding/sub-assembly/weld'
          : '/api/laser-welding/assembly/weld';
        const data = await apiPost(weldUrl, {
          draftLineId,
          workDate: _workDate,
          weldQty,
          timeTakenMinutes,
          operatorIds: _weldModalOperatorIds.length ? _weldModalOperatorIds : undefined,
          consumptions,
          otFlag,
          ...(parentInspection || {}),
        });
        showSnackbar(`${completeActionLabel(false, isSa)} — Lot No: ${data.newLotNo || ''}`, 'success');
      }
      closeWeldModal();
      invalidateLwCaches(true);
      if (isSa) await loadSubAssemblyRows(true);
      else await loadAssemblyRows(true);
    } catch (err) {
      showSnackbar(err.message || (isRw ? 'Re-work failed' : (isSa ? 'Assembly failed' : 'Weld failed')), 'error');
    }
  }

  function onWeldModalClick(e) {
    const removeBtn = e.target.closest('.lw-weld-line-remove');
    if (!removeBtn) return;
    const partIdx = Number(removeBtn.getAttribute('data-part-idx'));
    const lineIdx = Number(removeBtn.getAttribute('data-line-idx'));
    const ch = _weldModalChildren[partIdx];
    if (!ch?.lines) return;
    ch.lines.splice(lineIdx, 1);
    if (!ch.lines.length) ch.lines.push(emptyWeldLine());
    renderWeldModalChildren();
  }

  function onWeldModalChange(e) {
    const lotSel = e.target.closest('.lw-weld-child-lot');
    if (!lotSel) return;
    const partIdx = Number(lotSel.getAttribute('data-part-idx'));
    const lineIdx = Number(lotSel.getAttribute('data-line-idx'));
    const ln = getWeldLine(partIdx, lineIdx);
    if (!ln) return;
    ln.childLotId = parseInt(lotSel.value, 10) || null;
    const ch = _weldModalChildren[partIdx];
    if (ln.childLotId && ch && lineIdx === ch.lines.length - 1) {
      renderWeldModalChildren();
    }
  }

  function onWeldModalInput(e) {
    const consumedInp = e.target.closest('.lw-weld-consumed');
    if (consumedInp) {
      syncWeldLineQtyCaps(
        Number(consumedInp.getAttribute('data-part-idx')),
        Number(consumedInp.getAttribute('data-line-idx')),
        'consumed',
      );
      return;
    }
    const qaInp = e.target.closest('.lw-weld-qa');
    if (qaInp) {
      syncWeldLineQtyCaps(
        Number(qaInp.getAttribute('data-part-idx')),
        Number(qaInp.getAttribute('data-line-idx')),
        'qa',
      );
      return;
    }
    const scrapInp = e.target.closest('.lw-weld-scrap');
    if (scrapInp) {
      syncWeldLineQtyCaps(
        Number(scrapInp.getAttribute('data-part-idx')),
        Number(scrapInp.getAttribute('data-line-idx')),
        'scrap',
      );
    }
  }

  function showPanel(tab) {
    $$('.lw-panel').forEach(p => p.classList.remove('lw-panel--active'));
    if (isGridTab(tab)) {
      $('#lw-grid-panel')?.classList.add('lw-panel--active');
    } else if (SA_TABS.has(tab)) {
      $('#lw-sa-panel')?.classList.add('lw-panel--active');
    } else if (ASM_TABS.has(tab)) {
      $('#lw-asm-panel')?.classList.add('lw-panel--active');
    } else if (tab === 'trays_carton') {
      $('#lw-trays-carton-panel')?.classList.add('lw-panel--active');
    } else if (tab === 'tracking') {
      $('#lw-tracking-panel')?.classList.add('lw-panel--active');
    } else if (tab === 'reports') {
      $('#lw-reports-panel')?.classList.add('lw-panel--active');
    }
    const trackTools = $('#lw-track-toolbar-tools');
    const reportsTools = $('#lw-reports-toolbar-tools');
    if (trackTools) trackTools.hidden = tab !== 'tracking';
    if (reportsTools) reportsTools.hidden = tab !== 'reports';
    updateReportsToolbar();
    const search = $('#lw-grid-search');
    const dateInput = $('#lw-work-date');
    const dateLabel = $('.lw-date-label');
    const countEl = $('#lw-item-count');
    const showToolbarInputs = isGridTab(tab) || ASM_TABS.has(tab) || SA_TABS.has(tab) || tab === 'trays_carton';
    const hideDateSearch = TRACK_TABS.has(tab);
    if (search) search.style.display = showToolbarInputs && !hideDateSearch ? '' : 'none';
    if (dateInput) dateInput.style.display = showToolbarInputs && !hideDateSearch ? '' : 'none';
    if (dateLabel) dateLabel.style.display = showToolbarInputs && !hideDateSearch ? '' : 'none';
    if (countEl && TRACK_TABS.has(tab)) countEl.style.display = 'none';
    else if (countEl) countEl.style.display = '';
  }

  function switchTab(tab) {
    _tab = tab;
    _expanded = {};
    _asmExpanded = {};
    _saExpanded = {};

    $$('.lw-tab').forEach(btn => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle('lw-tab--active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    showPanel(tab);
    const root = $('#lw-root');
    if (root) root.classList.toggle('lw-tab--packing', tab === 'packing');
    updateGridTableHeaders();
    const subtitle = $('#lw-subtitle');
    if (subtitle) subtitle.textContent = TAB_LABELS[tab] || '';

    refreshActiveTab(false);
  }

  function onAsmTableClick(e) {
    if (handleLwTreeToggle(e)) return;
    const assignBtn = e.target.closest('.lw-eligible-act-assign');
    if (assignBtn && !assignBtn.disabled) {
      void assignEligibleAsmRow(
        assignBtn.getAttribute('data-eligible-key'),
        assignBtn.closest('tr'),
      );
      return;
    }
    const dismissBtn = e.target.closest('.lw-act-dismiss');
    if (dismissBtn) {
      const row = findAsmRow(dismissBtn.getAttribute('data-row-key'));
      if (row) dismissDraftRow(row);
      return;
    }
    const detailBtn = e.target.closest('.lw-asm-act-detail');
    if (detailBtn) {
      const key = detailBtn.getAttribute('data-row-key');
      if (key) {
        _asmExpanded[key] = !_asmExpanded[key];
        renderAssemblyTable();
      }
      return;
    }
    const weldBtn = e.target.closest('.lw-asm-act-weld');
    if (weldBtn) {
      const row = findAsmRow(weldBtn.getAttribute('data-row-key'));
      if (row) openWeldModal(row);
    }
  }

  function onSaTableClick(e) {
    if (handleLwTreeToggle(e)) return;
    const assignBtn = e.target.closest('.lw-eligible-act-assign');
    if (assignBtn && !assignBtn.disabled) {
      void assignEligibleSaRow(
        assignBtn.getAttribute('data-eligible-key'),
        assignBtn.closest('tr'),
      );
      return;
    }
    const dismissBtn = e.target.closest('.lw-act-dismiss');
    if (dismissBtn) {
      const row = findSaRow(dismissBtn.getAttribute('data-row-key'));
      if (row) dismissDraftRow(row);
      return;
    }
    const detailBtn = e.target.closest('.lw-asm-act-detail');
    if (detailBtn) {
      const key = detailBtn.getAttribute('data-row-key');
      if (key) {
        _saExpanded[key] = !_saExpanded[key];
        renderSubAssemblyTable();
      }
      return;
    }
    const weldBtn = e.target.closest('.lw-asm-act-weld');
    if (weldBtn) {
      const row = findSaRow(weldBtn.getAttribute('data-row-key'));
      if (row) openWeldModal(row);
    }
  }

  function onTableClick(e) {
    if (handleLwTreeToggle(e)) return;
    const assignBtn = e.target.closest('.lw-eligible-act-assign');
    if (assignBtn && !assignBtn.disabled) {
      void assignEligibleQaRow(
        assignBtn.getAttribute('data-eligible-key'),
        assignBtn.closest('tr'),
      );
      return;
    }
    const dismissBtn = e.target.closest('.lw-act-dismiss');
    if (dismissBtn) {
      const row = findRow(dismissBtn.getAttribute('data-row-key'));
      if (row) dismissDraftRow(row);
      return;
    }
    const detailBtn = e.target.closest('.lw-act-detail');
    if (detailBtn) {
      const key = detailBtn.getAttribute('data-row-key');
      if (key) {
        _expanded[key] = !_expanded[key];
        renderTable();
      }
      return;
    }
    const inspectBtn = e.target.closest('.lw-act-inspect');
    if (inspectBtn) {
      const row = findRow(inspectBtn.getAttribute('data-row-key'));
      if (row) openProductionModal(row);
    }
  }

  function onProductionModalClick(e) {
    const removeBtn = e.target.closest('.lw-prod-line-remove');
    if (removeBtn) {
      const idx = Number(removeBtn.getAttribute('data-idx'));
      _prodModalLines.splice(idx, 1);
      if (!_prodModalLines.length) _prodModalLines.push(emptyLine());
      renderProductionModalLines();
      return;
    }
    const lotSel = e.target.closest('.lw-prod-line-lot');
    if (lotSel) onProductionModalLotChange(lotSel);
  }

  function onProductionModalInput(e) {
    const insp = e.target.closest('.lw-prod-line-insp');
    if (insp) {
      syncProdLineQtyCaps(Number(insp.getAttribute('data-idx')), 'insp');
      return;
    }
    const qa = e.target.closest('.lw-prod-line-qa');
    if (qa) {
      syncProdLineQtyCaps(Number(qa.getAttribute('data-idx')), 'qa');
      return;
    }
    const passed = e.target.closest('.lw-prod-line-passed');
    if (passed) {
      syncProdLineQtyCaps(Number(passed.getAttribute('data-idx')), 'passed');
      return;
    }
    const rework = e.target.closest('.lw-prod-line-rework');
    if (rework) {
      syncProdLineQtyCaps(Number(rework.getAttribute('data-idx')), 'rework');
      return;
    }
    const scrap = e.target.closest('.lw-prod-line-scrap');
    if (scrap) {
      syncProdLineQtyCaps(Number(scrap.getAttribute('data-idx')), 'scrap');
      return;
    }
    const pack = e.target.closest('.lw-prod-line-pack');
    if (pack) {
      syncProdLineQtyCaps(Number(pack.getAttribute('data-idx')), 'pack');
    }
  }

  // --- Tracking ---

  const TRACK_CHILD_PHASES = [
    { id: 'erp_stock', label: 'ERP stock' },
    { id: 'inspected_ready', label: 'Inspected' },
    { id: 'qa_pending', label: 'QA pending' },
    { id: 'consumed', label: 'Consumed' },
  ];
  const TRACK_SA_PHASES = [
    { id: 'awaiting_clean', label: 'Awaiting clean' },
    { id: 'qa_pending', label: 'QA pending' },
    { id: 'ready_for_weld', label: 'Ready for weld' },
    { id: 'rework_pending', label: 'Rework' },
  ];
  const TRACK_FG_PHASES = [
    { id: 'awaiting_clean', label: 'Awaiting clean' },
    { id: 'qa_pending', label: 'QA pending' },
    { id: 'ready_to_pack', label: 'Ready to pack' },
    { id: 'rework_pending', label: 'Rework' },
  ];

  const TRACK_PHASE_LABELS = {
    erp_stock: 'ERP stock',
    inspected_ready: 'Inspected ready',
    qa_pending: 'QA pending',
    consumed: 'Consumed',
    awaiting_clean: 'Awaiting clean',
    ready_for_weld: 'Ready for weld',
    ready_to_pack: 'Ready to pack',
    rework_pending: 'Rework pending',
  };

  const MATERIAL_FLOW_STEPS = [
    { id: 'inspection', label: 'Inspection', tab: 'inspection', filterPhases: ['erp_stock', 'inspected_ready'] },
    { id: 'sub_assembly', label: 'Sub-Assembly', tab: 'sub_assembly', filterPhases: ['ready_for_weld'], kinds: ['sa'] },
    { id: 'sa_cleaning', label: 'SA Inspection', tab: 'sa_cleaning', filterPhases: ['awaiting_clean'], kinds: ['sa'] },
    { id: 'sa_rework', label: 'SA Re-Work', tab: 'sa_rework', filterPhases: ['rework_pending'], kinds: ['sa'] },
    { id: 'laser_welding', label: 'Laser Welding', tab: 'laser_welding', filterPhases: ['ready_for_weld'], kinds: ['fg'] },
    { id: 'lw_cleaning', label: 'LW Cleaning/Inspection', tab: 'lw_cleaning', filterPhases: ['awaiting_clean'], kinds: ['fg'] },
    { id: 'lw_rework', label: 'LW Re-Work', tab: 'lw_rework', filterPhases: ['rework_pending'], kinds: ['fg'] },
    { id: 'packing', label: 'Packing', tab: 'packing', filterPhases: ['ready_to_pack'], kinds: ['fg'] },
    { id: 'qa', label: 'QA', tab: 'qa', filterPhases: ['qa_pending'] },
  ];

  function actionTabForItem(item, kind) {
    if (!item || item.phase === 'consumed') return null;
    const phase = item.phase;
    if (kind === 'child' && (phase === 'erp_stock' || phase === 'inspected_ready')) {
      return 'inspection';
    }
    if (phase === 'qa_pending') return 'qa';
    if (phase === 'awaiting_clean') return kind === 'sa' ? 'sa_cleaning' : 'lw_cleaning';
    if (phase === 'rework_pending') return kind === 'sa' ? 'sa_rework' : 'lw_rework';
    if (phase === 'ready_to_pack' && kind === 'fg') return 'packing';
    if (phase === 'ready_for_weld' && kind === 'sa') return 'laser_welding';
    return null;
  }

  function matchWorkflowStep(step, item) {
    if (!step || !item) return false;
    return actionTabForItem(item, item.kind) === step.tab;
  }

  function findWorkflowStep(stepId) {
    return MATERIAL_FLOW_STEPS.find(s => s.id === stepId) || null;
  }

  function trackPhaseLabel(phase) {
    return TRACK_PHASE_LABELS[phase] || phase || '—';
  }

  function setTrackLoading(on, { skeleton = true } = {}) {
    _trackLoading = !!on;
    if (!skeleton) return;
    const shell = $('#lw-track-dash-shell');
    const skel = $('#lw-track-skeleton');
    if (shell) shell.classList.toggle('is-loading', !!on);
    if (skel) skel.setAttribute('aria-hidden', on ? 'false' : 'true');
  }

  function setTrackError(msg) {
    const trackEl = $('#lw-tracking-error');
    const reportsEl = $('#lw-reports-error');
    [trackEl, reportsEl].forEach(el => {
      if (!el) return;
      el.textContent = '';
      el.style.display = 'none';
    });
    const el = _tab === 'reports' ? reportsEl : trackEl;
    if (!el || !msg) return;
    el.textContent = msg;
    el.style.display = '';
  }

  function trackingQueryParams() {
    const params = new URLSearchParams();
    if (_trackCustId) params.set('custId', _trackCustId);
    if (_trackSearch.trim()) params.set('q', _trackSearch.trim());
    const qs = params.toString();
    return qs ? `?${qs}` : '';
  }

  function trackingFetchKey() {
    return `${_trackCustId || ''}|${_trackSearch.trim()}`;
  }

  function getActiveTrackingData() {
    return _trackingDataRaw;
  }

  function getFilteredTrackingData() {
    const raw = _trackingDataRaw;
    if (!raw || _tab !== 'tracking') return raw;
    if (_trackFlowStep) {
      const step = findWorkflowStep(_trackFlowStep);
      if (step) {
        const match = (item) => matchWorkflowStep(step, item);
        return {
          ...raw,
          childParts: (raw.childParts || []).filter(p => match({ ...p, kind: 'child' })),
          subAssemblies: (raw.subAssemblies || []).filter(s => match({ ...s, kind: 'sa' })),
          finalAssemblies: (raw.finalAssemblies || []).filter(f => match({ ...f, kind: 'fg' })),
        };
      }
    }
    if (!_trackPhase) return raw;
    const match = (item) => item?.phase === _trackPhase;
    return {
      ...raw,
      childParts: (raw.childParts || []).filter(match),
      subAssemblies: (raw.subAssemblies || []).filter(match),
      finalAssemblies: (raw.finalAssemblies || []).filter(match),
    };
  }

  function collectTrackActionRows(data) {
    const src = data || _trackingDataRaw;
    if (!src) return [];
    const rows = [];
    (src.childParts || []).forEach(p => {
      (p.lots || []).forEach(lot => {
        rows.push({
          type: 'Child',
          label: p.partNo,
          lot: lot.lotNo,
          phase: lot.phase || p.phase,
          okayed: lot.totalOkayed,
          qa: lot.totalQa,
          clean: lot.inspectionPending,
          rework: lot.reworkPending,
          item: { ...p, ...lot, kind: 'child', phase: lot.phase || p.phase },
        });
      });
      if (!p.lots?.length && p.phase !== 'consumed') {
        rows.push({
          type: 'Child',
          label: p.partNo,
          lot: '—',
          phase: p.phase,
          okayed: p.lwOkayed,
          qa: p.qaPending,
          clean: 0,
          rework: 0,
          item: { ...p, kind: 'child' },
        });
      }
    });
    (src.subAssemblies || []).forEach(s => {
      if (s.phase === 'consumed') return;
      rows.push({
        type: 'SA',
        label: s.saPartNo || s.partNo,
        lot: s.lotNo,
        phase: s.phase,
        okayed: s.totalOkayed,
        qa: s.totalQa,
        clean: s.inspectionPending,
        rework: s.reworkPending,
        item: { ...s, kind: 'sa' },
      });
    });
    (src.finalAssemblies || []).forEach(f => {
      if (f.phase === 'consumed') return;
      rows.push({
        type: 'FG',
        label: f.bomNo,
        lot: f.lotNo,
        phase: f.phase,
        okayed: f.totalOkayed,
        qa: f.totalQa,
        clean: f.inspectionPending,
        rework: f.reworkPending,
        item: { ...f, kind: 'fg' },
      });
    });
    return rows;
  }

  function countMaterialFlowStep(step) {
    return collectTrackActionRows(_trackingDataRaw).filter(r => matchWorkflowStep(step, r.item)).length;
  }

  async function ensureTrackCustomers() {
    const sel = $('#lw-track-cust');
    if (!sel || sel.dataset.loaded === '1') return;
    try {
      const data = await apiFetch('/api/laser-welding/bom-customers');
      const list = Array.isArray(data) ? data : (data.customers || data.rows || []);
      const current = sel.value;
      sel.innerHTML = '<option value="">All customers</option>';
      list.forEach(c => {
        const opt = document.createElement('option');
        opt.value = String(c.custId ?? c.cust_id ?? '');
        opt.textContent = c.customerName || c.customer_name || `Customer ${opt.value}`;
        sel.appendChild(opt);
      });
      if (current) sel.value = current;
      sel.dataset.loaded = '1';
    } catch (err) {
      console.error('Failed to load tracking customers', err);
    }
  }

  async function loadTracking(opts = {}) {
    if (!TRACK_TABS.has(_tab)) return;
    const forReports = _tab === 'reports';
    const cacheKey = forReports ? '__full__' : trackingFetchKey();
    if (!opts.force && _trackCache[cacheKey]) {
      _trackingDataRaw = _trackCache[cacheKey];
      _trackLoadedKey = cacheKey;
      renderTracking();
      return;
    }
    const showSkeleton = opts.skeleton !== false;
    setTrackLoading(true, { skeleton: showSkeleton });
    setTrackError('');
    try {
      if (!forReports) await ensureTrackCustomers();
      const qs = forReports ? '' : trackingQueryParams();
      const data = await apiFetch('/api/laser-welding/tracking' + qs);
      _trackingDataRaw = data;
      _trackCache[cacheKey] = data;
      _trackLoadedKey = cacheKey;
      renderTracking();
    } catch (err) {
      console.error(err);
      setTrackError(err.message || 'Failed to load tracking data');
    } finally {
      setTrackLoading(false, { skeleton: showSkeleton });
    }
  }

  function updateReportsToolbar() {
    const reportSel = $('#lw-report-view');
    const histFilters = $('#lw-history-toolbar-filters');
    const stepFilter = $('#lw-report-step-filter');
    const dateFrom = $('#lw-report-date-from');
    const dateTo = $('#lw-report-date-to');
    const fromInput = $('#lw-history-from');
    const toInput = $('#lw-history-to');
    const stepInput = $('#lw-history-step');
    const exportBtn = $('#lw-history-export');
    const view = _trackReportView;
    const onReports = _tab === 'reports';
    const filteredViews = new Set(['history', 'qa', 'scrap', 'stock']);
    const exportableViews = new Set(['history', 'stock', 'qa', 'scrap']);
    const isStock = view === 'stock';
    if (reportSel) reportSel.value = view;
    if (histFilters) histFilters.hidden = !onReports || !filteredViews.has(view);
    if (exportBtn) exportBtn.hidden = !onReports || !exportableViews.has(view);
    if (stepFilter) stepFilter.hidden = isStock;
    if (dateFrom) dateFrom.hidden = isStock;
    if (dateTo) dateTo.hidden = isStock;
    if (fromInput) fromInput.disabled = isStock;
    if (toInput) toInput.disabled = isStock;
    if (stepInput) stepInput.disabled = isStock;
  }

  const LW_REPORT_EXPORT_NAMES = {
    history: 'Activity',
    stock: 'Stock',
    qa: 'QA',
    scrap: 'Scrap',
  };

  const STOCK_QTY_COLUMNS = [
    { key: 'inspection_pending', label: 'Inspection Pending' },
    { key: 'fg', label: 'FG' },
    { key: 'qa', label: 'QA' },
    { key: 'scrap', label: 'Scrap' },
    { key: 'rework_pending', label: 'Rework Pending' },
    { key: 'packed', label: 'Packed' },
  ];

  const HISTORY_GRID_COLUMNS = [
    {
      key: '_expand',
      label: '',
      sortable: false,
      width: 40,
      format: (val, row) => {
        if (!row.hasDetail) return '';
        const exp = _historyExpanded[row._rowKey];
        return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-history-act-detail${exp ? ' is-expanded' : ''}" `
          + `data-history-key="${escapeAttr(row._rowKey)}" title="Show consumption lines">▤</button>`;
      },
    },
    { key: 'workDate', label: 'Date', width: 96, format: (v, row) => escapeHtml(row.workDateDisplay || v || '—') },
    { key: 'workflowLabel', label: 'Step', width: 120 },
    { key: 'rowClass', label: 'Type', width: 56 },
    { key: 'label', label: 'Part / BOM', width: 140 },
    {
      key: 'lotNo',
      label: 'Lot',
      width: 110,
      format: (v, row) => {
        const lot = row.packLotNo || v;
        if (!lot || lot === '—') return '—';
        if (row.workflowStep === 'packing' && row.packLotNo) {
          return `<span class="lw-lot-badge" title="Packed output lot">${escapeHtml(row.packLotNo)}</span>`;
        }
        return `<code>${escapeHtml(lot)}</code>`;
      },
    },
    { key: 'operator', label: 'Operator', width: 130 },
    { key: 'machineName', label: 'Machine', width: 110 },
    { key: 'inspectedQty', label: 'Qty', align: 'right', width: 64 },
    { key: 'qaQty', label: 'QA', align: 'right', width: 52 },
    { key: 'scrapQty', label: 'Scrap', align: 'right', width: 58 },
    { key: 'reworkQty', label: 'Rework', align: 'right', width: 64 },
    { key: 'timeTaken', label: 'Time', width: 72 },
    {
      key: 'otFlag',
      label: 'OT',
      width: 44,
      align: 'center',
      sortable: false,
      format: (v, row) => row.otHtml || '—',
    },
  ];

  function historyRowKey(row) {
    if (row.cdLineId) return `hist:cd:${row.cdLineId}`;
    return `hist:${row.lineId}`;
  }

  function historyDetailLinesHtml(row) {
    const consumptions = row.consumptions || [];
    const totalCols = 6;
    let html = '<table class="ti-table lw-detail-table lw-history-detail-table"><thead><tr>';
    html += '<th>Type</th><th>Item ID</th><th>Lot</th><th>Consumed</th><th>QA</th><th>Scrap</th>';
    html += '</tr></thead><tbody>';
    if (!consumptions.length) {
      html += `<tr><td colspan="${totalCols}" class="lw-detail-empty">No consumption lines.</td></tr>`;
    }
    consumptions.forEach(cons => {
      const traceLines = cons.traceLines || [];
      const nested = cons.nestedConsumptions || [];
      const hasNested = traceLines.length > 0 || nested.length > 0;
      const label = cons.partNo || '—';
      html += `<tr class="lw-detail-consume-row${hasNested ? ' lw-detail-consume-row--branch' : ''}">`;
      html += `<td>${escapeHtml(cons.rowClass || 'Part')}</td>`;
      html += `<td class="lw-consume-part-cell">${cellWithTreeToggle(escapeHtml(label), hasNested)}</td>`;
      html += `<td>${escapeHtml(cons.lotNo || '—')}</td>`;
      html += `<td>${Number(cons.consumedQty) || 0}</td>`;
      html += `<td>${Number(cons.qaQty) || 0}</td>`;
      html += `<td>${Number(cons.scrapQty) || 0}</td>`;
      html += '</tr>';
      if (hasNested) {
        const nestedLines = traceLines.length > 0
          ? traceLines
          : nested.map(n => ({
            partNumber: n.partNo,
            sourceLotNo: n.lotNo,
            inspectedQty: n.consumedQty,
            qaQty: n.qaQty,
            scrapQty: n.scrapQty,
            nestedLines: n.nestedLines,
          }));
        html += traceBranchRowHtml(totalCols, nestedLines, 1);
      }
    });
    html += '</tbody></table>';
    return html;
  }

  function buildHistoryDetailContent(row) {
    return `<div class="lw-detail-inline lw-detail-body">${historyDetailLinesHtml(row)}</div>`;
  }

  function mapHistoryRowForGrid(r) {
    const consumptions = r.consumptions || [];
    return {
      _rowKey: historyRowKey(r),
      workflowStep: r.workflowStep || '',
      hasDetail: !!(r.hasDetail && consumptions.length),
      consumptions,
      workDate: r.workDate || '',
      workDateDisplay: isoToDisplayDate(r.workDate) || r.workDate || '—',
      workflowLabel: r.workflowLabel || '—',
      rowClass: r.rowClass || r.rowType || '—',
      label: r.label || r.partNo || r.bomNo || '—',
      lotNo: r.packLotNo || r.lotNo || '—',
      operator: historyOperatorLabel(r),
      machineName: r.machineName || '—',
      inspectedQty: Number(r.inspectedQty) || 0,
      qaQty: Number(r.qaQty) || 0,
      scrapQty: Number(r.scrapQty) || 0,
      reworkQty: Number(r.reworkQty) || 0,
      timeTaken: formatTimeTaken(r.timeTakenMinutes) || '—',
      otFlag: r.otFlag || '',
      otHtml: historyOtHtml(r),
    };
  }

  function destroyHistoryGrid() {
    if (_historyGrid && _historyGrid.destroy) _historyGrid.destroy();
    _historyGrid = null;
    const host = $('#lw-track-history-grid');
    if (host) host.innerHTML = '';
  }

  function ensureHistoryDateDefaults() {
    const fromEl = $('#lw-history-from');
    const toEl = $('#lw-history-to');
    const stepEl = $('#lw-history-step');
    const searchEl = $('#lw-history-search');
    if (fromEl?.value) _historyFrom = fromEl.value;
    if (toEl?.value) _historyTo = toEl.value;
    if (stepEl) _historyStep = stepEl.value || '';
    if (!_historyTo) _historyTo = todayIso();
    if (!_historyFrom) _historyFrom = isoDaysAgo(30);
    if (fromEl && !fromEl.value) fromEl.value = _historyFrom;
    if (toEl && !toEl.value) toEl.value = _historyTo;
    if (stepEl) stepEl.value = _historyStep;
    if (searchEl && searchEl.value !== _historySearch) searchEl.value = _historySearch;
  }

  function historyQueryParams() {
    ensureHistoryDateDefaults();
    const params = new URLSearchParams();
    params.set('from', _historyFrom);
    params.set('to', _historyTo);
    if (_historyStep) params.set('step', _historyStep);
    if (_historySearch.trim()) params.set('q', _historySearch.trim());
    return params.toString();
  }

  async function loadActionHistory(opts = {}) {
    if (_tab !== 'reports' || _trackReportView !== 'history') return;
    ensureHistoryDateDefaults();
    if (_historyLoading && !opts.force) return;
    _historyLoading = true;
    setTrackError('');
    const host = $('#lw-track-history-grid');
    if (host && opts.skeleton !== false && !_historyGrid) {
      host.innerHTML = '<div class="lw-track-empty lw-track-history-loading">Loading…</div>';
    }
    try {
      const data = await apiFetch('/api/laser-welding/reports/action-history?' + historyQueryParams());
      _actionHistoryRows = data.rows || [];
      renderTrackActionHistoryTable();
    } catch (err) {
      console.error(err);
      setTrackError(err.message || 'Failed to load action history');
      destroyHistoryGrid();
      if (host) {
        host.innerHTML = '<div class="lw-track-empty">Failed to load history</div>';
      }
    } finally {
      _historyLoading = false;
    }
  }

  function historyOperatorLabel(row) {
    const names = String(row.operatorNames || row.operatorName || '').trim();
    const ecno = String(row.operatorEcno || '').trim();
    if (names && ecno) return `${names} (${ecno})`;
    return names || ecno || '—';
  }

  function historyOtHtml(row) {
    return String(row.otFlag || '').toUpperCase() === 'Y'
      ? '<span class="lw-ot-badge" title="Overtime">OT</span>'
      : '—';
  }

  function renderTrackActionHistoryTable() {
    const host = $('#lw-track-history-grid');
    const countEl = $('#lw-report-count');
    if (!host) return;

    if (typeof SuperGrid === 'undefined' || typeof SuperGrid.create !== 'function') {
      host.innerHTML = '<div class="lw-track-empty">Grid component not loaded</div>';
      return;
    }

    const mapped = (_actionHistoryRows || []).map(mapHistoryRowForGrid);

    if (!_historyGrid) {
      host.innerHTML = '';
      _historyGrid = SuperGrid.create(host, {
        columns: HISTORY_GRID_COLUMNS,
        rows: mapped,
        options: {
          omitToolbar: true,
          countElement: countEl,
          countLabel: 'lines',
          emptyText: 'No activity for this range',
          layoutKey: 'lw-action-history',
          resizable: true,
          reorderable: true,
          pinnable: true,
          detailRowExpanded: (row) => !!(row.hasDetail && _historyExpanded[row._rowKey]),
          detailRowHtml: (row) => buildHistoryDetailContent(row),
        },
      });
      return;
    }

    _historyGrid.setRows(mapped);
  }

  function destroyLwReportGrid(gridRef, hostSel) {
    if (gridRef && gridRef.destroy) gridRef.destroy();
    const host = $(hostSel);
    if (host) host.innerHTML = '';
    return null;
  }

  function stockGridColumns() {
    const cols = [
      { key: 'rowType', label: 'Type', width: 56 },
      { key: 'label', label: 'Part / BOM', width: 130 },
      { key: 'partName', label: 'Name', width: 160 },
    ];
    STOCK_QTY_COLUMNS.forEach(col => {
      cols.push({
        key: col.key,
        label: col.label,
        align: 'right',
        width: 96,
      });
    });
    cols.push({ key: 'totalQty', label: 'Total', align: 'right', width: 72 });
    return cols;
  }

  const QA_GRID_COLUMNS = [
    { key: 'workDateDisplay', label: 'Date', width: 96 },
    { key: 'rowClass', label: 'Type', width: 56 },
    { key: 'label', label: 'Part / BOM', width: 130 },
    { key: 'lotNo', label: 'Lot', width: 110, format: (v) => `<code>${escapeHtml(v || '—')}</code>` },
    { key: 'supplierName', label: 'Supplier', width: 140 },
    { key: 'workflowLabel', label: 'Step', width: 120 },
    { key: 'inspectedQty', label: 'Inspected', align: 'right', width: 80 },
    { key: 'qaQty', label: 'QA', align: 'right', width: 64 },
    { key: 'operator', label: 'Operator', width: 130 },
    { key: 'scrapRemark', label: 'Remark', width: 140 },
  ];

  const SCRAP_GRID_COLUMNS = [
    { key: 'workDateDisplay', label: 'Date', width: 96 },
    { key: 'rowClass', label: 'Type', width: 56 },
    { key: 'label', label: 'Part / BOM', width: 130 },
    { key: 'lotNo', label: 'Lot', width: 110, format: (v) => `<code>${escapeHtml(v || '—')}</code>` },
    { key: 'workflowLabel', label: 'Step', width: 120 },
    { key: 'scrapQty', label: 'Scrap', align: 'right', width: 64 },
    { key: 'scrapRemark', label: 'Remark', width: 160 },
    { key: 'operator', label: 'Operator', width: 130 },
    { key: 'machineName', label: 'Machine', width: 110 },
  ];

  function mapDatedReportRowForGrid(r) {
    return {
      workDate: r.workDate || '',
      workDateDisplay: isoToDisplayDate(r.workDate) || r.workDate || '—',
      rowClass: r.rowClass || r.rowType || '—',
      label: r.label || r.partNo || r.bomNo || '—',
      lotNo: r.lotNo || '—',
      workflowLabel: r.workflowLabel || '—',
      inspectedQty: Number(r.inspectedQty) || 0,
      qaQty: Number(r.qaQty) || 0,
      scrapQty: Number(r.scrapQty) || 0,
      scrapRemark: r.scrapRemark || r.reworkRemark || '—',
      operator: historyOperatorLabel(r),
      machineName: r.machineName || '—',
      supplierName: r.supplierName || '—',
    };
  }

  function renderLwReportGrid(hostSel, gridRef, columns, rows, layoutKey, emptyText) {
    const host = $(hostSel);
    const countEl = $('#lw-report-count');
    if (!host) return gridRef;
    if (typeof SuperGrid === 'undefined' || typeof SuperGrid.create !== 'function') {
      host.innerHTML = '<div class="lw-track-empty">Grid component not loaded</div>';
      return gridRef;
    }
    if (!gridRef) {
      host.innerHTML = '';
      return SuperGrid.create(host, {
        columns,
        rows,
        options: {
          omitToolbar: true,
          countElement: countEl,
          countLabel: 'lines',
          emptyText,
          layoutKey,
          resizable: true,
          reorderable: true,
          pinnable: true,
        },
      });
    }
    gridRef.setRows(rows);
    return gridRef;
  }

  async function loadStockReport(opts = {}) {
    if (_tab !== 'reports' || _trackReportView !== 'stock') return;
    if (_stockLoading && !opts.force) return;
    _stockLoading = true;
    setTrackError('');
    const host = $('#lw-track-stock-grid');
    if (host && opts.skeleton !== false && !_stockGrid) {
      host.innerHTML = '<div class="lw-track-empty lw-track-history-loading">Loading…</div>';
    }
    try {
      const params = new URLSearchParams();
      if (_historySearch.trim()) params.set('q', _historySearch.trim());
      const qs = params.toString();
      const data = await apiFetch('/api/laser-welding/reports/stock' + (qs ? '?' + qs : ''));
      _stockRows = data.rows || [];
      renderStockReportGrid();
    } catch (err) {
      console.error(err);
      setTrackError(err.message || 'Failed to load stock report');
      _stockGrid = destroyLwReportGrid(_stockGrid, '#lw-track-stock-grid');
      if (host) host.innerHTML = '<div class="lw-track-empty">Failed to load stock</div>';
    } finally {
      _stockLoading = false;
    }
  }

  function renderStockReportGrid() {
    if (_stockGrid) {
      _stockGrid = destroyLwReportGrid(_stockGrid, '#lw-track-stock-grid');
    }
    _stockGrid = renderLwReportGrid(
      '#lw-track-stock-grid',
      _stockGrid,
      stockGridColumns(),
      _stockRows,
      'lw-stock-report',
      'No stock on hand',
    );
  }

  async function loadQaHistory(opts = {}) {
    if (_tab !== 'reports' || _trackReportView !== 'qa') return;
    ensureHistoryDateDefaults();
    if (_qaLoading && !opts.force) return;
    _qaLoading = true;
    setTrackError('');
    const host = $('#lw-track-qa-grid');
    if (host && opts.skeleton !== false && !_qaGrid) {
      host.innerHTML = '<div class="lw-track-empty lw-track-history-loading">Loading…</div>';
    }
    try {
      const data = await apiFetch('/api/laser-welding/reports/qa-history?' + historyQueryParams());
      _qaRows = (data.rows || []).map(mapDatedReportRowForGrid);
      renderQaHistoryGrid();
    } catch (err) {
      console.error(err);
      setTrackError(err.message || 'Failed to load QA history');
      _qaGrid = destroyLwReportGrid(_qaGrid, '#lw-track-qa-grid');
      if (host) host.innerHTML = '<div class="lw-track-empty">Failed to load QA history</div>';
    } finally {
      _qaLoading = false;
    }
  }

  function renderQaHistoryGrid() {
    if (_qaGrid) {
      _qaGrid = destroyLwReportGrid(_qaGrid, '#lw-track-qa-grid');
    }
    _qaGrid = renderLwReportGrid(
      '#lw-track-qa-grid',
      _qaGrid,
      QA_GRID_COLUMNS,
      _qaRows,
      'lw-qa-history',
      'No QA entries for this range',
    );
  }

  async function loadScrapHistory(opts = {}) {
    if (_tab !== 'reports' || _trackReportView !== 'scrap') return;
    ensureHistoryDateDefaults();
    if (_scrapLoading && !opts.force) return;
    _scrapLoading = true;
    setTrackError('');
    const host = $('#lw-track-scrap-grid');
    if (host && opts.skeleton !== false && !_scrapGrid) {
      host.innerHTML = '<div class="lw-track-empty lw-track-history-loading">Loading…</div>';
    }
    try {
      const data = await apiFetch('/api/laser-welding/reports/scrap-history?' + historyQueryParams());
      _scrapRows = (data.rows || []).map(mapDatedReportRowForGrid);
      renderScrapHistoryGrid();
    } catch (err) {
      console.error(err);
      setTrackError(err.message || 'Failed to load scrap history');
      _scrapGrid = destroyLwReportGrid(_scrapGrid, '#lw-track-scrap-grid');
      if (host) host.innerHTML = '<div class="lw-track-empty">Failed to load scrap history</div>';
    } finally {
      _scrapLoading = false;
    }
  }

  function renderScrapHistoryGrid() {
    _scrapGrid = renderLwReportGrid(
      '#lw-track-scrap-grid',
      _scrapGrid,
      SCRAP_GRID_COLUMNS,
      _scrapRows,
      'lw-scrap-history',
      'No scrap entries for this range',
    );
  }

  function reloadActiveReport(opts = {}) {
    if (_trackReportView === 'history') return loadActionHistory(opts);
    if (_trackReportView === 'stock') return loadStockReport(opts);
    if (_trackReportView === 'qa') return loadQaHistory(opts);
    if (_trackReportView === 'scrap') return loadScrapHistory(opts);
    return Promise.resolve();
  }

  async function exportActiveReportExcel() {
    if (_tab !== 'reports') return;
    const view = _trackReportView;
    if (!LW_REPORT_EXPORT_NAMES[view]) {
      showSnackbar('Select a report to export', 'warning');
      return;
    }
    ensureHistoryDateDefaults();
    if (view !== 'stock' && (!_historyFrom || !_historyTo)) {
      showSnackbar('Set From and To dates before exporting', 'warning');
      return;
    }
    const variables = {};
    if (view !== 'stock') {
      variables.from = _historyFrom;
      variables.to = _historyTo;
      if (_historyStep) variables.step = _historyStep;
    }
    if (_historySearch.trim()) variables.q = _historySearch.trim();
    const reportName = LW_REPORT_EXPORT_NAMES[view];
    const fileName = `${reportName}.xlsx`;
    try {
      await apiDownload('/api/laser-welding/reports/export', {
        reportType: view,
        variables,
        fileName,
      }, fileName);
    } catch (err) {
      console.error(err);
      showSnackbar(err.message || 'Export failed', 'error');
    }
  }

  function animateCountUp(el, target) {
    const end = Number(target) || 0;
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      el.textContent = String(end);
      return;
    }
    const duration = 520;
    const t0 = performance.now();
    function frame(now) {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = String(Math.round(end * eased));
      if (p < 1) requestAnimationFrame(frame);
      else el.textContent = String(end);
    }
    el.textContent = '0';
    requestAnimationFrame(frame);
  }

  function trackPlotlyBase() {
    const isLight = typeof Hub !== 'undefined' && Hub.getTheme && Hub.getTheme() === 'light';
    const textColor = isLight ? '#334155' : '#94a3b8';
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(148,163,184,0.08)';
    return {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      margin: { l: 8, r: 8, t: 8, b: 8 },
      font: { family: "'Inter', sans-serif", size: 11, color: textColor },
      xaxis: { gridcolor: gridColor, zerolinecolor: gridColor },
      yaxis: { gridcolor: gridColor, zerolinecolor: gridColor },
    };
  }

  function trackPhaseCounts(items) {
    const m = {};
    (items || []).forEach(item => {
      const ph = item.phase;
      if (ph) m[ph] = (m[ph] || 0) + 1;
    });
    return m;
  }

  function trackTopLabels(items, limit) {
    return (items || [])
      .slice(0, limit)
      .map(i => i.partNo || i.lotNo || i.bomNo || '')
      .filter(Boolean);
  }

  const TRACK_FLOW_LANES = [
    { id: 'child', label: 'Child parts', phases: TRACK_CHILD_PHASES, itemsKey: 'childParts', y: 52 },
    { id: 'sa', label: 'Sub-assembly', phases: TRACK_SA_PHASES, itemsKey: 'subAssemblies', y: 152 },
    { id: 'fg', label: 'Final assembly', phases: TRACK_FG_PHASES, itemsKey: 'finalAssemblies', y: 252 },
  ];

  const TRACK_PHASE_COLORS = {
    erp_stock: '#8b5cf6',
    inspected_ready: '#10b981',
    qa_pending: '#f59e0b',
    consumed: '#94a3b8',
    awaiting_clean: '#3b82f6',
    ready_for_weld: '#10b981',
    ready_to_pack: '#059669',
    rework_pending: '#ef4444',
  };

  const TRACK_READY_PHASES = new Set(['inspected_ready', 'ready_for_weld', 'ready_to_pack']);

  function trackQtyBarHtml(label, value, maxVal) {
    const v = Math.max(0, Number(value) || 0);
    const max = Math.max(1, Number(maxVal) || 1);
    const pct = Math.min(100, Math.round((v / max) * 100));
    return `
      <div class="lw-track-qty-row">
        <span class="lw-track-qty-label">${escapeHtml(label)}</span>
        <div class="lw-track-qty-bar" aria-hidden="true"><span style="width:${pct}%"></span></div>
        <span class="lw-track-qty-val">${v}</span>
      </div>
    `;
  }

  function trackQueueIconSvg(kind) {
    const icons = {
      qa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>',
      rework: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M3 12a9 9 0 0115.5-6.5L21 8"/><path d="M21 12a9 9 0 01-15.5 6.5L3 16"/><path d="M16 3l2.5 2.5L16 8"/><path d="M8 16l-2.5 2.5L8 21"/></svg>',
      pack: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><path d="M3.3 7.7L12 12l8.7-4.3M12 22V12"/></svg>',
      ready: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>',
    };
    return icons[kind] || icons.qa;
  }

  function trackExecIconSvg(tone) {
    const icons = {
      erp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>',
      qa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>',
      clean: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>',
      pack: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>',
    };
    return icons[tone] || icons.erp;
  }

  function trackCardKey(kind, partNo, lotId) {
    return `${kind}:${partNo}:${lotId || ''}`;
  }

  function trackColCountLabel(n) {
    const count = Number(n) || 0;
    return count < 10 ? `(${String(count).padStart(2, '0')})` : `(${count})`;
  }

  function trackEmptyColHtml(phaseId, label) {
    return `
      <div class="lw-track-col-empty-state lw-track-col-empty-state--${escapeAttr(phaseId)}">
        <span class="lw-track-col-empty-icon" aria-hidden="true">${trackQueueIconSvg('qa')}</span>
        <span class="lw-track-col-empty-text">No lots in ${escapeHtml(label)}</span>
      </div>
    `;
  }

  function applyTrackPhaseFilter(phase) {
    _trackPhase = phase || '';
    _trackFlowStep = '';
    const sel = $('#lw-track-phase');
    if (sel) sel.value = _trackPhase;
    renderTracking();
  }

  function applyTrackFlowFilter(stepId) {
    if (_trackFlowStep === stepId) {
      applyTrackPhaseFilter('');
      return;
    }
    _trackFlowStep = stepId || '';
    const step = findWorkflowStep(stepId);
    _trackPhase = step?.filterPhases[0] || '';
    const sel = $('#lw-track-phase');
    if (sel) sel.value = _trackPhase;
    renderTracking();
  }

  function switchToReportsPipeline(phase) {
    if (phase) {
      _trackPhase = phase;
      const sel = $('#lw-track-phase');
      if (sel) sel.value = phase;
    }
    setTrackReportView('pipeline');
    if (_tab === 'reports') {
      renderTracking();
    } else {
      switchTab('reports');
    }
  }

  function renderMaterialFlowStrip() {
    const host = $('#lw-track-exec-flow');
    if (!host || !_trackingDataRaw) return;
    host.innerHTML = `
      <div class="lw-material-flow-strip lw-tabs lw-tabs--scroll" role="tablist" aria-label="Material flow by workflow step">
        ${MATERIAL_FLOW_STEPS.map((step, i) => {
          const count = countMaterialFlowStep(step);
          const active = _trackFlowStep === step.id
            || (!_trackFlowStep && _trackPhase && step.filterPhases.includes(_trackPhase));
          return `
            <button type="button" class="lw-material-flow-step lw-tab${active ? ' lw-tab--active' : ''}${count > 0 ? ' lw-material-flow-step--hot' : ''}"
                    data-flow-step="${escapeAttr(step.id)}"
                    data-goto-tab="${escapeAttr(step.tab)}"
                    style="--i:${i}" title="${count} lot${count === 1 ? '' : 's'} · ${escapeAttr(step.label)}">
              <span class="lw-material-flow-label">${escapeHtml(step.label)}</span>
              ${count > 0 ? `<span class="lw-material-flow-count">${count}</span>` : ''}
            </button>
          `;
        }).join('')}
      </div>
    `;
  }

  function renderTrackPhaseGrid() {
    const host = $('#lw-track-phase-grid');
    const data = getFilteredTrackingData();
    if (!host || !data) return;
    const laneAccent = { child: '#8b5cf6', sa: '#3b82f6', fg: '#059669' };

    host.innerHTML = TRACK_FLOW_LANES.map((lane, laneIdx) => {
      const items = data[lane.itemsKey] || [];
      const counts = trackPhaseCounts(items);
      const accent = laneAccent[lane.id] || '#64748b';
      return `
        <div class="lw-track-phase-lane lw-track-phase-lane--${lane.id}" style="--lane-accent:${accent}">
          <div class="lw-track-phase-lane-head">
            <span class="lw-track-phase-lane-dot" aria-hidden="true"></span>
            <span class="lw-track-phase-lane-title">${escapeHtml(lane.label)}</span>
            <span class="lw-track-phase-lane-total">${items.length} lots</span>
          </div>
          <div class="lw-track-phase-lane-track" role="list">
            ${lane.phases.map((ph, i) => {
              const count = counts[ph.id] || 0;
              const active = _trackPhase === ph.id;
              const samples = items.filter(it => it.phase === ph.id).slice(0, 2)
                .map(it => it.partNo || it.lotNo || it.bomNo).join(', ');
              const title = samples ? `${ph.label}: ${samples}` : ph.label;
              return `
                ${i > 0 ? '<span class="lw-track-phase-connector" aria-hidden="true"></span>' : ''}
                <button type="button" role="listitem"
                  class="lw-track-phase-cell lw-track-phase-cell--${ph.id}${active ? ' is-active' : ''}${count > 0 ? ' has-wip' : ''}"
                  data-track-phase="${escapeAttr(ph.id)}"
                  title="${escapeAttr(title)}"
                  style="--i:${laneIdx * 4 + i}">
                  <span class="lw-track-phase-cell-count">${count}</span>
                  <span class="lw-track-phase-cell-label">${escapeHtml(ph.label)}</span>
                </button>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }).join('');
    const details = document.querySelector('.lw-track-phase-details');
    if (details) details.open = !!_trackPhase;
  }

  function renderTrackSankey() {
    const el = $('#lw-track-sankey');
    const data = _trackingDataRaw;
    if (!el || !data || !window.Plotly) return;
    const s = data.summary || {};
    const childC = trackPhaseCounts(data.childParts);
    const saC = trackPhaseCounts(data.subAssemblies);
    const fgC = trackPhaseCounts(data.finalAssemblies);

    const nodes = [
      'ERP stock', 'Inspected', 'Child QA', 'Consumed',
      'SA clean', 'SA QA', 'SA ready', 'SA rework',
      'FG clean', 'FG QA', 'Ready pack', 'FG rework', 'Pack',
    ];
    const nodeColors = [
      '#8b5cf6', '#10b981', '#f59e0b', '#94a3b8',
      '#3b82f6', '#f59e0b', '#10b981', '#ef4444',
      '#3b82f6', '#f59e0b', '#059669', '#ef4444', '#6366f1',
    ];

    const links = [];
    function link(src, tgt, val) {
      const v = Math.max(0, Number(val) || 0);
      if (v > 0) links.push({ source: src, target: tgt, value: v });
    }

    link(0, 1, Math.max(childC.inspected_ready || 0, s.childPartsReady || 0));
    link(0, 1, childC.erp_stock || s.childErpStock || 0);
    link(1, 2, childC.qa_pending || s.childQaPending || 0);
    link(1, 4, saC.awaiting_clean || s.saAwaitingClean || 0);
    link(1, 8, fgC.awaiting_clean || s.fgAwaitingClean || 0);
    link(4, 5, saC.qa_pending || 0);
    link(5, 6, saC.ready_for_weld || s.saReadyForWeld || 0);
    link(6, 8, saC.ready_for_weld || 0);
    link(8, 9, fgC.qa_pending || 0);
    link(9, 10, fgC.ready_to_pack || s.fgReadyToPack || 0);
    link(10, 12, fgC.ready_to_pack || s.fgReadyToPack || 0);
    link(4, 7, saC.rework_pending || 0);
    link(8, 11, fgC.rework_pending || 0);

    if (!links.length) {
      el.innerHTML = '<p class="lw-track-dash-empty">No WIP flow data</p>';
      const insight = $('#lw-track-sankey-insight');
      if (insight) {
        insight.textContent = '';
        insight.hidden = true;
      }
      return;
    }

    const trace = {
      type: 'sankey',
      orientation: 'h',
      node: {
        pad: 20,
        thickness: 22,
        line: { color: 'rgba(15, 23, 42, 0.1)', width: 0.5 },
        label: nodes,
        color: nodeColors,
      },
      link: {
        source: links.map(l => l.source),
        target: links.map(l => l.target),
        value: links.map(l => l.value),
        color: 'rgba(59, 130, 246, 0.22)',
      },
    };

    const plotFont = trackPlotlyBase().font;
    if (window.Plotly.purge) window.Plotly.purge(el);
    Plotly.newPlot(el, [trace], {
      ...trackPlotlyBase(),
      font: { ...plotFont, size: 12 },
      margin: { l: 12, r: 12, t: 8, b: 8 },
    }, { responsive: true, displayModeBar: false });
    requestAnimationFrame(() => {
      if (window.Plotly?.Plots?.resize) window.Plotly.Plots.resize(el);
    });

    const insight = $('#lw-track-sankey-insight');
    if (insight) {
      const buckets = [
        { label: 'ERP stock', v: childC.erp_stock || s.childErpStock || 0 },
        { label: 'Child inspected', v: childC.inspected_ready || s.childPartsReady || 0 },
        { label: 'Child QA', v: childC.qa_pending || 0 },
        { label: 'SA awaiting clean', v: saC.awaiting_clean || s.saAwaitingClean || 0 },
        { label: 'SA ready weld', v: saC.ready_for_weld || s.saReadyForWeld || 0 },
        { label: 'FG awaiting clean', v: fgC.awaiting_clean || s.fgAwaitingClean || 0 },
        { label: 'FG ready pack', v: fgC.ready_to_pack || s.fgReadyToPack || 0 },
        { label: 'Rework', v: (saC.rework_pending || 0) + (fgC.rework_pending || 0) + (s.reworkPendingTotal || 0) },
      ].filter(b => b.v > 0).sort((a, b) => b.v - a.v);
      let msg = 'Each band is lot volume moving between stages — thicker = more WIP on that path.';
      if (buckets.length) {
        msg += ` Largest bucket right now: ${buckets[0].label} (${buckets[0].v}).`;
      }
      insight.textContent = msg;
      insight.hidden = false;
    }
  }

  function renderTrackCapacityList() {
    const host = $('#lw-track-capacity-list');
    if (!host || !_trackingDataRaw) return;
    const rows = (_trackingDataRaw.bomCapacity || [])
      .filter(b => b.maxBuildQty > 0)
      .sort((a, b) => b.maxBuildQty - a.maxBuildQty)
      .slice(0, 3);
    if (!rows.length) {
      host.innerHTML = '';
      return;
    }
    const top = rows[0].maxBuildQty || 1;
    host.innerHTML = rows.map((row, i) => {
      const pct = Math.round((row.maxBuildQty / top) * 100);
      return `
        <button type="button" class="lw-track-cap-list-row${i === 0 ? ' lw-track-cap-list-row--bn' : ''}" data-cap-idx="${i}">
          <div class="lw-track-cap-list-head">
            <span class="lw-track-cap-list-bom">${escapeHtml(row.bomNo)}</span>
            ${i === 0 ? '<span class="lw-track-cap-bn-chip">Bottleneck</span>' : ''}
            <span class="lw-track-cap-list-pct">${pct}%</span>
            <span class="lw-track-cap-list-val">${row.maxBuildQty}</span>
          </div>
          <span class="lw-track-cap-list-product">${escapeHtml(row.productName || row.bottleneckPartNo || '')}</span>
          <div class="lw-track-cap-list-bar" aria-hidden="true"><span style="width:${pct}%"></span></div>
        </button>
      `;
    }).join('');
    host.querySelectorAll('.lw-track-cap-list-row').forEach((btn, i) => {
      btn.addEventListener('click', () => openTrackBomDrawer(rows[i]));
    });
  }

  function renderTrackCapacityChart() {
    const el = $('#lw-track-capacity-chart');
    if (!el || !_trackingDataRaw || !window.Plotly) return;
    const rows = (_trackingDataRaw.bomCapacity || [])
      .filter(b => b.maxBuildQty > 0)
      .sort((a, b) => b.maxBuildQty - a.maxBuildQty)
      .slice(0, 8);
    if (!rows.length) {
      el.innerHTML = '<p class="lw-track-dash-empty">No build capacity available</p>';
      return;
    }
    const labels = rows.map(r => r.bomNo || r.productName || 'BOM');
    const values = rows.map(r => r.maxBuildQty);
    const colors = rows.map((_, i) => (i === 0 ? 'rgba(245,158,11,0.9)' : 'rgba(59,130,246,0.75)'));

    _trackCapacityChartRows = rows;
    if (window.Plotly.purge) window.Plotly.purge(el);
    Plotly.newPlot(el, [{
      type: 'bar',
      orientation: 'h',
      y: labels,
      x: values,
      marker: { color: colors, cornerradius: 4 },
      hovertemplate: '<b>%{y}</b><br>Max build: %{x}<extra></extra>',
    }], {
      ...trackPlotlyBase(),
      margin: { l: 100, r: 16, t: 8, b: 28 },
      xaxis: { ...trackPlotlyBase().xaxis, title: '' },
      yaxis: { ...trackPlotlyBase().yaxis, automargin: true },
    }, { responsive: true, displayModeBar: false });

    if (el.removeAllListeners) el.removeAllListeners('plotly_click');
    el.on('plotly_click', ev => {
      const idx = ev.points?.[0]?.pointIndex;
      if (idx == null || !_trackCapacityChartRows[idx]) return;
      openTrackBomDrawer(_trackCapacityChartRows[idx]);
    });
  }

  function renderTrackQueueTiles() {
    const host = $('#lw-track-queue-tiles');
    if (!host || !_trackingDataRaw?.summary) return;
    const s = _trackingDataRaw.summary;
    const tiles = [
      { id: 'qa', label: 'QA queue', value: s.qaQueueTotal, phase: 'qa_pending', tone: 'qa', icon: 'qa' },
      { id: 'rework', label: 'Rework', value: s.reworkPendingTotal, phase: 'rework_pending', tone: 'rework', icon: 'rework' },
      { id: 'fgpack', label: 'FG ready', value: s.fgReadyToPack, phase: 'ready_to_pack', tone: 'pack', icon: 'pack' },
      { id: 'saweld', label: 'SA ready weld', value: s.saReadyForWeld, phase: 'ready_for_weld', tone: 'ready', icon: 'ready' },
    ];
    host.innerHTML = tiles.map((t, i) => `
      <button type="button" class="lw-track-queue-tile lw-track-queue-tile--${t.tone}${t.value > 0 ? ' lw-track-queue-tile--hot' : ''}"
              data-track-queue-phase="${escapeAttr(t.phase)}" style="--i:${i}">
        <span class="lw-track-queue-icon" aria-hidden="true">${trackQueueIconSvg(t.icon)}</span>
        <span class="lw-track-queue-val" data-value="${t.value}">0</span>
        <span class="lw-track-queue-label">${escapeHtml(t.label)}</span>
        ${t.value > 0 ? '<span class="lw-track-queue-cta">Process now →</span>' : '<span class="lw-track-queue-hint">View in Reports</span>'}
      </button>
    `).join('');
    host.querySelectorAll('.lw-track-queue-val').forEach(el => animateCountUp(el, el.dataset.value));
  }

  function openTrackBomDrawer(bomRow) {
    const drawer = $('#lw-track-drawer');
    const backdrop = $('#lw-track-drawer-backdrop');
    if (!drawer || !bomRow) return;
    const title = $('#lw-track-drawer-title');
    const badge = $('#lw-track-drawer-badge');
    const body = $('#lw-track-drawer-body');
    const foot = $('#lw-track-drawer-foot');
    if (badge) badge.innerHTML = '<span class="lw-track-drawer-phase lw-track-drawer-phase--ready">BOM capacity</span>';
    if (title) title.textContent = bomRow.bomNo || 'BOM';
    if (body) {
      const maxVal = Math.max(bomRow.maxBuildQty, bomRow.bottleneckAvailable || 0, 1);
      body.innerHTML = `
        <p class="lw-track-drawer-sub">${escapeHtml(bomRow.productName || '')} · ${escapeHtml(bomRow.customerName || '')}</p>
        <div class="lw-track-drawer-qty-bars">
          ${trackQtyBarHtml('Max build', bomRow.maxBuildQty, maxVal)}
          ${trackQtyBarHtml('BN available', bomRow.bottleneckAvailable || 0, maxVal)}
        </div>
        <p class="lw-track-drawer-meta">Bottleneck: <strong>${escapeHtml(bomRow.bottleneckPartNo || '—')}</strong> (qty ${bomRow.bottleneckBomQty ?? '—'})</p>
        <h4 class="lw-track-drawer-lots-head">Children</h4>
        <ul class="lw-track-drawer-lots lw-track-drawer-lots--bn">
          ${(bomRow.children || []).map(c => `
            <li class="${c.isBottleneck ? 'lw-track-drawer-lot-bn' : ''}">${escapeHtml(c.partNo)} — max ${c.maxFromChild} (LW ${c.lwOkayed}, ERP ${c.erpAvailable})${c.isBottleneck ? ' <span class="lw-track-cap-bn-chip">BN</span>' : ''}</li>
          `).join('')}
        </ul>
      `;
    }
    if (foot) {
      foot.innerHTML = `<button type="button" class="ti-btn ti-btn-primary lw-track-goto" data-goto-tab="laser_welding">Weld up to ${bomRow.maxBuildQty}</button>`;
    }
    drawer.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    if (backdrop) backdrop.hidden = false;
    document.body.classList.add('lw-track-drawer-open');
  }

  function renderTrackDashboard() {
    renderMaterialFlowStrip();
    renderTrackSankey();
    renderTrackCapacityList();
    renderTrackQueueTiles();
    renderTrackPhaseGrid();
  }

  function renderTrackReports() {
    renderTrackPipeline();
    renderTrackCapacity();
    renderTrackActionsTable();
    ensureHistoryDateDefaults();
    setTrackReportView(_trackReportView);
  }

  function renderTrackFilterChip() {
    /* filter chip removed — phase filter is shown on material flow strip */
  }

  function trackCardHtml(item, kind) {
    const partNo = item.partNo || item.bomNo || item.saPartNo || '';
    const lotId = item.lotId || '';
    const cardKey = trackCardKey(kind, partNo, lotId);
    const title = kind === 'child'
      ? escapeHtml(item.partNo)
      : escapeHtml(item.lotNo || item.bomNo);
    const sub = kind === 'child'
      ? escapeHtml(item.partName || '')
      : escapeHtml(item.productName || item.saPartNo || item.partNo || '');
    const okayed = item.lwOkayed ?? item.totalOkayed ?? 0;
    const inwarded = item.totalInwarded || okayed || item.erpAvailable || 0;
    const meta = kind === 'child'
      ? `LW ${okayed} · ERP ${item.erpAvailable || 0}`
      : `OK ${item.totalOkayed || 0} · QA ${item.totalQa || 0}`;
    const readyBadge = TRACK_READY_PHASES.has(item.phase)
      ? '<span class="lw-track-ready-badge">READY</span>'
      : '';
    const priorityBadge = (kind !== 'child' && ((item.reworkPending || 0) > 0 || (item.totalQa || 0) > 0))
      ? '<span class="lw-track-priority-badge">PRIORITY</span>'
      : '';
    const selected = _trackSelectedCardKey === cardKey ? ' lw-track-card--selected' : '';
    const inw = Math.max(1, Number(inwarded) || 0);
    const ok = Math.max(0, Number(okayed) || 0);
    const pct = Math.min(100, Math.round((ok / inw) * 100));
    return `
      <button type="button" class="lw-track-card${selected}" data-track-kind="${kind}"
              data-track-part="${escapeAttr(partNo)}" data-track-lot-id="${lotId}"
              data-track-card-key="${escapeAttr(cardKey)}"
              data-phase="${escapeAttr(item.phase)}">
        <span class="lw-track-card-head">
          <span class="lw-track-card-part">${title}</span>
          <span class="lw-track-card-badges">${priorityBadge}${readyBadge}</span>
        </span>
        <span class="lw-track-card-name">${sub}</span>
        <div class="lw-track-bar lw-track-bar--${escapeAttr(item.phase)}" aria-hidden="true"><span style="width:${pct}%"></span></div>
        <span class="lw-track-card-meta">${meta}</span>
      </button>
    `;
  }

  function renderTrackPipelineLane(title, phases, items, kind) {
    const byPhase = {};
    phases.forEach(p => { byPhase[p.id] = []; });
    items.forEach(item => {
      const ph = item.phase;
      if (byPhase[ph]) byPhase[ph].push(item);
    });
    return `
      <section class="lw-track-lane">
        <h3 class="lw-track-lane-title">
          <span class="lw-track-lane-title-text">${escapeHtml(title)}</span>
          <span class="lw-track-lane-lot-count">${items.length} active lot${items.length === 1 ? '' : 's'}</span>
        </h3>
        <div class="lw-track-lane-cols">
          ${phases.map((p, colIdx) => {
            const colItems = byPhase[p.id] || [];
            return `
            <div class="lw-track-col lw-track-col--${p.id}" style="--col:${colIdx}">
              <div class="lw-track-col-head">
                <span class="lw-track-col-head-label">${escapeHtml(p.label)}</span>
                <span class="lw-track-col-count">${trackColCountLabel(colItems.length)}</span>
              </div>
              <div class="lw-track-col-body">
                ${colItems.map((item, i) =>
                  trackCardHtml(item, kind).replace('lw-track-card"', `lw-track-card" style="--i:${i}"`)
                ).join('') || trackEmptyColHtml(p.id, p.label)}
              </div>
            </div>
          `;
          }).join('')}
        </div>
      </section>
    `;
  }

  function renderTrackPipeline() {
    const host = $('#lw-track-pipeline');
    if (!host || !_trackingDataRaw) return;
    host.innerHTML = [
      renderTrackPipelineLane('Child parts', TRACK_CHILD_PHASES, _trackingDataRaw.childParts || [], 'child'),
      renderTrackPipelineLane('Sub-assembly', TRACK_SA_PHASES, _trackingDataRaw.subAssemblies || [], 'sa'),
      renderTrackPipelineLane('Final assembly', TRACK_FG_PHASES, _trackingDataRaw.finalAssemblies || [], 'fg'),
    ].join('');
    if (_trackSelectedCardKey) {
      $$('.lw-track-card').forEach(card => {
        card.classList.toggle('lw-track-card--selected', (card.dataset.trackCardKey || '') === _trackSelectedCardKey);
      });
    }
  }

  function renderCapacityChildRows(children) {
    if (!children?.length) return '<tr><td colspan="7" class="lw-track-empty">No children</td></tr>';
    return children.map(ch => `
      <tr class="${ch.isBottleneck ? 'lw-track-bn-row' : ''}">
        <td>${escapeHtml(ch.partNo)}</td>
        <td>${escapeHtml(ch.partName || '')}</td>
        <td class="lw-track-num">${ch.bomQty}</td>
        <td class="lw-track-num">${ch.lwOkayed}</td>
        <td class="lw-track-num">${ch.erpAvailable}</td>
        <td class="lw-track-num">${ch.maxFromChild}</td>
        <td>${escapeHtml(ch.source)}</td>
      </tr>
    `).join('');
  }

  function renderTrackCapacity() {
    const body = $('#lw-track-capacity-body');
    const saBody = $('#lw-track-sa-capacity-body');
    if (!body || !_trackingDataRaw) return;
    const rows = _trackingDataRaw.bomCapacity || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6" class="lw-track-empty">No BOM capacity data</td></tr>';
    } else {
      body.innerHTML = rows.map((row, idx) => {
        const key = `bom:${row.bomId}`;
        const open = !!_trackCapacityExpanded[key];
        return `
          <tr class="lw-track-cap-row${row.maxBuildQty === 0 ? ' lw-track-cap-row--zero' : ''}${open ? ' lw-track-cap-row--open' : ''}">
            <td>${escapeHtml(row.bomNo)}</td>
            <td>${escapeHtml(row.productName || '')}</td>
            <td>${escapeHtml(row.customerName || '')}</td>
            <td class="lw-track-num lw-track-max">${row.maxBuildQty}</td>
            <td class="lw-track-bn">
              ${row.bottleneckPartNo ? `<span class="lw-track-bn-dot"></span>${escapeHtml(row.bottleneckPartNo)}` : '—'}
            </td>
            <td>
              <button type="button" class="lw-track-expand" data-cap-key="${escapeAttr(key)}" aria-expanded="${open}">
                ${open ? 'Hide' : 'Details'}
              </button>
            </td>
          </tr>
          ${open ? `
          <tr class="lw-track-cap-detail">
            <td colspan="6">
              <table class="lw-track-cap-child-table">
                <thead><tr>
                  <th>Part</th><th>Name</th><th>BOM qty</th><th>LW OK</th><th>ERP</th><th>Max</th><th>Src</th>
                </tr></thead>
                <tbody>${renderCapacityChildRows(row.children)}</tbody>
              </table>
            </td>
          </tr>` : ''}
        `;
      }).join('');
    }

    if (saBody) {
      const saRows = _trackingDataRaw.saCapacity || [];
      if (!saRows.length) {
        saBody.innerHTML = '<tr><td colspan="5" class="lw-track-empty">No sub-assembly capacity</td></tr>';
      } else {
        saBody.innerHTML = saRows.map(row => {
          const key = `sa:${row.bomId}:${row.saPartNo}`;
          const open = !!_trackCapacityExpanded[key];
          return `
            <tr class="${open ? 'lw-track-cap-row--open' : ''}">
              <td>${escapeHtml(row.bomNo)}</td>
              <td>${escapeHtml(row.saPartNo)} — ${escapeHtml(row.saPartName || '')}</td>
              <td class="lw-track-num lw-track-max">${row.maxBuildQty}</td>
              <td>${row.bottleneckPartNo ? escapeHtml(row.bottleneckPartNo) : '—'}</td>
              <td>
                <button type="button" class="lw-track-expand" data-cap-key="${escapeAttr(key)}" aria-expanded="${open}">
                  ${open ? 'Hide' : 'Details'}
                </button>
              </td>
            </tr>
            ${open ? `
            <tr class="lw-track-cap-detail">
              <td colspan="5">
                <table class="lw-track-cap-child-table">
                  <thead><tr>
                    <th>Part</th><th>Name</th><th>BOM qty</th><th>LW OK</th><th>ERP</th><th>Max</th><th>Src</th>
                  </tr></thead>
                  <tbody>${renderCapacityChildRows(row.children)}</tbody>
                </table>
              </td>
            </tr>` : ''}
          `;
        }).join('');
      }
    }
  }

  function workflowStepLabel(tab) {
    const step = MATERIAL_FLOW_STEPS.find(s => s.tab === tab);
    return step?.label || TAB_LABELS[tab] || tab || '—';
  }

  function workflowStepOrder(tab) {
    const idx = MATERIAL_FLOW_STEPS.findIndex(s => s.tab === tab);
    return idx >= 0 ? idx : 99;
  }

  function buildTrackActionReportRows() {
    const rows = collectTrackActionRows()
      .map(r => {
        const tab = actionTabForItem(r.item, r.item.kind);
        return tab ? { ...r, workflowTab: tab, workflowLabel: workflowStepLabel(tab) } : null;
      })
      .filter(Boolean);
    rows.sort((a, b) => {
      const o = workflowStepOrder(a.workflowTab) - workflowStepOrder(b.workflowTab);
      if (o !== 0) return o;
      const la = String(a.label || '').localeCompare(String(b.label || ''));
      if (la !== 0) return la;
      return String(a.lot || '').localeCompare(String(b.lot || ''));
    });
    return rows;
  }

  function renderTrackActionsTable() {
    const body = $('#lw-track-actions-body');
    const countEl = $('#lw-track-actions-count');
    if (!body || !_trackingDataRaw) return;
    const rows = buildTrackActionReportRows();
    if (countEl) countEl.textContent = rows.length ? `${rows.length} lines` : '';
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="10" class="lw-track-empty">No actionable lots</td></tr>';
      return;
    }
    body.innerHTML = rows.map(r => `
      <tr class="lw-track-action-row" tabindex="0" data-track-kind="${escapeAttr(r.item.kind)}"
          data-track-part="${escapeAttr(r.item.partNo || r.item.bomNo || r.item.saPartNo || '')}"
          data-track-lot-id="${r.item.lotId || ''}">
        <td>${escapeHtml(r.workflowLabel)}</td>
        <td>${escapeHtml(r.type)}</td>
        <td>${escapeHtml(r.label)}</td>
        <td><code>${escapeHtml(r.lot)}</code></td>
        <td><span class="lw-track-phase lw-track-phase--${escapeAttr(r.phase)}">${escapeHtml(trackPhaseLabel(r.phase))}</span></td>
        <td class="lw-track-num">${r.okayed}</td>
        <td class="lw-track-num">${r.qa}</td>
        <td class="lw-track-num">${r.clean}</td>
        <td class="lw-track-num">${r.rework}</td>
        <td class="lw-col-actions">
          <button type="button" class="ti-btn ti-btn-xs ti-btn-outline lw-track-actions-goto" data-goto-tab="${escapeAttr(r.workflowTab)}">Open</button>
        </td>
      </tr>
    `).join('');
    body.querySelectorAll('.lw-track-action-row').forEach((tr, i) => {
      tr._trackItem = rows[i]?.item || null;
    });
  }

  function trackBomChildrenForLot(item, kind) {
    if (!_trackingDataRaw || kind === 'child') return null;
    if (kind === 'fg') {
      return (_trackingDataRaw.bomCapacity || []).find(b => String(b.bomId) === String(item.bomId)
        || b.bomNo === item.bomNo) || null;
    }
    if (kind === 'sa') {
      return (_trackingDataRaw.saCapacity || []).find(s =>
        (String(s.bomId) === String(item.bomId) || s.bomNo === item.bomNo)
        && (s.saPartNo === item.saPartNo || s.saPartNo === item.partNo)
      ) || null;
    }
    return null;
  }

  function trackBomChildrenTableHtml(capRow) {
    const children = capRow?.children || [];
    if (!children.length) return '';
    return `
      <h4 class="lw-track-drawer-lots-head">BOM children</h4>
      <table class="lw-track-drawer-bom-table">
        <thead>
          <tr><th>Part</th><th class="lw-track-num">Qty</th><th class="lw-track-num">LW OK</th><th></th></tr>
        </thead>
        <tbody>
          ${children.map(c => `
            <tr class="${c.isBottleneck ? 'lw-track-drawer-bom-bn' : ''}">
              <td><code>${escapeHtml(c.partNo)}</code></td>
              <td class="lw-track-num">${c.bomQty ?? '—'}</td>
              <td class="lw-track-num">${c.lwOkayed ?? 0}</td>
              <td>${c.isBottleneck ? '<span class="lw-track-cap-bn-chip">BN</span>' : ''}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function trackPhaseStepsHtml(phase, kind) {
    const stepsByKind = {
      child: ['erp_stock', 'inspected_ready', 'qa_pending', 'consumed'],
      sa: ['awaiting_clean', 'qa_pending', 'ready_for_weld', 'rework_pending'],
      fg: ['awaiting_clean', 'qa_pending', 'ready_to_pack', 'rework_pending'],
    };
    const steps = stepsByKind[kind] || stepsByKind.fg;
    const idx = Math.max(0, steps.indexOf(phase));
    return `
      <div class="lw-track-drawer-phase-steps" aria-label="Phase progress">
        ${steps.map((s, i) => `
          <div class="lw-track-drawer-step${i <= idx ? ' lw-track-drawer-step--done' : ''}${s === phase ? ' lw-track-drawer-step--current' : ''}">
            <span class="lw-track-drawer-step-dot"></span>
            <span class="lw-track-drawer-step-label">${escapeHtml(trackPhaseLabel(s))}</span>
          </div>
        `).join('')}
      </div>
    `;
  }

  function markTrackSelectedCard(kind, partNo, lotId) {
    _trackSelectedCardKey = trackCardKey(kind, partNo, lotId);
    $$('.lw-track-card').forEach(card => {
      const key = card.dataset.trackCardKey || '';
      card.classList.toggle('lw-track-card--selected', key === _trackSelectedCardKey);
    });
  }

  function clearTrackSelectedCard() {
    _trackSelectedCardKey = '';
    $$('.lw-track-card--selected').forEach(card => card.classList.remove('lw-track-card--selected'));
  }

  function trackSuggestedAction(item, kind) {
    const phase = item.phase;
    if (phase === 'erp_stock') return { text: 'Inspect parts in Part Inspection', tab: 'inspection' };
    if (phase === 'inspected_ready' && kind === 'child') return { text: 'Use in weld / sub-assembly', tab: 'laser_welding' };
    if (phase === 'qa_pending') return { text: 'Approve in QA Disposition', tab: 'qa' };
    if (phase === 'awaiting_clean') {
      if (kind === 'sa') return { text: 'SA Inspection', tab: 'sa_cleaning' };
      return { text: 'LW Cleaning/Inspection', tab: 'lw_cleaning' };
    }
    if (phase === 'ready_for_weld') return { text: 'Weld into final assembly', tab: 'laser_welding' };
    if (phase === 'ready_to_pack') return { text: 'Pack lot', tab: 'packing' };
    if (phase === 'rework_pending') {
      if (kind === 'sa') return { text: 'SA Re-Work', tab: 'sa_rework' };
      return { text: 'LW Re-Work', tab: 'lw_rework' };
    }
    return null;
  }

  function findTrackItem(kind, partNo, lotId) {
    if (!_trackingDataRaw) return null;
    if (kind === 'child') {
      if (lotId) {
        for (const p of _trackingDataRaw.childParts || []) {
          const lot = (p.lots || []).find(l => String(l.lotId) === String(lotId));
          if (lot) {
            return { ...p, ...lot, kind: 'child', phase: lot.phase || p.phase };
          }
        }
      }
      return (_trackingDataRaw.childParts || []).find(p => p.partNo === partNo) || null;
    }
    if (kind === 'sa') {
      if (lotId) {
        return (_trackingDataRaw.subAssemblies || []).find(s => String(s.lotId) === String(lotId)) || null;
      }
      return (_trackingDataRaw.subAssemblies || []).find(s => s.partNo === partNo || s.saPartNo === partNo) || null;
    }
    if (lotId) {
      return (_trackingDataRaw.finalAssemblies || []).find(f => String(f.lotId) === String(lotId)) || null;
    }
    return (_trackingDataRaw.finalAssemblies || []).find(f => f.bomNo === partNo || f.partNo === partNo) || null;
  }

  function trackDrawerFooterHtml(item, kind) {
    const action = trackSuggestedAction(item, kind);
    const extras = [];
    if (item.phase === 'awaiting_clean' && kind === 'sa' && action?.tab !== 'sa_cleaning') {
      if (kind === 'sa') extras.push({ text: 'SA Inspection', tab: 'sa_cleaning' });
      else extras.push({ text: 'LW Cleaning/Inspection', tab: 'lw_cleaning' });
    }
    if (item.phase === 'ready_to_pack' && action?.tab !== 'packing') {
      extras.push({ text: 'Pack', tab: 'packing' });
    }
    if (!action && !extras.length) return '';
    const primary = action
      ? `<button type="button" class="ti-btn ti-btn-primary lw-track-goto" data-goto-tab="${escapeAttr(action.tab)}">${escapeHtml(action.text)}</button>`
      : '';
    const secondary = extras.length
      ? `<div class="lw-track-drawer-foot-secondary">${extras.map(ex =>
        `<button type="button" class="ti-btn ti-btn-ghost lw-track-goto" data-goto-tab="${escapeAttr(ex.tab)}">${escapeHtml(ex.text)}</button>`
      ).join('')}</div>`
      : '';
    return `<div class="lw-track-drawer-foot-actions">${primary}${secondary}</div>`;
  }

  function openTrackDrawer(item, kind) {
    const drawer = $('#lw-track-drawer');
    const backdrop = $('#lw-track-drawer-backdrop');
    if (!drawer || !item) return;
    const title = $('#lw-track-drawer-title');
    const badge = $('#lw-track-drawer-badge');
    const body = $('#lw-track-drawer-body');
    const foot = $('#lw-track-drawer-foot');
    if (title) {
      title.textContent = kind === 'child'
        ? item.partNo
        : (item.lotNo || item.bomNo || 'Lot');
    }
    if (badge) {
      const lotBadge = (kind !== 'child' && item.lotNo)
        ? `<span class="lw-track-drawer-lot-badge">Lot: ${escapeHtml(item.lotNo)}</span>`
        : '';
      const phasePill = `<span class="lw-track-drawer-phase lw-track-drawer-phase--${escapeAttr(item.phase)}">${escapeHtml(trackPhaseLabel(item.phase))}</span>`;
      badge.innerHTML = lotBadge + phasePill;
    }
    const okayed = item.lwOkayed ?? item.totalOkayed ?? 0;
    const qa = item.qaPending ?? item.totalQa ?? 0;
    const erp = item.erpAvailable ?? 0;
    const cleaning = item.inspectionPending ?? 0;
    const maxVal = Math.max(okayed, qa, erp, cleaning, 1);
    if (body) {
      const capRow = trackBomChildrenForLot(item, kind);
      body.innerHTML = `
        <p class="lw-track-drawer-sub">${escapeHtml(item.partName || item.productName || '')}</p>
        ${trackPhaseStepsHtml(item.phase, kind)}
        <div class="lw-track-drawer-qty-bars">
          ${trackQtyBarHtml('Okayed', okayed, maxVal)}
          ${trackQtyBarHtml('QA', qa, maxVal)}
          ${trackQtyBarHtml('ERP', erp, maxVal)}
          ${trackQtyBarHtml('Cleaning', cleaning, maxVal)}
        </div>
        ${trackBomChildrenTableHtml(capRow)}
        ${(item.lots || []).length ? `
          <h4 class="lw-track-drawer-lots-head">Lots</h4>
          <ul class="lw-track-drawer-lots">
            ${item.lots.map(l => `<li><code>${escapeHtml(l.lotNo)}</code> — OK ${l.totalOkayed} / QA ${l.totalQa}</li>`).join('')}
          </ul>
        ` : ''}
      `;
    }
    if (foot) foot.innerHTML = trackDrawerFooterHtml(item, kind);
    markTrackSelectedCard(kind, item.partNo || item.bomNo || item.saPartNo || '', item.lotId || '');
    drawer.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    if (backdrop) backdrop.hidden = false;
    document.body.classList.add('lw-track-drawer-open');
  }

  function closeTrackDrawer() {
    const drawer = $('#lw-track-drawer');
    const backdrop = $('#lw-track-drawer-backdrop');
    if (drawer) {
      drawer.hidden = true;
      drawer.setAttribute('aria-hidden', 'true');
    }
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove('lw-track-drawer-open');
    clearTrackSelectedCard();
  }

  function setTrackReportView(view) {
    _trackReportView = view || 'pipeline';
    updateReportsToolbar();
    const map = {
      pipeline: '#lw-track-pipeline-view',
      capacity: '#lw-track-capacity-view',
      actions: '#lw-track-actions-view',
      history: '#lw-track-history-view',
      stock: '#lw-track-stock-view',
      qa: '#lw-track-qa-view',
      scrap: '#lw-track-scrap-view',
    };
    Object.entries(map).forEach(([key, sel]) => {
      const panel = $(sel);
      if (panel) panel.classList.toggle('lw-track-report-view--active', key === _trackReportView);
    });
    if (_trackReportView === 'actions' && _trackingDataRaw) {
      renderTrackActionsTable();
    }
    if (_trackReportView === 'history') {
      loadActionHistory({ skeleton: false });
    } else if (_trackReportView === 'stock') {
      loadStockReport({ skeleton: false });
    } else if (_trackReportView === 'qa') {
      loadQaHistory({ skeleton: false });
    } else if (_trackReportView === 'scrap') {
      loadScrapHistory({ skeleton: false });
    }
  }

  function renderTracking() {
    if (_tab === 'tracking') {
      renderTrackDashboard();
    } else if (_tab === 'reports') {
      renderTrackReports();
    }
  }

  function onTrackPipelineClick(e) {
    const card = e.target.closest('.lw-track-card');
    if (!card) return;
    const kind = card.dataset.trackKind;
    const partNo = card.dataset.trackPart || '';
    const lotId = card.dataset.trackLotId || '';
    const item = findTrackItem(kind, partNo, lotId);
    if (item) openTrackDrawer(item, kind);
  }

  function onTrackCapacityClick(e) {
    const btn = e.target.closest('.lw-track-expand');
    if (!btn) return;
    const key = btn.dataset.capKey;
    _trackCapacityExpanded[key] = !_trackCapacityExpanded[key];
    renderTrackCapacity();
  }

  function onTrackHistoryGridClick(e) {
    if (handleLwTreeToggle(e)) return;
    const detailBtn = e.target.closest('.lw-history-act-detail');
    if (!detailBtn) return;
    e.preventDefault();
    e.stopPropagation();
    const key = detailBtn.getAttribute('data-history-key');
    if (!key) return;
    _historyExpanded[key] = !_historyExpanded[key];
    if (_historyGrid && _historyGrid.redrawBody) _historyGrid.redrawBody();
  }

  function onTrackActionsClick(e) {
    const gotoBtn = e.target.closest('.lw-track-actions-goto');
    if (gotoBtn) {
      const tab = gotoBtn.dataset.gotoTab;
      if (tab) switchTab(tab);
      return;
    }
    const row = e.target.closest('.lw-track-action-row');
    if (!row || !row._trackItem) return;
    openTrackDrawer(row._trackItem, row._trackItem.kind);
  }

  function bindEvents() {
    const root = $('#lw-root');
    if (!root || root.dataset.lwBound === '1') return;
    root.dataset.lwBound = '1';

    document.addEventListener('click', e => {
      if (e.target.closest('.lw-operator-multi')) return;
      document.querySelectorAll('.lw-operator-multi.is-open').forEach(wrap => {
        wrap.classList.remove('is-open');
        resetOperatorMultiMenuPosition(wrap);
      });
    });

    $$('.lw-tab').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    $('#lw-table-body')?.addEventListener('click', onTableClick);
    $('#lw-asm-table-body')?.addEventListener('click', onAsmTableClick);
    $('#lw-sa-table-body')?.addEventListener('click', onSaTableClick);

    $('#lw-grid-search')?.addEventListener('input', e => {
      _filterQuery = e.target.value || '';
      if (_tab === 'trays_carton') renderTraysCartonTable();
      else if (ASM_TABS.has(_tab)) renderAssemblyTable();
      else if (SA_TABS.has(_tab)) renderSubAssemblyTable();
      else renderTable();
    });

    $('#lw-work-date')?.addEventListener('change', e => {
      _workDate = e.target.value || todayIso();
      refreshActiveTab(false);
    });

    if (!_visibilityRefreshBound) {
      _visibilityRefreshBound = true;
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible' || !isLaserWeldingVisible()) return;
        if (TRACK_TABS.has(_tab)) return;
        refreshActiveTab(true);
      });
    }

    $('#lw-production-modal-cancel')?.addEventListener('click', closeProductionModal);
    $('#lw-production-modal-save')?.addEventListener('click', saveProductionModal);
    $('#lw-production-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-production-modal-overlay') closeProductionModal();
    });
    $('#lw-prod-modal-lines')?.addEventListener('click', onProductionModalClick);
    $('#lw-prod-modal-lines')?.addEventListener('change', onProductionModalClick);
    $('#lw-prod-modal-lines')?.addEventListener('input', onProductionModalInput);
    $('#lw-prod-modal-mins')?.addEventListener('input', e => {
      const inp = e.target;
      let val = parseInt(inp.value, 10);
      if (Number.isNaN(val) || val < 0) val = 0;
      if (val > 60) {
        inp.value = '60';
        showSnackbar('Minutes cannot exceed 60', 'warning');
      }
    });
    $('#lw-prod-tray-item')?.addEventListener('change', () => updatePackMaterialAvailability('tray'));
    $('#lw-prod-carton-item')?.addEventListener('change', () => updatePackMaterialAvailability('carton'));

    $('#lw-weld-modal-cancel')?.addEventListener('click', closeWeldModal);
    $('#lw-weld-modal-save')?.addEventListener('click', saveWeldModal);
    $('#lw-weld-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-weld-modal-overlay') closeWeldModal();
    });
    $('#lw-weld-modal-qty')?.addEventListener('input', () => renderWeldModalChildren());
    $('#lw-weld-modal-parent-scrap')?.addEventListener('input', syncWeldParentScrapRemarkVisibility);
    $('#lw-weld-modal-parent-qa')?.addEventListener('input', syncWeldParentScrapRemarkVisibility);
    $('#lw-weld-modal-target-lot')?.addEventListener('change', onWeldTargetLotChange);
    $('#lw-weld-modal-children')?.addEventListener('click', onWeldModalClick);
    $('#lw-weld-modal-children')?.addEventListener('change', onWeldModalChange);
    $('#lw-weld-modal-children')?.addEventListener('input', onWeldModalInput);

    $('#lw-trays-carton-add')?.addEventListener('click', () => { if (canEdit()) void openTcModal(null); });
    $('#lw-tc-table-body')?.addEventListener('click', onTcTableClick);
    $('#lw-tc-modal-cancel')?.addEventListener('click', closeTcModal);
    $('#lw-tc-modal-save')?.addEventListener('click', () => { void saveTcModal(); });

    $('#lw-track-refresh')?.addEventListener('click', () => loadTracking({ force: true }));
    $('#lw-track-cust')?.addEventListener('change', e => {
      _trackCustId = e.target.value || '';
      _trackCache = {};
      loadTracking({ skeleton: false });
    });
    $('#lw-track-phase')?.addEventListener('change', e => {
      applyTrackPhaseFilter(e.target.value || '');
    });
    let _trackSearchTimer = null;
    $('#lw-track-search')?.addEventListener('input', e => {
      _trackSearch = e.target.value || '';
      clearTimeout(_trackSearchTimer);
      _trackSearchTimer = setTimeout(() => {
        _trackCache = {};
        loadTracking({ skeleton: false });
      }, 300);
    });
    $('#lw-report-view')?.addEventListener('change', e => setTrackReportView(e.target.value));
    $('#lw-history-refresh')?.addEventListener('click', () => reloadActiveReport({ force: true }));
    $('#lw-history-export')?.addEventListener('click', () => exportActiveReportExcel());
    $('#lw-history-from')?.addEventListener('change', e => {
      _historyFrom = e.target.value || '';
      if (_trackReportView !== 'stock') reloadActiveReport({ skeleton: false });
    });
    $('#lw-history-to')?.addEventListener('change', e => {
      _historyTo = e.target.value || '';
      if (_trackReportView !== 'stock') reloadActiveReport({ skeleton: false });
    });
    $('#lw-history-step')?.addEventListener('change', e => {
      _historyStep = e.target.value || '';
      if (_trackReportView !== 'stock') reloadActiveReport({ skeleton: false });
    });
    let _historySearchTimer = null;
    $('#lw-history-search')?.addEventListener('input', e => {
      _historySearch = e.target.value || '';
      clearTimeout(_historySearchTimer);
      _historySearchTimer = setTimeout(() => {
        if (['history', 'stock', 'qa', 'scrap'].includes(_trackReportView)) {
          reloadActiveReport({ skeleton: false });
        }
      }, 300);
    });
    $('#lw-track-exec-flow')?.addEventListener('click', e => {
      const step = e.target.closest('.lw-material-flow-step');
      if (!step) return;
      if (e.altKey || e.metaKey) {
        const tab = step.dataset.gotoTab;
        if (tab) switchTab(tab);
        return;
      }
      applyTrackFlowFilter(step.dataset.flowStep || '');
    });
    $('#lw-track-phase-grid')?.addEventListener('click', e => {
      const cell = e.target.closest('.lw-track-phase-cell');
      if (!cell) return;
      const phase = cell.dataset.trackPhase || '';
      applyTrackPhaseFilter(_trackPhase === phase ? '' : phase);
    });
    $('#lw-track-queue-tiles')?.addEventListener('click', e => {
      const tile = e.target.closest('.lw-track-queue-tile');
      if (!tile) return;
      switchToReportsPipeline(tile.dataset.trackQueuePhase || '');
    });
    $('#lw-track-pipeline')?.addEventListener('click', onTrackPipelineClick);
    $('#lw-track-capacity-body')?.addEventListener('click', onTrackCapacityClick);
    $('#lw-track-sa-capacity-body')?.addEventListener('click', onTrackCapacityClick);
    $('#lw-track-actions-body')?.addEventListener('click', onTrackActionsClick);
    $('#lw-track-history-grid')?.addEventListener('click', onTrackHistoryGridClick);
    $('#lw-track-drawer-close')?.addEventListener('click', closeTrackDrawer);
    $('#lw-track-drawer-backdrop')?.addEventListener('click', closeTrackDrawer);
    $('#lw-track-drawer-foot')?.addEventListener('click', e => {
      const btn = e.target.closest('.lw-track-goto');
      if (!btn) return;
      const tab = btn.dataset.gotoTab;
      closeTrackDrawer();
      if (tab) switchTab(tab);
    });

    $('#lw-tc-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-tc-modal-overlay') closeTcModal();
    });
    $('#lw-tc-cust')?.addEventListener('change', () => {
      refreshTcPartSelect();
      syncTcBoxTypeUi();
      scheduleTcPreview();
    });
    $('#lw-tc-part')?.addEventListener('change', () => {
      onTcPartChange();
      scheduleTcPreview();
    });
    $('#lw-tc-type-mode')?.addEventListener('change', scheduleTcPreview);
    $('#lw-tc-tray-existing')?.addEventListener('change', () => { void previewTcTray(); });
    ['lw-tc-no-parts', 'lw-tc-tray-cavity', 'lw-tc-tray-capacity',
      'lw-tc-box-type', 'lw-tc-box-l', 'lw-tc-box-w', 'lw-tc-box-h', 'lw-tc-bin-seq',
      'lw-tc-carton-capacity'].forEach(id => {
      $(`#${id}`)?.addEventListener('input', scheduleTcPreview);
      $(`#${id}`)?.addEventListener('change', scheduleTcPreview);
    });
  }

  async function init() {
    invalidateLwCaches();
    _loadGridRowsPending = false;
    _workDate = todayIso();
    const dateInput = $('#lw-work-date');
    if (dateInput) dateInput.value = _workDate;

    bindEvents();
    await Promise.all([loadOperators(), loadMachines()]);
    switchTab(_tab || 'inspection');
  }

  return { init, loadRows: loadGridRows };
})();

