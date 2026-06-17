/* ═══════════════════════════════════════════════════════════════════════════
   LASER_WELDING.JS — Laser Welding (Child Parts, QA Disposition, Rework)
   ═══════════════════════════════════════════════════════════════════════════ */

window.LaserWeldingPage = (() => {
  const TAB_LABELS = {
    child_parts: 'Inspection — part inspection & cleaning',
    qa_disposition: 'QA Disposition — approve passed / scrap / rework',
    sub_assembly: 'Sub-Assembly — build & re-work sub-assemblies',
    final_assembly: 'Laser Welding — BOM assembly & weld',
    packing: 'Packing — pack okayed lots to inventory / ERP',
  };

  let _tab = 'child_parts';
  let _workDate = '';
  let _batchMode = 'production';
  let _asmMode = 'welding';
  let _saMode = 'sub_assembly';
  let _parts = [];
  let _operators = [];
  let _machines = [];
  let _rows = [];
  let _expanded = {};
  let _sourceLotsCache = {};
  let _childLotsCache = {};
  let _qaRows = [];
  let _packingRows = [];
  let _asmRows = [];
  let _saRows = [];
  let _boms = [];
  let _saPartsList = [];
  let _bomCustomers = [];
  let _asmExpanded = {};
  let _saExpanded = {};
  let _saLoading = false;
  let _reworkTargetLotsCache = {};
  let _filterQuery = '';
  let _loading = false;
  let _loadChildRowsPending = false;
  let _asmLoading = false;
  let _prodModalLines = [];
  let _prodModalMode = 'production';
  let _prodModalDraftLineId = null;
  let _prodModalBomId = null;
  let _cleaningLotsCache = {};
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

  function isReworkWeldingMode() {
    return _asmMode === 'rework_welding';
  }

  function isReworkSubAssemblyMode() {
    return _saMode === 'rework_sub_assembly';
  }

  function isWeldReworkMode() {
    if (_weldModalContext === 'sub_assembly') return isReworkSubAssemblyMode();
    return isReworkWeldingMode();
  }

  function isSubAssemblyWeldContext() {
    return _weldModalContext === 'sub_assembly';
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

  function rowBatchMode(row) {
    return row.batchMode || _batchMode;
  }

  function rowMatchesMode(row) {
    return rowBatchMode(row) === _batchMode;
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
    };
  }

  function lotAvailableQty(lot) {
    if (!lot) return 0;
    const avail = Number(lot.availableQty);
    if (Number.isFinite(avail) && avail > 0) return avail;
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

  function invalidateLwCaches() {
    _sourceLotsCache = {};
    _cleaningLotsCache = {};
    _childLotsCache = {};
    _reworkTargetLotsCache = {};
  }

  function isLaserWeldingVisible() {
    return !!$('#lw-root');
  }

  async function refreshActiveTab(preserveFilter) {
    if (!isLaserWeldingVisible()) return;
    invalidateLwCaches();
    if (_tab === 'child_parts') {
      try {
        await refreshPartsDatalist();
      } catch (err) {
        console.error('Failed to refresh parts list', err);
      }
      await loadChildRows(preserveFilter);
    } else if (_tab === 'final_assembly') {
      await loadBomCatalog();
      await loadAssemblyRows(preserveFilter);
    } else if (_tab === 'sub_assembly') {
      await loadSubAssemblyPartCatalog();
      await loadSubAssemblyRows(preserveFilter);
    } else if (_tab === 'qa_disposition') {
      await loadQaRows();
    } else if (_tab === 'packing') {
      await loadPackingRows();
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

  function allDisplayRows() {
    return _rows.filter(r => rowMatchesMode(r));
  }

  function filteredRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = allDisplayRows();
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.partNumber,
        r.partName || partNameFor(r.partNumber),
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
    if (_batchMode === 'cleaning') {
      const bom = String(row.bomId || bomIdForPartNo(row.partNumber) || row.partNumber || '').trim();
      return `${bom}|${op}`;
    }
    const part = String(row.partNumber || '').trim().toLowerCase();
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
  }

  function tableDisplayRows() {
    const rows = filteredRows();
    if (_batchMode !== 'cleaning' && _batchMode !== 'production') return rows;

    const map = new Map();
    const order = [];
    rows.forEach(row => {
      const gk = groupDisplayKey(row);
      if (!map.has(gk)) {
        map.set(gk, {
          rowKey: `${_batchMode}:group:${gk}`,
          partNumber: row.partNumber,
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
          lines: [...(row.lines || [])],
          batchMode: row.batchMode,
        });
        order.push(gk);
        return;
      }
      mergeGroupedDisplayRow(map.get(gk), row);
    });
    return order.map(gk => map.get(gk));
  }

  function findRow(rowKey) {
    const grouped = tableDisplayRows().find(r => r.rowKey === rowKey);
    if (grouped) return grouped;
    return allDisplayRows().find(r => r.rowKey === rowKey);
  }

  function updateRowCount() {
    const el = $('#lw-item-count');
    if (!el) return;
    if (_tab === 'child_parts') {
      const n = tableDisplayRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'final_assembly') {
      const n = filteredAsmRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'sub_assembly') {
      const n = filteredSaRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'qa_disposition') {
      el.textContent = `${_qaRows.length} pending`;
    } else if (_tab === 'packing') {
      el.textContent = `${_packingRows.length} ready`;
    } else {
      el.textContent = '—';
    }
  }

  function updateTableHeader() {
    const head = $('#lw-table-head');
    if (!head) return;
    if (_batchMode === 'cleaning') {
      head.innerHTML = `
        <tr>
          <th class="lw-col-bom">BOM No</th>
          <th class="lw-col-name">Product</th>
          <th class="lw-col-operator">Operator</th>
          <th class="lw-col-time">Time taken</th>
          <th class="lw-col-actions">Actions</th>
        </tr>`;
    } else {
      head.innerHTML = `
        <tr>
          <th class="lw-col-part">Part No</th>
          <th class="lw-col-name">Part Name</th>
          <th class="lw-col-operator">Operator</th>
          <th class="lw-col-time">Time taken</th>
          <th class="lw-col-actions">Actions</th>
        </tr>`;
    }
  }

  function updateModeChrome() {
    /* mode bar is static — no extra chrome per mode */
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
    html += '<th>Lot No</th>';
    html += '<th class="text-right">Inspected QTY</th><th class="text-right">QA</th><th class="text-right">Scrap</th>';
    html += '</tr></thead><tbody>';

    if (!lines.length) {
      html += '<tr><td colspan="4" class="lw-detail-empty">No lot lines saved.</td></tr>';
    }

    lines.forEach(ln => {
      const insp = Number(ln.inspectedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      html += '<tr>';
      html += `<td>${escapeHtml(ln.sourceLotNo || '—')}</td>`;
      html += `<td class="text-right">${insp > 0 ? insp : '—'}</td>`;
      html += `<td class="text-right">${qa > 0 ? qa : '—'}</td>`;
      html += `<td class="text-right">${scrap > 0 ? scrap : '—'}</td>`;
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
      if (_tab === 'child_parts') await loadChildRows(true);
      else if (_tab === 'final_assembly') await loadAssemblyRows(true);
      else if (_tab === 'sub_assembly') await loadSubAssemblyRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to remove row', 'error');
    }
  }

  function buildActionsHtml(row) {
    const key = row.rowKey;
    const expCls = _expanded[key] ? ' is-expanded' : '';
    let actions = '';

    if (_batchMode === 'cleaning' || _batchMode === 'production') {
      if (row.isProcessed) {
        actions += `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Lot lines">▤</button>`;
      }
      if (row.isDraft) {
        if (!canEdit()) return actions || '<span class="lw-view-only">View only</span>';
        actions += `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-inspect" data-row-key="${escapeAttr(key)}">Inspect</button>`;
        actions += buildDraftDismissBtn(row);
      }
      if (actions) return actions;
      if (!canEdit()) return '<span class="lw-view-only">View only</span>';
      return '';
    }

    if (!canEdit()) return '<span class="lw-view-only">View only</span>';
    return '';
  }

  function buildDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;

    if (_batchMode === 'cleaning') {
      const product = row.productName || row.partName || row.partNumber;
      const operatorName = row.operatorName || '—';
      const timeStr = rowTimeTakenDisplay(row) || '—';
      tr.innerHTML = `
        <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
        <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
        <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
        <td class="lw-col-time">${escapeHtml(timeStr)}</td>
        <td class="lw-col-actions lw-actions-cell">${buildActionsHtml(row)}</td>
      `;
      return tr;
    }

    const partName = row.partName || partNameFor(row.partNumber);
    const operatorName = row.operatorName || '—';
    const timeStr = rowTimeTakenDisplay(row) || '—';
    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-time">${escapeHtml(timeStr)}</td>
      <td class="lw-col-actions lw-actions-cell">${buildActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;

    const td = document.createElement('td');
    td.colSpan = 5;
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

  function bomIdForPartNo(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => partNoKey(x) === key);
    return p?.bomId || p?.bom_id || null;
  }

  function appendNewRow(tbody) {
    if (!canEdit() || _tab !== 'child_parts') return;
    if (_batchMode === 'cleaning') {
      appendCleaningNewRow(tbody);
      return;
    }
    if (_batchMode !== 'production') return;

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
      <td class="lw-col-time">—</td>
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
      <td class="lw-col-bom lw-edit-cell">
        <input type="text" class="lw-cell-input lw-new-bom"
               list="lw-parts-datalist" placeholder="Select BOM…" autocomplete="off" />
      </td>
      <td class="lw-col-name lw-new-bom-name"></td>
      <td class="lw-col-operator lw-edit-cell">
        <select class="ti-input lw-new-operator">${operatorSelectHtml()}</select>
      </td>
      <td class="lw-col-time">—</td>
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
      showSnackbar('BOM not found or has no welded lots pending inspection', 'error');
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
      await loadChildRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add row', 'error');
    }
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

  async function tryCommitNewRow(partInput, operatorSel) {
    const partNumber = (partInput?.value || '').trim();
    const operatorId = parseInt(operatorSel?.value, 10);
    if (!partNumber || !operatorId) return;

    const partMatch = _parts.find(p => partNoKey(p) === partNumber.toLowerCase());
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

    try {
      await apiPost('/api/laser-welding/child-parts/pending', {
        partNumber,
        operatorId,
        workDate: _workDate,
      });
      partInput.value = '';
      if (operatorSel) operatorSel.value = '';
      const nameEl = partInput.closest('tr')?.querySelector('.lw-new-part-name');
      if (nameEl) nameEl.textContent = '';
      await loadChildRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Failed to add row', 'error');
    }
  }

  function renderTable() {
    const tbody = $('#lw-table-body');
    if (!tbody) return;

    updateTableHeader();
    updateModeChrome();
    tbody.innerHTML = '';

    if (_batchMode === 'cleaning') {
      tableDisplayRows().forEach(row => {
        tbody.appendChild(buildDataRow(row));
        if (_expanded[row.rowKey]) {
          tbody.appendChild(buildDetailRow(row));
        }
      });
      appendNewRow(tbody);
    } else {
      tableDisplayRows().forEach(row => {
        tbody.appendChild(buildDataRow(row));
        if (_expanded[row.rowKey]) {
          tbody.appendChild(buildDetailRow(row));
        }
      });
      appendNewRow(tbody);
    }
    updateRowCount();
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

  function prodLotOptionsHtml(partNo, selectedLot, usedLots, selectedTargetId, usedTargetIds) {
    if (_prodModalMode === 'cleaning') {
      const lots = _cleaningLotsCache[cleaningLotsCacheKey()] || [];
      let html = '<option value="">Select LW lot…</option>';
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

  function syncProdLineQtyCaps(idx, changedField) {
    if (_prodModalIsBo && _prodModalMode !== 'cleaning') {
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

    if (_prodModalLines[idx]) {
      _prodModalLines[idx].inspectedQty = insp;
      _prodModalLines[idx].qaQty = qa;
      _prodModalLines[idx].scrapQty = scrap;
    }
  }

  function renderProductionModalLines() {
    const body = $('#lw-prod-modal-lines');
    if (!body) return;

    if (!(_prodModalIsBo && _prodModalMode !== 'cleaning')) {
      ensureProdModalTrailingLine();
    }

    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const usedLots = new Set(_prodModalLines.map(l => l.sourceLotNo).filter(Boolean));
    const usedTargetIds = new Set(_prodModalLines.map(l => Number(l.targetLotId)).filter(Boolean));
    const isCleaning = _prodModalMode === 'cleaning';
    const isBo = _prodModalIsBo && !isCleaning;

    let html = '<table class="ti-table lw-prod-modal-table"><thead><tr>';
    if (isBo) {
      html += '<th class="text-right">Available</th>';
      html += '<th class="text-right">Inspected</th><th class="text-right">Scrap</th>';
    } else {
      html += `<th>${isCleaning ? 'LW Lot' : 'Lot No'}</th>`;
      html += '<th class="text-right">Available</th>';
      html += '<th class="text-right">Inspected</th><th class="text-right">QA</th><th class="text-right">Scrap</th><th></th>';
    }
    html += '</tr></thead><tbody>';

    if (isBo) {
      const info = sourceLotsInfo(partNo);
      const max = info.availableQty;
      const ln = _prodModalLines[0] || emptyLine();
      const insp = Number(ln.inspectedQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      html += '<tr>';
      html += `<td class="text-right lw-prod-line-comp" data-idx="0">${max || '—'}</td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-insp" data-idx="0" min="0" max="${max}" value="${insp}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-scrap" data-idx="0" min="0" max="${insp}" value="${scrap}" /></td>`;
      html += '</tr>';
    } else {
    _prodModalLines.forEach((ln, idx) => {
      const max = lotAvailableQty(ln);
      const insp = Number(ln.inspectedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      const qaMax = insp;
      const scrapMax = Math.max(0, insp - qa);
      const isTrailingEmpty = idx === _prodModalLines.length - 1 && isModalLineEmpty(ln);
      html += '<tr>';
      html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
      html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots, ln.targetLotId, usedTargetIds);
      html += '</select></td>';
      html += `<td class="text-right lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-insp" data-idx="${idx}" min="0" max="${max}" value="${insp}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-qa" data-idx="${idx}" min="0" max="${qaMax}" value="${qa}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-scrap" data-idx="${idx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
      if (!isTrailingEmpty) {
        html += `<td><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`;
      } else {
        html += '<td></td>';
      }
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

  async function openProductionModal(row) {
    const overlay = $('#lw-production-modal-overlay');
    if (!overlay) return;

    const isCleaning = _batchMode === 'cleaning';
    _prodModalMode = isCleaning ? 'cleaning' : 'production';
    _prodModalDraftLineId = row?.draftLineId || row?.lineId || null;
    _prodModalBomId = isCleaning ? (row?.bomId || bomIdForPartNo(row?.partNumber)) : null;
    _prodModalSubAssemblyPartNo = isCleaning ? cleaningSubAssemblyPartNo(row) : null;

    const partNo = row?.partNumber || '';
    const title = $('#lw-production-modal-title');
    const partEl = $('#lw-prod-modal-part');
    const operatorEl = $('#lw-prod-modal-operator');

    if (title) title.textContent = isCleaning ? 'Cleaning Inspection' : 'Part Inspection';
    if (partEl) {
      const label = isCleaning
        ? `${partNo} — ${row.productName || row.partName || ''}`
        : `${partNo} — ${row.partName || partNameFor(partNo)}`;
      partEl.textContent = partNo ? label : '—';
      partEl.dataset.partNumber = partNo;
    }
    if (operatorEl) {
      operatorEl.textContent = row?.operatorName || '—';
    }
    const hoursInp = $('#lw-prod-modal-hours');
    const minsInp = $('#lw-prod-modal-mins');
    if (hoursInp) hoursInp.value = '0';
    if (minsInp) minsInp.value = '0';

    if (isCleaning && _prodModalBomId) {
      await fetchCleaningSourceLots(_prodModalBomId, _prodModalSubAssemblyPartNo);
      _prodModalIsBo = false;
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
    if (isCleaning) {
      _prodModalLines = [emptyLine()];
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
  }

  function collectProductionModalLines() {
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const isCleaning = _prodModalMode === 'cleaning';
    const isBo = _prodModalIsBo && !isCleaning;
    const asmLots = _cleaningLotsCache[cleaningLotsCacheKey()] || [];
    const lines = [];

    if (isBo) {
      const info = sourceLotsInfo(partNo);
      const max = info.availableQty;
      const inspInp = $('.lw-prod-line-insp[data-idx="0"]');
      const scrapInp = $('.lw-prod-line-scrap[data-idx="0"]');
      const insp = parseInt(inspInp?.value, 10) || 0;
      const scrap = parseInt(scrapInp?.value, 10) || 0;
      if (scrap > insp) {
        throw new Error('Scrap cannot exceed Inspected QTY');
      }
      if (insp > max && max > 0) {
        throw new Error(`Inspected QTY cannot exceed available stock (${max})`);
      }
      if (insp > 0 || scrap > 0) {
        lines.push({
          noOfComp: max,
          availableQty: max,
          inspectedQty: insp,
          qaQty: 0,
          scrapQty: scrap,
        });
      }
      return lines;
    }

    const erpLots = sourceLotsInfo(partNo).lots;

    $$('.lw-prod-line-lot').forEach(sel => {
      const idx = Number(sel.getAttribute('data-idx'));
      const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
      const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
      const scrapInp = $(`.lw-prod-line-scrap[data-idx="${idx}"]`);
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
          if (!targetLotId) throw new Error('Select an LW lot for lines with quantity');
          lines.push({
            targetLotId,
            sourceLotNo: lotNo,
            noOfComp: max,
            availableQty: max,
            inspectedQty: insp,
            qaQty: qa,
            scrapQty: scrap,
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

    const nonZero = lines.filter(l => Number(l.inspectedQty) > 0);
    if (!nonZero.length) {
      showSnackbar('Enter at least one line with Inspected QTY > 0', 'warning');
      return;
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

    const isCleaning = _prodModalMode === 'cleaning';
    const endpoint = isCleaning
      ? '/api/laser-welding/cleaning/inspect'
      : '/api/laser-welding/child-parts/inspect';

    try {
      const data = await apiPost(endpoint, {
        draftLineId,
        workDate: _workDate,
        lines,
        timeTakenMinutes,
      });
      if (isCleaning) {
        showSnackbar('Cleaning inspection saved', 'success');
      } else {
        const lots = data.lots || [];
        if (lots.length > 1) {
          const labels = lots.map(l => l.newLotNo).filter(Boolean).join(', ');
          showSnackbar(`Inspected — ${lots.length} lots: ${labels}`, 'success');
        } else {
          showSnackbar(`Inspected — Lot No: ${data.newLotNo || lots[0]?.newLotNo || ''}`, 'success');
        }
      }
      closeProductionModal();
      invalidateLwCaches();
      await loadChildRows(true);
      if (_tab === 'child_parts') {
        try {
          await refreshPartsDatalist();
        } catch (err) {
          console.error('Failed to refresh parts list after inspect', err);
        }
      }
    } catch (err) {
      showSnackbar(err.message || 'Inspect failed', 'error');
    }
  }

  function onProductionModalLotChange(sel) {
    const idx = Number(sel.getAttribute('data-idx'));
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const isCleaning = _prodModalMode === 'cleaning';

    if (!_prodModalLines[idx]) _prodModalLines[idx] = emptyLine();

    if (isCleaning) {
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
    if (compEl) compEl.textContent = String(_prodModalLines[idx].noOfComp || '—');
    if (inspInp) inspInp.max = String(_prodModalLines[idx].noOfComp || 0);
    syncProdLineQtyCaps(idx, 'insp');

    const hasLot = isCleaning ? _prodModalLines[idx].targetLotId : _prodModalLines[idx].sourceLotNo;
    if (hasLot && idx === _prodModalLines.length - 1) {
      renderProductionModalLines();
    }
  }

  async function loadChildRows(preserveFilter) {
    if (_tab !== 'child_parts') return;

    const loadingEl = $('#lw-loading');
    const errorEl = $('#lw-error');
    if (_loading) {
      _loadChildRowsPending = true;
      return;
    }
    _loading = true;
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      const data = await apiFetch(
        '/api/laser-welding/child-parts/rows?date=' + encodeURIComponent(_workDate)
        + '&mode=' + encodeURIComponent(_batchMode)
      );
      _rows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || `row:${r.partNumber}:${r.lineId || r.lotId || ''}`,
        batchMode: r.batchMode || _batchMode,
        lines: r.lines || [],
      }));
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
      if (_loadChildRowsPending) {
        _loadChildRowsPending = false;
        await loadChildRows(preserveFilter);
      }
    }
  }

  async function refreshPartsDatalist() {
    const data = await apiFetch('/api/laser-welding/parts?mode=' + encodeURIComponent(_batchMode));
    _parts = data.parts || [];
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
      const data = await apiFetch('/api/laser-welding/machines');
      _machines = data.machines || [];
    } catch (err) {
      console.error('Failed to load machines', err);
      _machines = [];
    }
  }

  async function loadParts() {
    try {
      await refreshPartsDatalist();
      populateQaPartSelect();
    } catch (err) {
      console.error('Failed to load parts', err);
    }
  }

  async function refreshMeta() {
    try {
      const meta = await apiFetch('/api/laser-welding/meta?date=' + encodeURIComponent(_workDate));
      if (meta.workDate) _workDate = meta.workDate;
    } catch (_) { /* ignore */ }
  }

  function populateSelect(sel, items, valueKey, labelFn, placeholder) {
    if (!sel) return;
    sel.innerHTML = `<option value="">${placeholder || 'Select…'}</option>`;
    items.forEach(it => {
      const opt = document.createElement('option');
      opt.value = it[valueKey];
      opt.textContent = labelFn(it);
      sel.appendChild(opt);
    });
  }

  function populateQaPartSelect() {
    const partsInQa = [...new Set(_qaRows.map(r => r.partNumber))];
    const sel = $('#lw-qa-part');
    populateSelect(
      sel,
      partsInQa.map(pn => {
        const row = _qaRows.find(r => r.partNumber === pn);
        const label = row?.productName || row?.partName || partNameFor(pn);
        return { pn, name: label };
      }),
      'pn',
      it => `${it.pn} — ${it.name || ''}`,
      'Select part…'
    );
  }

  function populateQaLotSelect(partNo) {
    const sel = $('#lw-qa-lot');
    const lots = _qaRows.filter(r => r.partNumber === partNo);
    populateSelect(sel, lots, 'lotId', r => `${r.newLotNo} (QA: ${r.totalQa})`, 'Select lot…');
  }

  function renderQaQueue() {
    const el = $('#lw-qa-queue');
    if (!el) return;
    if (!_qaRows.length) {
      el.innerHTML = '<p class="lw-queue-empty">No lots pending QA disposition.</p>';
      return;
    }
    el.innerHTML = _qaRows.map(r => {
      const product = r.productName || r.partName || '';
      const label = product ? `${r.partNumber} — ${product}` : r.partNumber;
      return (
        `<button type="button" class="lw-queue-item" data-part="${escapeAttr(r.partNumber)}" data-lot-id="${r.lotId}">` +
        `${escapeHtml(label)} · ${escapeHtml(r.newLotNo || '—')} · QA ${r.totalQa}` +
        '</button>'
      );
    }).join('');
  }

  function resetQaForm() {
    const partSel = $('#lw-qa-part');
    const lotSel = $('#lw-qa-lot');
    if (partSel) partSel.value = '';
    if (lotSel) lotSel.innerHTML = '<option value="">Select lot…</option>';
    $('#lw-qa-qty-display').textContent = '—';
    $('#lw-qa-passed').value = '0';
    $('#lw-qa-scrap').value = '0';
    $('#lw-qa-rework').value = '0';
    const btn = $('#lw-qa-approve');
    if (btn) btn.disabled = true;
  }

  function qaEnteredSum() {
    return (parseInt($('#lw-qa-passed')?.value, 10) || 0)
      + (parseInt($('#lw-qa-scrap')?.value, 10) || 0)
      + (parseInt($('#lw-qa-rework')?.value, 10) || 0);
  }

  function updateQaApproveState() {
    const lotId = parseInt($('#lw-qa-lot')?.value, 10);
    const lot = _qaRows.find(r => Number(r.lotId) === lotId);
    const btn = $('#lw-qa-approve');
    const hint = $('#lw-qa-sum-hint');
    if (!btn) return;
    if (!lot || !canEdit()) {
      btn.disabled = true;
      if (hint) hint.textContent = 'Select a lot to see remaining QA quantity.';
      return;
    }
    const total = Number(lot.totalQa) || 0;
    if (total <= 0) {
      btn.disabled = true;
      if (hint) hint.textContent = 'This lot has no QTY for QA.';
      return;
    }
    const sum = qaEnteredSum();
    const remaining = total - sum;
    btn.disabled = sum !== total;
    if (hint) {
      hint.textContent = sum === total
        ? `All ${total} at QA accounted for — ready to approve.`
        : `${remaining} remaining at QA`;
    }
  }

  function onQaPartChange() {
    const partNo = $('#lw-qa-part')?.value || '';
    populateQaLotSelect(partNo);
    $('#lw-qa-qty-display').textContent = '—';
    $('#lw-qa-passed').value = '0';
    $('#lw-qa-scrap').value = '0';
    $('#lw-qa-rework').value = '0';
    updateQaApproveState();
  }

  function onQaLotChange() {
    const lotId = parseInt($('#lw-qa-lot')?.value, 10);
    const lot = _qaRows.find(r => Number(r.lotId) === lotId);
    const qtyEl = $('#lw-qa-qty-display');
    if (!lot) {
      qtyEl.textContent = '—';
      $('#lw-qa-passed').value = '0';
      $('#lw-qa-scrap').value = '0';
      $('#lw-qa-rework').value = '0';
      updateQaApproveState();
      return;
    }
    qtyEl.textContent = String(lot.totalQa || 0);
    $('#lw-qa-passed').value = '0';
    $('#lw-qa-scrap').value = '0';
    $('#lw-qa-rework').value = '0';
    updateQaApproveState();
  }

  async function loadQaRows() {
    const loadingEl = $('#lw-qa-loading');
    const errorEl = $('#lw-qa-error');
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      const data = await apiFetch('/api/laser-welding/qa/rows');
      _qaRows = data.rows || [];
      populateQaPartSelect();
      renderQaQueue();
      updateRowCount();
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load QA rows';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
    }
  }

  async function approveQa() {
    const lotId = parseInt($('#lw-qa-lot')?.value, 10);
    if (!lotId) {
      showSnackbar('Select a lot first', 'warning');
      return;
    }
    const lot = _qaRows.find(r => Number(r.lotId) === lotId);
    const total = Number(lot?.totalQa) || 0;
    if (total <= 0) {
      showSnackbar('This lot has no QTY for QA', 'warning');
      return;
    }
    const sum = qaEnteredSum();
    if (sum !== total) {
      showSnackbar(`QA Passed + Scrap + Rework must equal QTY for QA (${total})`, 'error');
      return;
    }
    if (!confirm('Approve QA disposition for this lot? This cannot be undone.')) return;

    try {
      await apiPost('/api/laser-welding/qa/approve', {
        lotId,
        qaPassed: parseInt($('#lw-qa-passed')?.value, 10) || 0,
        scrap: parseInt($('#lw-qa-scrap')?.value, 10) || 0,
        rework: parseInt($('#lw-qa-rework')?.value, 10) || 0,
      });
      showSnackbar('QA approved', 'success');
      resetQaForm();
      await loadQaRows();
    } catch (err) {
      showSnackbar(err.message || 'Approve failed', 'error');
    }
  }

  function populatePackingPartSelect() {
    const partsInPack = [...new Set(_packingRows.map(r => r.partNo))];
    const sel = $('#lw-packing-part');
    populateSelect(
      sel,
      partsInPack.map(pn => {
        const row = _packingRows.find(r => r.partNo === pn);
        const typeLabel = row?.packType === 'bom' ? 'BOM' : 'Part';
        const name = row?.partName || '';
        return { pn, name, typeLabel };
      }),
      'pn',
      it => `${it.pn} — ${it.name || ''} (${it.typeLabel})`,
      'Select part…'
    );
  }

  function populatePackingLotSelect(partNo) {
    const sel = $('#lw-packing-lot');
    const lots = _packingRows.filter(r => r.partNo === partNo);
    populateSelect(
      sel,
      lots,
      'lotId',
      r => `${r.newLotNo} (Avail: ${r.totalOkayed})`,
      'Select lot…'
    );
  }

  function renderPackingQueue() {
    const el = $('#lw-packing-queue');
    if (!el) return;
    if (!_packingRows.length) {
      el.innerHTML = '<p class="lw-queue-empty">No lots ready for packing.</p>';
      return;
    }
    el.innerHTML = _packingRows.map(r => {
      const typeLabel = r.packType === 'bom' ? 'BOM' : 'Part';
      const label = r.partName ? `${r.partNo} — ${r.partName}` : r.partNo;
      return (
        `<button type="button" class="lw-queue-item" data-part="${escapeAttr(r.partNo)}" data-lot-id="${r.lotId}">` +
        `${escapeHtml(label)} · ${escapeHtml(r.newLotNo || '—')} · ${typeLabel} · Avail ${r.totalOkayed}` +
        '</button>'
      );
    }).join('');
  }

  function resetPackingForm() {
    const partSel = $('#lw-packing-part');
    const lotSel = $('#lw-packing-lot');
    if (partSel) partSel.value = '';
    if (lotSel) lotSel.innerHTML = '<option value="">Select lot…</option>';
    $('#lw-packing-type-display').textContent = '—';
    $('#lw-packing-qty-display').textContent = '—';
    const qtyInp = $('#lw-packing-qty');
    if (qtyInp) {
      qtyInp.value = '';
      qtyInp.removeAttribute('max');
    }
    const btn = $('#lw-packing-pack');
    if (btn) btn.disabled = true;
    const hint = $('#lw-packing-hint');
    if (hint) hint.textContent = 'Select a lot to pack.';
  }

  function updatePackingPackState() {
    const lotId = parseInt($('#lw-packing-lot')?.value, 10);
    const lot = _packingRows.find(r => Number(r.lotId) === lotId);
    const btn = $('#lw-packing-pack');
    const hint = $('#lw-packing-hint');
    const qtyInp = $('#lw-packing-qty');
    if (!btn) return;
    if (!lot || !canEdit()) {
      btn.disabled = true;
      if (hint) hint.textContent = 'Select a lot to pack.';
      return;
    }
    const available = Number(lot.totalOkayed) || 0;
    if (available <= 0) {
      btn.disabled = true;
      if (hint) hint.textContent = 'This lot has no quantity available for packing.';
      return;
    }
    if (qtyInp) qtyInp.max = String(available);
    const packQty = parseInt(qtyInp?.value, 10);
    const valid = packQty > 0 && packQty <= available;
    btn.disabled = !valid;
    if (hint) {
      if (!packQty) {
        hint.textContent = `${available} available — enter pack quantity.`;
      } else if (packQty > available) {
        hint.textContent = `Pack quantity cannot exceed available (${available}).`;
      } else if (packQty === available) {
        hint.textContent = `Packing all ${available} — ready to confirm.`;
      } else {
        hint.textContent = `${available - packQty} will remain after this pack.`;
      }
    }
  }

  function onPackingPartChange() {
    const partNo = $('#lw-packing-part')?.value || '';
    populatePackingLotSelect(partNo);
    $('#lw-packing-type-display').textContent = '—';
    $('#lw-packing-qty-display').textContent = '—';
    const qtyInp = $('#lw-packing-qty');
    if (qtyInp) {
      qtyInp.value = '';
      qtyInp.removeAttribute('max');
    }
    updatePackingPackState();
  }

  function onPackingLotChange() {
    const lotId = parseInt($('#lw-packing-lot')?.value, 10);
    const lot = _packingRows.find(r => Number(r.lotId) === lotId);
    const qtyEl = $('#lw-packing-qty-display');
    const typeEl = $('#lw-packing-type-display');
    const qtyInp = $('#lw-packing-qty');
    if (!lot) {
      if (typeEl) typeEl.textContent = '—';
      if (qtyEl) qtyEl.textContent = '—';
      if (qtyInp) {
        qtyInp.value = '';
        qtyInp.removeAttribute('max');
      }
      updatePackingPackState();
      return;
    }
    if (typeEl) typeEl.textContent = lot.packType === 'bom' ? 'BOM' : 'Part';
    if (qtyEl) qtyEl.textContent = String(lot.totalOkayed || 0);
    if (qtyInp) {
      qtyInp.value = '';
      qtyInp.max = String(Number(lot.totalOkayed) || 1);
    }
    updatePackingPackState();
  }

  async function loadPackingRows() {
    const loadingEl = $('#lw-packing-loading');
    const errorEl = $('#lw-packing-error');
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      const data = await apiFetch('/api/laser-welding/packing/rows');
      _packingRows = data.rows || [];
      populatePackingPartSelect();
      renderPackingQueue();
      updateRowCount();
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load packing rows';
        errorEl.style.display = 'block';
      }
    } finally {
      if (loadingEl) loadingEl.style.display = 'none';
    }
  }

  async function packLot() {
    const lotId = parseInt($('#lw-packing-lot')?.value, 10);
    if (!lotId) {
      showSnackbar('Select a lot first', 'warning');
      return;
    }
    const lot = _packingRows.find(r => Number(r.lotId) === lotId);
    const available = Number(lot?.totalOkayed) || 0;
    const packQty = parseInt($('#lw-packing-qty')?.value, 10);
    if (!packQty || packQty <= 0) {
      showSnackbar('Enter a pack quantity greater than 0', 'warning');
      return;
    }
    if (packQty > available) {
      showSnackbar(`Pack quantity cannot exceed available (${available})`, 'error');
      return;
    }
    if (!confirm(`Pack ${packQty} of ${available} for lot ${lot?.newLotNo || lotId}?`)) return;

    try {
      await apiPost('/api/laser-welding/packing/pack', {
        lotId,
        packQty,
        workDate: todayIso(),
      });
      showSnackbar('Packed successfully', 'success');
      resetPackingForm();
      await loadPackingRows();
    } catch (err) {
      showSnackbar(err.message || 'Pack failed', 'error');
    }
  }

  function filteredAsmRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = _asmRows;
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.customerName,
        r.partNumber,
        r.productName,
        r.partName,
        r.operatorName,
        r.machineName,
        r.newLotNo,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function findAsmRow(rowKey) {
    return _asmRows.find(r => r.rowKey === rowKey);
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
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-machine" title="${escapeAttr(machineName)}">${escapeHtml(machineName)}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-actions lw-actions-cell">${buildAsmActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildAsmDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;
    const td = document.createElement('td');
    td.colSpan = 7;
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
    if (!canEdit() || _tab !== 'final_assembly') return;
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
      <td class="lw-col-lot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);
    const custSel = tr.querySelector('.lw-asm-new-customer');
    const bomSel = tr.querySelector('.lw-asm-new-bom');
    const opSel = tr.querySelector('.lw-asm-new-operator');
    const machineSel = tr.querySelector('.lw-asm-new-machine');
    const productEl = tr.querySelector('.lw-asm-new-product');

    custSel?.addEventListener('change', () => {
      refreshAsmNewRowBomSelect(tr);
    });

    bomSel?.addEventListener('change', () => {
      const bom = _boms.find(b => bomIdKey(b.bomId) === bomIdKey(bomSel.value));
      if (productEl) productEl.textContent = bom ? (bom.productName || '—') : '—';
      if (bom?.custId && custSel && !custSel.value) {
        custSel.value = String(bom.custId);
      }
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
      await apiPost(pendingUrl, {
        bomId,
        operatorId,
        machineId,
        workDate: _workDate,
      });
      if (custSel) custSel.value = '';
      if (bomSel) {
        bomSel.value = '';
        bomSel.innerHTML = bomSelectHtml('', '');
      }
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
      if (_asmExpanded[row.rowKey]) {
        tbody.appendChild(buildAsmDetailRow(row));
      }
    });
    appendAsmNewRow(tbody);
    updateRowCount();
  }

  async function loadBomCatalog() {
    try {
      const custData = await apiFetch('/api/laser-welding/bom-customers');
      _bomCustomers = custData.customers || [];
    } catch (err) {
      console.error('Failed to load BOM customers', err);
      _bomCustomers = [];
    }
    try {
      const bomUrl = isReworkWeldingMode()
        ? '/api/laser-welding/assembly/rework/boms'
        : '/api/laser-welding/boms';
      const bomData = await apiFetch(bomUrl);
      _boms = bomData.boms || [];
    } catch (err) {
      console.error('Failed to load BOMs', err);
      _boms = [];
      showSnackbar(err.message || 'Failed to load BOM list', 'error');
    }
  }

  async function loadAssemblyRows(preserveFilter) {
    if (_tab !== 'final_assembly') return;
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
      const data = await apiFetch(rowsUrl + encodeURIComponent(_workDate));
      _asmRows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || (r.draftLineId
          ? `draft:${r.batchMode || 'assembly'}:${r.draftLineId}`
          : (isReworkWeldingMode() ? `rweld:lot:${r.lotId}` : `asm:${r.lotId}`)),
        lines: r.lines || [],
      }));
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
        r.customerName,
        r.partNumber,
        r.subAssemblyPartNo,
        r.partName,
        r.productName,
        r.operatorName,
        r.newLotNo,
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
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(row.customerName || '')}">${escapeHtml(row.customerName || '—')}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber || '—')}</td>
      <td class="lw-col-part" title="${escapeAttr(saPart)}">${escapeHtml(saPart)}</td>
      <td class="lw-col-operator" title="${escapeAttr(row.operatorName || '')}">${escapeHtml(row.operatorName || '—')}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-actions lw-actions-cell">${buildAsmActionsHtml(row, isReworkSubAssemblyMode())}</td>
    `;
    return tr;
  }

  function buildSaDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;
    const td = document.createElement('td');
    td.colSpan = 6;
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
    const ids = new Set(
      _saPartsList.map(p => Number(p.custId)).filter(id => Number.isFinite(id) && id > 0),
    );
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
    if (!canEdit() || _tab !== 'sub_assembly') return;
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
      <td class="lw-col-lot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const custSel = tr.querySelector('.lw-sa-new-customer');
    const bomSel = tr.querySelector('.lw-sa-new-bom');
    const partSel = tr.querySelector('.lw-sa-new-part');
    const opSel = tr.querySelector('.lw-sa-new-operator');

    custSel?.addEventListener('change', () => refreshSaNewRowFilters(tr));
    bomSel?.addEventListener('change', () => refreshSaNewRowPartSelect(tr));
    partSel?.addEventListener('change', () => tryCommitSaNewRow(partSel, opSel));
    opSel?.addEventListener('change', () => tryCommitSaNewRow(partSel, opSel));
  }

  async function tryCommitSaNewRow(partSel, opSel) {
    const { bomId, partNo: saPart } = parseSaPartOptionValue(partSel?.value);
    const operatorId = parseInt(opSel?.value, 10);
    if (!bomId || !saPart || !operatorId) return;

    try {
      const pendingUrl = isReworkSubAssemblyMode()
        ? '/api/laser-welding/sub-assembly/rework/pending'
        : '/api/laser-welding/sub-assembly/pending';
      await apiPost(pendingUrl, {
        bomId,
        subAssemblyPartNo: saPart,
        operatorId,
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
      if (_saExpanded[row.rowKey]) {
        tbody.appendChild(buildSaDetailRow(row));
      }
    });
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
    if (_tab !== 'sub_assembly') return;
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
      const data = await apiFetch(rowsUrl + encodeURIComponent(_workDate));
      _saRows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || (r.draftLineId
          ? `draft:${r.batchMode || 'sub_assembly'}:${r.draftLineId}`
          : (isReworkSubAssemblyMode() ? `sa-rw:lot:${r.lotId}` : `sa:${r.lotId}`)),
        lines: r.lines || [],
      }));
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

  async function fetchReworkTargetLots(bomId, subAssemblyPartNo) {
    const bid = bomIdKey(bomId);
    if (!bid) return [];
    const saPart = String(subAssemblyPartNo || '').trim();
    const cacheKey = _weldModalContext === 'sub_assembly'
      ? `${bid}:${saPart || 'all'}`
      : bid;
    let url = _weldModalContext === 'sub_assembly'
      ? '/api/laser-welding/sub-assembly/rework/target-lots?bomId=' + encodeURIComponent(bid)
      : '/api/laser-welding/assembly/rework/target-lots?bomId=' + encodeURIComponent(bid);
    if (_weldModalContext === 'sub_assembly' && saPart) {
      url += '&subAssemblyPartNo=' + encodeURIComponent(saPart);
    }
    const data = await apiFetch(url);
    _reworkTargetLotsCache[cacheKey] = data.lots || [];
    return _reworkTargetLotsCache[cacheKey];
  }

  function updateWeldModalChrome() {
    const isRw = isWeldReworkMode();
    const isSa = _weldModalContext === 'sub_assembly';
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
    const machineWrap = $('#lw-weld-modal-machine-wrap');
    if (machineWrap) machineWrap.style.display = isSa ? 'none' : '';
  }

  function populateWeldTargetLotSelect(lots, selectedLotId) {
    const sel = $('#lw-weld-modal-target-lot');
    if (!sel) return;
    let html = '<option value="">Select lot…</option>';
    (lots || []).forEach(l => {
      const lid = Number(l.lotId);
      const selAttr = lid === Number(selectedLotId) ? ' selected' : '';
      html += `<option value="${lid}"${selAttr}>${escapeHtml(l.newLotNo)} (pending: ${l.reworkPending})</option>`;
    });
    sel.innerHTML = html;
  }

  function onWeldTargetLotChange() {
    const sel = $('#lw-weld-modal-target-lot');
    const lotId = parseInt(sel?.value, 10) || null;
    _weldModalTargetLotId = lotId;
    const lots = _reworkTargetLotsCache[bomIdKey(_weldModalBomId)] || [];
    const match = lots.find(l => Number(l.lotId) === lotId);
    const qtyInp = $('#lw-weld-modal-qty');
    if (qtyInp) {
      if (match) {
        qtyInp.max = String(match.reworkPending || 0);
      } else {
        qtyInp.removeAttribute('max');
      }
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
    return { childLotId: null, consumedQty: 0, qaQty: 0, scrapQty: 0 };
  }

  function weldRequiredForPart(ch, weldQty) {
    return (Number(ch.bomQty) || 0) * weldQty;
  }

  function weldWeldedTotal(ch) {
    return (ch.lines || []).reduce((sum, ln) => {
      const consumed = Number(ln.consumedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const scrap = Number(ln.scrapQty) || 0;
      if (ch.isBoPart) {
        return sum + Math.max(0, consumed - scrap);
      }
      return sum + Math.max(0, consumed - qa - scrap);
    }, 0);
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
    if (!isWeldLineEmpty(last)) {
      ch.lines.push(emptyWeldLine());
    }
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
    if (isWeldReworkMode()) {
      const removed = Math.max(0, consumed - qa - scrap);
      const removedCell = $(`.lw-weld-removed[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
      if (removedCell) removedCell.textContent = removed > 0 ? String(removed) : '—';
    }
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
    const strong = summary?.querySelector('strong');
    const reqStrong = block.querySelector('.lw-weld-part-req strong');
    if (reqStrong) reqStrong.textContent = String(required);
    if (strong) strong.textContent = String(weldedTotal);
    if (summary) {
      summary.classList.remove('lw-weld-part-welded--ok', 'lw-weld-part-welded--over');
      if (required > 0) {
        if (isWeldReworkMode()) {
          if (weldedTotal > 0 && weldedTotal <= required) {
            summary.classList.add('lw-weld-part-welded--ok');
          } else if (weldedTotal > required) {
            summary.classList.add('lw-weld-part-welded--over');
          }
        } else if (weldedTotal === required) {
          summary.classList.add('lw-weld-part-welded--ok');
        } else if (weldedTotal !== required) {
          summary.classList.add('lw-weld-part-welded--over');
        }
      }
    }
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
      if (!ch.lines?.length) ch.lines = [emptyWeldLine()];
      ensureWeldTrailingLine(ch);

      let weldedCls = '';
      if (required > 0) {
        if (isRw) {
          weldedCls = weldedTotal > 0 && weldedTotal <= required
            ? ' lw-weld-part-welded--ok'
            : (weldedTotal > required ? ' lw-weld-part-welded--over' : '');
        } else {
          weldedCls = weldedTotal === required
            ? ' lw-weld-part-welded--ok'
            : (weldedTotal !== required ? ' lw-weld-part-welded--over' : '');
        }
      }

      html += `<div class="lw-weld-part-block" data-part-idx="${partIdx}">`;
      html += '<div class="lw-weld-part-head">';
      html += `<span class="lw-weld-part-no" title="${escapeAttr(ch.partName || '')}">${escapeHtml(ch.partNo)}</span>`;
      if (ch.partName) {
        html += `<span class="lw-weld-part-name">${escapeHtml(ch.partName)}</span>`;
      }
      html += `<span class="lw-weld-part-req">Required: <strong>${required}</strong></span>`;
      html += `<span class="lw-weld-part-welded${weldedCls}">${totalLabel}: <strong>${weldedTotal}</strong></span>`;
      html += '</div>';

      html += '<table class="ti-table lw-weld-part-table"><thead><tr>';
      html += '<th>Child Lot</th><th class="text-right">Consumed</th>';
      if (!ch.isBoPart) html += '<th class="text-right">QA</th>';
      html += '<th class="text-right">Scrap</th>';
      if (isRw) html += '<th class="text-right">Removed</th>';
      html += '<th></th>';
      html += '</tr></thead><tbody>';

      ch.lines.forEach((ln, lineIdx) => {
        const usedLots = weldLotsUsedInPart(ch, lineIdx);
        const isTrailing = lineIdx === ch.lines.length - 1 && isWeldLineEmpty(ln);
        const consumed = Number(ln.consumedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
        const removed = ch.isBoPart
          ? Math.max(0, consumed - scrap)
          : Math.max(0, consumed - qa - scrap);
        const scrapMax = ch.isBoPart ? consumed : Math.max(0, consumed - qa);

        html += '<tr>';
        html += `<td><select class="ti-input lw-weld-child-lot" data-part-idx="${partIdx}" data-line-idx="${lineIdx}">`;
        html += '<option value="">Select lot…</option>';
        (ch.lots || []).forEach(l => {
          const lid = Number(l.lotId);
          if (usedLots.has(lid) && Number(ln.childLotId) !== lid) return;
          const sel = Number(ln.childLotId) === lid ? ' selected' : '';
          html += `<option value="${l.lotId}"${sel}>${escapeHtml(l.newLotNo)} (ok: ${l.totalOkayed})</option>`;
        });
        html += '</select></td>';
        html += `<td class="text-right"><input type="number" class="ti-input lw-weld-consumed" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" value="${consumed}" /></td>`;
        if (!ch.isBoPart) {
          html += `<td class="text-right"><input type="number" class="ti-input lw-weld-qa" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${consumed}" value="${qa}" /></td>`;
        }
        html += `<td class="text-right"><input type="number" class="ti-input lw-weld-scrap" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${scrapMax}" value="${scrap}" /></td>`;
        if (isRw) {
          html += `<td class="text-right lw-weld-removed" data-part-idx="${partIdx}" data-line-idx="${lineIdx}">${removed > 0 ? removed : '—'}</td>`;
        }
        if (!isTrailing) {
          html += `<td><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-weld-line-remove" data-part-idx="${partIdx}" data-line-idx="${lineIdx}">✕</button></td>`;
        } else {
          html += '<td></td>';
        }
        html += '</tr>';
      });

      html += '</tbody></table></div>';
    });
    body.innerHTML = html;
  }

  async function openWeldModal(row) {
    const overlay = $('#lw-weld-modal-overlay');
    if (!overlay || !row) return;
    _weldModalContext = _tab === 'sub_assembly' ? 'sub_assembly' : 'assembly';
    _weldModalDraftLineId = row.draftLineId || row.lineId || null;
    _weldModalBomId = row.bomId;
    _weldModalOperatorId = row.operatorId || null;
    _weldModalSubAssemblyPartNo = row.subAssemblyPartNo || null;
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
  }

  async function saveWeldModal() {
    const draftLineId = _weldModalDraftLineId;
    if (!draftLineId) {
      showSnackbar('Pending assembly row not found', 'warning');
      return;
    }
    const isRw = isWeldReworkMode();
    const isSa = isSubAssemblyWeldContext();
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
      const cacheKey = _weldModalContext === 'sub_assembly'
        ? `${bomIdKey(_weldModalBomId)}:${_weldModalSubAssemblyPartNo || 'all'}`
        : bomIdKey(_weldModalBomId);
      const lots = _reworkTargetLotsCache[cacheKey] || [];
      const match = lots.find(l => Number(l.lotId) === targetLotId);
      const pending = Number(match?.reworkPending) || 0;
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
    for (const ch of _weldModalChildren) {
      const required = weldRequiredForPart(ch, weldQty);
      let partWelded = 0;
      const seenLots = new Set();
      for (const ln of ch.lines || []) {
        const consumed = Number(ln.consumedQty) || 0;
        let qa = Number(ln.qaQty) || 0;
        const scrap = Number(ln.scrapQty) || 0;
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
        const welded = ch.isBoPart
          ? consumed - scrap
          : consumed - qa - scrap;
        partWelded += welded;
        consumptions.push({
          partNumber: ch.partNo,
          childLotId: ln.childLotId,
          consumedQty: consumed,
          qaQty: qa,
          scrapQty: scrap,
        });
      }
      if (isRw) {
        if (partWelded > required) {
          showSnackbar(
            `${completeTotalLabel(isSa)} total for ${ch.partNo} cannot exceed ${required} (BOM × re-work qty), got ${partWelded}`,
            'error'
          );
          return;
        }
      } else if (partWelded !== required) {
        const qtyWord = isSa ? 'assembly' : 'weld';
        showSnackbar(
          `${completeTotalLabel(isSa)} total for ${ch.partNo} must be ${required} (BOM × ${qtyWord} qty), got ${partWelded}`,
          'error'
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
        });
        showSnackbar(`${completeActionLabel(false, isSa)} — Lot No: ${data.newLotNo || ''}`, 'success');
      }
      closeWeldModal();
      invalidateLwCaches();
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
        'consumed'
      );
      return;
    }
    const qaInp = e.target.closest('.lw-weld-qa');
    if (qaInp) {
      syncWeldLineQtyCaps(
        Number(qaInp.getAttribute('data-part-idx')),
        Number(qaInp.getAttribute('data-line-idx')),
        'qa'
      );
      return;
    }
    const scrapInp = e.target.closest('.lw-weld-scrap');
    if (scrapInp) {
      syncWeldLineQtyCaps(
        Number(scrapInp.getAttribute('data-part-idx')),
        Number(scrapInp.getAttribute('data-line-idx')),
        'scrap'
      );
    }
  }

  function showPanel(tab) {
    $$('.lw-panel').forEach(p => p.classList.remove('lw-panel--active'));
    const map = {
      child_parts: '#lw-child-panel',
      qa_disposition: '#lw-qa-panel',
      sub_assembly: '#lw-sub-assembly-panel',
      final_assembly: '#lw-assembly-panel',
      packing: '#lw-packing-panel',
    };
    $(map[tab] || '#lw-sub-assembly-panel')?.classList.add('lw-panel--active');

    const modeBar = $('#lw-mode-bar');
    const asmModeBar = $('#lw-asm-mode-bar');
    const saModeBar = $('#lw-sa-mode-bar');
    const tableWrap = $('#lw-table-wrap');
    const asmTableWrap = $('#lw-asm-table-wrap');
    const saTableWrap = $('#lw-sa-table-wrap');
    const search = $('#lw-grid-search');
    const dateInput = $('#lw-work-date');
    const showInspect = tab === 'child_parts';
    const showAssembly = tab === 'final_assembly';
    const showSubAssembly = tab === 'sub_assembly';
    const showGrid = showInspect || showAssembly || showSubAssembly;
    if (modeBar) modeBar.style.display = showInspect ? '' : 'none';
    if (asmModeBar) asmModeBar.style.display = showAssembly ? '' : 'none';
    if (saModeBar) saModeBar.style.display = showSubAssembly ? '' : 'none';
    if (tableWrap) tableWrap.style.display = showInspect ? '' : 'none';
    if (asmTableWrap) asmTableWrap.style.display = showAssembly ? '' : 'none';
    if (saTableWrap) saTableWrap.style.display = showSubAssembly ? '' : 'none';
    if (search) search.style.display = showGrid ? '' : 'none';
    if (dateInput) dateInput.style.display = (showInspect || showAssembly || showSubAssembly) ? '' : 'none';
    const dateLabel = $('.lw-date-label');
    if (dateLabel) dateLabel.style.display = (showInspect || showAssembly || showSubAssembly) ? '' : 'none';
  }

  function switchTab(tab) {
    _tab = tab;

    $$('.lw-tab').forEach(btn => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle('lw-tab--active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    showPanel(tab);
    const subtitle = $('#lw-subtitle');
    if (subtitle) {
      if (tab === 'final_assembly') {
        subtitle.textContent = isReworkWeldingMode()
          ? 'Laser Welding — re-work welding'
          : TAB_LABELS.final_assembly;
      } else if (tab === 'sub_assembly') {
        subtitle.textContent = isReworkSubAssemblyMode()
          ? 'Sub-Assembly — re-work sub-assembly'
          : TAB_LABELS.sub_assembly;
      } else {
        subtitle.textContent = TAB_LABELS[tab] || '';
      }
    }

    refreshActiveTab(false);
  }

  function onAsmTableClick(e) {
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
    if (inspectBtn && (_batchMode === 'production' || _batchMode === 'cleaning')) {
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
    const scrap = e.target.closest('.lw-prod-line-scrap');
    if (scrap) {
      syncProdLineQtyCaps(Number(scrap.getAttribute('data-idx')), 'scrap');
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
      if (_tab === 'final_assembly') renderAssemblyTable();
      else if (_tab === 'sub_assembly') renderSubAssemblyTable();
      else renderTable();
    });

    $('#lw-work-date')?.addEventListener('change', e => {
      _workDate = e.target.value || todayIso();
      refreshActiveTab(false);
    });

    $$('input[name="lw-batch-mode"]').forEach(radio => {
      radio.addEventListener('change', async e => {
        _batchMode = e.target.value || 'production';
        _expanded = {};
        updateModeChrome();
        await refreshActiveTab(true);
      });
    });

    $$('input[name="lw-asm-mode"]').forEach(radio => {
      radio.addEventListener('change', async e => {
        _asmMode = e.target.value || 'welding';
        _asmExpanded = {};
        _boms = [];
        invalidateLwCaches();
        const subtitle = $('#lw-subtitle');
        if (subtitle && _tab === 'final_assembly') {
          subtitle.textContent = isReworkWeldingMode()
            ? 'Laser Welding — re-work welding'
            : TAB_LABELS.final_assembly;
        }
        if (_tab === 'final_assembly') {
          await refreshActiveTab(true);
        }
      });
    });

    $$('input[name="lw-sa-mode"]').forEach(radio => {
      radio.addEventListener('change', async e => {
        _saMode = e.target.value || 'sub_assembly';
        _saExpanded = {};
        _saPartsList = [];
        invalidateLwCaches();
        const subtitle = $('#lw-subtitle');
        if (subtitle && _tab === 'sub_assembly') {
          subtitle.textContent = isReworkSubAssemblyMode()
            ? 'Sub-Assembly — re-work sub-assembly'
            : TAB_LABELS.sub_assembly;
        }
        if (_tab === 'sub_assembly') {
          await refreshActiveTab(true);
        }
      });
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

    $('#lw-weld-modal-cancel')?.addEventListener('click', closeWeldModal);
    $('#lw-weld-modal-save')?.addEventListener('click', saveWeldModal);
    $('#lw-weld-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-weld-modal-overlay') closeWeldModal();
    });
    $('#lw-weld-modal-qty')?.addEventListener('input', () => {
      renderWeldModalChildren();
    });
    $('#lw-weld-modal-target-lot')?.addEventListener('change', onWeldTargetLotChange);
    $('#lw-weld-modal-children')?.addEventListener('click', onWeldModalClick);
    $('#lw-weld-modal-children')?.addEventListener('change', onWeldModalChange);
    $('#lw-weld-modal-children')?.addEventListener('input', onWeldModalInput);

    $('#lw-qa-passed')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-scrap')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-rework')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-part')?.addEventListener('change', onQaPartChange);
    $('#lw-qa-lot')?.addEventListener('change', onQaLotChange);
    $('#lw-qa-approve')?.addEventListener('click', approveQa);

    $('#lw-qa-queue')?.addEventListener('click', e => {
      const item = e.target.closest('.lw-queue-item');
      if (!item) return;
      $('#lw-qa-part').value = item.getAttribute('data-part');
      onQaPartChange();
      $('#lw-qa-lot').value = item.getAttribute('data-lot-id');
      onQaLotChange();
    });

    $('#lw-packing-part')?.addEventListener('change', onPackingPartChange);
    $('#lw-packing-lot')?.addEventListener('change', onPackingLotChange);
    $('#lw-packing-qty')?.addEventListener('input', updatePackingPackState);
    $('#lw-packing-pack')?.addEventListener('click', packLot);

    $('#lw-packing-queue')?.addEventListener('click', e => {
      const item = e.target.closest('.lw-queue-item');
      if (!item) return;
      $('#lw-packing-part').value = item.getAttribute('data-part');
      onPackingPartChange();
      $('#lw-packing-lot').value = item.getAttribute('data-lot-id');
      onPackingLotChange();
    });
  }

  async function init() {
    invalidateLwCaches();
    _loadChildRowsPending = false;
    _workDate = todayIso();
    const dateInput = $('#lw-work-date');
    if (dateInput) dateInput.value = _workDate;

    bindEvents();
    await Promise.all([loadParts(), loadOperators(), loadMachines()]);
    switchTab('child_parts');
  }

  return { init, loadRows: loadChildRows };
})();
