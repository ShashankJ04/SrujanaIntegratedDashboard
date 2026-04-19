window.DashboardController = (() => {
  const REPORT_KEY = "reports_main";
  let pageSizeSelect;
  let globalSearchInput;
  let exportBtn;
  let hardRefreshBtn;
  let zoomRange;
  let zoomOutBtn;
  let zoomInBtn;
  let zoomDisplay;
  let currentZoom = 100;
  let layoutSaveTimer = null;
  const LAYOUT_STORAGE_PREFIX = "reportLayout:";

  function init() {
    const headerDateEl = document.getElementById("header-date");
    if (headerDateEl) {
      const now = new Date();
      const options = {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric",
      };
      headerDateEl.textContent = now.toLocaleDateString(undefined, options);
    }

    pageSizeSelect = document.getElementById("page-size-select");
    globalSearchInput = document.getElementById("global-search");
    exportBtn = document.getElementById("export-btn");
    hardRefreshBtn = document.getElementById("hard-refresh-btn");
    zoomRange = document.getElementById("zoom-range");
    zoomOutBtn = document.getElementById("zoom-out");
    zoomInBtn = document.getElementById("zoom-in");
    zoomDisplay = document.getElementById("zoom-display");

    DataTable.init({
      containerId: "table-container",
      summaryId: "table-summary",
      reportKey: REPORT_KEY,
      onRequestReload: reload,
      onLayoutChange: queueLayoutSave,
      cellRenderer: renderCell,
      rowClassName: getRowClassName,
      statusColumns: ["production_pending", "balance_production_qty"],
    });
    DataTable.attachGlobalHandlers();

    Pagination.init({
      firstId: "first-page",
      prevId: "prev-page",
      nextId: "next-page",
      lastId: "last-page",
      pageInputId: "current-page-input",
      totalLabelId: "total-pages-label",
    });

    wireControls();
    loadInitial();
  }

  function wireControls() {
    let searchTimer = null;

    globalSearchInput.addEventListener("input", () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        DataTable.setExternalState({
          search: globalSearchInput.value.trim(),
          page: 1,
        });
        reload();
      }, 250);
    });

    pageSizeSelect.addEventListener("change", () => {
      const selected = pageSizeSelect.value;
      let size;
      if (selected === "all") {
        size = -1;
      } else {
        const value = parseInt(selected, 10);
        const maxPageSize = window.DASHBOARD_MAX_PAGE_SIZE || 200;
        size = Math.min(Math.max(1, value || 10), maxPageSize);
      }
      DataTable.setExternalState({
        pageSize: size,
        page: 1,
      });
      reload();
    });

    exportBtn.addEventListener("click", () => {
      const state = DataTable.getState();
      const params = {
        search: state.search,
        sortBy: state.sortBy,
        sortDir: state.sortDir,
      };
      const url = ApiClient.buildExportUrl(params);
      const a = document.createElement("a");
      a.href = url;
      a.download = "table_export.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
    });

    if (hardRefreshBtn) {
      hardRefreshBtn.addEventListener("click", () => {
        hardRefresh();
      });
    }

    if (zoomRange && zoomDisplay) {
      const applyZoom = () => {
        const value = parseInt(zoomRange.value, 10) || 100;
        currentZoom = Math.min(150, Math.max(50, value));
        zoomRange.value = String(currentZoom);
        zoomDisplay.textContent = `${currentZoom}%`;
        const container = document.getElementById("table-container");
        if (container) {
          const factor = currentZoom / 100;
          container.style.setProperty("--table-zoom", String(factor));
        }
      };

      zoomRange.addEventListener("input", applyZoom);

      if (zoomOutBtn) {
        zoomOutBtn.addEventListener("click", () => {
          currentZoom = Math.max(50, currentZoom - 10);
          zoomRange.value = String(currentZoom);
          applyZoom();
        });
      }

      if (zoomInBtn) {
        zoomInBtn.addEventListener("click", () => {
          currentZoom = Math.min(150, currentZoom + 10);
          zoomRange.value = String(currentZoom);
          applyZoom();
        });
      }

      applyZoom();
    }
  }

  async function loadInitial() {
    try {
      DataTable.setLayout(loadLayoutFromStorage(REPORT_KEY));
      await reload();
      if (
        typeof DashboardCharts !== "undefined" &&
        document.getElementById("chart-top-rm-requirement")
      ) {
        DashboardCharts.load();
      }
    } catch (err) {
      console.error(err);
      const container = document.getElementById("table-container");
      container.innerHTML =
        '<div class="placeholder">Failed to load table metadata. Check the backend connection.</div>';
    }
  }

  async function hardRefresh() {
    const container = document.getElementById("table-container");
    if (container) {
      container.classList.add("loading");
    }

    try {
      await ApiClient.refreshDashboard();
      await reload();
      if (
        typeof DashboardCharts !== "undefined" &&
        document.getElementById("chart-top-rm-requirement")
      ) {
        DashboardCharts.load();
      }
    } catch (err) {
      console.error(err);
      if (container) {
        container.innerHTML =
          '<div class="placeholder">Something went wrong while loading data. Try refreshing.</div>';
      }
    } finally {
      if (container) {
        container.classList.remove("loading");
      }
    }
  }

  async function reload() {
    const state = DataTable.getState();
    const params = {
      page: state.page,
      pageSize: state.pageSize,
      search: state.search,
      sortBy: state.sortBy,
      sortDir: state.sortDir,
    };

    const container = document.getElementById("table-container");
    if (container) {
      container.classList.add("loading");
    }

    try {
      const result = await ApiClient.getDashboardRows(params);
      DataTable.setExternalState({
        columns: result.columns,
        rows: result.rows,
        page: result.page,
        pageSize: result.pageSize,
        totalCount: result.totalCount,
        totalPages: Math.max(
          1,
          Math.ceil(result.totalCount / result.pageSize || 1),
        ),
      });
      DataTable.renderTable();
      Pagination.applyPaginationMeta({
        page: result.page,
        pageSize: result.pageSize,
        totalCount: result.totalCount,
      });
    } catch (err) {
      console.error(err);
      if (container) {
        container.innerHTML =
          '<div class="placeholder">Something went wrong while loading data. Try refreshing.</div>';
      }
    } finally {
      if (container) {
        container.classList.remove("loading");
      }
    }
  }

  function getRowClassName({ row }) {
    const prodPending = Number(row.production_pending);
    const balanceProd = Number(row.balance_production_qty);
    const rowIsReady =
      !Number.isNaN(prodPending) &&
      !Number.isNaN(balanceProd) &&
      prodPending <= 0 &&
      balanceProd <= 0;
    return rowIsReady ? "row-ready" : "";
  }

  function renderCell({ row, col, value, td }) {
    if (col.name !== "buffer_qty") return false;
    if (!window.BUFFER_EDIT_ALLOWED) return false;

    const wrapper = document.createElement("div");
    wrapper.className = "buffer-cell";

    const input = document.createElement("input");
    input.type = "number";
    input.step = "1";
    input.className = "buffer-input";
    input.value = value === null || value === undefined ? "" : String(Number(value));

    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "buffer-apply-btn";
    applyBtn.textContent = "\u2713";

    applyBtn.addEventListener("click", async () => {
      const partNo = row.part_no;
      if (!partNo) return;
      const raw = input.value.trim();
      if (raw === "") input.value = "0";
      const qty = Number(input.value);
      if (Number.isNaN(qty)) {
        input.value = value === null || value === undefined ? "0" : String(Number(value));
        return;
      }
      try {
        await ApiClient.updateBufferConfig(partNo, qty);
        reload();
      } catch (err) {
        console.error(err);
      }
    });

    wrapper.appendChild(input);
    wrapper.appendChild(applyBtn);
    td.appendChild(wrapper);
    return true;
  }

  function queueLayoutSave({ reportKey, layout }) {
    if (layoutSaveTimer) clearTimeout(layoutSaveTimer);
    layoutSaveTimer = setTimeout(() => {
      saveLayoutToStorage(reportKey || REPORT_KEY, layout || { columns: [] });
    }, 400);
  }

  function storageKey(reportKey) {
    return `${LAYOUT_STORAGE_PREFIX}${reportKey}`;
  }

  function loadLayoutFromStorage(reportKey) {
    try {
      const raw = window.localStorage.getItem(storageKey(reportKey));
      if (!raw) return { columns: [] };
      const parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.columns)) return { columns: [] };
      return parsed;
    } catch (err) {
      console.warn("Unable to parse saved layout, using defaults.", err);
      return { columns: [] };
    }
  }

  function saveLayoutToStorage(reportKey, layout) {
    try {
      window.localStorage.setItem(storageKey(reportKey), JSON.stringify(layout || { columns: [] }));
    } catch (err) {
      console.error("Failed to persist report layout in localStorage", err);
    }
  }

  document.addEventListener("DOMContentLoaded", init);

  return {
    reload,
    hardRefresh,
  };
})();
