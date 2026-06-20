/* ═══════════════════════════════════════════════════════════════════════════
   LASER_WELDING.JS — Laser Welding unified tab workflow
   ═══════════════════════════════════════════════════════════════════════════ */

window.LaserWeldingPage = (() => {
  const TAB_LABELS = {
    inspection: 'Inspection',
    sub_assembly: 'Sub-Assembly',
    sa_cleaning: 'SA Cleaning',
    sa_rework: 'SA Re-Work',
    laser_welding: 'Laser Welding',
    lw_cleaning: 'LW Cleaning',
    lw_rework: 'LW Re-Work',
    packing: 'Packing',
    qa: 'QA',
  };

  const GRID_TABS = new Set(['inspection', 'sa_cleaning', 'lw_cleaning', 'qa', 'packing']);
  const SA_TABS = new Set(['sub_assembly', 'sa_rework']);
  const ASM_TABS = new Set(['laser_welding', 'lw_rework']);

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
  let _packMaterials = { trays: [], cartons: [] };
  let _weldModalDraftLineId = null;
  let _weldModalBomId = null;
  let _weldModalOperatorId = null;
  let _weldModalTargetLotId = null;
  let _weldModalChildren = [];
  let _weldModalContext = 'assembly';
  let _weldModalSubAssemblyPartNo = null;
  let _prodModalSubAssemblyPartNo = null;
  let _prodModalIsBo = false;
  let _visibilityRefreshBound = false;

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
    const op = String(row.operatorId ?? '');
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
    const rows = filteredRows();
    const map = new Map();
    const order = [];
    rows.forEach(row => {
      const gk = groupDisplayKey(row);
      if (!map.has(gk)) {
        map.set(gk, {
          rowKey: `${_tab}:group:${gk}`,
          partNumber: row.partNumber || row.partNo,
          partName: row.partName,
          productName: row.productName,
          bomId: row.bomId,
          operatorId: row.operatorId,
          operatorName: row.operatorName,
          isDraft: !!row.isDraft,
          isProcessed: !!row.isProcessed,
          draftLineId: row.isDraft ? (row.draftLineId || row.lineId) : null,
          lineId: row.isDraft ? (row.draftLineId || row.lineId) : null,
          timeTakenMinutes: row.timeTakenMinutes ?? null,
          totalQty: row.totalQty ?? 0,
          lines: [...(row.lines || [])],
          batchMode: row.batchMode,
          isSubAssembly: row.isSubAssembly,
          subAssemblyPartNo: row.subAssemblyPartNo,
          _hasOt: rowHasOt(row),
        });
        order.push(gk);
        return;
      }
      mergeGroupedDisplayRow(map.get(gk), row);
    });
    return order.map(gk => {
      const g = map.get(gk);
      if (g.lines?.length) {
        g.totalQty = g.lines.reduce((sum, ln) => {
          return sum + (Number(ln.inspectedQty) || Number(ln.qaQty) || Number(ln.packQty) || 0);
        }, 0);
      }
      if (g._hasOt) g.otFlag = 'Y';
      return g;
    });
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

  function detailLinesHtml(row) {
    const lines = row.lines || [];
    let html = '<table class="ti-table lw-detail-table"><thead><tr>';
    if (_tab === 'qa') {
      html += '<th>Lot No</th><th class="text-right">Passed</th><th class="text-right">Scrap</th><th class="text-right">Rework</th>';
    } else if (_tab === 'packing') {
      html += '<th>Lot No</th><th class="text-right">Packed</th>';
    } else {
      html += '<th>Lot No</th>';
      html += '<th class="text-right">Inspected QTY</th><th class="text-right">QA</th><th class="text-right">Scrap</th>';
    }
    html += '</tr></thead><tbody>';

    if (!lines.length) {
      html += '<tr><td colspan="4" class="lw-detail-empty">No lot lines saved.</td></tr>';
    }

    lines.forEach(ln => {
      html += '<tr>';
      html += `<td>${escapeHtml(ln.sourceLotNo || ln.newLotNo || '—')}</td>`;
      if (_tab === 'qa') {
        const passed = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const rework = Number(ln.reworkQty) || 0;
        html += `<td class="text-right">${passed > 0 ? passed : '—'}</td>`;
        html += `<td class="text-right">${scrap > 0 ? scrap : '—'}</td>`;
        html += `<td class="text-right">${rework > 0 ? rework : '—'}</td>`;
      } else if (_tab === 'packing') {
        const packed = Number(ln.inspectedQty) || Number(ln.packQty) || 0;
        html += `<td class="text-right">${packed > 0 ? packed : '—'}</td>`;
      } else {
        const insp = Number(ln.inspectedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        html += `<td class="text-right">${insp > 0 ? insp : '—'}</td>`;
        html += `<td class="text-right">${qa > 0 ? qa : '—'}</td>`;
        html += `<td class="text-right">${scrap > 0 ? scrap : '—'}</td>`;
      }
      html += '</tr>';
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
    const operatorName = row.operatorName || '—';
    const timeStr = rowTimeTakenDisplay(row) || '—';
    const qty = Number(row.totalQty) || 0;

    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(partNo)}">${escapeHtml(partNo)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-qty text-right">${qty > 0 ? qty : '—'}</td>
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
    td.colSpan = 7;
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
    if (traySel) {
      const prev = traySel.value;
      traySel.innerHTML = packMaterialOptionsHtml(_packMaterials.trays, prev);
      if (prev && !traySel.value) traySel.value = '';
    }
    if (cartonSel) {
      const prev = cartonSel.value;
      cartonSel.innerHTML = packMaterialOptionsHtml(_packMaterials.cartons, prev);
      if (prev && !cartonSel.value) cartonSel.value = '';
    }
    updatePackMaterialAvailability('tray');
    updatePackMaterialAvailability('carton');
  }

  async function loadPackMaterials() {
    const data = await apiFetch('/api/laser-welding/packing/pack-materials');
    _packMaterials = {
      trays: data.trays || (data.materials || []).filter(m => m.type === 'tray'),
      cartons: data.cartons || (data.materials || []).filter(m => m.type === 'carton'),
    };
    renderPackMaterialSelects();
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
      return !ln?.targetLotId && Number(ln?.packQty) <= 0;
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
    const packInp = $(`.lw-prod-line-pack[data-idx="${idx}"]`);
    if (!packInp) return;
    let pack = parseInt(packInp.value, 10) || 0;
    const max = Number(packInp.max) || 0;
    if (max > 0 && pack > max) {
      pack = max;
      packInp.value = String(pack);
      showSnackbar('Pack QTY cannot exceed available quantity', 'warning');
    }
    if (_prodModalLines[idx]) _prodModalLines[idx].packQty = pack;
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
      html += '<th>Lot</th><th class="text-right">QA QTY</th>';
      html += '<th class="text-right">Passed</th><th class="text-right">Scrap</th><th class="text-right">Rework</th>';
      html += '<th class="lw-prod-col-remark">Scrap remark</th><th class="lw-prod-col-remark">Rework remark</th><th class="lw-prod-col-action"></th>';
    } else if (_prodModalMode === 'packing') {
      html += '<th>Lot</th><th class="text-right">Available</th><th class="text-right">Pack QTY</th><th></th>';
    } else if (isBo) {
      html += '<th class="text-right">Available</th>';
      html += '<th class="text-right">Inspected</th><th class="text-right">Scrap</th><th class="lw-prod-col-remark">Scrap remark</th>';
    } else {
      html += '<th>Lot No</th><th class="text-right">Available</th>';
      html += '<th class="text-right">Inspected</th><th class="text-right">QA</th><th class="text-right">Scrap</th>';
      html += '<th class="lw-prod-col-remark">Scrap remark</th><th class="lw-prod-col-action"></th>';
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
      html += `<td class="text-right lw-prod-line-comp" data-idx="0">${max || '—'}</td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-insp" data-idx="0" min="0" max="${max}" value="${insp}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-scrap" data-idx="0" min="0" max="${insp}" value="${scrap}" /></td>`;
      html += `<td><div class="lw-prod-scrap-remark-wrap" data-idx="0" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="0" value="${remark}" placeholder="Scrap remark" /></div></td>`;
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
          html += `<td class="text-right lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
          html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-passed" data-idx="${idx}" min="0" max="${max}" value="${passed}" /></td>`;
          html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" value="${scrap}" /></td>`;
          html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-rework" data-idx="${idx}" min="0" value="${rework}" /></td>`;
          html += `<td class="lw-prod-col-remark"><div class="lw-prod-scrap-remark-wrap" data-idx="${idx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="${idx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Scrap remark" /></div></td>`;
          html += `<td class="lw-prod-col-remark"><div class="lw-prod-rework-remark-wrap" data-idx="${idx}" style="display:${rework > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-rework-remark" data-idx="${idx}" value="${escapeAttr(ln.reworkRemark || '')}" placeholder="Rework remark" /></div></td>`;
          html += !isTrailingEmpty
            ? `<td class="lw-prod-col-action"><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`
            : '<td class="lw-prod-col-action"></td>';
          html += '</tr>';
          return;
        }

        if (_prodModalMode === 'packing') {
          const max = lotAvailableQty(ln);
          const pack = Number(ln.packQty) || 0;
          html += '<tr>';
          html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
          html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots, ln.targetLotId, usedTargetIds);
          html += '</select></td>';
          html += `<td class="text-right lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
          html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-pack" data-idx="${idx}" min="0" max="${max}" value="${pack}" /></td>`;
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
        html += `<td class="text-right lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
        html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-insp" data-idx="${idx}" min="0" max="${max}" value="${insp}" /></td>`;
        html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-qa" data-idx="${idx}" min="0" max="${insp}" value="${qa}" /></td>`;
        html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
        html += `<td class="lw-prod-col-remark"><div class="lw-prod-scrap-remark-wrap" data-idx="${idx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-prod-line-scrap-remark" data-idx="${idx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Scrap remark" /></div></td>`;
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
    if (operatorEl) operatorEl.textContent = row?.operatorName || '—';
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
      if (trayItem) trayItem.value = '';
      if (cartonItem) cartonItem.value = '';
      await loadPackMaterials();
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
        const packQty = parseInt($(`.lw-prod-line-pack[data-idx="${idx}"]`)?.value, 10) || 0;
        const match = packLots.find(l => Number(l.lotId) === targetLotId);
        const lotNo = match?.newLotNo || '';
        const max = Number(match?.totalOkayed || match?.noOfComp) || 0;
        if (packQty > max && max > 0) {
          throw new Error(`Pack QTY cannot exceed available (${max}) for lot ${lotNo}`);
        }
        if (targetLotId && packQty > 0) {
          lines.push({ targetLotId, packQty, inspectedQty: packQty });
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
        showSnackbar('Enter at least one lot with Pack QTY > 0', 'warning');
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
        packing: 'Packing saved',
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
    if (compEl) compEl.textContent = String(_prodModalLines[idx].noOfComp || '—');
    if (inspInp) inspInp.max = String(_prodModalLines[idx].noOfComp || 0);
    if (passedInp) passedInp.max = String(_prodModalLines[idx].noOfComp || 0);
    if (packInp) packInp.max = String(_prodModalLines[idx].noOfComp || 0);
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
        r.subAssemblyPartNo, r.bomNo, r.operatorName, r.machineName,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function updateEligibleAssignButton(tr, requireMachine) {
    const opSel = tr?.querySelector('.lw-eligible-operator');
    const machineSel = tr?.querySelector('.lw-eligible-machine');
    const btn = tr?.querySelector('.lw-eligible-act-assign');
    if (!btn) return;
    const operatorId = parseInt(opSel?.value, 10);
    const machineId = requireMachine ? parseInt(machineSel?.value, 10) : true;
    btn.disabled = !(operatorId && machineId);
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
    const operatorCell = editable
      ? `<select class="ti-input lw-eligible-operator">${operatorSelectHtml()}</select>`
      : '—';
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
      <td class="lw-col-qty text-right">${pendingQty > 0 ? pendingQty : '—'}</td>
      <td class="lw-col-lot">—</td>
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
      <td class="lw-col-qty text-right">${pendingQty > 0 ? pendingQty : '—'}</td>
      <td class="lw-col-lot">—</td>
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
      <td class="lw-col-qty text-right">${pendingQty > 0 ? pendingQty : '—'}</td>
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
    const operatorId = parseInt(tr?.querySelector('.lw-eligible-operator')?.value, 10);
    const machineId = parseInt(tr?.querySelector('.lw-eligible-machine')?.value, 10);
    if (!row.bomId || !operatorId || !machineId) return;
    try {
      const draft = await apiPost('/api/laser-welding/assembly/rework/pending', {
        bomId: row.bomId,
        operatorId,
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

  function nestedLinesTable(nestedLines) {
    let html = '<table class="ti-table lw-nested-table lw-nested-consume"><thead><tr>';
    html += '<th>Nested Part</th><th>Lot</th>';
    html += '</tr></thead><tbody>';
    nestedLines.forEach(nl => {
      html += '<tr>';
      html += `<td>${escapeHtml(nl.partNumber || '—')}</td>`;
      html += `<td>${escapeHtml(nl.sourceLotNo || '—')}</td>`;
      html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
  }

  function asmDetailLinesHtml(row) {
    const lines = row.lines || [];
    let html = '<table class="ti-table lw-detail-table"><thead><tr>';
    html += '<th>Child Part</th><th>Child Lot</th><th class="text-right">Consumed</th><th class="text-right">QA</th><th class="text-right">Scrap</th>';
    html += '</tr></thead><tbody>';
    if (!lines.length) {
      html += '<tr><td colspan="5" class="lw-detail-empty">No consumption lines.</td></tr>';
    }
    lines.forEach(ln => {
      html += '<tr>';
      html += `<td>${escapeHtml(ln.partNumber || '—')}</td>`;
      html += `<td>${escapeHtml(ln.sourceLotNo || '—')}</td>`;
      html += `<td class="text-right">${Number(ln.inspectedQty) || 0}</td>`;
      html += `<td class="text-right">${Number(ln.qaQty) || 0}</td>`;
      html += `<td class="text-right">${Number(ln.scrapQty) || 0}</td>`;
      html += '</tr>';
      if (ln.nestedLines?.length) {
        html += '<tr class="lw-nested-detail-row"><td colspan="5">';
        html += nestedLinesTable(ln.nestedLines);
        html += '</td></tr>';
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
    const operatorName = row.operatorName || '—';
    const machineName = row.machineName || '—';
    const customerName = row.customerName || '—';
    const qty = Number(row.weldQty ?? row.totalQty) || 0;
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-machine" title="${escapeAttr(machineName)}">${escapeHtml(machineName)}</td>
      <td class="lw-col-qty text-right">${qty > 0 ? qty : '—'}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
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
    td.colSpan = 9;
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
      <td class="lw-col-operator lw-edit-cell">
        <select class="ti-input lw-asm-new-operator">${operatorSelectHtml()}</select>
      </td>
      <td class="lw-col-machine lw-edit-cell">
        <select class="ti-input lw-asm-new-machine">${machineSelectHtml()}</select>
      </td>
      <td class="lw-col-qty">—</td>
      <td class="lw-col-lot">—</td>
      <td class="lw-col-ot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);
    const custSel = tr.querySelector('.lw-asm-new-customer');
    const bomSel = tr.querySelector('.lw-asm-new-bom');
    const opSel = tr.querySelector('.lw-asm-new-operator');
    const machineSel = tr.querySelector('.lw-asm-new-machine');
    const productEl = tr.querySelector('.lw-asm-new-product');

    custSel?.addEventListener('change', () => refreshAsmNewRowBomSelect(tr));
    bomSel?.addEventListener('change', () => {
      const bom = _boms.find(b => bomIdKey(b.bomId) === bomIdKey(bomSel.value));
      if (productEl) productEl.textContent = bom ? (bom.productName || '—') : '—';
      if (bom?.custId && custSel && !custSel.value) custSel.value = String(bom.custId);
      tryCommitAsmNewRow(custSel, bomSel, opSel, machineSel);
    });
    opSel?.addEventListener('change', () => tryCommitAsmNewRow(custSel, bomSel, opSel, machineSel));
    machineSel?.addEventListener('change', () => tryCommitAsmNewRow(custSel, bomSel, opSel, machineSel));
  }

  async function tryCommitAsmNewRow(custSel, bomSel, opSel, machineSel) {
    const bomId = bomIdKey(bomSel?.value);
    const operatorId = parseInt(opSel?.value, 10);
    const machineId = parseInt(machineSel?.value, 10);
    if (!bomId || !operatorId || !machineId) return;

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
      await apiPost(pendingUrl, { bomId, operatorId, machineId, workDate: _workDate });
      if (custSel) custSel.value = '';
      if (bomSel) { bomSel.value = ''; bomSel.innerHTML = bomSelectHtml('', ''); }
      if (opSel) opSel.value = '';
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
        r.productName, r.operatorName, r.machineName, r.newLotNo,
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
    const qty = Number(row.weldQty ?? row.totalQty) || 0;
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(row.customerName || '')}">${escapeHtml(row.customerName || '—')}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber || '—')}</td>
      <td class="lw-col-part" title="${escapeAttr(saPart)}">${escapeHtml(saPart)}</td>
      <td class="lw-col-operator" title="${escapeAttr(row.operatorName || '')}">${escapeHtml(row.operatorName || '—')}</td>
      <td class="lw-col-machine" title="${escapeAttr(row.machineName || '')}">${escapeHtml(row.machineName || '—')}</td>
      <td class="lw-col-qty text-right">${qty > 0 ? qty : '—'}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
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
    td.colSpan = 9;
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
      <td class="lw-col-lot">—</td>
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
      html += '<th class="text-right lw-weld-col-num">Consumed</th>';
      html += '<th class="text-right lw-weld-col-num">QA</th>';
      html += '<th class="text-right lw-weld-col-num">Scrap</th>';
      html += '<th class="lw-weld-col-remark">Scrap remark</th>';
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
        html += `<td class="text-right lw-weld-col-num"><input type="number" class="ti-input lw-weld-consumed" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" value="${consumed}" /></td>`;
        if (ch.isBoPart) {
          html += '<td class="text-right lw-weld-col-num lw-weld-qa-placeholder">—</td>';
        } else {
          html += `<td class="text-right lw-weld-col-num"><input type="number" class="ti-input lw-weld-qa" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${consumed}" value="${qa}" /></td>`;
        }
        html += `<td class="text-right lw-weld-col-num"><input type="number" class="ti-input lw-weld-scrap" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
        html += `<td class="lw-weld-col-remark"><div class="lw-weld-scrap-remark-wrap" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" style="display:${scrap > 0 ? '' : 'none'}"><input type="text" class="ti-input lw-weld-scrap-remark" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" value="${escapeAttr(ln.scrapRemark || '')}" placeholder="Scrap remark" /></div></td>`;
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
    _weldModalOperatorId = row.operatorId || null;
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
    $('#lw-weld-modal-operator').textContent = row.operatorName || '—';
    const machineEl = $('#lw-weld-modal-machine');
    if (machineEl) machineEl.textContent = row.machineName || '—';
    $('#lw-weld-modal-hours').value = '0';
    $('#lw-weld-modal-mins').value = '0';
    $('#lw-weld-modal-qty').value = '0';
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
    _weldModalOperatorId = null;
    _weldModalTargetLotId = null;
    _weldModalChildren = [];
    _weldModalSubAssemblyPartNo = null;
    _weldModalContext = 'assembly';
    const otInp = $('#lw-weld-modal-ot');
    if (otInp) otInp.checked = false;
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
          operatorId: _weldModalOperatorId || undefined,
          consumptions,
          otFlag,
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
          operatorId: _weldModalOperatorId || undefined,
          consumptions,
          otFlag,
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
    }
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
    const subtitle = $('#lw-subtitle');
    if (subtitle) subtitle.textContent = TAB_LABELS[tab] || '';

    refreshActiveTab(false);
  }

  function onAsmTableClick(e) {
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

  function bindEvents() {
    const root = $('#lw-root');
    if (!root || root.dataset.lwBound === '1') return;
    root.dataset.lwBound = '1';

    $$('.lw-tab').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    $('#lw-table-body')?.addEventListener('click', onTableClick);
    $('#lw-asm-table-body')?.addEventListener('click', onAsmTableClick);
    $('#lw-sa-table-body')?.addEventListener('click', onSaTableClick);

    $('#lw-grid-search')?.addEventListener('input', e => {
      _filterQuery = e.target.value || '';
      if (ASM_TABS.has(_tab)) renderAssemblyTable();
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
    $('#lw-weld-modal-target-lot')?.addEventListener('change', onWeldTargetLotChange);
    $('#lw-weld-modal-children')?.addEventListener('click', onWeldModalClick);
    $('#lw-weld-modal-children')?.addEventListener('change', onWeldModalChange);
    $('#lw-weld-modal-children')?.addEventListener('input', onWeldModalInput);
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

