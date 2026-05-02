/* ═══════════════════════════════════════════════════════════════════════════
   DATAGRID.JS — Generic reusable Excel-style data table component
   Used across Production, Inventory, Maintenance, RM Variance for consistency
   ═══════════════════════════════════════════════════════════════════════════ */

const DataGrid = (() => {
  /**
   * Render a consistent data grid into a container.
   *
   * @param {HTMLElement} container - DOM element to render into
   * @param {Object} config
   * @param {Array<Object>} config.columns - Column definitions
   *   { key, label, align?:'left'|'right'|'center', sortable?:boolean,
   *     format?:(val,row)=>string|HTMLElement, className?:string, width?:string }
   * @param {Array<Object>} config.rows - Data rows
   * @param {Object} [config.options]
   *   { search:boolean, export:boolean, exportFn:Function,
   *     emptyText:string, countLabel:string, onRowClick?:(row,idx)=>void,
   *     extraToolbar?:string, statusText?:string|Function }
   */
  function render(container, config) {
    const { columns = [], rows = [], options = {} } = config;
    const {
      search = true,
      exportBtn = false,
      exportFn = null,
      emptyText = 'No data available',
      countLabel = 'rows',
      onRowClick = null,
      extraToolbar = '',
      statusText = null,
    } = options;

    let filteredRows = [...rows];
    let sortKey = null;
    let sortDir = 'asc';
    let searchQuery = '';

    container.innerHTML = '';

    // ── Toolbar ──────────────────────────────────────────────
    const toolbar = document.createElement('div');
    toolbar.className = 'ti-dg-toolbar';
    toolbar.innerHTML = `
      <div class="ti-dg-toolbar-left">
        ${extraToolbar}
        <span class="ti-dg-count" id="dg-count-${uid()}"></span>
      </div>
      <div class="ti-dg-toolbar-right">
        ${search ? `<input type="text" class="ti-dg-search" placeholder="Search all columns…" />` : ''}
        ${exportBtn ? `<button class="ti-dg-export">⬇ Export to Excel</button>` : ''}
      </div>
    `;
    container.appendChild(toolbar);

    const countEl = toolbar.querySelector('.ti-dg-count');
    const searchInput = toolbar.querySelector('.ti-dg-search');
    const exportBtnEl = toolbar.querySelector('.ti-dg-export');

    // ── Table wrapper ───────────────────────────────────────
    const wrap = document.createElement('div');
    wrap.className = 'ti-dg-wrap';
    const scroll = document.createElement('div');
    scroll.className = 'ti-dg-scroll';
    const table = document.createElement('table');
    table.className = 'ti-dg';
    const thead = document.createElement('thead');
    const tbody = document.createElement('tbody');
    table.appendChild(thead);
    table.appendChild(tbody);
    scroll.appendChild(table);
    wrap.appendChild(scroll);

    // Status bar
    const status = document.createElement('div');
    status.className = 'ti-dg-status';
    wrap.appendChild(status);
    container.appendChild(wrap);

    // ── Render header ───────────────────────────────────────
    function renderHead() {
      let html = '<tr>';
      columns.forEach(col => {
        const sortable = col.sortable !== false;
        const cls = [
          sortable ? 'sortable' : '',
          sortKey === col.key ? (sortDir === 'asc' ? 'sort-asc' : 'sort-desc') : '',
          col.align === 'right' ? 'num' : col.align === 'center' ? 'ctr' : '',
        ].filter(Boolean).join(' ');
        const arrow = sortable ? `<span class="sort-arrow">${sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}</span>` : '';
        const style = col.width ? ` style="width:${col.width}"` : '';
        html += `<th class="${cls}" data-key="${col.key}"${style}>${col.label}${arrow}</th>`;
      });
      html += '</tr>';
      thead.innerHTML = html;

      // Attach sort handlers
      thead.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.key;
          if (sortKey === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
          else { sortKey = key; sortDir = 'asc'; }
          applySort();
          renderHead();
          renderBody();
        });
      });
    }

    // ── Render body ─────────────────────────────────────────
    function renderBody() {
      if (!filteredRows.length) {
        tbody.innerHTML = `<tr><td colspan="${columns.length}" style="text-align:center;padding:40px;color:var(--ti-text-dim)">${emptyText}</td></tr>`;
        updateCount();
        return;
      }

      let html = '';
      filteredRows.forEach((row, i) => {
        const clickable = onRowClick ? ' style="cursor:pointer"' : '';
        html += `<tr data-idx="${i}"${clickable}>`;
        columns.forEach(col => {
          const raw = row[col.key];
          let display;
          if (col.format) {
            const result = col.format(raw, row, i);
            if (result instanceof HTMLElement) {
              display = result.outerHTML;
            } else {
              display = result ?? '—';
            }
          } else if (raw != null && String(raw).trim() !== '' && !Number.isNaN(Number(raw))) {
            display = Number(raw).toLocaleString('en-IN', { maximumFractionDigits: 2 });
          } else {
            display = raw != null ? String(raw) : '—';
          }
          const cls = col.align === 'right' ? 'num' : col.align === 'center' ? 'ctr' : '';
          const extraCls = col.className ? ` ${typeof col.className === 'function' ? col.className(raw, row) : col.className}` : '';
          html += `<td class="${cls}${extraCls}">${display}</td>`;
        });
        html += '</tr>';
      });
      tbody.innerHTML = html;

      // Row click
      if (onRowClick) {
        tbody.querySelectorAll('tr[data-idx]').forEach(tr => {
          tr.addEventListener('click', () => {
            const idx = parseInt(tr.dataset.idx);
            onRowClick(filteredRows[idx], idx);
          });
        });
      }

      updateCount();
    }

    function updateCount() {
      if (countEl) {
        const total = rows.length;
        const showing = filteredRows.length;
        countEl.textContent = showing === total
          ? `${total} ${countLabel}`
          : `${showing} of ${total} ${countLabel}`;
      }
      // Status bar
      if (statusText) {
        status.innerHTML = typeof statusText === 'function' ? statusText(filteredRows, rows) : statusText;
        status.style.display = '';
      } else {
        status.style.display = 'none';
      }
    }

    // ── Search ──────────────────────────────────────────────
    function applySearch() {
      const q = searchQuery.toLowerCase();
      if (!q) {
        filteredRows = [...rows];
      } else {
        filteredRows = rows.filter(row =>
          columns.some(col => {
            const val = row[col.key];
            return val != null && String(val).toLowerCase().includes(q);
          })
        );
      }
      applySort();
      renderBody();
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value;
        applySearch();
      });
    }

    // ── Sort ────────────────────────────────────────────────
    function applySort() {
      if (!sortKey) return;
      const col = columns.find(c => c.key === sortKey);
      filteredRows.sort((a, b) => {
        let va = a[sortKey], vb = b[sortKey];
        // Try numeric comparison
        const na = Number(va), nb = Number(vb);
        if (!isNaN(na) && !isNaN(nb)) {
          return sortDir === 'asc' ? na - nb : nb - na;
        }
        // String comparison
        va = String(va ?? '').toLowerCase();
        vb = String(vb ?? '').toLowerCase();
        if (va < vb) return sortDir === 'asc' ? -1 : 1;
        if (va > vb) return sortDir === 'asc' ? 1 : -1;
        return 0;
      });
    }

    // ── Export ───────────────────────────────────────────────
    if (exportBtnEl && exportFn) {
      exportBtnEl.addEventListener('click', () => exportFn(filteredRows));
    }

    // ── Initial render ──────────────────────────────────────
    renderHead();
    renderBody();

    // Return update API
    return {
      /** Replace data and re-render */
      setRows(newRows) {
        rows.length = 0;
        rows.push(...newRows);
        searchQuery = '';
        if (searchInput) searchInput.value = '';
        filteredRows = [...rows];
        applySort();
        renderBody();
      },
      getFilteredRows() { return filteredRows; },
    };
  }

  let _uid = 0;
  function uid() { return ++_uid; }

  return { render };
})();
