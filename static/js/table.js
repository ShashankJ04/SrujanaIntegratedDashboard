const DataTable = (() => {
  function formatLocaleNumber(value) {
    if (value === null || value === undefined) return "";
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString("en-IN", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  let state = {
    reportKey: "reports_main",
    columns: [],
    rows: [],
    page: 1,
    pageSize: window.DASHBOARD_DEFAULT_PAGE_SIZE || 25,
    totalCount: 0,
    totalPages: 1,
    search: "",
    sortBy: null,
    sortDir: null,
    layout: { columns: [] },
  };

  let elements = { container: null, summary: null };
  let options = {
    onRequestReload: null,
    onLayoutChange: null,
    cellRenderer: null,
    rowClassName: null,
    statusColumns: [],
  };
  let resizing = null;
  let dragColumnName = null;
  let scrollSyncAttached = false;

  function init({ containerId, summaryId, reportKey, onRequestReload, onLayoutChange, cellRenderer, rowClassName, statusColumns }) {
    elements.container = document.getElementById(containerId);
    elements.summary = document.getElementById(summaryId);
    options.onRequestReload = onRequestReload || null;
    options.onLayoutChange = onLayoutChange || null;
    options.cellRenderer = cellRenderer || null;
    options.rowClassName = rowClassName || null;
    options.statusColumns = Array.isArray(statusColumns) ? statusColumns : [];
    if (reportKey) state.reportKey = reportKey;
  }

  function setExternalState(partial) {
    state = { ...state, ...partial };
  }

  function getState() {
    return { ...state };
  }

  function setLayout(layout) {
    const incoming = layout && Array.isArray(layout.columns) ? layout.columns : [];
    const safeColumns = incoming
      .filter((c) => c && c.name)
      .map((c) => ({
        name: String(c.name),
        width: Number.isFinite(Number(c.width)) ? Math.max(60, Math.min(1200, Number(c.width))) : undefined,
        pinned: c.pinned === "left" ? "left" : null,
      }));
    state.layout = { columns: safeColumns };
  }

  function getLayoutSnapshot() {
    return { columns: state.layout.columns.map((c) => ({ ...c })) };
  }

  function attachGlobalHandlers() {
    if (!scrollSyncAttached && elements.container) {
      elements.container.addEventListener("scroll", () => {
        syncPinnedOffsetsFromDom();
      });
      window.addEventListener("resize", () => {
        syncPinnedOffsetsFromDom();
      });
      scrollSyncAttached = true;
    }

    elements.container.addEventListener("mousedown", (e) => {
      const handle = e.target.closest(".resize-handle");
      if (!handle) return;
      const th = handle.parentElement;
      resizing = {
        th,
        startX: e.pageX,
        startWidth: th.offsetWidth,
        colName: th.dataset.colName,
      };
      document.body.classList.add("resizing-col");
      e.preventDefault();
      e.stopPropagation();
    });

    document.addEventListener("mousemove", (e) => {
      if (!resizing) return;
      const delta = e.pageX - resizing.startX;
      const newWidth = Math.max(60, resizing.startWidth + delta);
      applyColumnWidth(resizing.colName, newWidth, false);
    });

    document.addEventListener("mouseup", () => {
      if (!resizing) return;
      const finishedCol = resizing.colName;
      const finalWidth = resizing.th.offsetWidth;
      applyColumnWidth(finishedCol, finalWidth, true);
      resizing = null;
      document.body.classList.remove("resizing-col");
      emitLayoutChange("resize", finishedCol);
    });
  }

  function getLayoutMap() {
    const map = new Map();
    (state.layout.columns || []).forEach((c, idx) => {
      map.set(c.name, { ...c, _idx: idx });
    });
    return map;
  }

  function getEffectiveColumns() {
    const base = Array.isArray(state.columns) ? state.columns : [];
    const layoutMap = getLayoutMap();

    const columnsWithMeta = base.map((col, originalIdx) => {
      const layoutCol = layoutMap.get(col.name);
      return {
        ...col,
        _originalIdx: originalIdx,
        _layoutIdx: layoutCol ? layoutCol._idx : Number.MAX_SAFE_INTEGER,
        _pinned: layoutCol && layoutCol.pinned === "left" ? "left" : null,
        _width: layoutCol && Number.isFinite(layoutCol.width) ? layoutCol.width : null,
      };
    });

    columnsWithMeta.sort((a, b) => {
      const ap = a._pinned ? 0 : 1;
      const bp = b._pinned ? 0 : 1;
      if (ap !== bp) return ap - bp;
      if (a._layoutIdx !== b._layoutIdx) return a._layoutIdx - b._layoutIdx;
      return a._originalIdx - b._originalIdx;
    });

    const normalizedLayout = columnsWithMeta.map((col) => ({
      name: col.name,
      width: col._width || undefined,
      pinned: col._pinned || null,
    }));
    state.layout = { columns: normalizedLayout };
    return columnsWithMeta;
  }

  function applyColumnWidth(colName, width, updateLayout = true) {
    const table = elements.container?.querySelector("table.data-table");
    if (!table || !colName) return;
    const px = `${Math.max(60, Math.min(1200, Math.round(width)))}px`;
    const cells = table.querySelectorAll(`[data-col-name="${colName}"]`);
    cells.forEach((el) => {
      el.style.width = px;
      el.style.minWidth = px;
      el.style.maxWidth = px;
    });
    if (!updateLayout) return;
    state.layout.columns = state.layout.columns.map((c) =>
      c.name === colName ? { ...c, width: Number.parseInt(px, 10) } : c,
    );
  }

  function setPinned(colName, pinned) {
    state.layout.columns = state.layout.columns.map((c) =>
      c.name === colName ? { ...c, pinned: pinned === "left" ? "left" : null } : c,
    );
    renderTable();
    emitLayoutChange("pin", colName);
  }

  function reorderColumn(sourceName, targetName) {
    if (!sourceName || !targetName || sourceName === targetName) return;
    const cols = [...state.layout.columns];
    const from = cols.findIndex((c) => c.name === sourceName);
    const to = cols.findIndex((c) => c.name === targetName);
    if (from < 0 || to < 0 || from === to) return;
    const [item] = cols.splice(from, 1);
    cols.splice(to, 0, item);
    state.layout = { columns: cols };
    renderTable();
    emitLayoutChange("reorder", sourceName);
  }

  function emitLayoutChange(reason, colName) {
    if (typeof options.onLayoutChange !== "function") return;
    options.onLayoutChange({
      reason,
      colName: colName || null,
      reportKey: state.reportKey,
      layout: getLayoutSnapshot(),
    });
  }

  function requestReload() {
    if (typeof options.onRequestReload === "function") {
      options.onRequestReload();
      return;
    }
    if (typeof window.DashboardController?.reload === "function") {
      window.DashboardController.reload();
    }
  }

  function renderTable() {
    if (!elements.container) return;
    const columns = getEffectiveColumns();
    const rows = state.rows || [];

    if (!columns.length) {
      elements.container.innerHTML = '<div class="placeholder">No columns to display.</div>';
      return;
    }

    const table = document.createElement("table");
    table.className = "data-table";
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach((col) => {
      const th = document.createElement("th");
      th.dataset.colName = col.name;
      th.setAttribute("draggable", "true");

      const headerCell = document.createElement("div");
      headerCell.className = "header-cell";

      const title = document.createElement("span");
      title.className = "header-title";
      title.textContent = col.label;

      const sortIndicator = document.createElement("span");
      sortIndicator.className = "sort-indicator";
      if (state.sortBy === col.name) {
        headerCell.classList.add("sorted");
        sortIndicator.textContent = state.sortDir === "desc" ? "▼" : "▲";
      } else {
        sortIndicator.textContent = "↕";
      }

      const pinBtn = document.createElement("button");
      pinBtn.type = "button";
      pinBtn.className = "pin-toggle-btn";
      pinBtn.title = col._pinned ? "Unpin column" : "Pin column to left";
      pinBtn.setAttribute("aria-label", pinBtn.title);
      pinBtn.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M9 3h6v3l2 3v3H7V9l2-3V3zM12 12v9" />
        </svg>
      `;
      if (col._pinned) {
        pinBtn.classList.add("is-pinned");
      }
      pinBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        setPinned(col.name, col._pinned ? null : "left");
      });

      const resizeHandle = document.createElement("div");
      resizeHandle.className = "resize-handle";

      headerCell.appendChild(pinBtn);
      headerCell.appendChild(title);
      headerCell.appendChild(sortIndicator);
      th.appendChild(headerCell);
      th.appendChild(resizeHandle);
      headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.textContent = "No rows match your criteria.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      const statusCols = new Set(options.statusColumns || []);
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        if (typeof options.rowClassName === "function") {
          const cls = options.rowClassName({ row });
          if (cls) tr.classList.add(cls);
        }
        columns.forEach((col) => {
          const td = document.createElement("td");
          td.dataset.colName = col.name;
          const value = row[col.name];

          const rendered = typeof options.cellRenderer === "function"
            ? options.cellRenderer({ row, col, value, td })
            : false;
          if (!rendered) {
            if (statusCols.has(col.name) && value !== null && value !== undefined) {
              const numVal = Number(value);
              if (!Number.isNaN(numVal)) {
                td.classList.add(numVal <= 0 ? "cell-good" : "cell-bad");
              }
            }
            td.textContent = col.is_numeric
              ? formatLocaleNumber(value)
              : value === null || value === undefined ? "" : String(value);
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    table.appendChild(tbody);
    elements.container.innerHTML = "";
    elements.container.appendChild(table);

    columns.forEach((col) => {
      if (col._width) applyColumnWidth(col.name, col._width, false);
    });
    applyPinnedStyles(columns);
    wireHeaderInteractions();
    wireDragAndDrop();
    updateSummary();
  }

  function applyPinnedStyles(columns) {
    const table = elements.container?.querySelector("table.data-table");
    if (!table) return;
    columns.forEach((col) => {
      const colCells = table.querySelectorAll(`[data-col-name="${col.name}"]`);
      colCells.forEach((cell) => {
        cell.classList.remove("is-pinned-left");
        cell.classList.remove("is-pinned-left-last");
        cell.style.left = "";
        cell.style.zIndex = "";
      });
      if (col._pinned === "left") {
        colCells.forEach((cell) => {
          cell.classList.add("is-pinned-left");
        });
      }
    });
    // Re-sync after layout/paint to avoid drift with multiple pinned columns.
    requestAnimationFrame(() => {
      syncPinnedOffsetsFromDom();
    });
  }

  function syncPinnedOffsetsFromDom() {
    const table = elements.container?.querySelector("table.data-table");
    if (!table) return;
    const headerCells = Array.from(table.querySelectorAll("thead th.is-pinned-left[data-col-name]"));
    if (!headerCells.length) return;

    // Compute each pinned column's left offset as the cumulative width of all
    // preceding pinned columns.  This avoids the fragile pattern of temporarily
    // clearing left, forcing reflow, then reading offsetLeft on sticky elements.
    let cumulativeLeft = 0;
    headerCells.forEach((th, idx) => {
      const colName = th.dataset.colName;
      if (!colName) return;

      const cellWidth = th.getBoundingClientRect().width || th.offsetWidth || 120;
      const roundedWidth = Math.max(0, Math.round(cellWidth));

      const cells = table.querySelectorAll(`[data-col-name="${colName}"]`);
      cells.forEach((cell) => {
        cell.style.left = `${cumulativeLeft}px`;
        if (cell.tagName === "TH") {
          cell.style.top = "0px";
          cell.style.zIndex = String(90 - idx);
        } else {
          cell.style.zIndex = String(25 - idx);
        }
      });

      cumulativeLeft += roundedWidth;
    });

    const lastPinnedColName = headerCells[headerCells.length - 1]?.dataset?.colName;
    if (!lastPinnedColName) return;
    table.querySelectorAll("[data-col-name]").forEach((cell) => {
      if (cell.classList.contains("is-pinned-left") && cell.dataset.colName === lastPinnedColName) {
        cell.classList.add("is-pinned-left-last");
      } else {
        cell.classList.remove("is-pinned-left-last");
      }
    });
  }

  function wireHeaderInteractions() {
    const headerCells = elements.container.querySelectorAll("th .header-cell");
    headerCells.forEach((cell) => {
      cell.addEventListener("click", () => {
        const th = cell.closest("th");
        const colName = th?.dataset?.colName;
        if (!colName) return;
        let nextDir = "asc";
        if (state.sortBy === colName) {
          if (state.sortDir === "asc") nextDir = "desc";
          else if (state.sortDir === "desc") nextDir = null;
          else nextDir = "asc";
        }
        state.sortBy = nextDir ? colName : null;
        state.sortDir = nextDir;
        state.page = 1;
        requestReload();
      });
    });
  }

  function wireDragAndDrop() {
    const headers = elements.container.querySelectorAll("thead th[data-col-name]");
    headers.forEach((th) => {
      th.addEventListener("dragstart", (e) => {
        const handle = e.target.closest(".resize-handle");
        const pinBtn = e.target.closest(".pin-toggle-btn");
        const isPinned = th.classList.contains("is-pinned-left");
        if (isPinned) {
          e.preventDefault();
          return;
        }
        if (handle || pinBtn) {
          e.preventDefault();
          return;
        }
        dragColumnName = th.dataset.colName || null;
        th.classList.add("is-dragging");
      });
      th.addEventListener("dragend", () => {
        dragColumnName = null;
        th.classList.remove("is-dragging");
        headers.forEach((x) => x.classList.remove("is-drop-target"));
      });
      th.addEventListener("dragover", (e) => {
        if (!dragColumnName) return;
        e.preventDefault();
        th.classList.add("is-drop-target");
      });
      th.addEventListener("dragleave", () => {
        th.classList.remove("is-drop-target");
      });
      th.addEventListener("drop", (e) => {
        e.preventDefault();
        th.classList.remove("is-drop-target");
        const targetName = th.dataset.colName || null;
        reorderColumn(dragColumnName, targetName);
      });
    });
  }

  function updateSummary() {
    if (!elements.summary) return;
    const { page, pageSize, totalCount } = state;
    if (!totalCount) {
      elements.summary.textContent = "No rows.";
      return;
    }
    const start = (page - 1) * pageSize + 1;
    const end = Math.min(totalCount, page * pageSize);
    elements.summary.textContent = `Showing ${start.toLocaleString("en-IN")}–${end.toLocaleString("en-IN")} of ${totalCount.toLocaleString("en-IN")} rows`;
  }

  return {
    init,
    setExternalState,
    getState,
    setLayout,
    getLayoutSnapshot,
    renderTable,
    attachGlobalHandlers,
    updateSummary,
  };
})();

