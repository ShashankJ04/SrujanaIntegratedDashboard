/* ═══════════════════════════════════════════════════════════════════════════
   MACHINE_PLANNING.JS — Machine-wise Monthly Production Plan
   ═══════════════════════════════════════════════════════════════════════════ */

window.MachinePlanningPage = (() => {
  let _machines = [];
  let _parts = [];
  let _plan = null;
  let _currentMachineId = null;
  let _currentMonth = null;

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
  const fmt = (n) => typeof formatIndianNumber === 'function' ? formatIndianNumber(n) : Number(n).toLocaleString('en-IN');
  const _canEdit = () => !!window.DPR_EDIT_ALLOWED;

  const MP_LAYOUT_STORAGE_KEY = 'mp_layout_v1';
  const MP_FROZEN_ACTIONS_COL = 'actions';
  const MP_DEFAULT_COL_ORDER = [
    'actions', 'part_number', 'part_name', 'production_pending', 'produced_qty',
    'additional_qty', 'priority', 'spm', 'max_pts_day', 'days_required',
    'rm_code', 'remarks',
  ];
  const MP_SORTABLE_COLS = new Set([
    'part_number', 'part_name', 'production_pending', 'produced_qty',
    'additional_qty', 'priority', 'spm', 'max_pts_day', 'days_required', 'rm_code', 'remarks',
  ]);

  let mpLayout = { order: [...MP_DEFAULT_COL_ORDER], pinnedLeft: [], widths: {} };
  let mpSortBy = null;
  let mpSortDir = 'asc';
  let mpDragCol = null;
  let mpResizeDrag = null;

  // ── Init ──────────────────────────────────────────────────────────────
  async function init() {
    const monthInput = $('#mp-month-input');
    if (monthInput) {
      const now = new Date();
      monthInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    }

    $('#mp-load-btn')?.addEventListener('click', loadPlan);
    $('#mp-export-btn')?.addEventListener('click', _exportExcel);
    $('#mp-reset-columns')?.addEventListener('click', () => _resetMpLayout());
    _loadMpLayout();
    _attachMpResizeGlobals();

    await Promise.all([_loadMachines(), _loadParts()]);
  }

  // ── Load machine dropdown ─────────────────────────────────────────────
  async function _loadMachines() {
    try {
      _machines = await apiFetch('/api/machine-planning/machines');
      const sel = $('#mp-machine-select');
      if (!sel) return;
      sel.innerHTML = '<option value="">Select machine…</option>';
      _machines.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.label} (${m.capacity})`;
        sel.appendChild(opt);
      });
    } catch (err) {
      console.error('Failed to load machines', err);
      showSnackbar('Failed to load machine list', 'error');
    }
  }

  // ── Load parts into datalist (DPR-style) ──────────────────────────────
  async function _loadParts() {
    try {
      const opts = await apiFetch('/api/dpr/options');
      _parts = opts.parts || [];
      _buildDatalist();
    } catch (err) {
      console.error('Failed to load parts', err);
    }
  }

  function _buildDatalist() {
    const dl = $('#mp-parts-datalist');
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
  }

  function _partNameFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    const p = _parts.find(x => String(x.part_no || '').trim().toLowerCase() === key);
    return p ? String(p.part_name || '').trim() : '';
  }

  // ── Load plan ─────────────────────────────────────────────────────────
  async function loadPlan() {
    const machineId = $('#mp-machine-select')?.value;
    const month = $('#mp-month-input')?.value;
    if (!machineId || !month) {
      showSnackbar('Please select a machine and month', 'warning');
      return;
    }
    _currentMachineId = parseInt(machineId);
    _currentMonth = month;

    _showLoading(true);
    try {
      _plan = await apiFetch(`/api/machine-planning/plan?machine_id=${machineId}&month=${month}`);
      _renderPlan();
    } catch (err) {
      console.error(err);
      showSnackbar('Failed to load plan: ' + err.message, 'error');
    } finally {
      _showLoading(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────
  function _renderPlan() {
    if (!_plan) return;

    const headerCard = $('#mp-header-card');
    const tableWrap = $('#mp-table-wrap');
    const empty = $('#mp-empty-state');

    if (empty) empty.style.display = 'none';
    if (headerCard) headerCard.style.display = '';
    if (tableWrap) tableWrap.style.display = '';

    const exportBtn = $('#mp-export-btn');
    const resetBtn = $('#mp-reset-columns');
    if (exportBtn) exportBtn.style.display = '';
    if (resetBtn) resetBtn.style.display = '';

    const mc = _plan.machine || {};
    const monthLabel = _currentMonth ? _formatMonthLabel(_currentMonth) : '';

    _setText('#mp-kpi-machine', mc.label || '–');
    _setText('#mp-kpi-tonnage', mc.capacity || '–');
    _setText('#mp-kpi-make', mc.make || '–');
    _setText('#mp-kpi-unit', '2');
    _setText('#mp-kpi-month', monthLabel || '–');
    _setText('#mp-kpi-days', _plan.total_days_required ?? '–');
    _setText('#mp-kpi-parts', _plan.rows?.length ?? 0);
    _setText('#mp-subtitle', `${mc.label || 'Machine'} — ${monthLabel}`);

    const rows = _plan.rows || [];
    const earliest = rows.reduce((min, r) => {
      if (!r.created_at) return min;
      return (!min || r.created_at < min) ? r.created_at : min;
    }, null);
    _setText('#mp-kpi-created', earliest ? _formatDate(earliest) : '–');

    const readOnly = !_canEdit();
    const table = $('#mp-table');
    const gridRoot = $('#mp-grid-root');
    const actionsTh = $('#mp-action-col');
    if (table) table.classList.toggle('mp-readonly', readOnly);
    if (gridRoot) gridRoot.classList.toggle('mp-readonly', readOnly);
    if (actionsTh) actionsTh.classList.toggle('dpr-layout-hidden', readOnly);
    if (mpSortBy === 'sl') mpSortBy = null;

    _renderRows(_sortMpRows(rows));
  }

  function _renderRows(rows) {
    const tbody = $('#mp-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    rows.forEach(r => {
      tbody.appendChild(_buildDataRow(r));
    });

    if (_canEdit()) {
      _appendEmptyRow(tbody);
      _bindEditEvents(tbody);
    }

    _applyMpTableChrome();
  }

  function _buildDataRow(r) {
    const tr = document.createElement('tr');
    tr.dataset.mpId = r.mp_id;
    const canEdit = _canEdit();
    tr.innerHTML = `
      <td data-col-name="actions" class="mp-action-cell" style="text-align:center${canEdit ? '' : ';display:none'}">
        ${canEdit
        ? `<button class="mp-delete-btn" data-mp-id="${r.mp_id}" title="Remove part">✕</button>`
        : ''}
      </td>
      <td data-col-name="part_number" title="${_esc(r.part_number)}">${_esc(r.part_number)}</td>
      <td data-col-name="part_name" title="${_esc(r.part_name)}">${_esc(r.part_name)}</td>
      <td data-col-name="production_pending" style="text-align:right">${fmt(r.production_pending)}</td>
      <td data-col-name="produced_qty" style="text-align:right">${fmt(r.produced_qty)}</td>
      <td data-col-name="additional_qty" class="${canEdit ? 'mp-edit-cell' : ''}" style="text-align:right">${canEdit
        ? `<input type="number" value="${r.additional_qty}" data-field="additional_qty" data-mp-id="${r.mp_id}" class="mp-cell-input mp-cell-input--num mp-editable-input" />`
        : fmt(r.additional_qty)}</td>
      <td data-col-name="priority" class="${canEdit ? 'mp-edit-cell' : ''}" style="text-align:center">${canEdit
        ? `<input type="number" value="${r.priority}" data-field="priority" data-mp-id="${r.mp_id}" class="mp-cell-input mp-cell-input--priority mp-editable-input" />`
        : fmt(r.priority)}</td>
      <td data-col-name="spm" style="text-align:right">${fmt(r.spm)}</td>
      <td data-col-name="max_pts_day" style="text-align:right">${fmt(r.max_parts_per_day)}</td>
      <td data-col-name="days_required" style="text-align:right">${r.days_required}</td>
      <td data-col-name="rm_code" title="${_esc(r.rm_code)}">${_esc(r.rm_code)}</td>
      <td data-col-name="remarks" class="mp-remarks-cell${canEdit ? ' mp-edit-cell' : ''}">${canEdit
        ? `<input type="text" value="${_esc(r.remarks)}" data-field="remarks" data-mp-id="${r.mp_id}" class="mp-cell-input mp-cell-input--text mp-editable-input" placeholder="Add remarks…" />`
        : _esc(r.remarks)}</td>
    `;
    return tr;
  }

  function _appendEmptyRow(tbody) {
    const tr = document.createElement('tr');
    tr.className = 'mp-new-row';
    tr.innerHTML = `
      <td data-col-name="actions"></td>
      <td data-col-name="part_number" class="mp-edit-cell">
        <input type="text" class="mp-cell-input mp-cell-input--part" id="mp-new-part-input"
               list="mp-parts-datalist" placeholder="Select part…" autocomplete="off" />
      </td>
      <td data-col-name="part_name" style="color:var(--ti-text-muted)" id="mp-new-part-name"></td>
      <td data-col-name="production_pending"></td>
      <td data-col-name="produced_qty"></td>
      <td data-col-name="additional_qty" class="mp-edit-cell" style="text-align:right">
        <input type="number" id="mp-new-addqty" class="mp-cell-input mp-cell-input--num" value="0" />
      </td>
      <td data-col-name="priority" class="mp-edit-cell" style="text-align:center">
        <input type="number" id="mp-new-priority" class="mp-cell-input mp-cell-input--priority" value="0" />
      </td>
      <td data-col-name="spm"></td>
      <td data-col-name="max_pts_day"></td>
      <td data-col-name="days_required"></td>
      <td data-col-name="rm_code"></td>
      <td data-col-name="remarks" class="mp-remarks-cell mp-edit-cell">
        <input type="text" id="mp-new-remarks" class="mp-cell-input mp-cell-input--text" value="" placeholder="Add remarks…" />
      </td>
    `;
    tbody.appendChild(tr);

    const partInput = tr.querySelector('#mp-new-part-input');
    if (partInput) {
      partInput.addEventListener('change', _onNewPartSelected);
      partInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); partInput.blur(); }
      });
      partInput.addEventListener('blur', () => {
        const v = partInput.value.trim();
        if (v) {
          const name = _partNameFor(v);
          const nameEl = tr.querySelector('#mp-new-part-name');
          if (nameEl) nameEl.textContent = name;
        }
      });
    }
  }

  // ── New part selected → auto-save to DB ───────────────────────────────
  async function _onNewPartSelected(e) {
    if (!_canEdit()) return;
    const partNumber = (e.target.value || '').trim();
    if (!partNumber || !_currentMachineId || !_currentMonth) return;

    const nameEl = $('#mp-new-part-name');
    if (nameEl) nameEl.textContent = _partNameFor(partNumber);

    const body = {
      machine_id: _currentMachineId,
      month: _currentMonth,
      part_number: partNumber,
      additional_qty: parseInt($('#mp-new-addqty')?.value) || 0,
      priority: parseInt($('#mp-new-priority')?.value) || 0,
      remarks: ($('#mp-new-remarks')?.value || '').trim(),
    };

    try {
      await apiPost('/api/machine-planning/plan', body);
      showSnackbar('Part added', 'success');
      await loadPlan();
    } catch (err) {
      showSnackbar(err.message || 'Failed to add part', 'error');
    }
  }

  // ── Bind events on data rows ──────────────────────────────────────────
  function _bindEditEvents(tbody) {
    if (!_canEdit()) return;
    tbody.querySelectorAll('tr:not(.mp-new-row) .mp-editable-input').forEach(inp => {
      inp.addEventListener('blur', _onInlineEdit);
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') inp.blur(); });
    });

    tbody.querySelectorAll('.mp-delete-btn').forEach(btn => {
      btn.addEventListener('click', _onDelete);
    });
  }

  // ── Inline edit (save on blur) ────────────────────────────────────────
  async function _onInlineEdit(e) {
    if (!_canEdit()) return;
    const inp = e.target;
    const mpId = parseInt(inp.dataset.mpId);
    const field = inp.dataset.field;
    let value = field === 'remarks' ? inp.value : parseInt(inp.value) || 0;

    try {
      await apiPatch(`/api/machine-planning/plan/${mpId}`, { [field]: value });
      if (field === 'spm' || field === 'additional_qty') {
        await loadPlan();
      }
    } catch (err) {
      showSnackbar('Failed to save: ' + err.message, 'error');
    }
  }

  // ── Delete row ────────────────────────────────────────────────────────
  async function _onDelete(e) {
    if (!_canEdit()) return;
    const mpId = parseInt(e.currentTarget.dataset.mpId);
    if (!confirm('Remove this part from the plan?')) return;
    try {
      await apiDelete(`/api/machine-planning/plan/${mpId}`);
      showSnackbar('Part removed', 'success');
      await loadPlan();
    } catch (err) {
      showSnackbar('Failed to delete: ' + err.message, 'error');
    }
  }

  // ── Column layout (DPR-style sort / resize / reorder / pin) ─────────
  function _loadMpLayout() {
    try {
      const raw = window.localStorage.getItem(MP_LAYOUT_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return;
      if (Array.isArray(parsed.order)) {
        mpLayout.order = parsed.order
          .map(x => String(x || '').trim())
          .filter(c => c && c !== 'sl');
      }
      if (Array.isArray(parsed.pinnedLeft)) {
        mpLayout.pinnedLeft = parsed.pinnedLeft
          .map(x => String(x || '').trim())
          .filter(c => c && c !== 'sl' && c !== MP_FROZEN_ACTIONS_COL);
      }
      if (parsed.widths && typeof parsed.widths === 'object') {
        mpLayout.widths = { ...parsed.widths };
        delete mpLayout.widths.sl;
        delete mpLayout.widths[MP_FROZEN_ACTIONS_COL];
      }
    } catch (_) { /* ignore */ }
  }

  function _saveMpLayout() {
    try {
      window.localStorage.setItem(MP_LAYOUT_STORAGE_KEY, JSON.stringify(mpLayout));
    } catch (_) { /* ignore */ }
  }

  function _resetMpLayout() {
    mpLayout = {
      order: _canEdit()
        ? [...MP_DEFAULT_COL_ORDER]
        : MP_DEFAULT_COL_ORDER.filter(c => c !== MP_FROZEN_ACTIONS_COL),
      pinnedLeft: [],
      widths: {},
    };
    if (mpSortBy === 'sl') mpSortBy = null;
    mpSortDir = 'asc';
    _saveMpLayout();
    if (_plan) _renderRows(_sortMpRows(_plan.rows || []));
  }

  function _mpSortValue(row, col) {
    switch (col) {
      case 'part_number': return String(row.part_number || '').toLowerCase();
      case 'part_name': return String(row.part_name || '').toLowerCase();
      case 'production_pending': return Number(row.production_pending) || 0;
      case 'produced_qty': return Number(row.produced_qty) || 0;
      case 'additional_qty': return Number(row.additional_qty) || 0;
      case 'priority': return Number(row.priority) || 0;
      case 'spm': return Number(row.spm) || 0;
      case 'max_pts_day': return Number(row.max_parts_per_day) || 0;
      case 'days_required': return Number(row.days_required) || 0;
      case 'rm_code': return String(row.rm_code || '').toLowerCase();
      case 'remarks': return String(row.remarks || '').toLowerCase();
      default: return '';
    }
  }

  function _sortMpRows(rows) {
    if (!mpSortBy || !MP_SORTABLE_COLS.has(mpSortBy)) return rows;
    const dir = mpSortDir === 'desc' ? -1 : 1;
    return [...rows].sort((a, b) => {
      const av = _mpSortValue(a, mpSortBy);
      const bv = _mpSortValue(b, mpSortBy);
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }

  function _applyMpColumnWidths(table) {
    if (!table) return;
    const wmap = mpLayout.widths || {};
    table.querySelectorAll('[data-col-name]').forEach(cell => {
      const k = String(cell.dataset.colName || '');
      const n = wmap[k];
      if (n != null && Number.isFinite(Number(n)) && Number(n) >= 40) {
        const px = `${Math.round(Number(n))}px`;
        cell.style.width = px;
        cell.style.minWidth = px;
        cell.style.maxWidth = px;
      } else {
        cell.style.width = '';
        cell.style.minWidth = '';
        cell.style.maxWidth = '';
      }
    });
  }

  function _applyMpPinnedStyles(table) {
    if (!table) return;
    table.querySelectorAll('[data-col-name]').forEach(el => {
      el.classList.remove('is-pinned-left', 'is-pinned-left-last', 'mp-actions-frozen');
      el.style.left = '';
      el.style.zIndex = '';
    });

    let left = 0;
    let pinIndex = 0;

    if (_canEdit()) {
      const actionsTh = table.querySelector('thead th[data-col-name="actions"]');
      if (actionsTh) {
        const w = actionsTh.offsetWidth || 40;
        table.querySelectorAll('[data-col-name="actions"]').forEach(c => {
          c.classList.add('is-pinned-left', 'mp-actions-frozen');
          c.style.left = '0px';
          c.style.zIndex = c.tagName === 'TH' ? '90' : '30';
        });
        left += w;
        pinIndex += 1;
      }
    }

    const headerPinned = Array.from(table.querySelectorAll('thead th[data-col-name]'))
      .filter(th => {
        const name = String(th.dataset.colName || '');
        return name !== MP_FROZEN_ACTIONS_COL && mpLayout.pinnedLeft.includes(name);
      });

    headerPinned.forEach((th) => {
      const name = String(th.dataset.colName || '');
      const w = th.offsetWidth || 0;
      table.querySelectorAll(`[data-col-name="${name}"]`).forEach(c => {
        c.classList.add('is-pinned-left');
        c.style.left = `${left}px`;
        c.style.zIndex = c.tagName === 'TH' ? String(90 - pinIndex) : String(30 - pinIndex);
      });
      left += w;
      pinIndex += 1;
    });

    const lastPinnedName = headerPinned.length
      ? String(headerPinned[headerPinned.length - 1].dataset.colName || '')
      : (_canEdit() ? MP_FROZEN_ACTIONS_COL : null);
    if (lastPinnedName) {
      table.querySelectorAll(`[data-col-name="${lastPinnedName}"]`)
        .forEach(c => c.classList.add('is-pinned-left-last'));
    }
  }

  function _applyMpColumnLayout() {
    const table = $('#mp-table');
    if (!table) return;
    const headerRow = table.querySelector('thead tr');
    if (!headerRow) return;
    const editable = _canEdit();
    const ths = Array.from(headerRow.querySelectorAll('th[data-col-name]'));
    const allColNames = ths
      .map(th => String(th.dataset.colName || ''))
      .filter(c => c && c !== 'sl');
    mpLayout.order = mpLayout.order.filter(c => c !== 'sl' && c !== MP_FROZEN_ACTIONS_COL);
    mpLayout.pinnedLeft = mpLayout.pinnedLeft.filter(c => c !== 'sl' && c !== MP_FROZEN_ACTIONS_COL);
    if (!editable) mpLayout.order = mpLayout.order.filter(c => c !== MP_FROZEN_ACTIONS_COL);
    const dataColNames = allColNames.filter(c => c !== MP_FROZEN_ACTIONS_COL);
    let order = [
      ...mpLayout.order.filter(c => dataColNames.includes(c)),
      ...dataColNames.filter(c => !mpLayout.order.includes(c)),
    ];
    const pinned = order.filter(c => mpLayout.pinnedLeft.includes(c));
    const unpinned = order.filter(c => !mpLayout.pinnedLeft.includes(c));
    order = [...pinned, ...unpinned];
    order = [MP_FROZEN_ACTIONS_COL, ...order];
    mpLayout.order = order;
    headerRow.innerHTML = '';
    order.forEach(name => {
      const th = ths.find(x => String(x.dataset.colName || '') === name);
      if (th) {
        if (name === MP_FROZEN_ACTIONS_COL) {
          th.classList.toggle('dpr-layout-hidden', !editable);
        }
        headerRow.appendChild(th);
      }
    });

    table.querySelectorAll('tbody tr').forEach(tr => {
      const tds = Array.from(tr.querySelectorAll('td[data-col-name]'));
      const map = new Map(tds.map(td => [String(td.dataset.colName || ''), td]));
      tds.forEach(td => td.remove());
      order.forEach(name => {
        const td = map.get(name);
        if (td) {
          if (!editable && name === MP_FROZEN_ACTIONS_COL) {
            td.style.display = 'none';
          }
          tr.appendChild(td);
        }
      });
    });

    _applyMpColumnWidths(table);
    _applyMpPinnedStyles(table);
    _saveMpLayout();
  }

  function _updateMpSortIndicators() {
    const table = $('#mp-table');
    if (!table) return;
    table.querySelectorAll('thead th[data-col-name]').forEach(th => {
      const c = String(th.dataset.colName || '');
      th.classList.remove('dpr-th-sorted-asc', 'dpr-th-sorted-desc');
      let ind = th.querySelector('.dpr-sort-ind');
      if (!MP_SORTABLE_COLS.has(c)) {
        if (ind) ind.textContent = '';
        return;
      }
      if (!ind) {
        ind = document.createElement('span');
        ind.className = 'dpr-sort-ind';
        ind.setAttribute('aria-hidden', 'true');
        th.appendChild(ind);
      }
      if (mpSortBy === c) {
        th.classList.add(mpSortDir === 'desc' ? 'dpr-th-sorted-desc' : 'dpr-th-sorted-asc');
        ind.textContent = mpSortDir === 'desc' ? ' ▼' : ' ▲';
      } else {
        ind.textContent = '';
      }
    });
  }

  function _wireMpHeaderControls() {
    const table = $('#mp-table');
    if (!table) return;
    const editable = _canEdit();
    table.querySelectorAll('thead th[data-col-name]').forEach(th => {
      const col = String(th.dataset.colName || '');
      if (!col) return;
      const isFrozenActions = col === MP_FROZEN_ACTIONS_COL;
      if (isFrozenActions) {
        th.removeAttribute('draggable');
        th.querySelector('.pin-toggle-btn')?.remove();
        th.querySelector('.dpr-col-resize')?.remove();
        th.ondragstart = null;
        th.ondragend = null;
        th.ondragover = null;
        th.ondragleave = null;
        th.ondrop = null;
        return;
      }
      th.setAttribute('draggable', 'true');

      if (!th.querySelector('.pin-toggle-btn')) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pin-toggle-btn';
        btn.title = 'Pin column to left';
        btn.setAttribute('aria-label', 'Pin column to left');
        btn.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 3h6v3l2 3v3H7V9l2-3V3zM12 12v9" /></svg>`;
        btn.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          const pinned = mpLayout.pinnedLeft.includes(col);
          mpLayout.pinnedLeft = pinned
            ? mpLayout.pinnedLeft.filter(x => x !== col)
            : [...mpLayout.pinnedLeft, col];
          _applyMpColumnLayout();
          _wireMpHeaderControls();
          _wireMpColumnSort();
        });
        th.insertBefore(btn, th.firstChild);
      }

      if (!th.querySelector('.dpr-col-resize')) {
        const rz = document.createElement('div');
        rz.className = 'dpr-col-resize';
        rz.dataset.col = col;
        rz.title = 'Drag to resize column';
        rz.addEventListener('mousedown', e => {
          e.preventDefault();
          e.stopPropagation();
          mpResizeDrag = { col, startX: e.pageX, origW: th.offsetWidth || 120 };
          document.body.classList.add('dpr-col-resizing');
        });
        th.appendChild(rz);
      }

      const pinBtn = th.querySelector('.pin-toggle-btn');
      if (pinBtn) pinBtn.classList.toggle('is-pinned', mpLayout.pinnedLeft.includes(col));

      th.ondragstart = e => {
        if (col === MP_FROZEN_ACTIONS_COL) return;
        if (e.target?.closest?.('.pin-toggle-btn')) return;
        if (e.target?.closest?.('.dpr-col-resize')) { e.preventDefault(); return; }
        mpDragCol = col;
        th.classList.add('is-dragging');
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
      };
      th.ondragend = () => {
        mpDragCol = null;
        th.classList.remove('is-dragging');
        table.querySelectorAll('th').forEach(h => h.classList.remove('drag-over'));
      };
      th.ondragover = e => {
        if (!mpDragCol || mpDragCol === col) return;
        e.preventDefault();
        th.classList.add('drag-over');
      };
      th.ondragleave = () => th.classList.remove('drag-over');
      th.ondrop = e => {
        if (!mpDragCol || mpDragCol === col || mpDragCol === MP_FROZEN_ACTIONS_COL) return;
        e.preventDefault();
        th.classList.remove('drag-over');
        const order = [...mpLayout.order].filter(c => c !== MP_FROZEN_ACTIONS_COL);
        const from = order.indexOf(mpDragCol);
        const to = order.indexOf(col);
        if (from < 0 || to < 0 || from === to) return;
        const [item] = order.splice(from, 1);
        order.splice(to, 0, item);
        mpLayout.order = editable ? [MP_FROZEN_ACTIONS_COL, ...order] : order;
        _applyMpColumnLayout();
        _wireMpHeaderControls();
        _wireMpColumnSort();
      };
    });
  }

  function _wireMpColumnSort() {
    const table = $('#mp-table');
    if (!table) return;
    table.querySelectorAll('thead th[data-col-name]').forEach(th => {
      const col = String(th.dataset.colName || '');
      if (!MP_SORTABLE_COLS.has(col)) return;
      if (th.dataset.mpSortWired === '1') return;
      th.dataset.mpSortWired = '1';
      th.addEventListener('click', e => {
        if (e.target?.closest?.('.pin-toggle-btn')) return;
        if (e.target?.closest?.('.dpr-col-resize')) return;
        e.preventDefault();
        if (mpSortBy === col) {
          if (mpSortDir === 'asc') mpSortDir = 'desc';
          else { mpSortBy = null; mpSortDir = 'asc'; }
        } else {
          mpSortBy = col;
          mpSortDir = 'asc';
        }
        _updateMpSortIndicators();
        if (_plan) _renderRows(_sortMpRows(_plan.rows || []));
      });
    });
  }

  function _attachMpResizeGlobals() {
    if (_attachMpResizeGlobals._done) return;
    _attachMpResizeGlobals._done = true;
    document.addEventListener('mousemove', e => {
      if (!mpResizeDrag) return;
      const table = $('#mp-table');
      if (!table) return;
      const delta = e.pageX - mpResizeDrag.startX;
      const newW = Math.max(60, mpResizeDrag.origW + delta);
      if (!mpLayout.widths || typeof mpLayout.widths !== 'object') mpLayout.widths = {};
      mpLayout.widths[mpResizeDrag.col] = newW;
      _applyMpColumnWidths(table);
      _applyMpPinnedStyles(table);
    });
    document.addEventListener('mouseup', () => {
      if (!mpResizeDrag) return;
      mpResizeDrag = null;
      document.body.classList.remove('dpr-col-resizing');
      _saveMpLayout();
      const table = $('#mp-table');
      if (table) _applyMpPinnedStyles(table);
    });
  }

  function _applyMpTableChrome() {
    _applyMpColumnLayout();
    _wireMpHeaderControls();
    _wireMpColumnSort();
    _updateMpSortIndicators();
  }

  // ── Export to Excel ──────────────────────────────────────────────────
  function _exportExcel() {
    const month = $('#mp-month-input')?.value;
    if (!month) {
      showSnackbar('Select a month first', 'warning');
      return;
    }
    window.location.href = `/api/machine-planning/export?month=${encodeURIComponent(month)}`;
  }

  // ── Helpers ───────────────────────────────────────────────────────────
  function _showLoading(show) {
    const el = $('#mp-loading');
    const empty = $('#mp-empty-state');
    if (el) el.style.display = show ? '' : 'none';
    if (show && empty) empty.style.display = 'none';
  }

  function _setText(sel, val) {
    const el = $(sel);
    if (el) el.textContent = val;
  }

  function _esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function _formatMonthLabel(ym) {
    const [y, m] = ym.split('-');
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(m) - 1] || m} ${y}`;
  }

  function _formatDate(dt) {
    if (!dt) return '–';
    const d = new Date(dt);
    if (isNaN(d.getTime())) return String(dt);
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yy = d.getFullYear();
    return `${dd}-${mm}-${yy}`;
  }

  return { init };
})();
