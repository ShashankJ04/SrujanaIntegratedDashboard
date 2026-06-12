/* ═══════════════════════════════════════════════════════════════════════════
   LASER_WELDING.JS — Laser Welding (Child Parts, QA Disposition, Rework)
   ═══════════════════════════════════════════════════════════════════════════ */

window.LaserWeldingPage = (() => {
  const TAB_LABELS = {
    child_parts: 'Inspection — part inspection & cleaning',
    qa_disposition: 'QA Disposition — approve passed / scrap / rework',
    rework: 'Rework — inward full pending quantity',
    sub_assembly: 'Sub-Assembly — coming soon',
    final_assembly: 'Laser Welding — BOM assembly & weld',
  };

  let _tab = 'child_parts';
  let _workDate = '';
  let _batchMode = 'production';
  let _parts = [];
  let _operators = [];
  let _rows = [];
  let _expanded = {};
  let _sourceLotsCache = {};
  let _reworkLotsCache = {};
  let _childLotsCache = {};
  let _qaRows = [];
  let _reworkRows = [];
  let _asmRows = [];
  let _boms = [];
  let _bomCustomers = [];
  let _asmExpanded = {};
  let _filterQuery = '';
  let _loading = false;
  let _asmLoading = false;
  let _prodModalLines = [];
  let _prodModalLotId = null;
  let _reworkModalLines = [];
  let _storeModalLotId = null;
  let _storeModalPending = 0;
  let _cleanModalLotId = null;
  let _cleanModalUncleaned = 0;
  let _weldModalLotId = null;
  let _weldModalBomId = null;
  let _weldModalChildren = [];

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

  function partNoKey(part) {
    return String(part?.part_no || part?.partNo || '').trim().toLowerCase();
  }

  function partNameFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => partNoKey(x) === key);
    return p ? String(p.part_name || p.partName || '').trim() : '';
  }

  function isStorePart(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => partNoKey(x) === key);
    return !!(p && p.isStorePart);
  }

  function rowBatchMode(row) {
    return row.batchMode || _batchMode;
  }

  function rowMatchesMode(row) {
    return rowBatchMode(row) === _batchMode;
  }

  function emptyLine() {
    return { sourceLotNo: '', productionDate: '', noOfComp: 0, availableQty: 0, inspectedQty: 0, qaQty: 0 };
  }

  function lotAvailableQty(lot) {
    if (!lot) return 0;
    const avail = Number(lot.availableQty);
    if (Number.isFinite(avail) && avail > 0) return avail;
    return Number(lot.noOfComp) || 0;
  }

  function emptyReworkLine() {
    return { lotId: null, sourceLotNo: '', reworkPool: 0, inspectedQty: 0, qaQty: 0 };
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
        r.operatorName,
        r.newLotNo,
        r.workDate,
        isoToDisplayDate(r.workDate),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function findRow(rowKey) {
    return allDisplayRows().find(r => r.rowKey === rowKey);
  }

  function updateRowCount() {
    const el = $('#lw-item-count');
    if (!el) return;
    if (_tab === 'child_parts') {
      const n = filteredRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'final_assembly') {
      const n = filteredAsmRows().length;
      el.textContent = n === 1 ? '1 row' : `${n} rows`;
    } else if (_tab === 'qa_disposition') {
      el.textContent = `${_qaRows.length} pending`;
    } else if (_tab === 'rework') {
      el.textContent = `${_reworkRows.length} pending`;
    } else {
      el.textContent = '—';
    }
  }

  function updateTableHeader() {
    const head = $('#lw-table-head');
    if (!head) return;
    if (_batchMode === 'rework') {
      head.innerHTML = `
        <tr>
          <th class="lw-col-part">Part No</th>
          <th class="lw-col-name">Part Name</th>
          <th class="lw-col-lot">Lot No</th>
          <th class="lw-col-insp">Inspected</th>
          <th class="lw-col-qa">QA</th>
          <th class="lw-col-actions">Actions</th>
        </tr>`;
    } else if (_batchMode === 'cleaning') {
      head.innerHTML = `
        <tr>
          <th class="lw-col-bom">BOM No</th>
          <th class="lw-col-name">Product</th>
          <th class="lw-col-lot">Lot No</th>
          <th class="lw-col-insp">Uncleaned</th>
          <th class="lw-col-actions">Actions</th>
        </tr>`;
    } else {
      head.innerHTML = `
        <tr>
          <th class="lw-col-part">Part No</th>
          <th class="lw-col-name">Part Name</th>
          <th class="lw-col-operator">Operator</th>
          <th class="lw-col-lot">Lot No</th>
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

  function detailLinesHtml(row) {
    const lines = row.lines || [];
    let html = '';
    const timeStr = formatTimeTaken(row.timeTakenMinutes);
    if (timeStr) {
      html += `<div class="lw-detail-meta">Time taken: ${escapeHtml(timeStr)}</div>`;
    }
    html += '<table class="ti-table lw-detail-table"><thead><tr>';
    html += '<th>Lot No</th><th class="text-right">Available</th>';
    html += '<th class="text-right">Inspected QTY</th><th class="text-right">QA</th>';
    html += '</tr></thead><tbody>';

    if (!lines.length) {
      html += '<tr><td colspan="4" class="lw-detail-empty">No lot lines saved.</td></tr>';
    }

    lines.forEach(ln => {
      const insp = Number(ln.inspectedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const max = Number(ln.availableQty) || Number(ln.noOfComp) || 0;
      html += '<tr>';
      html += `<td>${escapeHtml(ln.sourceLotNo || '—')}</td>`;
      html += `<td class="text-right">${max || '—'}</td>`;
      html += `<td class="text-right">${insp > 0 ? insp : '—'}</td>`;
      html += `<td class="text-right">${qa > 0 ? qa : '—'}</td>`;
      html += '</tr>';
    });

    html += '</tbody></table>';
    return html;
  }

  function buildReworkActionsHtml(row) {
    const key = row.rowKey;
    if (!canEdit()) return '<span class="lw-view-only">View only</span>';
    if (!row.isDraft) return '';
    return (
      `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-edit-rework" data-row-key="${escapeAttr(key)}">Edit</button>` +
      `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-process" data-row-key="${escapeAttr(key)}">Inspect</button>`
    );
  }

  function buildReworkDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isReinspected ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;
    const partName = row.partName || partNameFor(row.partNumber);
    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-insp text-right">${Number(row.inspectedQty) || 0}</td>
      <td class="lw-col-qa text-right">${Number(row.qaQty) || 0}</td>
      <td class="lw-col-actions lw-actions-cell">${buildReworkActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildActionsHtml(row) {
    const key = row.rowKey;
    const expCls = _expanded[key] ? ' is-expanded' : '';

    if (_batchMode === 'cleaning') {
      if (!canEdit()) return '<span class="lw-view-only">View only</span>';
      return `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-clean" data-row-key="${escapeAttr(key)}">Cleaned</button>`;
    }

    if (row.isStorePart && Number(row.inspectionPending || row.inspectedQty) > 0) {
      if (!canEdit()) return '<span class="lw-view-only">View only</span>';
      return `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-store-inspect" data-row-key="${escapeAttr(key)}">Inspect</button>`;
    }

    if (row.isProcessed) {
      return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Lot lines">▤</button>`;
    }
    if (!canEdit()) return '<span class="lw-view-only">View only</span>';

    return `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-inspect" data-row-key="${escapeAttr(key)}">Inspect</button>`;
  }

  function buildDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;

    if (_batchMode === 'cleaning') {
      const product = row.productName || row.partName || row.partNumber;
      const uncleaned = Number(row.uncleanedQty) || 0;
      tr.innerHTML = `
        <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
        <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
        <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
        <td class="lw-col-insp text-right">${uncleaned}</td>
        <td class="lw-col-actions lw-actions-cell">${buildActionsHtml(row)}</td>
      `;
      return tr;
    }

    const partName = row.partName || partNameFor(row.partNumber);
    const operatorName = row.operatorName || '—';
    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
      <td class="lw-col-lot">${row.newLotNo ? `<span class="lw-lot-badge">${escapeHtml(row.newLotNo)}</span>` : '—'}</td>
      <td class="lw-col-actions lw-actions-cell">${buildActionsHtml(row)}</td>
    `;
    return tr;
  }

  function buildDetailRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-detail-row';
    tr.dataset.detailFor = row.rowKey;

    const td = document.createElement('td');
    td.colSpan = _batchMode === 'rework' ? 6 : (_batchMode === 'cleaning' ? 5 : 5);
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

  function appendNewRow(tbody) {
    if (!canEdit() || _tab !== 'child_parts' || _batchMode !== 'production') return;
    // Store assembly parts appear from backend rows — no empty-row create

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
      <td class="lw-col-lot">—</td>
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

  async function fetchSourceLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    if (_sourceLotsCache[pn]) return _sourceLotsCache[pn];
    const data = await apiFetch('/api/laser-welding/source-lots?partNo=' + encodeURIComponent(pn));
    _sourceLotsCache[pn] = data.lots || [];
    return _sourceLotsCache[pn];
  }

  async function fetchReworkLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    if (_reworkLotsCache[pn]) return _reworkLotsCache[pn];
    const data = await apiFetch('/api/laser-welding/rework-lots?partNo=' + encodeURIComponent(pn));
    _reworkLotsCache[pn] = data.lots || [];
    return _reworkLotsCache[pn];
  }

  function reworkDraftRowsForPart(partNumber) {
    const pn = String(partNumber || '').trim();
    return allDisplayRows().filter(r =>
      r.isDraft && String(r.partNumber || '').trim() === pn
    );
  }

  async function tryCommitNewRow(partInput, operatorSel) {
    const partNumber = (partInput?.value || '').trim();
    const operatorId = parseInt(operatorSel?.value, 10);
    if (!partNumber || !operatorId) return;

    const partMatch = _parts.find(p => partNoKey(p) === partNumber.toLowerCase());
    if (!partMatch) {
      showSnackbar('Part not found or has no FG lots with stock', 'error');
      return;
    }
    if (partMatch.isStorePart) {
      showSnackbar('Store assembly parts are inspected from existing lots — not added here', 'warning');
      return;
    }

    const lots = await fetchSourceLots(partNumber);
    if (!lots.length) {
      showSnackbar('No FG lots with stock for this part', 'warning');
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

  function appendReworkNewRow(tbody) {
    if (!canEdit() || _tab !== 'child_parts' || _batchMode !== 'rework') return;

    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-part lw-edit-cell">
        <input type="text" class="lw-cell-input lw-new-part"
               list="lw-parts-datalist" placeholder="Select part…" autocomplete="off" />
      </td>
      <td class="lw-col-name lw-new-part-name"></td>
      <td class="lw-col-lot">—</td>
      <td class="lw-col-insp text-right">—</td>
      <td class="lw-col-qa text-right">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const partInput = tr.querySelector('.lw-new-part');
    partInput?.addEventListener('input', () => {
      const nameEl = tr.querySelector('.lw-new-part-name');
      if (nameEl) nameEl.textContent = partNameFor(partInput.value) || '';
    });
    partInput?.addEventListener('change', () => tryCommitReworkNewRow(partInput));
    partInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        tryCommitReworkNewRow(partInput);
      }
    });
  }

  async function tryCommitReworkNewRow(partInput) {
    const partNumber = (partInput?.value || '').trim();
    if (!partNumber) return;

    const validPart = _parts.some(p => partNoKey(p) === partNumber.toLowerCase());
    if (!validPart) {
      showSnackbar('Part has no rework pool lots', 'error');
      return;
    }

    const lots = await fetchReworkLots(partNumber);
    if (!lots.length) {
      showSnackbar('No rework pool available for this part', 'warning');
      return;
    }

    partInput.value = '';
    const nameEl = partInput.closest('tr')?.querySelector('.lw-new-part-name');
    if (nameEl) nameEl.textContent = '';

    openReworkModal({ partNumber, partName: partNameFor(partNumber) });
  }

  function renderTable() {
    const tbody = $('#lw-table-body');
    if (!tbody) return;

    updateTableHeader();
    updateModeChrome();
    tbody.innerHTML = '';

    if (_batchMode === 'rework') {
      filteredRows().forEach(row => tbody.appendChild(buildReworkDataRow(row)));
      appendReworkNewRow(tbody);
    } else if (_batchMode === 'cleaning') {
      filteredRows().forEach(row => tbody.appendChild(buildDataRow(row)));
    } else {
      filteredRows().forEach(row => {
        tbody.appendChild(buildDataRow(row));
        if (_expanded[row.rowKey]) {
          tbody.appendChild(buildDetailRow(row));
        }
      });
      appendNewRow(tbody);
    }
    updateRowCount();
  }

  function prodLotOptionsHtml(partNo, selectedLot, usedLots) {
    const lots = _sourceLotsCache[partNo] || [];
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
    return !ln?.sourceLotNo && Number(ln?.inspectedQty) <= 0 && Number(ln?.qaQty) <= 0;
  }

  function ensureProdModalTrailingLine() {
    const last = _prodModalLines[_prodModalLines.length - 1];
    if (!last || last.sourceLotNo) {
      _prodModalLines.push(emptyLine());
    }
  }

  function renderProductionModalLines() {
    const body = $('#lw-prod-modal-lines');
    if (!body) return;

    ensureProdModalTrailingLine();

    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const usedLots = new Set(_prodModalLines.map(l => l.sourceLotNo).filter(Boolean));

    let html = '<table class="ti-table lw-prod-modal-table"><thead><tr>';
    html += '<th>Lot No</th><th>Date</th><th class="text-right">Available</th>';
    html += '<th class="text-right">Inspected</th><th class="text-right">QA</th><th></th>';
    html += '</tr></thead><tbody>';

    _prodModalLines.forEach((ln, idx) => {
      const max = lotAvailableQty(ln);
      const insp = Number(ln.inspectedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const isTrailingEmpty = idx === _prodModalLines.length - 1 && isModalLineEmpty(ln);
      html += '<tr>';
      html += `<td><select class="ti-input lw-prod-line-lot" data-idx="${idx}">`;
      html += prodLotOptionsHtml(partNo, ln.sourceLotNo, usedLots);
      html += '</select></td>';
      html += `<td class="lw-prod-line-date" data-idx="${idx}">${escapeHtml(ln.productionDate || '—')}</td>`;
      html += `<td class="text-right lw-prod-line-comp" data-idx="${idx}">${max || '—'}</td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-insp" data-idx="${idx}" min="0" max="${max}" value="${insp}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-prod-line-qa" data-idx="${idx}" min="0" max="${insp || max}" value="${qa}" /></td>`;
      if (!isTrailingEmpty) {
        html += `<td><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-prod-line-remove" data-idx="${idx}">✕</button></td>`;
      } else {
        html += '<td></td>';
      }
      html += '</tr>';
    });

    html += '</tbody></table>';
    body.innerHTML = html;
  }

  async function openProductionModal(row) {
    const overlay = $('#lw-production-modal-overlay');
    if (!overlay) return;

    const partNo = row?.partNumber || '';
    const title = $('#lw-production-modal-title');
    const partEl = $('#lw-prod-modal-part');
    const operatorEl = $('#lw-prod-modal-operator');
    _prodModalLotId = row?.lotId || null;

    if (title) title.textContent = 'Part Inspection';
    if (partEl) {
      partEl.textContent = partNo ? `${partNo} — ${row.partName || partNameFor(partNo)}` : '—';
      partEl.dataset.partNumber = partNo;
    }
    if (operatorEl) {
      operatorEl.textContent = row?.operatorName || '—';
    }
    const hoursInp = $('#lw-prod-modal-hours');
    const minsInp = $('#lw-prod-modal-mins');
    if (hoursInp) hoursInp.value = '0';
    if (minsInp) minsInp.value = '0';

    await fetchSourceLots(partNo);
    _prodModalLines = [emptyLine()];

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
    _prodModalLotId = null;
  }

  function collectProductionModalLines() {
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const lots = _sourceLotsCache[partNo] || [];
    const lines = [];

    $$('.lw-prod-line-lot').forEach(sel => {
      const idx = Number(sel.getAttribute('data-idx'));
      const lotNo = sel.value || '';
      const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
      const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
      let insp = parseInt(inspInp?.value, 10) || 0;
      let qa = parseInt(qaInp?.value, 10) || 0;
      const match = lots.find(l => l.lotNo === lotNo);
      const max = lotAvailableQty(match);

      if (qa > insp) throw new Error(`QA cannot exceed Inspected QTY for lot ${lotNo}`);
      if (insp > max && max > 0) throw new Error(`Inspected QTY cannot exceed available stock (${max}) for lot ${lotNo}`);

      if (lotNo || insp > 0 || qa > 0) {
        if (!lotNo) throw new Error('Select a lot number for lines with quantity');
        lines.push({
          sourceLotNo: lotNo,
          productionDate: match?.productionDate || '',
          noOfComp: max,
          availableQty: max,
          inspectedQty: insp,
          qaQty: qa,
        });
      }
    });
    return lines;
  }

  async function saveProductionModal() {
    const lotId = _prodModalLotId;
    if (!lotId) {
      showSnackbar('Pending lot not found', 'warning');
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

    try {
      const data = await apiPost('/api/laser-welding/child-parts/inspect', {
        lotId,
        workDate: _workDate,
        lines,
        timeTakenMinutes,
      });
      showSnackbar(`Inspected — Lot No: ${data.newLotNo || ''}`, 'success');
      closeProductionModal();
      _sourceLotsCache = {};
      await loadChildRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Inspect failed', 'error');
    }
  }

  function onProductionModalLotChange(sel) {
    const idx = Number(sel.getAttribute('data-idx'));
    const partNo = $('#lw-prod-modal-part')?.dataset.partNumber || '';
    const lotNo = sel.value;
    const match = (_sourceLotsCache[partNo] || []).find(l => l.lotNo === lotNo);

    if (!_prodModalLines[idx]) _prodModalLines[idx] = emptyLine();
    _prodModalLines[idx].sourceLotNo = lotNo;
    if (match) {
      const avail = lotAvailableQty(match);
      _prodModalLines[idx].productionDate = match.productionDate || '';
      _prodModalLines[idx].noOfComp = avail;
      _prodModalLines[idx].availableQty = avail;
    }

    const dateEl = $(`.lw-prod-line-date[data-idx="${idx}"]`);
    const compEl = $(`.lw-prod-line-comp[data-idx="${idx}"]`);
    const inspInp = $(`.lw-prod-line-insp[data-idx="${idx}"]`);
    if (dateEl) dateEl.textContent = _prodModalLines[idx].productionDate || '—';
    if (compEl) compEl.textContent = String(_prodModalLines[idx].noOfComp || '—');
    if (inspInp) inspInp.max = String(_prodModalLines[idx].noOfComp || 0);

    if (lotNo && idx === _prodModalLines.length - 1) {
      renderProductionModalLines();
    }
  }

  function findReworkDraftRow(partNumber, lotId) {
    return _rows.find(r =>
      r.isDraft
      && String(r.partNumber || '').trim() === String(partNumber || '').trim()
      && Number(r.lotId) === Number(lotId)
    );
  }

  function isReworkModalLineEmpty(ln) {
    return !ln?.lotId && Number(ln?.inspectedQty) <= 0 && Number(ln?.qaQty) <= 0;
  }

  function ensureReworkModalTrailingLine() {
    const last = _reworkModalLines[_reworkModalLines.length - 1];
    if (!last || last.lotId) {
      _reworkModalLines.push(emptyReworkLine());
    }
  }

  function reworkLotOptionsHtml(partNo, selectedLotId, usedLotIds) {
    const lots = _reworkLotsCache[partNo] || [];
    let html = '<option value="">Select lot…</option>';
    lots.forEach(l => {
      const lotId = Number(l.lotId);
      if (!lotId) return;
      if (usedLotIds.has(lotId) && lotId !== Number(selectedLotId)) return;
      const sel = lotId === Number(selectedLotId) ? ' selected' : '';
      const label = `${l.newLotNo} (pool: ${l.reworkPool})`;
      html += `<option value="${lotId}"${sel}>${escapeHtml(label)}</option>`;
    });
    return html;
  }

  function renderReworkModalLines() {
    const body = $('#lw-rework-modal-lines');
    if (!body) return;

    ensureReworkModalTrailingLine();

    const partNo = $('#lw-rework-modal-part')?.dataset.partNumber || '';
    const usedLotIds = new Set(_reworkModalLines.map(l => Number(l.lotId)).filter(Boolean));

    let html = '<table class="ti-table lw-prod-modal-table lw-rework-modal-table"><thead><tr>';
    html += '<th>LW Lot</th><th class="text-right">Pool QTY</th>';
    html += '<th class="text-right">Inspected</th><th class="text-right">QA</th><th></th>';
    html += '</tr></thead><tbody>';

    _reworkModalLines.forEach((ln, idx) => {
      const pool = Number(ln.reworkPool) || 0;
      const insp = Number(ln.inspectedQty) || 0;
      const qa = Number(ln.qaQty) || 0;
      const isTrailingEmpty = idx === _reworkModalLines.length - 1 && isReworkModalLineEmpty(ln);
      html += '<tr>';
      html += `<td><select class="ti-input lw-rework-line-lot" data-idx="${idx}">`;
      html += reworkLotOptionsHtml(partNo, ln.lotId, usedLotIds);
      html += '</select></td>';
      html += `<td class="text-right lw-rework-line-pool" data-idx="${idx}">${pool || '—'}</td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-rework-line-insp" data-idx="${idx}" min="0" max="${pool}" value="${insp}" /></td>`;
      html += `<td class="text-right"><input type="number" class="ti-input lw-rework-line-qa" data-idx="${idx}" min="0" max="${insp || pool}" value="${qa}" /></td>`;
      if (!isTrailingEmpty) {
        html += `<td><button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-rework-line-remove" data-idx="${idx}">✕</button></td>`;
      } else {
        html += '<td></td>';
      }
      html += '</tr>';
    });

    html += '</tbody></table>';
    body.innerHTML = html;
  }

  async function openReworkModal(row) {
    const overlay = $('#lw-rework-modal-overlay');
    if (!overlay) return;

    const partNo = row?.partNumber || '';
    const title = $('#lw-rework-modal-title');
    const partEl = $('#lw-rework-modal-part');
    const drafts = partNo ? reworkDraftRowsForPart(partNo) : [];

    if (title) {
      title.textContent = drafts.length ? 'Edit Rework Inspect' : 'Add Rework Inspect';
    }
    if (partEl) {
      partEl.textContent = partNo ? `${partNo} — ${row?.partName || partNameFor(partNo)}` : '—';
      partEl.dataset.partNumber = partNo;
    }

    if (partNo) await fetchReworkLots(partNo);
    const lots = _reworkLotsCache[partNo] || [];

    _reworkModalLines = drafts.map(d => {
      const match = lots.find(l => Number(l.lotId) === Number(d.lotId));
      return {
        lotId: d.lotId,
        sourceLotNo: d.newLotNo || match?.newLotNo || '',
        reworkPool: d.reworkPool ?? match?.reworkPool ?? 0,
        inspectedQty: d.inspectedQty || 0,
        qaQty: d.qaQty || 0,
      };
    });
    if (!_reworkModalLines.length) {
      _reworkModalLines.push(emptyReworkLine());
    } else {
      ensureReworkModalTrailingLine();
    }

    renderReworkModalLines();
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeReworkModal() {
    const overlay = $('#lw-rework-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _reworkModalLines = [];
  }

  function onReworkModalLotChange(sel) {
    const idx = Number(sel.getAttribute('data-idx'));
    const partNo = $('#lw-rework-modal-part')?.dataset.partNumber || '';
    const lotId = parseInt(sel.value, 10) || null;
    const lots = _reworkLotsCache[partNo] || [];
    const match = lots.find(l => Number(l.lotId) === lotId);

    if (!_reworkModalLines[idx]) _reworkModalLines[idx] = emptyReworkLine();
    _reworkModalLines[idx].lotId = lotId;
    if (match) {
      _reworkModalLines[idx].sourceLotNo = match.newLotNo || '';
      _reworkModalLines[idx].reworkPool = match.reworkPool || 0;
    }

    const draft = lotId ? findReworkDraftRow(partNo, lotId) : null;
    if (draft) {
      _reworkModalLines[idx].inspectedQty = draft.inspectedQty || 0;
      _reworkModalLines[idx].qaQty = draft.qaQty || 0;
    } else if (!_reworkModalLines[idx].inspectedQty && !_reworkModalLines[idx].qaQty) {
      _reworkModalLines[idx].inspectedQty = 0;
      _reworkModalLines[idx].qaQty = 0;
    }

    const poolEl = $(`.lw-rework-line-pool[data-idx="${idx}"]`);
    const inspInp = $(`.lw-rework-line-insp[data-idx="${idx}"]`);
    const qaInp = $(`.lw-rework-line-qa[data-idx="${idx}"]`);
    const pool = _reworkModalLines[idx].reworkPool || 0;
    if (poolEl) poolEl.textContent = pool || '—';
    if (inspInp) {
      inspInp.max = String(pool);
      inspInp.value = String(_reworkModalLines[idx].inspectedQty || 0);
    }
    if (qaInp) {
      qaInp.max = String(_reworkModalLines[idx].inspectedQty || pool);
      qaInp.value = String(_reworkModalLines[idx].qaQty || 0);
    }

    if (lotId && idx === _reworkModalLines.length - 1) {
      renderReworkModalLines();
    }
  }

  function collectReworkModalLines() {
    const partNo = $('#lw-rework-modal-part')?.dataset.partNumber || '';
    const lots = _reworkLotsCache[partNo] || [];
    const lines = [];

    $$('.lw-rework-line-lot').forEach(sel => {
      const idx = Number(sel.getAttribute('data-idx'));
      const lotId = parseInt(sel.value, 10) || null;
      const inspInp = $(`.lw-rework-line-insp[data-idx="${idx}"]`);
      const qaInp = $(`.lw-rework-line-qa[data-idx="${idx}"]`);
      let insp = parseInt(inspInp?.value, 10) || 0;
      let qa = parseInt(qaInp?.value, 10) || 0;
      const match = lots.find(l => Number(l.lotId) === lotId);
      const pool = match?.reworkPool || 0;
      const newLotNo = match?.newLotNo || '';

      if (qa > insp) throw new Error(`QA cannot exceed Inspected QTY for lot ${newLotNo || lotId}`);
      if (insp > pool) throw new Error(`Inspected QTY cannot exceed rework pool for lot ${newLotNo || lotId}`);

      if (lotId || insp > 0 || qa > 0) {
        if (!lotId) throw new Error('Select an LW lot for lines with quantity');
        lines.push({
          lotId,
          sourceLotNo: newLotNo,
          reworkPool: pool,
          inspectedQty: insp,
          qaQty: qa,
        });
      }
    });
    return lines;
  }

  async function saveReworkModal() {
    const partNumber = $('#lw-rework-modal-part')?.dataset.partNumber || '';
    if (!partNumber) {
      showSnackbar('Part number is required', 'warning');
      return;
    }

    let lines;
    try {
      lines = collectReworkModalLines();
    } catch (err) {
      showSnackbar(err.message, 'error');
      return;
    }

    const previousDrafts = reworkDraftRowsForPart(partNumber);
    const keptLotIds = new Set(lines.map(l => Number(l.lotId)));
    const hasPositiveQty = lines.some(l => Number(l.inspectedQty) > 0);

    if (!hasPositiveQty && !previousDrafts.length) {
      showSnackbar('Enter Inspected QTY (greater than 0) for at least one lot', 'warning');
      return;
    }

    try {
      for (const draft of previousDrafts) {
        if (!keptLotIds.has(Number(draft.lotId))) {
          await apiPost('/api/laser-welding/child-parts/save', {
            partNumber,
            workDate: _workDate,
            batchMode: 'rework',
            lotId: draft.lotId,
            lines: [{
              sourceLotNo: draft.newLotNo || '',
              inspectedQty: 0,
              qaQty: 0,
            }],
          });
        }
      }

      for (const line of lines) {
        await apiPost('/api/laser-welding/child-parts/save', {
          partNumber,
          workDate: _workDate,
          batchMode: 'rework',
          lotId: line.lotId,
          lines: [{
            sourceLotNo: line.sourceLotNo,
            noOfComp: line.reworkPool,
            inspectedQty: line.inspectedQty,
            qaQty: line.qaQty,
          }],
        });
      }

      showSnackbar('Saved successfully', 'success');
      closeReworkModal();
      _reworkLotsCache = {};
      await loadChildRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Save failed', 'error');
    }
  }

  async function processReworkRow(rowKey) {
    const row = findRow(rowKey);
    if (!row || !row.isDraft) return;

    if (!row.lotId || !row.lineId) {
      showSnackbar('Save rework entry before re-inspect', 'warning');
      return;
    }
    if (!confirm('Re-inspect this rework batch on the same LW lot?')) return;

    try {
      await apiPost('/api/laser-welding/child-parts/reinspect', {
        lotId: row.lotId,
        workDate: row.workDate || _workDate,
        lineId: row.lineId,
      });
      showSnackbar('Re-inspected successfully', 'success');
      _reworkLotsCache = {};
      await loadChildRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Re-inspect failed', 'error');
      await loadChildRows(true);
    }
  }

  async function processRow(rowKey) {
    if (_batchMode === 'rework') {
      await processReworkRow(rowKey);
    }
  }

  async function loadChildRows(preserveFilter) {
    if (_tab !== 'child_parts') return;

    const loadingEl = $('#lw-loading');
    const errorEl = $('#lw-error');
    if (_loading) return;
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

  async function loadParts() {
    try {
      await refreshPartsDatalist();
      populateQaPartSelect();
      populateReworkPartSelect();
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
    populateSelect(sel, partsInQa.map(pn => ({ pn, name: partNameFor(pn) })), 'pn', it => `${it.pn} — ${it.name || ''}`, 'Select part…');
  }

  function populateQaLotSelect(partNo) {
    const sel = $('#lw-qa-lot');
    const lots = _qaRows.filter(r => r.partNumber === partNo);
    populateSelect(sel, lots, 'lotId', r => `${r.newLotNo} (QA: ${r.totalQa})`, 'Select lot…');
  }

  function populateReworkPartSelect() {
    const partsInRw = [...new Set(_reworkRows.map(r => r.partNumber))];
    const sel = $('#lw-rework-part');
    populateSelect(sel, partsInRw.map(pn => ({ pn, name: partNameFor(pn) })), 'pn', it => `${it.pn} — ${it.name || ''}`, 'Select part…');
  }

  function populateReworkLotSelect(partNo) {
    const sel = $('#lw-rework-lot');
    const lots = _reworkRows.filter(r => r.partNumber === partNo);
    populateSelect(sel, lots, 'lotId', r => `${r.newLotNo} (pending: ${r.reworkPending})`, 'Select lot…');
  }

  function renderQaQueue() {
    const el = $('#lw-qa-queue');
    if (!el) return;
    if (!_qaRows.length) {
      el.innerHTML = '<p class="lw-queue-empty">No lots pending QA disposition.</p>';
      return;
    }
    el.innerHTML = _qaRows.map(r =>
      `<button type="button" class="lw-queue-item" data-part="${escapeAttr(r.partNumber)}" data-lot-id="${r.lotId}">` +
      `${escapeHtml(r.partNumber)} · ${escapeHtml(r.newLotNo || '—')} · QA ${r.totalQa}` +
      '</button>'
    ).join('');
  }

  function renderReworkQueue() {
    const el = $('#lw-rework-queue');
    if (!el) return;
    if (!_reworkRows.length) {
      el.innerHTML = '<p class="lw-queue-empty">No lots pending rework inward.</p>';
      return;
    }
    el.innerHTML = _reworkRows.map(r =>
      `<button type="button" class="lw-queue-item" data-part="${escapeAttr(r.partNumber)}" data-lot-id="${r.lotId}">` +
      `${escapeHtml(r.partNumber)} · ${escapeHtml(r.newLotNo || '—')} · pending ${r.reworkPending}` +
      '</button>'
    ).join('');
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

  function resetReworkForm() {
    const partSel = $('#lw-rework-part');
    const lotSel = $('#lw-rework-lot');
    if (partSel) partSel.value = '';
    if (lotSel) lotSel.innerHTML = '<option value="">Select lot…</option>';
    $('#lw-rework-pending-display').textContent = '—';
    const btn = $('#lw-rework-inward');
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
    if (!lot || !canEdit() || lot.isQaApproved) {
      btn.disabled = true;
      if (hint) hint.textContent = 'Select a lot to see remaining QA quantity.';
      return;
    }
    const total = Number(lot.totalQa) || 0;
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

  function updateReworkInwardState() {
    const lotId = parseInt($('#lw-rework-lot')?.value, 10);
    const lot = _reworkRows.find(r => Number(r.lotId) === lotId);
    const btn = $('#lw-rework-inward');
    const pending = Number(lot?.reworkPending) || 0;
    if (!btn) return;
    if (!lot || !canEdit()) {
      btn.disabled = true;
      return;
    }
    btn.disabled = pending <= 0;
  }

  function onReworkPartChange() {
    const partNo = $('#lw-rework-part')?.value || '';
    populateReworkLotSelect(partNo);
    $('#lw-rework-pending-display').textContent = '—';
    updateReworkInwardState();
  }

  function onReworkLotChange() {
    const lotId = parseInt($('#lw-rework-lot')?.value, 10);
    const lot = _reworkRows.find(r => Number(r.lotId) === lotId);
    const pendingEl = $('#lw-rework-pending-display');
    if (!lot) {
      pendingEl.textContent = '—';
      updateReworkInwardState();
      return;
    }
    pendingEl.textContent = String(lot.reworkPending || 0);
    updateReworkInwardState();
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

  async function loadReworkRows() {
    const loadingEl = $('#lw-rework-loading');
    const errorEl = $('#lw-rework-error');
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      const data = await apiFetch('/api/laser-welding/rework/rows');
      _reworkRows = data.rows || [];
      populateReworkPartSelect();
      renderReworkQueue();
      updateRowCount();
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || 'Failed to load rework rows';
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
      _reworkLotsCache = {};
    } catch (err) {
      showSnackbar(err.message || 'Approve failed', 'error');
    }
  }

  async function inwardRework() {
    const lotId = parseInt($('#lw-rework-lot')?.value, 10);
    const lot = _reworkRows.find(r => Number(r.lotId) === lotId);
    if (!lotId || !lot) {
      showSnackbar('Select a lot first', 'warning');
      return;
    }
    const pending = Number(lot.reworkPending) || 0;
    if (pending <= 0) {
      showSnackbar('No pending rework to inward', 'warning');
      return;
    }
    if (!confirm(`Inward all ${pending} pending rework units?`)) return;

    try {
      await apiPost('/api/laser-welding/rework/inward', { lotId });
      showSnackbar(`Rework inwarded (${pending} units)`, 'success');
      resetReworkForm();
      await loadReworkRows();
      _reworkLotsCache = {};
      await loadParts();
    } catch (err) {
      showSnackbar(err.message || 'Inward failed', 'error');
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
    html += '<th>Child Part</th><th>Child Lot</th><th class="text-right">Used</th><th class="text-right">QA</th>';
    html += '</tr></thead><tbody>';
    if (!lines.length) {
      html += '<tr><td colspan="4" class="lw-detail-empty">No consumption lines.</td></tr>';
    }
    lines.forEach(ln => {
      html += '<tr>';
      html += `<td>${escapeHtml(ln.partNumber || '—')}</td>`;
      html += `<td>${escapeHtml(ln.sourceLotNo || '—')}</td>`;
      html += `<td class="text-right">${Number(ln.inspectedQty) || 0}</td>`;
      html += `<td class="text-right">${Number(ln.qaQty) || 0}</td>`;
      html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
  }

  function buildAsmActionsHtml(row) {
    const key = row.rowKey;
    const expCls = _asmExpanded[key] ? ' is-expanded' : '';
    if (row.isProcessed) {
      return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-asm-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Consumption lines">▤</button>`;
    }
    if (!canEdit()) return '<span class="lw-view-only">View only</span>';
    return `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-asm-act-weld" data-row-key="${escapeAttr(key)}">Welded</button>`;
  }

  function buildAsmDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row'
      + (row.isProcessed ? ' lw-data-row--processed' : '')
      + (row.isDraft ? ' lw-data-row--draft' : '');
    tr.dataset.rowKey = row.rowKey;
    const product = row.productName || row.partName || '';
    const operatorName = row.operatorName || '—';
    const customerName = row.customerName || '—';
    tr.innerHTML = `
      <td class="lw-col-customer" title="${escapeAttr(customerName)}">${escapeHtml(customerName)}</td>
      <td class="lw-col-bom val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(product)}">${escapeHtml(product || '—')}</td>
      <td class="lw-col-operator" title="${escapeAttr(operatorName)}">${escapeHtml(operatorName)}</td>
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
    td.colSpan = 6;
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

  function bomsForCustomer(custId) {
    const cid = custId ? Number(custId) : null;
    return cid ? _boms.filter(b => Number(b.custId) === cid) : _boms;
  }

  function bomSelectHtml(custId, selectedBomId) {
    const list = bomsForCustomer(custId);
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
      <td class="lw-col-lot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);
    const custSel = tr.querySelector('.lw-asm-new-customer');
    const bomSel = tr.querySelector('.lw-asm-new-bom');
    const opSel = tr.querySelector('.lw-asm-new-operator');
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
      tryCommitAsmNewRow(custSel, bomSel, opSel);
    });

    opSel?.addEventListener('change', () => tryCommitAsmNewRow(custSel, bomSel, opSel));
  }

  async function tryCommitAsmNewRow(custSel, bomSel, opSel) {
    const bomId = bomIdKey(bomSel?.value);
    const operatorId = parseInt(opSel?.value, 10);
    if (!bomId || !operatorId) return;

    const bom = _boms.find(b => bomIdKey(b.bomId) === bomId);
    const custId = parseInt(custSel?.value, 10);
    if (custId && bom && Number(bom.custId) !== custId) {
      showSnackbar('Selected BOM does not belong to this customer', 'error');
      return;
    }

    try {
      await apiPost('/api/laser-welding/assembly/pending', {
        bomId,
        operatorId,
        workDate: _workDate,
      });
      if (custSel) custSel.value = '';
      if (bomSel) {
        bomSel.value = '';
        bomSel.innerHTML = bomSelectHtml('', '');
      }
      if (opSel) opSel.value = '';
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
      const bomData = await apiFetch('/api/laser-welding/boms');
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
      const data = await apiFetch(
        '/api/laser-welding/assembly/rows?date=' + encodeURIComponent(_workDate)
      );
      _asmRows = (data.rows || []).map(r => ({
        ...r,
        rowKey: r.rowKey || `asm:${r.lotId}`,
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

  async function fetchChildLots(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    if (_childLotsCache[pn]) return _childLotsCache[pn];
    const data = await apiFetch('/api/laser-welding/assembly/child-lots?partNo=' + encodeURIComponent(pn));
    _childLotsCache[pn] = data.lots || [];
    return _childLotsCache[pn];
  }

  function emptyWeldLine() {
    return { childLotId: null, usedQty: 0, qaQty: 0 };
  }

  function weldRequiredForPart(ch, weldQty) {
    return (Number(ch.bomQty) || 0) * weldQty;
  }

  function weldUsedTotal(ch) {
    return (ch.lines || []).reduce((sum, ln) => sum + (Number(ln.usedQty) || 0), 0);
  }

  function isWeldLineEmpty(ln) {
    return !ln?.childLotId && Number(ln?.usedQty) <= 0 && Number(ln?.qaQty) <= 0;
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

  function renderWeldModalChildren() {
    const body = $('#lw-weld-modal-children');
    if (!body) return;
    const weldQty = parseInt($('#lw-weld-modal-qty')?.value, 10) || 0;

    let html = '';
    _weldModalChildren.forEach((ch, partIdx) => {
      const required = weldRequiredForPart(ch, weldQty);
      const usedTotal = weldUsedTotal(ch);
      if (!ch.lines?.length) ch.lines = [emptyWeldLine()];
      ensureWeldTrailingLine(ch);

      const usedCls = usedTotal === required && required > 0
        ? ' lw-weld-part-used--ok'
        : (usedTotal > required ? ' lw-weld-part-used--over' : '');

      html += `<div class="lw-weld-part-block" data-part-idx="${partIdx}">`;
      html += '<div class="lw-weld-part-head">';
      html += `<span class="lw-weld-part-no" title="${escapeAttr(ch.partName || '')}">${escapeHtml(ch.partNo)}</span>`;
      if (ch.partName) {
        html += `<span class="lw-weld-part-name">${escapeHtml(ch.partName)}</span>`;
      }
      html += `<span class="lw-weld-part-req">Required: <strong>${required}</strong></span>`;
      html += `<span class="lw-weld-part-used${usedCls}">Used: <strong>${usedTotal}</strong></span>`;
      html += '</div>';

      html += '<table class="ti-table lw-weld-part-table"><thead><tr>';
      html += '<th>Child Lot</th><th class="text-right">Used</th><th class="text-right">QA</th><th></th>';
      html += '</tr></thead><tbody>';

      ch.lines.forEach((ln, lineIdx) => {
        const usedLots = weldLotsUsedInPart(ch, lineIdx);
        const isTrailing = lineIdx === ch.lines.length - 1 && isWeldLineEmpty(ln);
        const used = Number(ln.usedQty) || 0;
        const qa = Number(ln.qaQty) || 0;

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
        html += `<td class="text-right"><input type="number" class="ti-input lw-weld-used" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" value="${used}" /></td>`;
        html += `<td class="text-right"><input type="number" class="ti-input lw-weld-qa" data-part-idx="${partIdx}" data-line-idx="${lineIdx}" min="0" max="${used}" value="${qa}" /></td>`;
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
    _weldModalLotId = row.lotId;
    _weldModalBomId = row.bomId;

    $('#lw-weld-modal-bom').textContent = row.partNumber
      ? `${row.partNumber} — ${row.productName || ''}`
      : '—';
    $('#lw-weld-modal-bom').dataset.bomId = String(row.bomId || '');
    $('#lw-weld-modal-operator').textContent = row.operatorName || '—';
    $('#lw-weld-modal-hours').value = '0';
    $('#lw-weld-modal-mins').value = '0';
    $('#lw-weld-modal-qty').value = '0';

    const data = await apiFetch('/api/laser-welding/boms/' + encodeURIComponent(row.bomId) + '/children');
    const children = data.children || [];
    _weldModalChildren = [];
    for (const ch of children) {
      const lots = await fetchChildLots(ch.partNo);
      _weldModalChildren.push({
        partNo: ch.partNo,
        partName: ch.partName,
        bomQty: ch.qty,
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
    _weldModalLotId = null;
    _weldModalBomId = null;
    _weldModalChildren = [];
  }

  async function saveWeldModal() {
    const lotId = _weldModalLotId;
    if (!lotId) return;
    const weldQty = parseInt($('#lw-weld-modal-qty')?.value, 10) || 0;
    if (weldQty <= 0) {
      showSnackbar('Weld QTY must be greater than 0', 'error');
      return;
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
      let partUsed = 0;
      const seenLots = new Set();
      for (const ln of ch.lines || []) {
        const used = Number(ln.usedQty) || 0;
        const qa = Number(ln.qaQty) || 0;
        if (!ln.childLotId && used <= 0 && qa <= 0) continue;
        if (!ln.childLotId) {
          showSnackbar(`Select child lot for ${ch.partNo}`, 'error');
          return;
        }
        if (used <= 0) {
          showSnackbar(`Enter Used QTY for ${ch.partNo}`, 'error');
          return;
        }
        if (qa > used) {
          showSnackbar(`QA cannot exceed Used for ${ch.partNo}`, 'error');
          return;
        }
        const lotKey = Number(ln.childLotId);
        if (seenLots.has(lotKey)) {
          showSnackbar(`Duplicate child lot for ${ch.partNo}`, 'error');
          return;
        }
        seenLots.add(lotKey);
        partUsed += used;
        consumptions.push({
          partNumber: ch.partNo,
          childLotId: ln.childLotId,
          usedQty: used,
          qaQty: qa,
        });
      }
      if (partUsed !== required) {
        showSnackbar(
          `Used total for ${ch.partNo} must be ${required} (BOM × weld qty), got ${partUsed}`,
          'error'
        );
        return;
      }
    }

    try {
      const data = await apiPost('/api/laser-welding/assembly/weld', {
        lotId,
        workDate: _workDate,
        weldQty,
        timeTakenMinutes,
        consumptions,
      });
      showSnackbar(`Welded — Lot No: ${data.newLotNo || ''}`, 'success');
      closeWeldModal();
      _childLotsCache = {};
      await loadAssemblyRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Weld failed', 'error');
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
    const usedInp = e.target.closest('.lw-weld-used');
    if (usedInp) {
      const partIdx = Number(usedInp.getAttribute('data-part-idx'));
      const lineIdx = Number(usedInp.getAttribute('data-line-idx'));
      const ln = getWeldLine(partIdx, lineIdx);
      if (ln) {
        ln.usedQty = parseInt(usedInp.value, 10) || 0;
        const qaInp = $(`.lw-weld-qa[data-part-idx="${partIdx}"][data-line-idx="${lineIdx}"]`);
        if (qaInp) qaInp.max = usedInp.value || '0';
      }
      const head = usedInp.closest('.lw-weld-part-block')?.querySelector('.lw-weld-part-used strong');
      if (head) head.textContent = String(weldUsedTotal(_weldModalChildren[partIdx]));
      return;
    }
    const qaInp = e.target.closest('.lw-weld-qa');
    if (qaInp) {
      const partIdx = Number(qaInp.getAttribute('data-part-idx'));
      const lineIdx = Number(qaInp.getAttribute('data-line-idx'));
      const ln = getWeldLine(partIdx, lineIdx);
      if (!ln) return;
      const max = Number(qaInp.max) || 0;
      let val = parseInt(qaInp.value, 10) || 0;
      if (val > max) {
        qaInp.value = String(max);
        val = max;
        showSnackbar('QA cannot exceed Used QTY', 'warning');
      }
      ln.qaQty = val;
    }
  }

  function openStoreInspectModal(row) {
    const overlay = $('#lw-store-modal-overlay');
    if (!overlay || !row) return;
    _storeModalLotId = row.lotId;
    _storeModalPending = Number(row.inspectionPending || row.inspectedQty) || 0;
    const label = `${row.partNumber} — ${row.productName || row.partName || ''}`;
    $('#lw-store-modal-part').textContent = label;
    $('#lw-store-modal-lot').textContent = row.newLotNo || '—';
    $('#lw-store-modal-pending').textContent = String(_storeModalPending);
    $('#lw-store-modal-hours').value = '0';
    $('#lw-store-modal-mins').value = '0';
    const qtyInp = $('#lw-store-modal-qty');
    const qaInp = $('#lw-store-modal-qa');
    if (qtyInp) {
      qtyInp.value = String(_storeModalPending);
      qtyInp.max = String(_storeModalPending);
    }
    if (qaInp) qaInp.value = '0';
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeStoreModal() {
    const overlay = $('#lw-store-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _storeModalLotId = null;
    _storeModalPending = 0;
  }

  async function saveStoreModal() {
    const lotId = _storeModalLotId;
    if (!lotId) return;
    const qty = parseInt($('#lw-store-modal-qty')?.value, 10) || 0;
    const qa = parseInt($('#lw-store-modal-qa')?.value, 10) || 0;
    if (qty <= 0) {
      showSnackbar('QTY must be greater than 0', 'error');
      return;
    }
    if (qty > _storeModalPending) {
      showSnackbar(`QTY cannot exceed pending (${_storeModalPending})`, 'error');
      return;
    }
    if (qa > qty) {
      showSnackbar('QA cannot exceed QTY', 'error');
      return;
    }
    const hours = parseInt($('#lw-store-modal-hours')?.value, 10) || 0;
    const mins = parseInt($('#lw-store-modal-mins')?.value, 10) || 0;
    const timeTakenMinutes = hours * 60 + mins;
    if (timeTakenMinutes <= 0) {
      showSnackbar('Time taken is required', 'error');
      return;
    }
    try {
      await apiPost('/api/laser-welding/inspection/store-inspect', {
        lotId,
        qty,
        qaQty: qa,
        timeTakenMinutes,
      });
      showSnackbar('Store inspection saved', 'success');
      closeStoreModal();
      await loadChildRows(true);
      await loadParts();
    } catch (err) {
      showSnackbar(err.message || 'Inspect failed', 'error');
    }
  }

  function openCleanModal(row) {
    const overlay = $('#lw-clean-modal-overlay');
    if (!overlay || !row) return;
    _cleanModalLotId = row.lotId;
    _cleanModalUncleaned = Number(row.uncleanedQty) || 0;
    const product = row.productName || row.partName || row.partNumber;
    $('#lw-clean-modal-product').textContent = `${row.partNumber} — ${product}`;
    $('#lw-clean-modal-uncleaned').textContent = String(_cleanModalUncleaned);
    const lotInp = $('#lw-clean-modal-lot');
    const qtyInp = $('#lw-clean-modal-qty');
    const opSel = $('#lw-clean-modal-operator');
    if (lotInp) lotInp.value = row.newLotNo || '';
    if (qtyInp) {
      qtyInp.value = String(_cleanModalUncleaned);
      qtyInp.max = String(_cleanModalUncleaned);
    }
    if (opSel) opSel.innerHTML = operatorSelectHtml(row.operatorId);
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function closeCleanModal() {
    const overlay = $('#lw-clean-modal-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    _cleanModalLotId = null;
    _cleanModalUncleaned = 0;
  }

  async function saveCleanModal() {
    const lotId = _cleanModalLotId;
    if (!lotId) return;
    const lotNo = ($('#lw-clean-modal-lot')?.value || '').trim();
    const qty = parseInt($('#lw-clean-modal-qty')?.value, 10) || 0;
    const operatorId = parseInt($('#lw-clean-modal-operator')?.value, 10);
    if (!lotNo) {
      showSnackbar('Lot number is required', 'error');
      return;
    }
    if (qty <= 0 || qty > _cleanModalUncleaned) {
      showSnackbar(`QTY must be between 1 and ${_cleanModalUncleaned}`, 'error');
      return;
    }
    if (!operatorId) {
      showSnackbar('Operator is required', 'error');
      return;
    }
    try {
      await apiPost('/api/laser-welding/cleaning/clean', {
        lotId,
        lotNo,
        qty,
        operatorId,
        workDate: _workDate,
      });
      showSnackbar('Cleaned successfully', 'success');
      closeCleanModal();
      await loadChildRows(true);
      await loadParts();
    } catch (err) {
      showSnackbar(err.message || 'Clean failed', 'error');
    }
  }

  function showPanel(tab) {
    $$('.lw-panel').forEach(p => p.classList.remove('lw-panel--active'));
    const map = {
      child_parts: '#lw-child-panel',
      qa_disposition: '#lw-qa-panel',
      rework: '#lw-rework-panel',
      sub_assembly: '#lw-placeholder-panel',
      final_assembly: '#lw-assembly-panel',
    };
    $(map[tab] || '#lw-placeholder-panel')?.classList.add('lw-panel--active');

    const modeBar = $('#lw-mode-bar');
    const tableWrap = $('#lw-table-wrap');
    const search = $('#lw-grid-search');
    const dateInput = $('#lw-work-date');
    const showInspect = tab === 'child_parts';
    const showAssembly = tab === 'final_assembly';
    const showGrid = showInspect || showAssembly;
    if (modeBar) modeBar.style.display = showInspect ? '' : 'none';
    if (tableWrap) tableWrap.style.display = showInspect ? '' : 'none';
    if (search) search.style.display = showGrid ? '' : 'none';
    if (dateInput) dateInput.style.display = showGrid ? '' : 'none';
    const dateLabel = $('.lw-date-label');
    if (dateLabel) dateLabel.style.display = showGrid ? '' : 'none';
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
    if (subtitle) subtitle.textContent = TAB_LABELS[tab] || 'Coming soon';

    if (tab === 'child_parts') loadChildRows();
    else if (tab === 'final_assembly') {
      loadBomCatalog().then(() => loadAssemblyRows());
    } else if (tab === 'qa_disposition') loadQaRows();
    else if (tab === 'rework') loadReworkRows();
    else updateRowCount();
  }

  function onAsmTableClick(e) {
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

  function onTableClick(e) {
    const detailBtn = e.target.closest('.lw-act-detail');
    if (detailBtn) {
      const key = detailBtn.getAttribute('data-row-key');
      if (key) {
        _expanded[key] = !_expanded[key];
        renderTable();
      }
      return;
    }

    const storeInspectBtn = e.target.closest('.lw-act-store-inspect');
    if (storeInspectBtn) {
      const row = findRow(storeInspectBtn.getAttribute('data-row-key'));
      if (row) openStoreInspectModal(row);
      return;
    }

    const cleanBtn = e.target.closest('.lw-act-clean');
    if (cleanBtn) {
      const row = findRow(cleanBtn.getAttribute('data-row-key'));
      if (row) openCleanModal(row);
      return;
    }

    const inspectProdBtn = e.target.closest('.lw-act-inspect');
    if (inspectProdBtn && _batchMode === 'production') {
      const row = findRow(inspectProdBtn.getAttribute('data-row-key'));
      if (row) openProductionModal(row);
      return;
    }

    const editReworkBtn = e.target.closest('.lw-act-edit-rework');
    if (editReworkBtn) {
      const row = findRow(editReworkBtn.getAttribute('data-row-key'));
      if (row) openReworkModal(row);
      return;
    }

    const processBtn = e.target.closest('.lw-act-process');
    if (processBtn) {
      processRow(processBtn.getAttribute('data-row-key'));
    }
  }

  function onReworkModalClick(e) {
    const removeBtn = e.target.closest('.lw-rework-line-remove');
    if (removeBtn) {
      const idx = Number(removeBtn.getAttribute('data-idx'));
      _reworkModalLines.splice(idx, 1);
      if (!_reworkModalLines.length) _reworkModalLines.push(emptyReworkLine());
      renderReworkModalLines();
      return;
    }

    const lotSel = e.target.closest('.lw-rework-line-lot');
    if (lotSel) onReworkModalLotChange(lotSel);
  }

  function onReworkModalInput(e) {
    const insp = e.target.closest('.lw-rework-line-insp');
    if (insp) {
      const idx = Number(insp.getAttribute('data-idx'));
      const max = Number(insp.max) || 0;
      let val = parseInt(insp.value, 10);
      if (Number.isNaN(val) || val < 0) val = 0;
      if (val > max) {
        insp.value = String(max);
        showSnackbar('Inspected QTY cannot exceed rework pool', 'warning');
      }
      const qaInp = $(`.lw-rework-line-qa[data-idx="${idx}"]`);
      if (qaInp) qaInp.max = insp.value || '0';
      if (_reworkModalLines[idx]) _reworkModalLines[idx].inspectedQty = parseInt(insp.value, 10) || 0;
    }
    const qa = e.target.closest('.lw-rework-line-qa');
    if (qa) {
      const idx = Number(qa.getAttribute('data-idx'));
      const max = Number(qa.max) || 0;
      let val = parseInt(qa.value, 10);
      if (Number.isNaN(val) || val < 0) val = 0;
      if (val > max) {
        qa.value = String(max);
        showSnackbar('QA cannot exceed Inspected QTY', 'warning');
      }
      if (_reworkModalLines[idx]) _reworkModalLines[idx].qaQty = parseInt(qa.value, 10) || 0;
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
      const idx = Number(insp.getAttribute('data-idx'));
      const max = Number(insp.max) || 0;
      let val = parseInt(insp.value, 10);
      if (Number.isNaN(val) || val < 0) val = 0;
      if (val > max) {
        insp.value = String(max);
        showSnackbar('Inspected QTY cannot exceed No of Comp', 'warning');
      }
      const qaInp = $(`.lw-prod-line-qa[data-idx="${idx}"]`);
      if (qaInp) qaInp.max = insp.value || '0';
      if (_prodModalLines[idx]) _prodModalLines[idx].inspectedQty = parseInt(insp.value, 10) || 0;
    }
    const qa = e.target.closest('.lw-prod-line-qa');
    if (qa) {
      const idx = Number(qa.getAttribute('data-idx'));
      const max = Number(qa.max) || 0;
      let val = parseInt(qa.value, 10);
      if (Number.isNaN(val) || val < 0) val = 0;
      if (val > max) {
        qa.value = String(max);
        showSnackbar('QA cannot exceed Inspected QTY', 'warning');
      }
      if (_prodModalLines[idx]) _prodModalLines[idx].qaQty = parseInt(qa.value, 10) || 0;
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

    $('#lw-grid-search')?.addEventListener('input', e => {
      _filterQuery = e.target.value || '';
      if (_tab === 'final_assembly') renderAssemblyTable();
      else renderTable();
    });

    $('#lw-work-date')?.addEventListener('change', e => {
      _workDate = e.target.value || todayIso();
      if (_tab === 'final_assembly') loadAssemblyRows();
      else loadChildRows();
    });

    $$('input[name="lw-batch-mode"]').forEach(radio => {
      radio.addEventListener('change', async e => {
        _batchMode = e.target.value || 'production';
        _expanded = {};
        updateModeChrome();
        try {
          await refreshPartsDatalist();
        } catch (err) {
          console.error('Failed to load parts for mode', err);
        }
        await loadChildRows(true);
      });
    });

    $('#lw-rework-modal-cancel')?.addEventListener('click', closeReworkModal);
    $('#lw-rework-modal-save')?.addEventListener('click', saveReworkModal);
    $('#lw-rework-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-rework-modal-overlay') closeReworkModal();
    });
    $('#lw-rework-modal-lines')?.addEventListener('click', onReworkModalClick);
    $('#lw-rework-modal-lines')?.addEventListener('change', onReworkModalClick);
    $('#lw-rework-modal-lines')?.addEventListener('input', onReworkModalInput);

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

    $('#lw-store-modal-cancel')?.addEventListener('click', closeStoreModal);
    $('#lw-store-modal-save')?.addEventListener('click', saveStoreModal);
    $('#lw-store-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-store-modal-overlay') closeStoreModal();
    });
    $('#lw-store-modal-qty')?.addEventListener('input', e => {
      const qaInp = $('#lw-store-modal-qa');
      if (qaInp) qaInp.max = e.target.value || '0';
    });

    $('#lw-clean-modal-cancel')?.addEventListener('click', closeCleanModal);
    $('#lw-clean-modal-save')?.addEventListener('click', saveCleanModal);
    $('#lw-clean-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-clean-modal-overlay') closeCleanModal();
    });

    $('#lw-weld-modal-cancel')?.addEventListener('click', closeWeldModal);
    $('#lw-weld-modal-save')?.addEventListener('click', saveWeldModal);
    $('#lw-weld-modal-overlay')?.addEventListener('click', e => {
      if (e.target.id === 'lw-weld-modal-overlay') closeWeldModal();
    });
    $('#lw-weld-modal-qty')?.addEventListener('input', () => renderWeldModalChildren());
    $('#lw-weld-modal-children')?.addEventListener('click', onWeldModalClick);
    $('#lw-weld-modal-children')?.addEventListener('change', onWeldModalChange);
    $('#lw-weld-modal-children')?.addEventListener('input', onWeldModalInput);

    $('#lw-qa-passed')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-scrap')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-rework')?.addEventListener('input', updateQaApproveState);
    $('#lw-qa-part')?.addEventListener('change', onQaPartChange);
    $('#lw-qa-lot')?.addEventListener('change', onQaLotChange);
    $('#lw-qa-approve')?.addEventListener('click', approveQa);
    $('#lw-rework-part')?.addEventListener('change', onReworkPartChange);
    $('#lw-rework-lot')?.addEventListener('change', onReworkLotChange);
    $('#lw-rework-inward')?.addEventListener('click', inwardRework);

    $('#lw-qa-queue')?.addEventListener('click', e => {
      const item = e.target.closest('.lw-queue-item');
      if (!item) return;
      $('#lw-qa-part').value = item.getAttribute('data-part');
      onQaPartChange();
      $('#lw-qa-lot').value = item.getAttribute('data-lot-id');
      onQaLotChange();
    });

    $('#lw-rework-queue')?.addEventListener('click', e => {
      const item = e.target.closest('.lw-queue-item');
      if (!item) return;
      $('#lw-rework-part').value = item.getAttribute('data-part');
      onReworkPartChange();
      $('#lw-rework-lot').value = item.getAttribute('data-lot-id');
      onReworkLotChange();
    });
  }

  async function init() {
    _workDate = todayIso();
    const dateInput = $('#lw-work-date');
    if (dateInput) dateInput.value = _workDate;

    bindEvents();
    await Promise.all([loadParts(), loadOperators()]);
    switchTab('child_parts');
  }

  return { init, loadRows: loadChildRows };
})();
