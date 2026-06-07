/* ═══════════════════════════════════════════════════════════════════════════
   LASER_WELDING.JS — Laser Welding section (Child Parts tab)
   Inline table + expandable production details (Machine Planning style)
   ═══════════════════════════════════════════════════════════════════════════ */

window.LaserWeldingPage = (() => {
  const TAB_LABELS = {
    child_parts: 'Child Parts — lot tracking & processing',
    sub_assembly: 'Sub-Assembly — coming soon',
    final_assembly: 'Final Assembly — coming soon',
  };

  let _tab = 'child_parts';
  let _stages = [];
  let _parts = [];
  let _rows = [];
  let _openRows = [];
  let _expanded = {};
  let _prodCache = {};
  let _filterQuery = '';
  let _loading = false;

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
  const canEdit = () => !!window.DPR_EDIT_ALLOWED;

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

  function partNameFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => String(x.part_no || '').trim().toLowerCase() === key);
    return p ? String(p.part_name || '').trim() : '';
  }

  function stageNameFor(stageId) {
    const s = _stages.find(x => Number(x.id) === Number(stageId));
    return s ? s.name : '';
  }

  function stageOptionsHtml(selectedId) {
    let html = '<option value="">Select stage…</option>';
    _stages.forEach(s => {
      const sel = Number(s.id) === Number(selectedId) ? ' selected' : '';
      html += `<option value="${s.id}"${sel}>${escapeHtml(s.name)}</option>`;
    });
    return html;
  }

  function unprocessedKey(partNumber, stageId) {
    return `${String(partNumber || '').trim().toLowerCase()}::${Number(stageId)}`;
  }

  function rowHasPositiveQty(items) {
    return (items || []).some(it => Number(it.qtyProcessed) > 0);
  }

  function itemsAllZero(items) {
    if (!items || !items.length) return true;
    return items.every(it => Number(it.qtyProcessed) <= 0);
  }

  function ensureOpenRow(row) {
    const key = unprocessedKey(row.partNumber, row.stageId);
    const exists = _openRows.some(r => unprocessedKey(r.partNumber, r.stageId) === key);
    if (!exists) {
      _openRows.push({
        rowKey: row.rowKey || `open:${row.partNumber}:${row.stageId}:${Date.now()}`,
        partNumber: row.partNumber,
        partName: row.partName || partNameFor(row.partNumber),
        stageId: row.stageId,
        stageName: row.stageName || stageNameFor(row.stageId),
        newLotNo: null,
        isProcessed: false,
        isOpen: true,
        items: row.items || [],
      });
    }
  }

  function removeOpenRow(partNumber, stageId) {
    const key = unprocessedKey(partNumber, stageId);
    _openRows = _openRows.filter(r => unprocessedKey(r.partNumber, r.stageId) !== key);
  }

  function syncOpenRowsAfterLoad() {
    const serverOpen = new Set(
      _rows.filter(r => !r.isProcessed).map(r => unprocessedKey(r.partNumber, r.stageId))
    );
    _openRows = _openRows.filter(r => !serverOpen.has(unprocessedKey(r.partNumber, r.stageId)));
  }

  function allDisplayRows() {
    const merged = [..._rows];
    const seenOpen = new Set(
      _rows.filter(r => !r.isProcessed).map(r => unprocessedKey(r.partNumber, r.stageId))
    );
    _openRows.forEach(r => {
      const key = unprocessedKey(r.partNumber, r.stageId);
      if (!seenOpen.has(key)) {
        merged.unshift(r);
        seenOpen.add(key);
      }
    });
    return merged;
  }

  function filteredRows() {
    const q = _filterQuery.trim().toLowerCase();
    const rows = allDisplayRows();
    if (!q) return rows;
    return rows.filter(r => {
      const hay = [
        r.partNumber,
        r.partName || partNameFor(r.partNumber),
        r.stageName || stageNameFor(r.stageId),
        r.newLotNo,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function findRow(rowKey) {
    return allDisplayRows().find(r => r.rowKey === rowKey);
  }

  function hasOpenForPartStage(partNumber, stageId, excludeKey) {
    const pn = String(partNumber || '').trim().toLowerCase();
    const sid = Number(stageId);
    return allDisplayRows().some(r => {
      if (excludeKey && r.rowKey === excludeKey) return false;
      if (r.isProcessed) return false;
      return String(r.partNumber || '').trim().toLowerCase() === pn
        && Number(r.stageId) === sid;
    });
  }

  function updateRowCount() {
    const el = $('#lw-item-count');
    if (!el) return;
    const n = filteredRows().length;
    el.textContent = n === 1 ? '1 row' : `${n} rows`;
  }

  function mergeSavedQty(row, entries) {
    const saved = {};
    (row.items || []).forEach(it => {
      saved[it.sourceLotNo] = it.qtyProcessed;
    });
    return entries.map(e => ({
      ...e,
      qtyProcessed: saved[e.lotNo] != null ? saved[e.lotNo] : 0,
    }));
  }

  function detailTableHtml(row, entries, readonly) {
    if (!entries.length) {
      return '<span class="lw-detail-empty">No production lots found for this part.</span>';
    }

    const merged = mergeSavedQty(row, entries);
    let html = '';
    html += '<table class="ti-table lw-detail-table"><thead><tr>';
    html += '<th>Lot No</th><th>Production Date</th><th class="text-right">No Of Comp</th><th class="text-right">Qty Processed</th>';
    html += '</tr></thead><tbody>';

    merged.forEach(e => {
      const max = Number(e.noOfComp) || 0;
      const val = Number(e.qtyProcessed) || 0;
      html += '<tr>';
      html += `<td>${escapeHtml(e.lotNo || '—')}</td>`;
      html += `<td>${escapeHtml(e.productionDate || '—')}</td>`;
      html += `<td class="text-right">${max}</td>`;
      html += '<td class="text-right">';
      if (readonly) {
        html += val > 0 ? val : '—';
      } else {
        html += `<input type="number" class="lw-cell-input lw-qty-input" min="0" max="${max}" step="1" value="${val}" ` +
          `data-row-key="${escapeAttr(row.rowKey)}" data-lot-no="${escapeAttr(e.lotNo)}" ` +
          `data-no-of-comp="${max}" data-prod-date="${escapeAttr(e.productionDate || '')}" />`;
      }
      html += '</td></tr>';
    });

    html += '</tbody></table>';
    return html;
  }

  function buildActionsHtml(row) {
    const key = row.rowKey;
    const expCls = _expanded[key] ? ' is-expanded' : '';

    if (row.isProcessed) {
      return `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Production Details">▤</button>`;
    }

    if (!canEdit()) {
      return '<span class="lw-view-only">View only</span>';
    }

    return (
      `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-detail${expCls}" data-row-key="${escapeAttr(key)}" title="Production Details">▤</button>` +
      `<button type="button" class="ti-btn ti-btn-outline ti-btn-xs lw-act-save" data-row-key="${escapeAttr(key)}" title="Save">Save</button>` +
      `<button type="button" class="ti-btn ti-btn-primary ti-btn-xs lw-act-process" data-row-key="${escapeAttr(key)}" title="Processed">Processed</button>`
    );
  }

  function buildDataRow(row) {
    const tr = document.createElement('tr');
    tr.className = 'lw-data-row' + (row.isProcessed ? ' lw-data-row--processed' : '');
    tr.dataset.rowKey = row.rowKey;

    const partName = row.partName || partNameFor(row.partNumber);
    const stageCell = row.isProcessed || !canEdit()
      ? `<span class="lw-stage-text">${escapeHtml(row.stageName || stageNameFor(row.stageId) || '—')}</span>`
      : `<select class="lw-cell-input lw-row-stage" data-row-key="${escapeAttr(row.rowKey)}">${stageOptionsHtml(row.stageId)}</select>`;

    tr.innerHTML = `
      <td class="lw-col-part val-bold" title="${escapeAttr(row.partNumber)}">${escapeHtml(row.partNumber)}</td>
      <td class="lw-col-name" title="${escapeAttr(partName)}">${escapeHtml(partName || '—')}</td>
      <td class="lw-col-stage lw-edit-cell">${stageCell}</td>
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
    td.colSpan = 5;
    td.className = 'lw-detail-cell';

    const partNo = row.partNumber;
    if (row.isProcessed && row.items && row.items.length) {
      const entries = row.items.map(it => ({
        lotNo: it.sourceLotNo,
        productionDate: it.productionDate,
        noOfComp: it.noOfComp,
        qtyProcessed: it.qtyProcessed,
      }));
      td.innerHTML = `<div class="lw-detail-inline">${detailTableHtml(row, entries, true)}</div>`;
    } else if (_prodCache[partNo]?.entries) {
      td.innerHTML = `<div class="lw-detail-inline lw-detail-body" data-part-no="${escapeAttr(partNo)}" data-row-key="${escapeAttr(row.rowKey)}">${detailTableHtml(row, _prodCache[partNo].entries, row.isProcessed || !canEdit())}</div>`;
    } else {
      td.innerHTML = `<div class="lw-detail-inline lw-detail-body" data-part-no="${escapeAttr(partNo)}" data-row-key="${escapeAttr(row.rowKey)}" data-needs-load="1"><span class="lw-detail-loading">Loading production details…</span></div>`;
    }

    tr.appendChild(td);
    return tr;
  }

  function appendNewRow(tbody) {
    if (!canEdit() || _tab !== 'child_parts') return;

    const tr = document.createElement('tr');
    tr.className = 'lw-new-row';
    tr.innerHTML = `
      <td class="lw-col-part lw-edit-cell">
        <input type="text" class="lw-cell-input lw-new-part"
               list="lw-parts-datalist" placeholder="Select part…" autocomplete="off" />
      </td>
      <td class="lw-col-name lw-new-part-name"></td>
      <td class="lw-col-stage lw-edit-cell">
        <select class="lw-cell-input lw-new-stage">${stageOptionsHtml('')}</select>
      </td>
      <td class="lw-col-lot">—</td>
      <td class="lw-col-actions"></td>
    `;
    tbody.appendChild(tr);

    const partInput = tr.querySelector('.lw-new-part');
    const stageSel = tr.querySelector('.lw-new-stage');

    partInput?.addEventListener('input', () => {
      const nameEl = tr.querySelector('#lw-new-part-name');
      if (nameEl) nameEl.textContent = partNameFor(partInput.value) || '';
    });

    partInput?.addEventListener('change', () => tryCommitNewRow(partInput, stageSel));
    stageSel?.addEventListener('change', () => tryCommitNewRow(partInput, stageSel));

    partInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        tryCommitNewRow(partInput, stageSel);
      }
    });
  }

  async function fetchProductionDetails(partNo) {
    const pn = String(partNo || '').trim();
    if (!pn) return [];
    if (_prodCache[pn]?.entries) return _prodCache[pn].entries;
    const data = await apiFetch('/api/laser-welding/production-details?partNo=' + encodeURIComponent(pn));
    _prodCache[pn] = { entries: data.entries || [] };
    return _prodCache[pn].entries;
  }

  async function tryCommitNewRow(partInput, stageSel) {
    const partNumber = (partInput?.value || '').trim();
    const stageId = parseInt(stageSel?.value, 10);
    if (!partNumber || !stageId) return;

    if (hasOpenForPartStage(partNumber, stageId)) {
      showSnackbar('An open row already exists for this part and stage', 'error');
      return;
    }

    const rowKey = `open:${partNumber}:${stageId}:${Date.now()}`;
    _openRows.push({
      rowKey,
      partNumber,
      partName: partNameFor(partNumber),
      stageId,
      stageName: stageNameFor(stageId),
      newLotNo: null,
      isProcessed: false,
      isOpen: true,
      items: [],
    });

    const tr = partInput?.closest('tr');
    partInput.value = '';
    if (stageSel) stageSel.value = '';
    const nameEl = tr?.querySelector('.lw-new-part-name');
    if (nameEl) nameEl.textContent = '';

    renderTable();
    showSnackbar('Part row added', 'success');

    try {
      const entries = await fetchProductionDetails(partNumber);
      if (!entries.length) {
        showSnackbar('No production details found for this part — expand Production Details to verify', 'warning');
      }
    } catch (_) { /* ignore prefetch errors */ }
  }

  function renderTable() {
    const tbody = $('#lw-table-body');
    const tableWrap = $('#lw-table-wrap');
    if (!tbody) return;

    tbody.innerHTML = '';
    const rows = filteredRows();

    rows.forEach(row => {
      tbody.appendChild(buildDataRow(row));
      if (_expanded[row.rowKey]) {
        tbody.appendChild(buildDetailRow(row));
      }
    });

    appendNewRow(tbody);
    mountInlineDetails();

    if (tableWrap) tableWrap.style.display = _tab === 'child_parts' ? '' : 'none';
    updateRowCount();
  }

  function mountInlineDetails() {
    $$('.lw-detail-body[data-needs-load="1"]').forEach(el => {
      el.removeAttribute('data-needs-load');
      const partNo = el.getAttribute('data-part-no');
      const rowKey = el.getAttribute('data-row-key');
      if (partNo) loadProductionDetail(partNo, rowKey, el);
    });
  }

  async function loadProductionDetail(partNo, rowKey, container) {
    const row = findRow(rowKey);
    if (_prodCache[partNo]?.entries && row && container) {
      container.innerHTML = detailTableHtml(row, _prodCache[partNo].entries, row.isProcessed || !canEdit());
      return;
    }
    if (container) {
      container.innerHTML = '<span class="lw-detail-loading">Loading production details…</span>';
    }
    try {
      const entries = await fetchProductionDetails(partNo);
      const freshRow = findRow(rowKey);
      if (freshRow && container?.isConnected) {
        container.innerHTML = detailTableHtml(freshRow, entries, freshRow.isProcessed || !canEdit());
      }
    } catch (err) {
      if (container?.isConnected) {
        container.innerHTML = `<div class="ti-alert ti-alert-error lw-detail-error">${escapeHtml(err.message || 'Failed to load')}</div>`;
      }
    }
  }

  function collectQtyItems(rowKey) {
    const row = findRow(rowKey);
    if (!row) return [];

    const inputs = $$(`.lw-qty-input[data-row-key="${CSS.escape(rowKey)}"]`);
    if (!inputs.length) {
      return (row.items || []).map(it => ({
        sourceLotNo: it.sourceLotNo,
        productionDate: it.productionDate,
        noOfComp: it.noOfComp,
        qtyProcessed: it.qtyProcessed,
      }));
    }

    const items = [];
    inputs.forEach(inp => {
      const lot = inp.getAttribute('data-lot-no') || '';
      const max = Number(inp.getAttribute('data-no-of-comp')) || 0;
      let qty = parseInt(inp.value, 10);
      if (Number.isNaN(qty)) qty = 0;
      if (qty > max) {
        throw new Error(`Qty Processed cannot exceed No of Comp for lot ${lot}`);
      }
      items.push({
        sourceLotNo: lot,
        productionDate: inp.getAttribute('data-prod-date') || '',
        noOfComp: max,
        qtyProcessed: qty,
      });
    });
    return items;
  }

  async function saveRowInternal(rowKey, opts = {}) {
    const { silent = false, skipReload = false } = opts;
    const row = findRow(rowKey);
    if (!row || row.isProcessed) return false;
    if (!row.partNumber || !row.stageId) {
      if (!silent) showSnackbar('Part number and stage are required', 'error');
      return false;
    }

    let items;
    try {
      items = collectQtyItems(rowKey);
    } catch (err) {
      if (!silent) showSnackbar(err.message, 'error');
      return false;
    }

    try {
      await apiPost('/api/laser-welding/save', {
        tab: _tab,
        partNumber: row.partNumber,
        stageId: row.stageId,
        items,
      });

      const hasQty = rowHasPositiveQty(items);
      if (hasQty) {
        removeOpenRow(row.partNumber, row.stageId);
        if (!skipReload) await loadRows(true);
        if (!silent) showSnackbar('Saved successfully', 'success');
      } else {
        row.items = [];
        ensureOpenRow(row);
        if (!skipReload) renderTable();
        if (!silent) {
          showSnackbar('Saved — zero-quantity lot entries cleared; part row kept open', 'info');
        }
      }
      return true;
    } catch (err) {
      if (!silent) showSnackbar(err.message || 'Save failed', 'error');
      return false;
    }
  }

  async function saveRow(rowKey) {
    await saveRowInternal(rowKey);
  }

  async function processRow(rowKey) {
    const row = findRow(rowKey);
    if (!row || row.isProcessed) return;
    if (!row.partNumber || !row.stageId) {
      showSnackbar('Part number and stage are required', 'error');
      return;
    }

    let items;
    try {
      items = collectQtyItems(rowKey);
    } catch (err) {
      showSnackbar(err.message, 'error');
      return;
    }

    if (itemsAllZero(items)) {
      showSnackbar('Enter Qty Processed greater than 0 before processing', 'warning');
      return;
    }

    if (!confirm('Mark this part as processed and generate a new lot number?')) return;

    const saved = await saveRowInternal(rowKey, { silent: true, skipReload: true });
    if (!saved) return;

    try {
      const data = await apiPost('/api/laser-welding/process', {
        tab: _tab,
        partNumber: row.partNumber,
        stageId: row.stageId,
      });
      showSnackbar(`Processed — Lot No: ${data.newLotNo || ''}`, 'success');
      removeOpenRow(row.partNumber, row.stageId);
      delete _expanded[rowKey];
      await loadRows(true);
    } catch (err) {
      showSnackbar(err.message || 'Process failed', 'error');
      await loadRows(true);
    }
  }

  async function loadRows(preserveFilter) {
    if (_tab !== 'child_parts') return;

    const loadingEl = $('#lw-loading');
    const errorEl = $('#lw-error');
    if (_loading) return;
    _loading = true;

    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';

    try {
      const data = await apiFetch('/api/laser-welding/rows?tab=' + encodeURIComponent(_tab));
      _rows = data.rows || [];
      syncOpenRowsAfterLoad();
      renderTable();
      if (!preserveFilter) {
        _filterQuery = '';
        const search = $('#lw-grid-search');
        if (search) search.value = '';
      }
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

  async function loadStages() {
    try {
      _stages = await apiFetch('/api/laser-welding/stages');
    } catch (err) {
      console.error('Failed to load stages', err);
    }
  }

  async function loadParts() {
    try {
      const opts = await apiFetch('/api/dpr/options');
      _parts = opts.parts || [];
      const dl = $('#lw-parts-datalist');
      if (!dl) return;
      dl.innerHTML = '';
      _parts.forEach(p => {
        const partNo = String(p.part_no || '').trim();
        if (!partNo) return;
        const opt = document.createElement('option');
        opt.value = partNo;
        opt.label = String(p.part_name || '').trim();
        dl.appendChild(opt);
      });
    } catch (err) {
      console.error('Failed to load parts', err);
    }
  }

  function switchTab(tab) {
    _tab = tab;

    $$('.lw-tab').forEach(btn => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle('lw-tab--active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    const childPanel = $('#lw-child-panel');
    const placeholder = $('#lw-placeholder-panel');
    const subtitle = $('#lw-subtitle');

    if (tab === 'child_parts') {
      childPanel?.classList.add('lw-panel--active');
      placeholder?.classList.remove('lw-panel--active');
      if (subtitle) subtitle.textContent = TAB_LABELS.child_parts;
      loadRows();
    } else {
      childPanel?.classList.remove('lw-panel--active');
      placeholder?.classList.add('lw-panel--active');
      if (subtitle) subtitle.textContent = TAB_LABELS[tab] || 'Coming soon';
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

    const saveBtn = e.target.closest('.lw-act-save');
    if (saveBtn) {
      saveRow(saveBtn.getAttribute('data-row-key'));
      return;
    }

    const processBtn = e.target.closest('.lw-act-process');
    if (processBtn) {
      processRow(processBtn.getAttribute('data-row-key'));
    }
  }

  function onTableChange(e) {
    const sel = e.target.closest('.lw-row-stage');
    if (!sel) return;
    const rowKey = sel.getAttribute('data-row-key');
    const row = findRow(rowKey);
    if (!row || row.isProcessed) return;

    const newStageId = parseInt(sel.value, 10);
    if (!newStageId) return;

    const prevStageId = row.stageId;
    if (hasOpenForPartStage(row.partNumber, newStageId, rowKey)) {
      showSnackbar('An open row already exists for this part and stage', 'error');
      sel.value = prevStageId;
      return;
    }

    row.stageId = newStageId;
    row.stageName = stageNameFor(newStageId);
    if (row.isOpen) {
      row.rowKey = `open:${row.partNumber}:${newStageId}:${Date.now()}`;
      const idx = _openRows.findIndex(r => unprocessedKey(r.partNumber, r.stageId) === unprocessedKey(row.partNumber, prevStageId));
      if (idx >= 0) {
        _openRows[idx] = { ...row };
      }
    }
    renderTable();
  }

  function onQtyInput(e) {
    const inp = e.target.closest('.lw-qty-input');
    if (!inp) return;
    const max = Number(inp.getAttribute('data-no-of-comp')) || 0;
    let val = parseInt(inp.value, 10);
    if (Number.isNaN(val) || val < 0) val = 0;
    if (val > max) {
      inp.value = String(max);
      showSnackbar('Qty Processed cannot exceed No of Comp', 'warning');
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
    $('#lw-table-body')?.addEventListener('change', onTableChange);
    $('#lw-table-body')?.addEventListener('input', onQtyInput);

    $('#lw-grid-search')?.addEventListener('input', e => {
      _filterQuery = e.target.value || '';
      renderTable();
    });
  }

  async function init() {
    bindEvents();
    await Promise.all([loadStages(), loadParts()]);
    switchTab('child_parts');
  }

  return { init, loadRows };
})();
