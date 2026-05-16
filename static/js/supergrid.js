/* ═══════════════════════════════════════════════════════════════════════════
   SUPERGRID.JS — Unified Excel-like Data Table Component
   Sorting · Search · Column Pinning · Resize · Drag Reorder · Export
   Drop-in for all hub sections — replaces both DataGrid and DataTable
   ═══════════════════════════════════════════════════════════════════════════ */

const SuperGrid = (() => {
  let _uid = 0;
  function uid() { return `sg-${++_uid}`; }

  /**
   * Create a SuperGrid instance.
   *
   * @param {HTMLElement} container — DOM element to render into
   * @param {Object} config
   * @param {Array<Object>} config.columns — Column definitions
   *   { key, label, align?:'left'|'right'|'center', sortable?:boolean,
   *     format?:(val,row,idx)=>string|HTMLElement, className?:string|Function,
   *     width?:number, pinned?:boolean }
   * @param {Array<Object>} config.rows — Data row objects
   * @param {Object} [config.options]
   *   { search:boolean, exportBtn:boolean, exportFn:Function,
   *     emptyText:string, countLabel:string,
   *     onRowClick?:(row,idx)=>void, extraToolbar?:string,
   *     statusText?:string|Function, pagination?:boolean, pageSize?:number,
   *     resizable?:boolean, pinnable?:boolean, reorderable?:boolean,
   *     layoutKey?:string,
   *     omitToolbar?:boolean (may also be set on the top-level config object),
   *     countElement?:HTMLElement, searchInputElement?:HTMLElement,
   *     detailRowExpanded?:(row,rowIdx)=>boolean,
   *     detailRowHtml?:(row,rowIdx,colCount)=>string,
   *     onBodyRendered?:(tbody,rows)=>void,
   *     grandTotalRowFn?:(dataRows,columns)=>Object|null }
   * @returns {Object} API { setRows, getFilteredRows, destroy }
   */
  function create(container, config) {
    const { columns: _cols = [], rows: _origRows = [], options = {} } = config;
    const {
      search = true,
      exportBtn = false,
      exportFn = null,
      emptyText = 'No data available',
      countLabel = 'rows',
      onRowClick = null,
      extraToolbar = '',
      statusText = null,
      pagination = false,
      pageSize: defaultPageSize = 25,
      resizable = true,
      pinnable = true,
      reorderable = true,
      layoutKey = null,
      countElement: countElementOption = null,
      searchInputElement: searchInputElementOption = null,
      detailRowExpanded = null,
      detailRowHtml = null,
      onBodyRendered = null,
      grandTotalRowFn = null,
    } = options;

    /* Support both SuperGrid.create(el, { options: { omitToolbar } }) and flat { omitToolbar } */
    const omitToolbar = Boolean(options.omitToolbar ?? config.omitToolbar);

    const id = uid();
    let allRows = [..._origRows];
    let filteredRows = [...allRows];
    let displayRows = [];
    let sortKey = null;
    let sortDir = 'asc';
    let searchQuery = '';
    let currentPage = 1;
    let pageSize = defaultPageSize;

    // Column layout state
    let columnOrder = _cols.map(c => c.key);
    let pinnedKeys = new Set(_cols.filter(c => c.pinned).map(c => c.key));
    let colWidths = {};
    _cols.forEach(c => { if (c.width) colWidths[c.key] = c.width; });

    // Restore saved layout
    _restoreLayout();

    // Resize state
    let resizing = null;
    let dragCol = null;

    container.innerHTML = '';
    container.classList.add('sg-host');
    if (omitToolbar) container.classList.add('sg-host--no-toolbar');

    // ── Toolbar (optional — use countElement / searchInputElement when omitted) ──
    let countEl = null;
    let searchInput = null;
    let exportBtnEl = null;
    if (!omitToolbar) {
      const toolbar = _el('div', 'sg-toolbar');
      toolbar.innerHTML = `
        <div class="sg-toolbar-left">
          ${extraToolbar}
          <span class="sg-count" id="cnt-${id}"></span>
        </div>
        <div class="sg-toolbar-right">
          ${search ? `<input type="text" class="sg-search" placeholder="Search all columns…" />` : ''}
          ${exportBtn ? `<button class="sg-export-btn">⬇ Export</button>` : ''}
        </div>
      `;
      container.appendChild(toolbar);
      countEl = toolbar.querySelector('.sg-count');
      searchInput = toolbar.querySelector('.sg-search');
      exportBtnEl = toolbar.querySelector('.sg-export-btn');
    } else {
      if (countElementOption) countEl = countElementOption;
      if (searchInputElementOption) searchInput = searchInputElementOption;
    }

    // ── Table wrapper ──────────────────────────────────────────
    const wrap = _el('div', 'sg-wrap');
    const scroll = _el('div', 'sg-scroll');
    const table = document.createElement('table');
    table.className = 'sg-table';
    const thead = document.createElement('thead');
    const tbody = document.createElement('tbody');
    table.appendChild(thead);
    table.appendChild(tbody);
    scroll.appendChild(table);
    wrap.appendChild(scroll);
    container.appendChild(wrap);

    // ── Pagination bar ─────────────────────────────────────────
    let pagBar = null;
    let pagInfo = null;
    let pagBtns = null;
    let pagSizeSelect = null;
    if (pagination) {
      pagBar = _el('div', 'sg-pagination');
      pagBar.innerHTML = `
        <div class="sg-pag-left">
          <label class="sg-pag-label">Rows
            <select class="sg-pag-size">
              <option value="10">10</option>
              <option value="25" ${defaultPageSize === 25 ? 'selected' : ''}>25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="-1">All</option>
            </select>
          </label>
        </div>
        <div class="sg-pag-center">
          <button class="sg-pag-btn" data-act="first">« First</button>
          <button class="sg-pag-btn" data-act="prev">‹ Prev</button>
          <span class="sg-pag-info"></span>
          <button class="sg-pag-btn" data-act="next">Next ›</button>
          <button class="sg-pag-btn" data-act="last">Last »</button>
        </div>
        <div class="sg-pag-right">
          <span class="sg-pag-summary"></span>
        </div>
      `;
      container.appendChild(pagBar);
      pagInfo = pagBar.querySelector('.sg-pag-info');
      pagBtns = pagBar.querySelectorAll('.sg-pag-btn');
      pagSizeSelect = pagBar.querySelector('.sg-pag-size');
      pagSizeSelect.value = String(defaultPageSize);

      pagSizeSelect.addEventListener('change', () => {
        pageSize = parseInt(pagSizeSelect.value);
        currentPage = 1;
        _paginate();
        _renderBody();
      });
      pagBtns.forEach(btn => btn.addEventListener('click', () => {
        const totalPages = _totalPages();
        switch (btn.dataset.act) {
          case 'first': currentPage = 1; break;
          case 'prev': currentPage = Math.max(1, currentPage - 1); break;
          case 'next': currentPage = Math.min(totalPages, currentPage + 1); break;
          case 'last': currentPage = totalPages; break;
        }
        _paginate();
        _renderBody();
      }));
    }

    // ── Search ─────────────────────────────────────────────────
    let searchDebounce = null;
    function _onSearchInput() {
      if (!searchInput) return;
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        searchQuery = searchInput.value.trim().toLowerCase();
        currentPage = 1;
        _filter();
        _sort();
        _paginate();
        _renderBody();
      }, 180);
    }
    if (searchInput) searchInput.addEventListener('input', _onSearchInput);

    // ── Export ──────────────────────────────────────────────────
    if (exportBtnEl && exportFn) {
      exportBtnEl.addEventListener('click', () => exportFn(filteredRows, _getOrderedCols()));
    }

    // ── Global mouse handlers for resize ───────────────────────
    function _onMouseMove(e) {
      if (!resizing) return;
      const delta = e.pageX - resizing.startX;
      const newW = Math.max(80, resizing.startW + delta);
      _applyColWidth(resizing.key, newW);
    }
    function _onMouseUp() {
      if (!resizing) return;
      resizing = null;
      document.body.classList.remove('sg-resizing');
      _saveLayout();
    }
    document.addEventListener('mousemove', _onMouseMove);
    document.addEventListener('mouseup', _onMouseUp);

    // ── Scroll sync for pinned ─────────────────────────────────
    function _onScrollOrResize() { requestAnimationFrame(_syncPinnedOffsets); }
    scroll.addEventListener('scroll', _onScrollOrResize);
    window.addEventListener('resize', _onScrollOrResize);

    // ── Column ordering ────────────────────────────────────────
    function _getOrderedCols() {
      const colMap = new Map(_cols.map(c => [c.key, c]));
      const pinned = columnOrder.filter(k => pinnedKeys.has(k)).map(k => colMap.get(k)).filter(Boolean);
      const unpinned = columnOrder.filter(k => !pinnedKeys.has(k)).map(k => colMap.get(k)).filter(Boolean);
      return [...pinned, ...unpinned];
    }

    function _isSyntheticRow(row) {
      return !!(row && (row.__sgStickyTop || row.__sgStickyBottom));
    }

    function _appendGrandTotalRow() {
      filteredRows = filteredRows.filter(r => !r.__sgStickyBottom);
      if (!grandTotalRowFn || !filteredRows.length) return;
      const gt = grandTotalRowFn(filteredRows, _getOrderedCols());
      if (gt) {
        gt.__sgStickyBottom = true;
        filteredRows.push(gt);
      }
    }

    // ── Filter ─────────────────────────────────────────────────
    function _filter() {
      const sourceRows = allRows.filter(r => !_isSyntheticRow(r));
      if (!searchQuery) {
        filteredRows = [...sourceRows];
      } else {
        filteredRows = sourceRows.filter(row =>
          _cols.some(col => {
            const v = row[col.key];
            return v != null && String(v).toLowerCase().includes(searchQuery);
          })
        );
      }
      _appendGrandTotalRow();
    }

    // ── Sort ───────────────────────────────────────────────────
    function _sort() {
      if (!sortKey) return;
      filteredRows.sort((a, b) => {
        // Optional sticky-top rows (e.g., Grand Total) must remain first across sorting.
        const aStickyTop = !!(a && a.__sgStickyTop);
        const bStickyTop = !!(b && b.__sgStickyTop);
        if (aStickyTop !== bStickyTop) return aStickyTop ? -1 : 1;
        // Optional sticky-bottom rows (e.g., column totals) stay last.
        const aStickyBottom = !!(a && a.__sgStickyBottom);
        const bStickyBottom = !!(b && b.__sgStickyBottom);
        if (aStickyBottom !== bStickyBottom) return aStickyBottom ? 1 : -1;

        let va = a[sortKey], vb = b[sortKey];
        const na = Number(va), nb = Number(vb);
        if (!isNaN(na) && !isNaN(nb) && va !== '' && vb !== '') {
          return sortDir === 'asc' ? na - nb : nb - na;
        }
        va = String(va ?? '').toLowerCase();
        vb = String(vb ?? '').toLowerCase();
        if (va < vb) return sortDir === 'asc' ? -1 : 1;
        if (va > vb) return sortDir === 'asc' ? 1 : -1;
        return 0;
      });
    }

    // ── Paginate ───────────────────────────────────────────────
    function _totalPages() {
      if (!pagination || pageSize <= 0) return 1;
      return Math.max(1, Math.ceil(filteredRows.length / pageSize));
    }
    function _paginate() {
      if (!pagination || pageSize <= 0) {
        displayRows = filteredRows;
        return;
      }
      const start = (currentPage - 1) * pageSize;
      displayRows = filteredRows.slice(start, start + pageSize);
    }

    // ── Render Header ──────────────────────────────────────────
    function _renderHead() {
      const cols = _getOrderedCols();
      let html = '<tr>';
      cols.forEach(col => {
        const isPinned = pinnedKeys.has(col.key);
        const isSorted = sortKey === col.key;
        const sortable = col.sortable !== false;
        const w = colWidths[col.key] || col.width;
        const style = w ? ` style="width:${w}px;min-width:${w}px;max-width:${w}px"` : '';
        const pinCls = isPinned ? ' sg-pinned' : '';
        const dragAttr = reorderable && !isPinned ? ' draggable="true"' : '';

        html += `<th data-key="${col.key}" class="${pinCls}"${style}${dragAttr}>`;
        html += `<div class="sg-hdr-cell">`;

        // Pin button
        if (pinnable) {
          html += `<button class="sg-pin-btn${isPinned ? ' active' : ''}" data-key="${col.key}" title="${isPinned ? 'Unpin' : 'Pin left'}">
            <svg viewBox="0 0 24 24"><path d="M9 3h6v3l2 3v3H7V9l2-3V3zM12 12v9"/></svg>
          </button>`;
        }

        html += `<span class="sg-hdr-title">${col.label}</span>`;

        // Sort indicator
        if (sortable) {
          html += `<span class="sg-sort${isSorted ? ' active' : ''}">${isSorted ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}</span>`;
        }

        html += `</div>`;

        // Resize handle
        if (resizable) {
          html += `<div class="sg-resize" data-key="${col.key}"></div>`;
        }

        html += `</th>`;
      });
      html += '</tr>';
      thead.innerHTML = html;

      // Wire sort
      thead.querySelectorAll('.sg-hdr-cell').forEach(cell => {
        cell.addEventListener('click', (e) => {
          if (e.target.closest('.sg-pin-btn')) return;
          const th = cell.closest('th');
          const key = th?.dataset?.key;
          if (!key) return;
          const col = _cols.find(c => c.key === key);
          if (!col || col.sortable === false) return;
          if (sortKey === key) {
            sortDir = sortDir === 'asc' ? 'desc' : 'asc';
          } else {
            sortKey = key;
            sortDir = 'asc';
          }
          currentPage = 1;
          _sort();
          _paginate();
          _renderHead();
          _renderBody();
        });
      });

      // Wire pin
      thead.querySelectorAll('.sg-pin-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const key = btn.dataset.key;
          if (pinnedKeys.has(key)) pinnedKeys.delete(key);
          else pinnedKeys.add(key);
          _renderHead();
          _renderBody();
          _saveLayout();
        });
      });

      // Wire resize
      if (resizable) {
        thead.querySelectorAll('.sg-resize').forEach(handle => {
          handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const th = handle.closest('th');
            resizing = {
              key: handle.dataset.key,
              startX: e.pageX,
              startW: th.offsetWidth,
            };
            document.body.classList.add('sg-resizing');
          });
        });
      }

      // Wire drag reorder
      if (reorderable) {
        thead.querySelectorAll('th[draggable="true"]').forEach(th => {
          th.addEventListener('dragstart', (e) => {
            if (e.target.closest('.sg-resize') || e.target.closest('.sg-pin-btn')) {
              e.preventDefault();
              return;
            }
            dragCol = th.dataset.key;
            th.classList.add('sg-dragging');
          });
          th.addEventListener('dragend', () => {
            dragCol = null;
            th.classList.remove('sg-dragging');
            thead.querySelectorAll('.sg-drop-target').forEach(el => el.classList.remove('sg-drop-target'));
          });
          th.addEventListener('dragover', (e) => {
            if (!dragCol) return;
            e.preventDefault();
            th.classList.add('sg-drop-target');
          });
          th.addEventListener('dragleave', () => {
            th.classList.remove('sg-drop-target');
          });
          th.addEventListener('drop', (e) => {
            e.preventDefault();
            th.classList.remove('sg-drop-target');
            const target = th.dataset.key;
            if (!dragCol || dragCol === target) return;
            const from = columnOrder.indexOf(dragCol);
            const to = columnOrder.indexOf(target);
            if (from < 0 || to < 0) return;
            const [item] = columnOrder.splice(from, 1);
            columnOrder.splice(to, 0, item);
            _renderHead();
            _renderBody();
            _saveLayout();
          });
        });
      }

      requestAnimationFrame(_syncPinnedOffsets);
    }

    // ── Render Body ────────────────────────────────────────────
    function _renderBody() {
      const cols = _getOrderedCols();
      const rows = pagination ? displayRows : filteredRows;

      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="${cols.length}" class="sg-empty">${emptyText}</td></tr>`;
        _updateMeta();
        return;
      }

      const globalOffset = pagination ? (currentPage - 1) * pageSize : 0;
      let html = '';
      rows.forEach((row, i) => {
        const clickCls = onRowClick ? ' sg-clickable' : '';
        const stickyTopCls = row && row.__sgStickyTop ? ' sg-sticky-top-row' : '';
        const stickyBottomCls = row && row.__sgStickyBottom ? ' sg-sticky-bottom-row' : '';
        const stickyTopAttr = row && row.__sgStickyTop ? ' data-sg-sticky-top="1"' : '';
        html += `<tr data-idx="${i}" class="${clickCls}${stickyTopCls}${stickyBottomCls}"${stickyTopAttr}>`;
        cols.forEach(col => {
          const raw = row[col.key];
          let display;
          if (col.format) {
            const result = col.format(raw, row, globalOffset + i);
            display = result instanceof HTMLElement ? result.outerHTML : (result ?? '—');
          } else {
            if (raw == null) display = '—';
            else {
              const n = Number(raw);
              display = (!isNaN(n) && raw !== '' && col.align === 'right')
                ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
                : String(raw);
            }
          }
          const isPinned = pinnedKeys.has(col.key);
          const pinCls = isPinned ? ' sg-pinned' : '';
          const alignCls = col.align === 'right' ? ' sg-r' : col.align === 'center' ? ' sg-c' : '';
          const extraCls = col.className
            ? ` ${typeof col.className === 'function' ? col.className(raw, row) : col.className}`
            : '';
          const w = colWidths[col.key];
          const style = w ? ` style="width:${w}px;min-width:${w}px;max-width:${w}px"` : '';
          html += `<td data-key="${col.key}" class="${pinCls}${alignCls}${extraCls}"${style}>${display}</td>`;
        });
        html += '</tr>';
        if (detailRowExpanded && detailRowHtml && detailRowExpanded(row, globalOffset + i)) {
          const detailContent = detailRowHtml(row, globalOffset + i, cols.length);
          const detailKey = row && (row._rowKey != null ? String(row._rowKey) : '');
          const detailKeyAttr = detailKey
            ? ` data-detail-key="${detailKey.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"`
            : '';
          html += `<tr class="sg-detail-row" data-idx="${i}"${detailKeyAttr}><td colspan="${cols.length}" class="sg-detail-cell">${detailContent}</td></tr>`;
        }
      });
      tbody.innerHTML = html;

      if (onBodyRendered) onBodyRendered(tbody, rows);

      // Row click
      if (onRowClick) {
        tbody.querySelectorAll('tr[data-idx]').forEach(tr => {
          tr.addEventListener('click', () => {
            const idx = parseInt(tr.dataset.idx);
            const actualRow = rows[idx];
            if (actualRow) onRowClick(actualRow, globalOffset + idx);
          });
        });
      }

      _updateMeta();
      requestAnimationFrame(_syncPinnedOffsets);
    }

    // ── Pinned offset sync ─────────────────────────────────────
    function _syncPinnedOffsets() {
      // Clean up unpinned cells that may have stale inline styles from a previous pin
      table.querySelectorAll('th[data-key], td[data-key]').forEach(cell => {
        if (!cell.classList.contains('sg-pinned')) {
          cell.style.left = '';
          cell.style.zIndex = '';
          cell.classList.remove('sg-pinned-last');
        }
      });

      const cols = _getOrderedCols();
      const pinnedCols = cols.filter(c => pinnedKeys.has(c.key));
      if (!pinnedCols.length) return;

      // Compute each pinned column's left offset as the cumulative width of
      // all preceding pinned columns.  This avoids measuring offsetLeft on
      // sticky elements (which is unreliable) and keeps headers + body cells
      // perfectly aligned regardless of scroll position.
      let cumulativeLeft = 0;
      pinnedCols.forEach((col, idx) => {
        const key = col.key;
        const allCells = table.querySelectorAll(`th[data-key="${key}"], td[data-key="${key}"]`);
        if (!allCells.length) return;

        // Determine rendered width from the header cell
        const th = thead.querySelector(`th[data-key="${key}"]`);
        const cellWidth = th
          ? (colWidths[key] || th.getBoundingClientRect().width || th.offsetWidth)
          : (colWidths[key] || 120);
        const roundedWidth = Math.max(0, Math.round(cellWidth));

        allCells.forEach(cell => {
          cell.style.left = `${cumulativeLeft}px`;
          const stickyTopRow = !!(cell.closest && cell.closest('tr.sg-sticky-top-row'));
          if (cell.tagName === 'TH') {
            cell.style.zIndex = String(120 - idx);
          } else {
            cell.style.zIndex = String(stickyTopRow ? (180 - idx) : (60 - idx));
          }
        });

        cumulativeLeft += roundedWidth;
      });

      // Mark the last pinned column for the right-edge shadow
      const lastKey = pinnedCols[pinnedCols.length - 1].key;
      table.querySelectorAll('.sg-pinned').forEach(cell => {
        cell.classList.toggle('sg-pinned-last', cell.dataset?.key === lastKey);
      });
    }

    // ── Apply column width ─────────────────────────────────────
    function _applyColWidth(key, width) {
      const px = Math.max(60, Math.min(1200, Math.round(width)));
      colWidths[key] = px;
      const cells = table.querySelectorAll(`th[data-key="${key}"], td[data-key="${key}"]`);
      cells.forEach(el => {
        el.style.width = `${px}px`;
        el.style.minWidth = `${px}px`;
        el.style.maxWidth = `${px}px`;
      });
      requestAnimationFrame(_syncPinnedOffsets);
    }

    // ── Meta/count update ──────────────────────────────────────
    function _updateMeta() {
      const total = allRows.filter(r => !_isSyntheticRow(r)).length;
      const filtered = filteredRows.filter(r => !_isSyntheticRow(r)).length;
      if (countEl) {
        countEl.textContent = filtered === total
          ? `${total} ${countLabel}`
          : `${filtered} of ${total} ${countLabel}`;
      }

      if (pagination && pagBar) {
        const tp = _totalPages();
        pagInfo.textContent = `Page ${currentPage} of ${tp}`;
        pagBtns.forEach(btn => {
          switch (btn.dataset.act) {
            case 'first': case 'prev': btn.disabled = currentPage <= 1; break;
            case 'next': case 'last': btn.disabled = currentPage >= tp; break;
          }
        });
        const summary = pagBar.querySelector('.sg-pag-summary');
        if (summary) {
          const start = Math.min(filtered, (currentPage - 1) * (pageSize > 0 ? pageSize : filtered) + 1);
          const end = Math.min(filtered, pageSize > 0 ? currentPage * pageSize : filtered);
          summary.textContent = `${start.toLocaleString('en-IN')}–${end.toLocaleString('en-IN')} of ${filtered.toLocaleString('en-IN')}`;
        }
      }

      if (statusText) {
        // Totals / status strip — sibling of .sg-wrap so the scroll area can flex above it
        let statusEl = container.querySelector('.sg-status');
        if (!statusEl) {
          statusEl = _el('div', 'sg-status');
          container.appendChild(statusEl);
        }
        statusEl.innerHTML = typeof statusText === 'function' ? statusText(filteredRows, allRows) : statusText;
      }
    }

    // ── Layout persistence ─────────────────────────────────────
    function _saveLayout() {
      if (!layoutKey) return;
      try {
        const data = {
          order: columnOrder,
          pinned: [...pinnedKeys],
          widths: colWidths,
        };
        localStorage.setItem(`sg_layout_v3_${layoutKey}`, JSON.stringify(data));
      } catch (e) { /* no-op */ }
    }

    function _restoreLayout() {
      if (!layoutKey) return;
      try {
        const raw = localStorage.getItem(`sg_layout_v3_${layoutKey}`);
        if (!raw) return;
        const data = JSON.parse(raw);
        if (Array.isArray(data.order)) {
          // Merge: keep saved order, append new columns, remove deleted ones
          const validKeys = new Set(_cols.map(c => c.key));
          const restored = data.order.filter(k => validKeys.has(k));
          const remaining = _cols.map(c => c.key).filter(k => !restored.includes(k));
          columnOrder = [...restored, ...remaining];
        }
        if (Array.isArray(data.pinned)) pinnedKeys = new Set(data.pinned.filter(k => _cols.some(c => c.key === k)));
        if (data.widths && typeof data.widths === 'object') colWidths = { ...colWidths, ...data.widths };
      } catch (e) { /* no-op */ }
    }

    // ── Helpers ─────────────────────────────────────────────────
    function _el(tag, cls) {
      const el = document.createElement(tag);
      el.className = cls;
      return el;
    }

    // ── Initial render ─────────────────────────────────────────
    _filter();
    _sort();
    _paginate();
    _renderHead();
    _renderBody();

    // Capture initial natural widths so resizing one column doesn't squish others
    requestAnimationFrame(() => {
      let changed = false;
      _cols.forEach(col => {
        if (!colWidths[col.key]) {
          const th = thead.querySelector(`th[data-key="${col.key}"]`);
          if (th && th.offsetWidth) {
            colWidths[col.key] = th.offsetWidth;
            changed = true;
          }
        }
      });
      // Apply the captured widths to inline styles so table-layout: fixed behaves reliably
      if (changed) {
        _cols.forEach(col => {
           if (colWidths[col.key]) _applyColWidth(col.key, colWidths[col.key]);
        });
        _saveLayout();
      }
    });

    // ── Public API ─────────────────────────────────────────────
    return {
      /** Replace all data and re-render */
      setRows(newRows) {
        allRows = [...newRows];
        searchQuery = '';
        if (searchInput) searchInput.value = '';
        currentPage = 1;
        _filter();
        _sort();
        _paginate();
        _renderHead();
        _renderBody();
      },
      /** Get current filtered (and sorted) rows */
      getFilteredRows() { return [...filteredRows]; },
      /** Re-render tbody only (keeps sort, filter, search, column layout) */
      redrawBody() { _renderBody(); },
      /** Cleanup listeners */
      destroy() {
        document.removeEventListener('mousemove', _onMouseMove);
        document.removeEventListener('mouseup', _onMouseUp);
        window.removeEventListener('resize', _onScrollOrResize);
        if (searchInput) searchInput.removeEventListener('input', _onSearchInput);
      },
    };
  }

  return { create };
})();
